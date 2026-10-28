"""Safe outbound HTTP for source adapters (NF04, doc. chapter 15, OWASP SSRF cheat sheet).

- HTTPS only, host allowlist (exact names or ".domain" suffixes), default port only.
- Every redirect hop is re-validated; at most 3 redirects.
- Host names are resolved and rejected if any address is private, loopback, link-local,
  multicast, reserved or unspecified (IPv4 and IPv6).
- Response size is capped while streaming; timeouts 5 s connect / 20 s read / 60 s total.
- Retries (2) only for network errors, 408, 429 and 5xx, honouring Retry-After up to 5 min.

Known limit: DNS is resolved for validation and again by the HTTP client. A DNS-rebinding
attacker controlling an allowlisted domain could race this. The allowlist contains only
public-sector and ArcGIS hosts, and production should also restrict egress at the firewall.
"""

import ipaddress
import socket
import time
from collections.abc import Callable
from dataclasses import dataclass
from email.utils import parsedate_to_datetime
from urllib.parse import urljoin, urlsplit

import httpx

from app import __version__

USER_AGENT = f"ProstorIQ/{__version__} (student project; Datathon 2026)"
MAX_REDIRECTS = 3
RETRY_STATUSES = {408, 429, 500, 502, 503, 504}
RETRY_BACKOFF_S = (2.0, 5.0)
MAX_RETRY_AFTER_S = 300.0

Resolver = Callable[[str], list[str]]


class FetchError(Exception):
    def __init__(self, code: str, detail: str) -> None:
        super().__init__(f"{code}: {detail}")
        self.code = code
        self.detail = detail


@dataclass(frozen=True)
class FetchResult:
    url: str
    final_url: str
    status: int
    content: bytes
    content_type: str | None
    etag: str | None
    last_modified: str | None


def system_resolver(host: str) -> list[str]:
    try:
        infos = socket.getaddrinfo(host, 443, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise FetchError("dns_failed", f"Naziv {host} se ne može razriješiti.") from exc
    return sorted({str(info[4][0]) for info in infos})


def _host_allowed(host: str, allowed: tuple[str, ...]) -> bool:
    host = host.lower().rstrip(".")
    for rule in (r.lower() for r in allowed):
        if rule.startswith("."):
            if host == rule[1:] or host.endswith(rule):
                return True
        elif host == rule:
            return True
    return False


def _is_public(address: str) -> bool:
    ip = ipaddress.ip_address(address)
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return not (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    )


class SafeFetcher:
    def __init__(
        self,
        allowed_hosts: tuple[str, ...],
        *,
        resolver: Resolver = system_resolver,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        total_timeout_s: float = 60.0,
    ) -> None:
        self.allowed_hosts = allowed_hosts
        self.resolver = resolver
        self.sleep = sleep
        self.total_timeout_s = total_timeout_s
        self._client = httpx.Client(
            transport=transport,
            follow_redirects=False,
            timeout=httpx.Timeout(connect=5.0, read=20.0, write=20.0, pool=5.0),
            headers={"User-Agent": USER_AGENT, "Accept": "*/*"},
            trust_env=True,  # honour HTTPS_PROXY / egress proxy when configured
        )

    def close(self) -> None:
        self._client.close()

    def __enter__(self) -> "SafeFetcher":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()

    def validate_url(self, url: str) -> None:
        parts = urlsplit(url)
        if parts.scheme != "https":
            raise FetchError("url_not_https", f"Dopušten je samo HTTPS: {url}")
        if parts.username or parts.password:
            raise FetchError("url_credentials", "URL ne smije sadržavati korisničke podatke.")
        host = parts.hostname or ""
        if not host or not _host_allowed(host, self.allowed_hosts):
            raise FetchError("host_not_allowed", f"Host {host or '?'} nije na popisu dopuštenih.")
        if parts.port not in (None, 443):
            raise FetchError("port_not_allowed", f"Port {parts.port} nije dopušten.")
        addresses = self.resolver(host)
        if not addresses:
            raise FetchError("dns_failed", f"Naziv {host} nema adresu.")
        blocked = [a for a in addresses if not _is_public(a)]
        if blocked:
            raise FetchError("private_address", f"Host {host} pokazuje na nedopuštenu adresu.")

    def get(
        self,
        url: str,
        *,
        max_bytes: int,
        etag: str | None = None,
        last_modified: str | None = None,
    ) -> FetchResult:
        deadline = time.monotonic() + self.total_timeout_s
        attempt = 0
        while True:
            try:
                return self._get_once(url, max_bytes, etag, last_modified, deadline)
            except _RetryableError as exc:
                if attempt >= len(RETRY_BACKOFF_S):
                    raise FetchError("upstream_unavailable", exc.detail) from None
                wait = exc.retry_after if exc.retry_after is not None else RETRY_BACKOFF_S[attempt]
                if wait > MAX_RETRY_AFTER_S:
                    raise FetchError("retry_after_too_long", exc.detail) from None
                attempt += 1
                self.sleep(wait)

    def _get_once(
        self,
        url: str,
        max_bytes: int,
        etag: str | None,
        last_modified: str | None,
        deadline: float,
    ) -> FetchResult:
        current = url
        headers: dict[str, str] = {}
        if etag:
            headers["If-None-Match"] = etag
        if last_modified:
            headers["If-Modified-Since"] = last_modified
        for _hop in range(MAX_REDIRECTS + 1):
            self.validate_url(current)
            if time.monotonic() > deadline:
                raise FetchError("timeout", "Ukupno vrijeme dohvata je isteklo.")
            try:
                with self._client.stream("GET", current, headers=headers) as response:
                    if response.is_redirect:
                        location = response.headers.get("location")
                        if not location:
                            raise FetchError("bad_redirect", "Preusmjeravanje bez odredišta.")
                        current = urljoin(current, location)
                        continue
                    if response.status_code in RETRY_STATUSES:
                        raise _RetryableError(
                            f"HTTP {response.status_code} s {urlsplit(current).hostname}",
                            _retry_after(response.headers.get("retry-after")),
                        )
                    if response.status_code == 304:
                        content = b""
                    elif response.status_code != 200:
                        raise FetchError(
                            "http_error", f"HTTP {response.status_code} za {urlsplit(current).path}"
                        )
                    else:
                        content = _read_capped(response, max_bytes, deadline)
                    return FetchResult(
                        url=url,
                        final_url=current,
                        status=response.status_code,
                        content=content,
                        content_type=response.headers.get("content-type"),
                        etag=response.headers.get("etag"),
                        last_modified=response.headers.get("last-modified"),
                    )
            except httpx.TransportError as exc:
                raise _RetryableError(f"Mrežna greška: {type(exc).__name__}", None) from exc
        raise FetchError("too_many_redirects", f"Više od {MAX_REDIRECTS} preusmjeravanja.")


class _RetryableError(Exception):
    def __init__(self, detail: str, retry_after: float | None) -> None:
        super().__init__(detail)
        self.detail = detail
        self.retry_after = retry_after


def _read_capped(response: httpx.Response, max_bytes: int, deadline: float) -> bytes:
    declared = response.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > max_bytes:
        raise FetchError("too_large", f"Odgovor je veći od {max_bytes} bajtova.")
    chunks: list[bytes] = []
    total = 0
    for chunk in response.iter_bytes():
        total += len(chunk)
        if total > max_bytes:
            raise FetchError("too_large", f"Odgovor je veći od {max_bytes} bajtova.")
        if time.monotonic() > deadline:
            raise FetchError("timeout", "Ukupno vrijeme dohvata je isteklo.")
        chunks.append(chunk)
    return b"".join(chunks)


def _retry_after(value: str | None) -> float | None:
    if not value:
        return None
    if value.isdigit():
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError):
        return None
    return max(0.0, when.timestamp() - time.time())
