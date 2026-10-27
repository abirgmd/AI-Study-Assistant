"""Chargement du modèle de classification entraîné, prédiction et explication."""

from __future__ import annotations

import csv
import logging
import threading
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path

import joblib
import numpy as np
from sklearn.calibration import CalibratedClassifierCV
from sklearn.linear_model import LogisticRegression
from sklearn.naive_bayes import MultinomialNB
from sklearn.pipeline import Pipeline

from app.errors import InvalidInputError, ModelNotReadyError

logger = logging.getLogger(__name__)
UNCLASSIFIED = "À classer"


@dataclass
class Prediction:
    """Catégorie prédite pour un cours."""

    category: str
    confidence: float
    accepted: bool
    top: list[dict] = field(default_factory=list)
    explanation: list[str] = field(default_factory=list)
    model_version: str = ""

    def to_dict(self) -> dict:
        """Sérialisation JSON."""
        return asdict(self)


def class_weights(clf) -> np.ndarray | None:
    """Poids (classes × variables) d'un classifieur linéaire, ou None.

    Pour Naive Bayes, on utilise l'écart du log-probabilité de chaque terme à sa
    moyenne entre classes ; pour le SVM calibré, la moyenne des SVM internes.
    """
    if isinstance(clf, LogisticRegression):
        return clf.coef_
    if isinstance(clf, CalibratedClassifierCV):
        coefs = [c.estimator.coef_ for c in clf.calibrated_classifiers_ if hasattr(c.estimator, "coef_")]
        return np.mean(coefs, axis=0) if coefs else None
    if isinstance(clf, MultinomialNB):
        logp = clf.feature_log_prob_
        return logp - logp.mean(axis=0, keepdims=True)
    return None


def word_feature_mask(pipeline: Pipeline) -> tuple[np.ndarray, np.ndarray] | None:
    """Noms des variables et masque des variables « mots » (les n-grammes de caractères
    ne sont pas lisibles pour un humain et sont exclus de l'explication)."""
    features = pipeline.named_steps.get("features")
    if features is None or not hasattr(features, "get_feature_names_out"):
        return None
    try:
        names = features.get_feature_names_out()
    except (AttributeError, ValueError):
        return None
    mask = np.char.startswith(names.astype(str), "word__")
    return names, mask


def top_terms_per_class(pipeline: Pipeline, n: int = 10) -> dict[str, list[str]]:
    """Les n termes (mots) les plus discriminants de chaque catégorie."""
    weights = class_weights(pipeline.named_steps["clf"])
    named = word_feature_mask(pipeline)
    if weights is None or named is None:
        return {}
    names, mask = named
    result: dict[str, list[str]] = {}
    for row, label in zip(weights, pipeline.classes_, strict=True):
        scores = np.where(mask, row, -np.inf)
        best = np.argsort(scores)[::-1][:n]
        result[str(label)] = [str(names[i]).removeprefix("word__") for i in best if np.isfinite(scores[i])]
    return result


class CourseClassifier:
    """Modèle de classification chargé depuis le fichier joblib produit par l'entraînement."""

    def __init__(self, bundle: dict, min_confidence: float | None, max_chars: int) -> None:
        self.pipeline: Pipeline = bundle["pipeline"]
        self.categories: list[str] = list(bundle["categories"])
        self.meta: dict = dict(bundle.get("meta", {}))
        # Seuil forcé par la configuration, sinon celui choisi à l'entraînement, sinon 0,5.
        self.min_confidence = (min_confidence if min_confidence is not None
                               else float(self.meta.get("seuil_confiance", 0.5)))
        self.max_chars = max_chars
        self._weights = class_weights(self.pipeline.named_steps["clf"])
        self._names = word_feature_mask(self.pipeline)

    @classmethod
    def load(cls, path: Path, min_confidence: float | None, max_chars: int) -> CourseClassifier:
        """Charge le modèle (fichier produit par scripts/train_classifier.py uniquement).

        Raises:
            ModelNotReadyError: Si le fichier n'existe pas encore.
        """
        if not path.is_file():
            raise ModelNotReadyError("Aucun modèle de classification entraîné. Lancez scripts/train_classifier.py.")
        # joblib s'appuie sur pickle : on ne charge que notre propre fichier, jamais un fichier reçu.
        return cls(joblib.load(path), min_confidence, max_chars)

    def predict(self, text: str) -> Prediction:
        """Prédit la catégorie d'un texte de cours.

        Si la probabilité maximale est inférieure au seuil, la catégorie retournée
        est « À classer » : on préfère ne rien afficher qu'afficher une erreur.
        """
        text = (text or "").strip()[: self.max_chars]
        if len(text) < 20:
            raise InvalidInputError("Texte trop court pour être classé.")
        probabilities = self.pipeline.predict_proba([text])[0]
        classes = [str(c) for c in self.pipeline.classes_]
        order = np.argsort(probabilities)[::-1]
        best = int(order[0])
        confidence = float(probabilities[best])
        accepted = confidence >= self.min_confidence
        top = [{"category": classes[i], "probability": round(float(probabilities[i]), 4)} for i in order[:3]]
        return Prediction(
            category=classes[best] if accepted else UNCLASSIFIED,
            confidence=round(confidence, 4),
            accepted=accepted,
            top=top,
            explanation=self._explain(text, best),
            model_version=str(self.meta.get("version", "")),
        )

    def _explain(self, text: str, class_index: int, n: int = 6) -> list[str]:
        """Mots du document qui ont le plus pesé en faveur de la catégorie prédite."""
        if self._weights is None or self._names is None:
            return []
        names, mask = self._names
        vector = self.pipeline.named_steps["features"].transform([text])
        row = vector.tocsr()
        contributions = {}
        for col, value in zip(row.indices, row.data, strict=True):
            if mask[col]:
                contributions[col] = value * self._weights[class_index][col]
        best = sorted(contributions.items(), key=lambda item: item[1], reverse=True)[:n]
        return [str(names[col]).removeprefix("word__") for col, score in best if score > 0]


class FeedbackStore:
    """Enregistre les corrections des étudiants pour un futur réentraînement."""

    FIELDS = ["text", "label", "predicted", "created_at"]

    def __init__(self, path: Path, max_chars: int = 3000) -> None:
        self.path = path
        self.max_chars = max_chars
        self._lock = threading.Lock()

    def add(self, text: str, label: str, predicted: str) -> None:
        """Ajoute une correction (texte tronqué à max_chars caractères)."""
        with self._lock:
            new_file = not self.path.exists()
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8", newline="") as handle:
                writer = csv.DictWriter(handle, fieldnames=self.FIELDS)
                if new_file:
                    writer.writeheader()
                writer.writerow({"text": " ".join(text.split())[: self.max_chars], "label": label,
                                 "predicted": predicted,
                                 "created_at": datetime.now(UTC).isoformat(timespec="seconds")})
