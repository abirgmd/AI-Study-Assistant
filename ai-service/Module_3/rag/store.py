"""Index vectoriel FAISS, un par étudiant.

Organisation sur le disque :

    storage/indexes/<student_id>/
        index.faiss     vecteurs (IndexIDMap2 sur IndexFlatIP ou IndexFlatL2)
        chunks.json     texte et métadonnées de chaque bloc, par identifiant
        manifest.json   modèle d'embeddings, dimension, métrique, version

Isolation : chaque étudiant a son propre dossier et son propre index. Une
recherche ne charge que l'index de l'étudiant indiqué par PHP (identifiant tiré
de la session), il est donc impossible de retrouver le passage d'un autre.

Robustesse : chaque écriture passe par des fichiers temporaires remplacés de
façon atomique (os.replace), sous un verrou par étudiant.
"""

from __future__ import annotations

import json
import logging
import os
import threading
from dataclasses import asdict, dataclass
from pathlib import Path

import faiss
import numpy as np

from app.errors import IndexMismatchError, InvalidInputError

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StoredChunk:
    """Bloc indexé, avec ce qu'il faut pour citer la source."""

    chunk_id: int
    course_id: int
    title: str
    page: int | None
    rank: int
    text: str


@dataclass(frozen=True)
class SearchHit:
    """Résultat de recherche : un bloc et sa similarité cosinus (de -1 à 1)."""

    chunk: StoredChunk
    score: float


class StudentIndex:
    """Index FAISS et métadonnées d'un seul étudiant."""

    def __init__(self, directory: Path, embedder_name: str, dim: int, metric: str) -> None:
        self.directory = directory
        self.embedder_name = embedder_name
        self.dim = dim
        self.metric = metric
        self.version = 0
        self.next_id = 0
        self.chunks: dict[int, StoredChunk] = {}
        self.index = self._new_index()

    def _new_index(self) -> faiss.Index:
        base = faiss.IndexFlatIP(self.dim) if self.metric == "ip" else faiss.IndexFlatL2(self.dim)
        return faiss.IndexIDMap2(base)

    # --- persistance -------------------------------------------------------
    @classmethod
    def load(cls, directory: Path, embedder_name: str, dim: int, metric: str) -> StudentIndex:
        """Charge l'index d'un étudiant, ou en crée un vide s'il n'existe pas.

        Raises:
            IndexMismatchError: Si l'index existant a été créé avec un autre modèle ou une
                autre métrique (les vecteurs ne seraient pas comparables).
        """
        instance = cls(directory, embedder_name, dim, metric)
        manifest_path = directory / "manifest.json"
        if not manifest_path.exists():
            return instance
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        if (manifest["embedder"], manifest["dim"], manifest["metric"]) != (embedder_name, dim, metric):
            raise IndexMismatchError()
        instance.version = int(manifest["version"])
        instance.next_id = int(manifest["next_id"])
        instance.index = faiss.read_index(str(directory / "index.faiss"))
        raw = json.loads((directory / "chunks.json").read_text(encoding="utf-8"))
        instance.chunks = {int(k): StoredChunk(**v) for k, v in raw.items()}
        if instance.index.ntotal != len(instance.chunks):
            logger.error("Index incohérent pour %s : %d vecteurs, %d blocs", directory.name,
                         instance.index.ntotal, len(instance.chunks))
            raise IndexMismatchError("L'index de cet étudiant est incohérent. Relancez l'indexation.")
        return instance

    def save(self) -> None:
        """Écrit l'index, les blocs et le manifeste de façon atomique."""
        self.directory.mkdir(parents=True, exist_ok=True)
        self.version += 1
        files = {
            "index.faiss": None,
            "chunks.json": json.dumps({str(k): asdict(v) for k, v in self.chunks.items()}, ensure_ascii=False),
            "manifest.json": json.dumps({"embedder": self.embedder_name, "dim": self.dim, "metric": self.metric,
                                         "version": self.version, "next_id": self.next_id}),
        }
        temporary: list[tuple[Path, Path]] = []
        for name, content in files.items():
            target = self.directory / name
            tmp = self.directory / f".{name}.tmp"
            if content is None:
                faiss.write_index(self.index, str(tmp))
            else:
                tmp.write_text(content, encoding="utf-8")
            temporary.append((tmp, target))
        # Le manifeste est remplacé en dernier : il « valide » l'écriture.
        for tmp, target in temporary:
            os.replace(tmp, target)

    # --- opérations --------------------------------------------------------
    def remove_course(self, course_id: int) -> int:
        """Retire tous les blocs d'un cours. Retourne le nombre de blocs retirés."""
        ids = [cid for cid, chunk in self.chunks.items() if chunk.course_id == course_id]
        if ids:
            self.index.remove_ids(np.asarray(ids, dtype=np.int64))
            for cid in ids:
                del self.chunks[cid]
        return len(ids)

    def add_course(self, course_id: int, title: str, items: list[tuple[str, int | None, int]],
                   vectors: np.ndarray) -> int:
        """Remplace les blocs d'un cours par de nouveaux blocs.

        Args:
            course_id: Identifiant du cours.
            title: Titre affiché dans les sources.
            items: Pour chaque bloc : (texte, page, rang).
            vectors: Vecteurs normalisés, une ligne par bloc.

        Returns:
            Nombre de blocs ajoutés.
        """
        if len(items) != vectors.shape[0]:
            raise InvalidInputError("Nombre de vecteurs différent du nombre de blocs.")
        if vectors.shape[1] != self.dim:
            raise IndexMismatchError()
        self.remove_course(course_id)
        ids = np.arange(self.next_id, self.next_id + len(items), dtype=np.int64)
        self.index.add_with_ids(np.ascontiguousarray(vectors, dtype=np.float32), ids)
        for chunk_id, (text, page, rank) in zip(ids.tolist(), items, strict=True):
            self.chunks[chunk_id] = StoredChunk(chunk_id, course_id, title, page, rank, text)
        self.next_id += len(items)
        return len(items)

    def search(self, vector: np.ndarray, k: int, course_id: int | None = None) -> list[SearchHit]:
        """Retourne les k blocs les plus proches, éventuellement limités à un cours.

        Pour la métrique L2, la distance d entre vecteurs normalisés est convertie
        en similarité cosinus : cos = 1 - d / 2 (FAISS retourne d = distance au carré).
        """
        if self.index.ntotal == 0:
            return []
        # Avec un filtre par cours, on interroge tout l'index puis on filtre :
        # l'index d'un étudiant reste petit (quelques milliers de blocs au plus).
        fetch = self.index.ntotal if course_id is not None else min(k, self.index.ntotal)
        query = np.ascontiguousarray(vector.reshape(1, -1), dtype=np.float32)
        scores, ids = self.index.search(query, fetch)
        hits: list[SearchHit] = []
        for score, chunk_id in zip(scores[0].tolist(), ids[0].tolist(), strict=True):
            if chunk_id < 0:
                continue
            chunk = self.chunks.get(chunk_id)
            if chunk is None or (course_id is not None and chunk.course_id != course_id):
                continue
            similarity = score if self.metric == "ip" else 1.0 - score / 2.0
            hits.append(SearchHit(chunk, float(similarity)))
            if len(hits) == k:
                break
        return hits

    def courses(self) -> set[int]:
        """Identifiants des cours présents dans l'index."""
        return {chunk.course_id for chunk in self.chunks.values()}


class IndexRepository:
    """Accès aux index des étudiants, avec un verrou par étudiant."""

    def __init__(self, base_dir: Path, embedder_name: str, dim: int, metric: str = "ip") -> None:
        self.base_dir = base_dir
        self.embedder_name = embedder_name
        self.dim = dim
        self.metric = metric
        self._locks: dict[int, threading.Lock] = {}
        self._guard = threading.Lock()

    def _directory(self, student_id: int) -> Path:
        if not isinstance(student_id, int) or isinstance(student_id, bool) or student_id < 1:
            raise InvalidInputError("Identifiant étudiant invalide.")
        return self.base_dir / str(student_id)

    def lock(self, student_id: int) -> threading.Lock:
        """Verrou dédié à un étudiant (évite deux écritures simultanées)."""
        with self._guard:
            return self._locks.setdefault(student_id, threading.Lock())

    def load(self, student_id: int) -> StudentIndex:
        """Charge l'index d'un étudiant (vide s'il n'existe pas encore)."""
        return StudentIndex.load(self._directory(student_id), self.embedder_name, self.dim, self.metric)
