"""Moteur de recherche sémantique sur des notes de cours.

Le moteur découpe les notes en passages, calcule des embeddings avec
sentence-transformers, puis recherche les passages les plus proches avec FAISS
(ou NumPy si FAISS n'est pas disponible). Aucun appel à une API externe n'est
nécessaire.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

import numpy as np


DEFAULT_MODEL_NAME = (
    "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
)
DEFAULT_CHUNK_SIZE = 80
DEFAULT_OVERLAP = 15
INDEX_FORMAT_VERSION = 1

_SENTENCE_SPLIT = re.compile(r"(?<=[.!?…])\s+|\n{2,}")


@dataclass(frozen=True)
class SearchResult:
    """Passage retourné par une recherche."""

    note_id: str
    title: str
    passage: str
    score: float


@dataclass(frozen=True)
class NoteChunk:
    """Passage indexé issu d'une note."""

    note_id: str
    title: str
    passage: str
    chunk_index: int


class Embedder(Protocol):
    """Interface minimale compatible avec SentenceTransformer.encode."""

    def encode(self, sentences: Sequence[str], **kwargs: Any) -> Any:
        """Retourne une matrice de vecteurs, une ligne par texte."""


def _normalize_whitespace(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases, sans dépendance externe."""
    normalized = _normalize_whitespace(text)
    if not normalized:
        return []
    return [
        sentence.strip()
        for sentence in _SENTENCE_SPLIT.split(normalized)
        if sentence.strip()
    ]


def chunk_text(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[str]:
    """Découpe un texte en passages d'environ ``chunk_size`` mots.

    Les phrases sont conservées autant que possible. Un chevauchement de
    ``overlap`` mots est ajouté entre deux passages consécutifs.
    """
    if chunk_size < 1:
        raise ValueError("chunk_size doit être supérieur ou égal à 1.")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap doit être compris entre 0 et chunk_size - 1.")

    sentences = split_sentences(text)
    if not sentences:
        return []

    chunks: list[str] = []
    current: list[str] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if current:
            chunks.append(" ".join(current).strip())
            current = []
            current_words = 0

    for sentence in sentences:
        words = sentence.split()
        if not words:
            continue

        if len(words) > chunk_size:
            flush()
            step = chunk_size - overlap
            for start in range(0, len(words), step):
                window = words[start : start + chunk_size]
                if not window:
                    break
                chunks.append(" ".join(window))
                if start + chunk_size >= len(words):
                    break
            continue

        if current and current_words + len(words) > chunk_size:
            previous = " ".join(current)
            flush()
            if overlap:
                room = chunk_size - len(words)
                if room > 0:
                    tail = previous.split()[-min(overlap, room):]
                    if tail:
                        current = [" ".join(tail)]
                        current_words = len(tail)

        current.append(sentence)
        current_words += len(words)

    flush()
    return [chunk for chunk in dict.fromkeys(chunks) if chunk]


def chunk_notes(
    notes: Sequence[Mapping[str, Any]],
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_OVERLAP,
) -> list[NoteChunk]:
    """Valide les notes et retourne les passages à indexer."""
    if not notes:
        raise ValueError("Le corpus de notes est vide.")

    chunks: list[NoteChunk] = []
    for position, note in enumerate(notes):
        if not isinstance(note, Mapping):
            raise ValueError(f"La note à la position {position} doit être un objet.")

        note_id = str(note.get("id", "")).strip()
        raw_title = note.get("title")
        title = str(raw_title).strip() if raw_title is not None else ""
        text = note.get("text", "")

        if not note_id:
            raise ValueError(f"La note à la position {position} n'a pas d'identifiant.")
        if not title:
            title = note_id
        if not isinstance(text, str):
            raise ValueError(f"Le texte de la note {note_id!r} doit être une chaîne.")

        for chunk_index, passage in enumerate(
            chunk_text(text, chunk_size=chunk_size, overlap=overlap)
        ):
            chunks.append(
                NoteChunk(
                    note_id=note_id,
                    title=title,
                    passage=passage,
                    chunk_index=chunk_index,
                )
            )

    if not chunks:
        raise ValueError("Aucun passage exploitable n'a été trouvé dans les notes.")
    return chunks


class SemanticSearchEngine:
    """Recherche les passages les plus proches sémantiquement d'une requête."""

    def __init__(
        self,
        model_name: str = DEFAULT_MODEL_NAME,
        *,
        embedder: Embedder | None = None,
        batch_size: int = 32,
        device: str | None = None,
    ) -> None:
        if not model_name.strip():
            raise ValueError("Le nom du modèle ne peut pas être vide.")
        if batch_size < 1:
            raise ValueError("batch_size doit être supérieur ou égal à 1.")

        self.model_name = model_name
        self.batch_size = batch_size
        self.device = device
        self._embedder = embedder
        self._chunks: list[NoteChunk] = []
        self._embeddings: np.ndarray | None = None
        self._faiss_index: Any | None = None
        self._backend: str | None = None

    @property
    def size(self) -> int:
        """Nombre de passages indexés."""
        return len(self._chunks)

    @property
    def backend(self) -> str | None:
        """Backend de recherche actif : ``faiss`` ou ``numpy``."""
        return self._backend

    def _ensure_embedder(self) -> Embedder:
        if self._embedder is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError(
                    "sentence-transformers n'est pas installé. "
                    "Exécutez : pip install -r requirements.txt"
                ) from exc
            self._embedder = SentenceTransformer(
                self.model_name,
                device=self.device,
            )
        return self._embedder

    def _encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            raise ValueError("Aucun texte à encoder.")

        vectors = self._ensure_embedder().encode(
            list(texts),
            batch_size=self.batch_size,
            show_progress_bar=False,
            convert_to_numpy=True,
            normalize_embeddings=True,
        )
        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim == 1:
            matrix = matrix.reshape(1, -1)
        if matrix.shape[0] != len(texts):
            raise RuntimeError("Le modèle a retourné un nombre de vecteurs incohérent.")

        norms = np.linalg.norm(matrix, axis=1, keepdims=True)
        norms[norms == 0] = 1.0
        return matrix / norms

    def _install_index(
        self,
        chunks: Sequence[NoteChunk],
        embeddings: np.ndarray,
    ) -> None:
        self._chunks = list(chunks)
        self._embeddings = np.asarray(embeddings, dtype=np.float32)
        self._faiss_index = None
        self._backend = "numpy"

        try:
            import faiss
        except ImportError:
            return

        index = faiss.IndexFlatIP(self._embeddings.shape[1])
        index.add(self._embeddings)
        self._faiss_index = index
        self._backend = "faiss"

    def index(
        self,
        notes: Sequence[Mapping[str, Any]],
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        """Découpe les notes, calcule les embeddings et construit l'index."""
        chunks = chunk_notes(notes, chunk_size=chunk_size, overlap=overlap)
        embeddings = self._encode([chunk.passage for chunk in chunks])
        self._install_index(chunks, embeddings)

    def save_index(self, directory: str | Path) -> Path:
        """Sauvegarde les embeddings et les passages dans un dossier."""
        if self._embeddings is None or not self._chunks:
            raise RuntimeError("L'index est vide : appelez index() avant save_index().")

        target = Path(directory)
        target.mkdir(parents=True, exist_ok=True)
        np.save(target / "embeddings.npy", self._embeddings)
        faiss_path = target / "faiss.index"
        if self._faiss_index is not None:
            import faiss

            faiss.write_index(self._faiss_index, str(faiss_path))
        elif faiss_path.exists():
            faiss_path.unlink()
        payload = {
            "format_version": INDEX_FORMAT_VERSION,
            "model_name": self.model_name,
            "chunks": [
                {
                    "note_id": chunk.note_id,
                    "title": chunk.title,
                    "passage": chunk.passage,
                    "chunk_index": chunk.chunk_index,
                }
                for chunk in self._chunks
            ],
        }
        (target / "index.json").write_text(
            json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        return target

    def load_index(
        self,
        directory: str | Path,
        *,
        embedder: Embedder | None = None,
    ) -> int:
        """Charge un index sauvegardé et retourne le nombre de passages."""
        target = Path(directory)
        try:
            payload = json.loads(
                (target / "index.json").read_text(encoding="utf-8")
            )
        except OSError as exc:
            raise RuntimeError(f"Index introuvable ou illisible : {target}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Index JSON invalide : {target / 'index.json'}") from exc

        if not isinstance(payload, dict):
            raise RuntimeError("Le fichier index.json doit contenir un objet.")
        if payload.get("format_version") != INDEX_FORMAT_VERSION:
            raise RuntimeError("Version d'index non compatible.")

        model_name = payload.get("model_name")
        if not isinstance(model_name, str) or not model_name.strip():
            raise RuntimeError("Le nom du modèle est absent de l'index.")

        raw_chunks = payload.get("chunks")
        if not isinstance(raw_chunks, list) or not raw_chunks:
            raise RuntimeError("L'index ne contient aucun passage.")

        chunks: list[NoteChunk] = []
        for position, raw in enumerate(raw_chunks):
            if not isinstance(raw, dict):
                raise RuntimeError(f"Passage {position} invalide dans l'index.")
            note_id = raw.get("note_id")
            title = raw.get("title")
            passage = raw.get("passage")
            chunk_index = raw.get("chunk_index")
            if not all(
                isinstance(value, str) and value
                for value in (note_id, title, passage)
            ):
                raise RuntimeError(f"Passage {position} incomplet dans l'index.")
            if (
                not isinstance(chunk_index, int)
                or isinstance(chunk_index, bool)
                or chunk_index < 0
            ):
                raise RuntimeError(f"Passage {position} sans index valide.")
            chunks.append(
                NoteChunk(
                    note_id=note_id,
                    title=title,
                    passage=passage,
                    chunk_index=chunk_index,
                )
            )

        try:
            embeddings = np.load(
                target / "embeddings.npy",
                allow_pickle=False,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError("Fichier embeddings.npy absent ou invalide.") from exc
        if embeddings.ndim != 2 or embeddings.shape[0] != len(chunks):
            raise RuntimeError("La forme des embeddings ne correspond pas aux passages.")
        if embeddings.shape[1] < 1:
            raise RuntimeError("Les embeddings doivent avoir au moins une dimension.")

        self.model_name = model_name
        if embedder is not None:
            self._embedder = embedder
        self._install_index(chunks, embeddings)

        faiss_path = target / "faiss.index"
        if faiss_path.is_file():
            try:
                import faiss

                saved_index = faiss.read_index(str(faiss_path))
                if (
                    saved_index.ntotal == len(chunks)
                    and saved_index.d == embeddings.shape[1]
                ):
                    self._faiss_index = saved_index
                    self._backend = "faiss"
            except Exception:
                pass
        return len(chunks)

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Retourne les ``top_k`` passages les plus proches de la requête."""
        if not isinstance(query, str) or not query.strip():
            raise ValueError("La requête ne peut pas être vide.")
        if (
            not isinstance(top_k, int)
            or isinstance(top_k, bool)
            or top_k < 1
        ):
            raise ValueError("top_k doit être un entier supérieur ou égal à 1.")
        if self._embeddings is None or not self._chunks:
            raise RuntimeError("L'index est vide : appelez index() avant search().")

        query_vector = self._encode([query])[0]
        if query_vector.shape[0] != self._embeddings.shape[1]:
            raise RuntimeError(
                "La dimension du vecteur de requête ne correspond pas à l'index."
            )
        limit = min(top_k, len(self._chunks))

        if self._faiss_index is not None:
            scores, indices = self._faiss_index.search(
                query_vector.reshape(1, -1),
                limit,
            )
            pairs = list(zip(scores[0].tolist(), indices[0].tolist()))
        else:
            raw_scores = self._embeddings @ query_vector
            order = np.argsort(-raw_scores)[:limit]
            pairs = [(float(raw_scores[index]), int(index)) for index in order]

        pairs.sort(key=lambda pair: (-pair[0], pair[1]))

        results: list[SearchResult] = []
        for score, index in pairs:
            if index < 0 or index >= len(self._chunks):
                continue
            chunk = self._chunks[index]
            results.append(
                SearchResult(
                    note_id=chunk.note_id,
                    title=chunk.title,
                    passage=chunk.passage,
                    score=float(score),
                )
            )
        return results
