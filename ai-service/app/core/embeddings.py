"""Vectorisation du texte (embeddings), partagée par les modules 2, 3 et 5.

Deux implémentations derrière la même interface :

- ``SentenceTransformerEmbedder`` : modèle du cours
  ``paraphrase-multilingual-MiniLM-L12-v2`` (384 dimensions, multilingue, CPU).
  C'est le choix par défaut en production.
- ``HashingEmbedder`` : vectorisation lexicale sans modèle à télécharger
  (hachage de n-grammes de caractères et de mots, puis projection aléatoire
  fixe). Il sert de solution de secours hors ligne, pour la CI, et de point de
  comparaison « lexical contre sémantique » dans l'évaluation.

Tous les vecteurs sont normalisés (norme 1, float32) : le produit scalaire est
alors égal à la similarité cosinus.
"""

from __future__ import annotations

import logging
import threading
from functools import lru_cache
from typing import Protocol

import numpy as np

logger = logging.getLogger(__name__)


class Embedder(Protocol):
    """Interface commune des modèles d'embeddings."""

    name: str
    dim: int

    def encode(self, texts: list[str]) -> np.ndarray:
        """Retourne une matrice (len(texts), dim) de vecteurs normalisés float32."""
        ...


def normalize_rows(matrix: np.ndarray) -> np.ndarray:
    """Normalise chaque ligne à la norme 1 (les lignes nulles restent nulles).

    Args:
        matrix: Matrice de vecteurs.

    Returns:
        Matrice float32 contiguë, prête pour FAISS.
    """
    matrix = np.asarray(matrix, dtype=np.float32)
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return np.ascontiguousarray(matrix / norms, dtype=np.float32)


class SentenceTransformerEmbedder:
    """Embeddings sémantiques avec sentence-transformers (chargement paresseux et unique)."""

    def __init__(self, model_name: str, batch_size: int = 32) -> None:
        self.name = f"st:{model_name}"
        self._model_name = model_name
        self._batch_size = batch_size
        self._model = None
        self._lock = threading.Lock()
        self.dim = 384 if "MiniLM-L12" in model_name else 0

    def _load(self):
        with self._lock:
            if self._model is None:
                from sentence_transformers import SentenceTransformer

                logger.info("Chargement du modèle d'embeddings %s", self._model_name)
                self._model = SentenceTransformer(self._model_name, device="cpu")
                self.dim = int(self._model.get_sentence_embedding_dimension())
        return self._model

    def encode(self, texts: list[str]) -> np.ndarray:
        """Vectorise une liste de textes."""
        model = self._load()
        vectors = model.encode(texts, batch_size=self._batch_size, show_progress_bar=False,
                               convert_to_numpy=True, normalize_embeddings=True)
        return normalize_rows(vectors)


class HashingEmbedder:
    """Embeddings lexicaux sans apprentissage ni téléchargement.

    Le texte est transformé en n-grammes de caractères (3 à 5) et de mots
    (1 à 2) par hachage, pondérés en log(1 + tf), puis projetés sur ``dim``
    dimensions par une matrice aléatoire fixe (graine constante). Le résultat
    est déterministe et sans état : deux appels donnent toujours les mêmes
    vecteurs, ce qui permet d'ajouter des cours à un index existant.
    """

    def __init__(self, dim: int = 512, n_features: int = 2**18, seed: int = 42) -> None:
        from sklearn.feature_extraction.text import HashingVectorizer
        from sklearn.random_projection import SparseRandomProjection

        self.name = f"hashing:{dim}"
        self.dim = dim
        self._char = HashingVectorizer(analyzer="char_wb", ngram_range=(3, 5), n_features=n_features,
                                       alternate_sign=False, norm=None, lowercase=True,
                                       strip_accents="unicode")
        self._word = HashingVectorizer(analyzer="word", ngram_range=(1, 2), n_features=n_features,
                                       alternate_sign=False, norm=None, lowercase=True,
                                       strip_accents="unicode")
        self._projection = SparseRandomProjection(n_components=dim, random_state=seed, dense_output=True)
        from scipy import sparse

        self._projection.fit(sparse.csr_matrix((1, 2 * n_features), dtype=np.float32))

    def encode(self, texts: list[str]) -> np.ndarray:
        """Vectorise une liste de textes."""
        from scipy import sparse

        char = self._char.transform(texts)
        word = self._word.transform(texts)
        char.data = np.log1p(char.data)
        word.data = np.log1p(word.data)
        # Les deux familles de n-grammes pèsent autant l'une que l'autre.
        char = _row_normalize_sparse(char)
        word = _row_normalize_sparse(word)
        features = sparse.hstack([char, word]).tocsr().astype(np.float32)
        return normalize_rows(self._projection.transform(features))


def _row_normalize_sparse(matrix):
    from sklearn.preprocessing import normalize

    return normalize(matrix, norm="l2", axis=1, copy=False)


@lru_cache(maxsize=4)
def build_embedder(backend: str, model_name: str) -> Embedder:
    """Construit (une seule fois par configuration) le modèle d'embeddings.

    Args:
        backend: "sentence-transformers" ou "hashing".
        model_name: Nom du modèle sentence-transformers.

    Returns:
        L'instance partagée.
    """
    if backend == "hashing":
        return HashingEmbedder()
    if backend == "sentence-transformers":
        return SentenceTransformerEmbedder(model_name)
    raise ValueError(f"Backend d'embeddings inconnu : {backend}")
