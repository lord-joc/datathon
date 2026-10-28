"""CKAN package_show: confirm the resource and read its real download URL (FZ02)."""

import hashlib
import json
from dataclasses import dataclass
from typing import Any

from app.adapters.http import FetchError, SafeFetcher

# CKAN licence identifiers/titles accepted as the Croatian open licence (OD) without review.
# Anything else is recorded and sent to manual review rather than silently accepted.
_OD_EXACT = {"od", "otvorena-dozvola", "open-licence", "otvorena dozvola"}
_OD_CONTAINS = ("otvorena dozvola", "otvorenu dozvolu")


@dataclass(frozen=True)
class CkanResource:
    resource_id: str
    url: str
    name: str | None
    format: str | None
    last_modified: str | None


@dataclass(frozen=True)
class CkanPackage:
    package_id: str
    title: str | None
    license_id: str | None
    license_title: str | None
    metadata_modified: str | None
    resources: tuple[CkanResource, ...]
    metadata_sha256: str
    raw: dict[str, Any]

    @property
    def license_is_open(self) -> bool:
        values = [v.strip().lower() for v in (self.license_id, self.license_title) if v]
        return any(v in _OD_EXACT or any(m in v for m in _OD_CONTAINS) for v in values)

    def resource(self, resource_id: str | None, wanted_format: str | None) -> CkanResource:
        if resource_id:
            for res in self.resources:
                if res.resource_id == resource_id:
                    return res
            raise FetchError(
                "resource_missing", f"Resurs {resource_id} više nije u paketu {self.package_id}."
            )
        fmt = (wanted_format or "").lower()
        matches = [r for r in self.resources if (r.format or "").lower() == fmt]
        if len(matches) == 1:
            return matches[0]
        raise FetchError(
            "resource_ambiguous",
            f"U paketu {self.package_id} postoji {len(matches)} resursa formata {wanted_format}. "
            "Pokreni 'source-resources' i upiši resource_id u config/source_registry_extra.json.",
        )


def fetch_package(fetcher: SafeFetcher, endpoint: str) -> CkanPackage:
    result = fetcher.get(endpoint, max_bytes=2 * 1024 * 1024)
    try:
        body = json.loads(result.content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise FetchError("metadata_invalid", "CKAN odgovor nije valjan JSON.") from exc
    if not isinstance(body, dict) or body.get("success") is not True:
        raise FetchError("metadata_unsuccessful", "CKAN je vratio success=false.")
    pkg = body.get("result")
    if not isinstance(pkg, dict):
        raise FetchError("metadata_invalid", "CKAN odgovor nema 'result'.")
    resources = tuple(
        CkanResource(
            resource_id=str(r.get("id")),
            url=str(r.get("url", "")),
            name=r.get("name"),
            format=r.get("format"),
            last_modified=r.get("last_modified") or r.get("metadata_modified"),
        )
        for r in pkg.get("resources", [])
        if isinstance(r, dict) and r.get("id") and r.get("url")
    )
    canonical = json.dumps(pkg, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return CkanPackage(
        package_id=str(pkg.get("name") or pkg.get("id")),
        title=pkg.get("title"),
        license_id=pkg.get("license_id"),
        license_title=pkg.get("license_title"),
        metadata_modified=pkg.get("metadata_modified"),
        resources=resources,
        metadata_sha256=hashlib.sha256(canonical.encode("utf-8")).hexdigest(),
        raw=pkg,
    )
