"""Représentations du texte pour la classification des cours.

- Représentation A : TF-IDF mots (1-2 grammes) + TF-IDF caractères (3-5 grammes),
  combinées par FeatureUnion. Les n-grammes de caractères résistent aux fautes,
  aux pluriels et aux mots composés (« sous-requête », « requêtes »).
- Représentation B : embeddings du module 3 (même modèle que le RAG), via un
  transformateur scikit-learn qui ne sérialise que le nom du modèle.
"""

from __future__ import annotations

import re

import numpy as np
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.pipeline import FeatureUnion

from app.core.text import STOPWORDS_FR, normalize

_ISOLATED_NUMBER = re.compile(r"\b\d+\b")


def preprocess(text: str) -> str:
    """Prétraitement : minuscules, accents normalisés, nombres isolés supprimés."""
    return " ".join(_ISOLATED_NUMBER.sub(" ", normalize(text)).split())


def build_tfidf_features(word_ngrams: tuple[int, int] = (1, 2), word_min_df: int = 2,
                         char_ngrams: tuple[int, int] = (3, 5), char_min_df: int = 2) -> FeatureUnion:
    """Construit la représentation A (TF-IDF mots + caractères).

    Args:
        word_ngrams: Taille des n-grammes de mots.
        word_min_df: Fréquence documentaire minimale des n-grammes de mots.
        char_ngrams: Taille des n-grammes de caractères.
        char_min_df: Fréquence documentaire minimale des n-grammes de caractères.

    Returns:
        Un FeatureUnion nommé ``word`` / ``char`` (noms utilisés par GridSearchCV).
    """
    word = TfidfVectorizer(preprocessor=preprocess, stop_words=sorted(STOPWORDS_FR), ngram_range=word_ngrams,
                           min_df=word_min_df, sublinear_tf=True, token_pattern=r"(?u)\b[a-z][a-z0-9]+\b")
    char = TfidfVectorizer(preprocessor=preprocess, analyzer="char_wb", ngram_range=char_ngrams,
                           min_df=char_min_df, sublinear_tf=True, max_features=60_000)
    return FeatureUnion([("word", word), ("char", char)])


class EmbeddingFeatures(BaseEstimator, TransformerMixin):
    """Transformateur scikit-learn qui vectorise avec le modèle d'embeddings partagé.

    Seuls ``backend`` et ``model_name`` sont sérialisés par joblib : le modèle
    lui-même est rechargé (une seule fois) à la première utilisation.
    """

    def __init__(self, backend: str = "sentence-transformers",
                 model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                 max_chars: int = 2000) -> None:
        self.backend = backend
        self.model_name = model_name
        self.max_chars = max_chars

    def fit(self, X, y=None):  # noqa: N803 - convention scikit-learn
        """Aucun apprentissage : le modèle d'embeddings est pré-entraîné."""
        return self

    def transform(self, X) -> np.ndarray:  # noqa: N803 - convention scikit-learn
        """Vectorise les textes (tronqués à ``max_chars`` caractères)."""
        from app.core.embeddings import build_embedder

        embedder = build_embedder(self.backend, self.model_name)
        return embedder.encode([str(t)[: self.max_chars] for t in X])
