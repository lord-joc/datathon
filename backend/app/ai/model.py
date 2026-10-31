"""Local MiniLM sentence embeddings with onnxruntime (ADR21): no torch, no paid API, no network.

The pinned revision of sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 ships an
ONNX export of the same weights. Sentence embeddings follow the model's own sentence-transformers
configuration: mean pooling over the attention mask, then L2 normalisation, at most 128 tokens.
Files are downloaded once by `ai-fetch-model` and checked against hashes in config/ai_config.json.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

import httpx
import numpy as np
import numpy.typing as npt

from app.core.config import get_settings

_MAX_REDIRECTS = 5


class ModelError(RuntimeError):
    """The model is missing, does not match the pinned hashes, or its configuration changed."""


def load_ai_config(config_dir: Path | None = None) -> dict[str, Any]:
    path = (config_dir or get_settings().config_dir) / "ai_config.json"
    data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return data


def config_sha256(config: dict[str, Any]) -> str:
    body = json.dumps(config, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(body.encode()).hexdigest()


def model_path(config: dict[str, Any], model_dir: Path | None = None) -> Path:
    base = model_dir or get_settings().model_dir
    return base / str(config["model_id"]).replace("/", "__") / str(config["model_revision"])


def _git_blob_sha1(data: bytes) -> str:
    return hashlib.sha1(b"blob %d\0" % len(data) + data, usedforsecurity=False).hexdigest()


def _matches(path: Path, pin: dict[str, Any]) -> bool:
    if not path.is_file() or path.stat().st_size != pin["size"]:
        return False
    if "sha256" in pin:
        digest = hashlib.sha256()
        with path.open("rb") as fh:
            for block in iter(lambda: fh.read(1 << 20), b""):
                digest.update(block)
        return bool(digest.hexdigest() == pin["sha256"])
    return bool(_git_blob_sha1(path.read_bytes()) == pin["git_sha1"])


def verify_files(config: dict[str, Any], model_dir: Path | None = None) -> Path:
    root = model_path(config, model_dir)
    bad = [name for name, pin in config["model_files"].items() if not _matches(root / name, pin)]
    if bad:
        raise ModelError(
            f"Datoteke modela nedostaju ili se ne podudaraju s hashovima: {', '.join(bad)}. "
            "Pokreni: python -m app.cli ai-fetch-model"
        )
    return root


def _allowed(url: str) -> bool:
    # Hugging Face serves small files itself and large (LFS/Xet) files from its *.hf.co CDN.
    parts = urlsplit(url)
    host = parts.hostname or ""
    return parts.scheme == "https" and (host == "huggingface.co" or host.endswith(".hf.co"))


def _download(client: httpx.Client, url: str, target: Path) -> None:
    for _ in range(_MAX_REDIRECTS + 1):
        if not _allowed(url):
            raise ModelError(f"Preuzimanje s neočekivane adrese odbijeno: {urlsplit(url).hostname}")
        with client.stream("GET", url) as response:
            if response.is_redirect:
                url = str(response.url.join(response.headers["location"]))
                continue
            response.raise_for_status()
            target.parent.mkdir(parents=True, exist_ok=True)
            fd, tmp = tempfile.mkstemp(dir=target.parent, prefix=".part-")
            try:
                with os.fdopen(fd, "wb") as fh:
                    for chunk in response.iter_bytes(1 << 20):
                        fh.write(chunk)
                os.replace(tmp, target)
            finally:
                if os.path.exists(tmp):
                    os.unlink(tmp)
            return
    raise ModelError("Previše preusmjeravanja pri preuzimanju modela.")


def fetch_model(config: dict[str, Any], model_dir: Path | None = None) -> list[str]:
    """Download missing pinned files, verify every hash, return one log line per file."""
    root = model_path(config, model_dir)
    base = f"https://huggingface.co/{config['model_id']}/resolve/{config['model_revision']}"
    lines: list[str] = []
    timeout = httpx.Timeout(60.0, connect=10.0)
    with httpx.Client(timeout=timeout, follow_redirects=False) as client:
        for name, pin in config["model_files"].items():
            target = root / name
            if _matches(target, pin):
                lines.append(f"{name}: već preuzeto, hash odgovara")
                continue
            _download(client, f"{base}/{name}", target)
            if not _matches(target, pin):
                target.unlink(missing_ok=True)
                raise ModelError(f"{name}: hash ne odgovara zaključanoj vrijednosti; obrisano.")
            lines.append(f"{name}: preuzeto ({pin['size']} B), hash odgovara")
    return lines


@dataclass
class Embedder:
    """Sentence embeddings, normalised, so a dot product is the cosine similarity."""

    session: Any
    tokenizer: Any
    input_names: tuple[str, ...]
    model_id: str
    model_revision: str

    def embed(self, texts: list[str]) -> npt.NDArray[np.float32]:
        if not texts:
            return np.zeros((0, 384), dtype=np.float32)
        encodings = self.tokenizer.encode_batch(texts)
        ids = np.array([e.ids for e in encodings], dtype=np.int64)
        mask = np.array([e.attention_mask for e in encodings], dtype=np.int64)
        feed = {"input_ids": ids, "attention_mask": mask}
        if "token_type_ids" in self.input_names:
            feed["token_type_ids"] = np.zeros_like(ids)
        hidden = self.session.run(None, feed)[0]
        weights = mask[:, :, None].astype(np.float32)
        pooled = (hidden * weights).sum(axis=1) / np.clip(weights.sum(axis=1), 1e-9, None)
        norms = np.linalg.norm(pooled, axis=1, keepdims=True)
        result: npt.NDArray[np.float32] = (pooled / np.clip(norms, 1e-12, None)).astype(np.float32)
        return result


def load_embedder(config: dict[str, Any], model_dir: Path | None = None) -> Embedder:
    import onnxruntime as ort
    from tokenizers import Tokenizer

    root = verify_files(config, model_dir)
    pooling = json.loads((root / "1_Pooling" / "config.json").read_text(encoding="utf-8"))
    sbert = json.loads((root / "sentence_bert_config.json").read_text(encoding="utf-8"))
    if not pooling.get("pooling_mode_mean_tokens"):
        raise ModelError("Model ne koristi mean pooling kako očekuje ai_config.json.")
    if sbert.get("max_seq_length") != config["max_seq_length"]:
        raise ModelError("Najveća duljina ulaza modela ne odgovara ai_config.json.")
    tokenizer = Tokenizer.from_file(str(root / "tokenizer.json"))
    tokenizer.enable_truncation(max_length=int(config["max_seq_length"]))
    tokenizer.enable_padding()
    options = ort.SessionOptions()
    options.intra_op_num_threads = 2
    session = ort.InferenceSession(
        str(root / "onnx" / "model.onnx"), options, providers=["CPUExecutionProvider"]
    )
    return Embedder(
        session,
        tokenizer,
        tuple(i.name for i in session.get_inputs()),
        str(config["model_id"]),
        str(config["model_revision"]),
    )


@lru_cache(maxsize=1)
def shared_embedder() -> Embedder:
    """One model per process, loaded on first use. The API never downloads it."""
    return load_embedder(load_ai_config())
