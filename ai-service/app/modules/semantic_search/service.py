"""Service HTTP local du module 2 (recherche sémantique).

L'application PHP appelle ce service sur 127.0.0.1:8002. Le modèle
sentence-transformers est chargé une seule fois, les index sont mis en cache
par contenu de cours, et les passages les plus proches sont renvoyés en JSON.

Le service n'est jamais exposé sur le réseau : il écoute par défaut sur
127.0.0.1 et exige un jeton interne.
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import os
import re
import sys
import threading
from collections import OrderedDict
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any, Sequence

import numpy as np

MODULE_DIR = Path(__file__).resolve().parent
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

from src.module import SemanticSearchEngine  # noqa: E402

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 300
OVERLAP = 50
MIN_QUERY_CHARS = 2
MAX_QUERY_CHARS = 200
MAX_NOTES = 50
MAX_TEXT_CHARS = 24000
DEFAULT_TOP_K = 5
MAX_TOP_K = 10
DEFAULT_TOKEN = "demo-semantic-search-token"
MAX_BODY_BYTES = 5 * 1024 * 1024


class ServiceError(ValueError):
    """Erreur de validation renvoyée au client en 422."""


class HashingEmbedder:
    """Embedder déterministe sans téléchargement, utilisé par les tests.

    Il ne remplace pas le modèle sémantique en production, mais il permet de
    vérifier le service HTTP et le classement sur de petits corpus.
    """

    def __init__(self, dimensions: int = 256) -> None:
        self.dimensions = dimensions

    def encode(self, sentences: Sequence[str], **_: Any) -> np.ndarray:
        vectors = np.zeros((len(sentences), self.dimensions), dtype=np.float32)
        for row, sentence in enumerate(sentences):
            for token in re.findall(r"[0-9A-Za-zÀ-ÖØ-öø-ÿ]+", sentence.lower()):
                digest = hashlib.sha256(token.encode("utf-8")).digest()
                column = int.from_bytes(digest[:4], "big") % self.dimensions
                sign = 1.0 if digest[4] % 2 == 0 else -1.0
                vectors[row, column] += sign
        norms = np.linalg.norm(vectors, axis=1, keepdims=True)
        norms[norms == 0.0] = 1.0
        return vectors / norms


def validate_query(value: Any) -> str:
    if not isinstance(value, str):
        raise ServiceError("La requête doit être un texte.")
    query = value.strip()
    if not (MIN_QUERY_CHARS <= len(query) <= MAX_QUERY_CHARS):
        raise ServiceError(
            f"La requête doit contenir entre {MIN_QUERY_CHARS} et "
            f"{MAX_QUERY_CHARS} caractères."
        )
    return query


def validate_notes(value: Any) -> list[dict[str, str]]:
    if not isinstance(value, list) or not value:
        raise ServiceError("Au moins un cours est nécessaire.")
    if len(value) > MAX_NOTES:
        raise ServiceError(f"Au plus {MAX_NOTES} cours peuvent être indexés.")
    notes: list[dict[str, str]] = []
    for position, raw in enumerate(value, start=1):
        if not isinstance(raw, dict):
            raise ServiceError(f"Cours {position} invalide.")
        note_id = raw.get("id")
        if not isinstance(note_id, (str, int)) or str(note_id).strip() == "":
            raise ServiceError(f"Cours {position} sans identifiant.")
        title = raw.get("title")
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ServiceError(f"Cours {position} sans texte.")
        cleaned = text.strip()
        if len(cleaned) > MAX_TEXT_CHARS:
            cleaned = cleaned[:MAX_TEXT_CHARS]
        notes.append(
            {
                "id": str(note_id).strip(),
                "title": (
                    title.strip()
                    if isinstance(title, str) and title.strip()
                    else f"Cours {position}"
                )[:200],
                "text": cleaned,
            }
        )
    return notes


def validate_top_k(value: Any) -> int:
    if value is None:
        return DEFAULT_TOP_K
    if isinstance(value, bool):
        raise ServiceError("top_k doit être un entier.")
    try:
        top_k = int(value)
    except (TypeError, ValueError) as exc:
        raise ServiceError("top_k doit être un entier.") from exc
    if not 1 <= top_k <= MAX_TOP_K:
        raise ServiceError(f"top_k doit être compris entre 1 et {MAX_TOP_K}.")
    return top_k


class EngineCache:
    """Construit et réutilise les index pour un contenu de cours donné."""

    def __init__(self, embedder: Any, max_entries: int = 8) -> None:
        self._embedder = embedder
        self._max_entries = max_entries
        self._engines: OrderedDict[str, SemanticSearchEngine] = OrderedDict()
        self._lock = threading.Lock()

    @staticmethod
    def _key(notes: list[dict[str, str]]) -> str:
        canonical = json.dumps(
            notes, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def engine_for(self, notes: list[dict[str, str]]) -> SemanticSearchEngine:
        key = self._key(notes)
        with self._lock:
            engine = self._engines.get(key)
            if engine is not None:
                self._engines.move_to_end(key)
                return engine
            engine = SemanticSearchEngine(
                model_name=MODEL_NAME,
                embedder=self._embedder,
            )
            engine.index(notes, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
            self._engines[key] = engine
            while len(self._engines) > self._max_entries:
                self._engines.popitem(last=False)
            return engine

    def search(
        self,
        query: str,
        notes: list[dict[str, str]],
        top_k: int,
    ) -> dict[str, Any]:
        engine = self.engine_for(notes)
        results = engine.search(query, top_k=top_k)
        return {
            "results": [
                {
                    "note_id": result.note_id,
                    "title": result.title,
                    "passage": result.passage,
                    "score": round(float(result.score), 6),
                }
                for result in results
            ],
            "backend": engine.backend,
            "notes": len(notes),
            "passages": engine.size,
        }


class SemanticSearchHandler(BaseHTTPRequestHandler):
    server_version = "SemanticSearch/1.0"
    token: str = DEFAULT_TOKEN
    cache: EngineCache
    embedder_name: str = "sentence-transformers"

    def log_message(self, format: str, *args: Any) -> None:
        sys.stderr.write(
            "%s - %s\n" % (self.address_string(), format % args)
        )

    def _write_json(self, status: int, payload: dict[str, Any]) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def _authorized(self) -> bool:
        header = self.headers.get("Authorization", "")
        if header.lower().startswith("bearer "):
            candidate = header[7:].strip()
        else:
            candidate = self.headers.get("X-Semantic-Search-Token", "").strip()
        return bool(self.token) and hmac.compare_digest(candidate, self.token)

    def do_GET(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route in ("/", "/health"):
            self._write_json(
                200,
                {
                    "status": "ok",
                    "service": "semantic-search",
                    "embedder": self.embedder_name,
                    "model": MODEL_NAME if self.embedder_name != "hashing" else None,
                },
            )
            return
        self._write_json(404, {"error": "Route inconnue."})

    def do_POST(self) -> None:  # noqa: N802
        route = self.path.split("?", 1)[0]
        if route != "/search":
            self._write_json(404, {"error": "Route inconnue."})
            return
        if not self._authorized():
            self._write_json(401, {"error": "Jeton du service invalide."})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
        except ValueError:
            length = 0
        if length <= 0 or length > MAX_BODY_BYTES:
            self._write_json(413, {"error": "Requête vide ou trop volumineuse."})
            return
        try:
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if not isinstance(payload, dict):
                raise ServiceError("Corps JSON invalide.")
            query = validate_query(payload.get("query"))
            notes = validate_notes(payload.get("notes"))
            top_k = validate_top_k(payload.get("top_k"))
            data = self.cache.search(query, notes, top_k)
        except ServiceError as exc:
            self._write_json(422, {"error": str(exc)})
            return
        except json.JSONDecodeError:
            self._write_json(400, {"error": "JSON invalide."})
            return
        except Exception as exc:  # pragma: no cover - garde-fou HTTP
            self.log_message("Erreur interne : %s", exc)
            self._write_json(
                500,
                {"error": "Erreur interne du service de recherche sémantique."},
            )
            return
        self._write_json(200, data)


def build_embedder(kind: str) -> tuple[Any, str]:
    if kind == "hashing":
        return HashingEmbedder(), "hashing"
    try:
        from sentence_transformers import SentenceTransformer
    except ImportError as exc:
        raise SystemExit(
            "sentence-transformers n'est pas installé. "
            "Exécutez : pip install -r requirements.txt"
        ) from exc
    return SentenceTransformer(MODEL_NAME), "sentence-transformers"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8002)
    parser.add_argument(
        "--token",
        default=os.environ.get("SEMANTIC_SEARCH_TOKEN", DEFAULT_TOKEN),
    )
    parser.add_argument(
        "--embedder",
        choices=("sentence-transformers", "hashing"),
        default="sentence-transformers",
    )
    args = parser.parse_args(argv)

    embedder, embedder_name = build_embedder(args.embedder)
    handler = type(
        "ConfiguredSemanticSearchHandler",
        (SemanticSearchHandler,),
        {
            "token": args.token,
            "cache": EngineCache(embedder),
            "embedder_name": embedder_name,
        },
    )
    server = ThreadingHTTPServer((args.host, args.port), handler)
    print(
        f"Recherche sémantique : http://{args.host}:{args.port} "
        f"(embedder={embedder_name})",
        flush=True,
    )
    print("Appuyez sur Ctrl+C pour arrêter.", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nArrêt du service.", flush=True)
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
