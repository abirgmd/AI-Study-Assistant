"""Phases 5 et 6 : module 5 (classification) — données, pipeline, seuil, explication, API, feedback."""

from __future__ import annotations

import csv
from pathlib import Path

import joblib
import pytest
from sklearn.linear_model import LogisticRegression
from sklearn.pipeline import Pipeline

from app.config import load_categories
from app.errors import InvalidInputError, ModelNotReadyError
from app.main import Container
from app.modules.classification.classifier import UNCLASSIFIED, CourseClassifier, FeedbackStore, top_terms_per_class
from app.modules.classification.features import EmbeddingFeatures, build_tfidf_features, preprocess
from app.modules.classification.models import build_candidates
from tests.conftest import COURS_RESEAUX, COURS_TESTS, store_document

DATA = Path(__file__).resolve().parent.parent / "data" / "classification"


def read(name: str) -> list[dict]:
    with (DATA / name).open(encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


@pytest.fixture(scope="module")
def small_bundle() -> dict:
    """Petit modèle entraîné sur le vrai jeu d'entraînement (rapide : régression logistique)."""
    rows = read("train.csv")
    pipeline = Pipeline([("features", build_tfidf_features()), ("clf", LogisticRegression(max_iter=2000))])
    pipeline.fit([r["text"] for r in rows], [r["label"] for r in rows])
    return {"pipeline": pipeline, "categories": load_categories(), "meta": {"version": "test", "seuil_confiance": 0.25}}


# --- données ---------------------------------------------------------------------
def test_categories_partagees_avec_php():
    categories = load_categories()
    assert len(categories) == 8 and "Génie logiciel" in categories


def test_jeu_entrainement_equilibre_et_etiquete():
    rows = read("train.csv")
    counts = {c: sum(r["label"] == c for r in rows) for c in load_categories()}
    assert all(60 <= n <= 80 for n in counts.values()), counts
    assert {r["source"] for r in rows} == {"synthetique"}


def test_aucune_fuite_entre_entrainement_et_test_reel():
    train = {" ".join(r["text"].lower().split()) for r in read("train.csv")}
    test = [" ".join(r["text"].lower().split()) for r in read("test_reel.csv")]
    assert not train.intersection(test)
    assert all(r["source"].startswith("reel_cours:") for r in read("test_reel.csv"))


# --- pipeline ---------------------------------------------------------------------
def test_pretraitement():
    assert preprocess("Les 3 Requêtes SQL du TP n°2") == "les requetes sql du tp n"


def test_cinq_candidats_compares():
    keys = [c.key for c in build_candidates(embedding_backend="hashing")]
    assert keys == ["nb", "logreg", "svm", "rf", "emb_logreg"]


def test_transformateur_embeddings_ne_serialise_que_le_nom():
    features = EmbeddingFeatures(backend="hashing", model_name="x")
    vectors = features.fit([]).transform(["un texte", "un autre texte"])
    assert vectors.shape == (2, 512)
    assert features.get_params()["backend"] == "hashing"


def test_prediction_et_explication(small_bundle):
    classifier = CourseClassifier(small_bundle, None, 20_000)
    assert classifier.min_confidence == 0.25  # seuil choisi à l'entraînement
    prediction = classifier.predict(COURS_RESEAUX)
    assert prediction.top[0]["category"] == "Réseaux et sécurité"
    assert len(prediction.top) == 3
    assert prediction.top[0]["probability"] == prediction.confidence
    assert prediction.top[0]["probability"] >= prediction.top[1]["probability"] >= prediction.top[2]["probability"]
    assert prediction.explanation and all(isinstance(w, str) for w in prediction.explanation)


def test_seuil_de_confiance_force_a_classer(small_bundle):
    classifier = CourseClassifier(small_bundle, 0.99, 20_000)  # seuil forcé par la configuration
    prediction = classifier.predict(COURS_TESTS)
    assert prediction.category == UNCLASSIFIED and not prediction.accepted
    assert prediction.top[0]["category"] != UNCLASSIFIED  # la meilleure catégorie reste visible


def test_texte_trop_court(small_bundle):
    with pytest.raises(InvalidInputError):
        CourseClassifier(small_bundle, None, 20_000).predict("SQL")


def test_termes_par_categorie(small_bundle):
    terms = top_terms_per_class(small_bundle["pipeline"], 5)
    assert set(terms) == set(load_categories())
    assert any("reseau" in t or "protocole" in t for t in terms["Réseaux et sécurité"])


def test_modele_absent(tmp_path):
    with pytest.raises(ModelNotReadyError):
        CourseClassifier.load(tmp_path / "absent.joblib", None, 1000)


def test_feedback_store(tmp_path):
    store = FeedbackStore(tmp_path / "feedback.csv", max_chars=50)
    store.add("Texte   corrigé " * 20, "Génie logiciel", "Intelligence artificielle")
    store.add("Autre texte", "Mathématiques", "À classer")
    rows = list(csv.DictReader((tmp_path / "feedback.csv").open(encoding="utf-8")))
    assert [r["label"] for r in rows] == ["Génie logiciel", "Mathématiques"]
    assert len(rows[0]["text"]) == 50


# --- API ---------------------------------------------------------------------------
@pytest.fixture
def model_ready(settings, small_bundle):
    settings.classifier_path.parent.mkdir(parents=True, exist_ok=True)
    joblib.dump(small_bundle, settings.classifier_path)
    return settings


def test_api_classify_texte_et_document(client, model_ready):
    response = client.post("/classify", json={"text": COURS_RESEAUX})
    assert response.status_code == 200
    body = response.json()
    assert body["category"] == "Réseaux et sécurité" and body["model_version"] == "test"
    name = store_document(model_ready, COURS_RESEAUX)
    assert client.post("/classify", json={"stored_name": name}).json()["top"][0]["category"] == "Réseaux et sécurité"


def test_api_classify_erreurs(client, model_ready):
    assert client.post("/classify", json={}).status_code == 422
    assert client.post("/classify", json={"stored_name": "../../x.txt"}).status_code == 422
    assert client.post("/classify", json={"stored_name": "cd" * 24 + ".pdf"}).status_code == 404


def test_api_classify_sans_modele(client):
    response = client.post("/classify", json={"text": COURS_RESEAUX})
    assert response.status_code == 503 and "entraîné" in response.json()["detail"]
    assert client.get("/health").json()["classifier_ready"] is False


def test_api_categories(client):
    body = client.get("/classify/categories").json()
    assert body["unclassified"] == UNCLASSIFIED and len(body["categories"]) == 8


def test_api_feedback(client, model_ready):
    name = store_document(model_ready, COURS_TESTS)
    assert client.post("/classify/feedback", json={"stored_name": name, "predicted": "À classer",
                                                   "corrected": "Génie logiciel"}).json() == {"saved": True}
    assert client.post("/classify/feedback", json={"stored_name": name, "predicted": "x",
                                                   "corrected": "Cuisine"}).status_code == 422
    assert model_ready.feedback_file.exists()


def test_container_charge_le_modele_une_seule_fois(model_ready):
    container = Container(model_ready)
    assert container.classifier is container.classifier
