"""Modèles candidats comparés pour la classification des cours.

Chaque candidat est un Pipeline scikit-learn et une grille d'hyperparamètres
explorée par GridSearchCV en validation croisée stratifiée à 5 plis.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sklearn.calibration import CalibratedClassifierCV
from sklearn.ensemble import RandomForestClassifier
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline
from sklearn.svm import LinearSVC

from app.modules.classification.features import EmbeddingFeatures, build_tfidf_features


@dataclass
class Candidate:
    """Modèle candidat : nom lisible, pipeline et grille de recherche."""

    key: str
    label: str
    pipeline: Pipeline
    grid: dict[str, list] = field(default_factory=dict)


def build_candidates(embedding_backend: str = "sentence-transformers",
                     embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                     random_state: int = 42) -> list[Candidate]:
    """Retourne les cinq modèles comparés dans le rapport.

    Args:
        embedding_backend: Backend d'embeddings pour le candidat « embeddings ».
        embedding_model: Nom du modèle sentence-transformers.
        random_state: Graine pour la reproductibilité.

    Returns:
        Liste des candidats, du plus simple au plus coûteux.
    """
    tfidf_grid = {"features__word__ngram_range": [(1, 1), (1, 2)], "features__word__min_df": [1, 2]}
    return [
        Candidate("nb", "TF-IDF + Naive Bayes multinomial (référence)",
                  Pipeline([("features", build_tfidf_features()), ("clf", MultinomialNB())]),
                  {**tfidf_grid, "clf__alpha": [0.05, 0.2, 1.0]}),
        Candidate("logreg", "TF-IDF + Régression logistique",
                  Pipeline([("features", build_tfidf_features()),
                            ("clf", LogisticRegression(max_iter=3000, random_state=random_state))]),
                  {**tfidf_grid, "clf__C": [1.0, 10.0, 50.0]}),
        Candidate("svm", "TF-IDF + SVM linéaire calibré",
                  Pipeline([("features", build_tfidf_features()),
                            ("clf", CalibratedClassifierCV(LinearSVC(random_state=random_state), cv=3))]),
                  {**tfidf_grid, "clf__estimator__C": [0.1, 1.0, 10.0]}),
        Candidate("rf", "TF-IDF + Forêt aléatoire",
                  Pipeline([("features", build_tfidf_features()),
                            ("clf", RandomForestClassifier(n_estimators=300, n_jobs=-1,
                                                           random_state=random_state))]),
                  {"clf__max_depth": [None, 40], "clf__min_samples_leaf": [1, 2]}),
        Candidate("emb_logreg", "Embeddings (module 3) + Régression logistique",
                  Pipeline([("features", EmbeddingFeatures(embedding_backend, embedding_model)),
                            ("clf", LogisticRegression(max_iter=3000, random_state=random_state))]),
                  {"clf__C": [1.0, 10.0, 50.0]}),
    ]
