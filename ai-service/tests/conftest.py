"""Fixtures communes : configuration isolée, documents d'exemple, client HTTP."""

from __future__ import annotations

import secrets
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.config import Settings
from app.main import Container, create_app

TOKEN = "jeton-de-test-" + "x" * 32
FIXTURES = Path(__file__).parent / "fixtures"


def make_settings(tmp_path: Path, **overrides) -> Settings:
    """Configuration de test : stockage temporaire, modèles légers, aucun .env lu."""
    values = {
        "internal_token": TOKEN,
        "storage_dir": tmp_path / "storage",
        "embedding_backend": "hashing",
        "llm_backend": "extractive",
        "rag_min_score": 0.15,
        "classifier_path": tmp_path / "models" / "classifier.joblib",
        "feedback_file": tmp_path / "feedback.csv",
    }
    values.update(overrides)
    settings = Settings(_env_file=None, **values)  # type: ignore[call-arg]
    settings.courses_dir.mkdir(parents=True, exist_ok=True)
    return settings


def store_document(settings: Settings, content: bytes | str, extension: str = "txt") -> str:
    """Dépose un document dans storage/courses comme le ferait PHP. Retourne son nom."""
    name = f"{secrets.token_hex(24)}.{extension}"
    data = content.encode("utf-8") if isinstance(content, str) else content
    (settings.courses_dir / name).write_bytes(data)
    return name


@pytest.fixture
def settings(tmp_path: Path) -> Settings:
    return make_settings(tmp_path)


@pytest.fixture
def container(settings: Settings) -> Container:
    return Container(settings)


@pytest.fixture
def client(settings: Settings, container: Container):
    app = create_app(settings, container)
    with TestClient(app, headers={"X-Internal-Token": TOKEN}) as test_client:
        yield test_client


COURS_TESTS = (
    "Chapitre 5 : génération automatique de tests. Un test automatisé est un programme qui vérifie "
    "le bon fonctionnement d'un autre programme. Le triptyque Arrange-Act-Assert structure chaque test : "
    "préparer l'état initial, exécuter l'action, vérifier le résultat. La couverture de code mesure le "
    "pourcentage du code exécuté par la suite de tests. Le mutation testing modifie volontairement le code "
    "pour vérifier qu'un test échoue."
)
COURS_RESEAUX = (
    "Le protocole TCP assure un transport fiable grâce à la poignée de main en trois temps (SYN, SYN-ACK, ACK). "
    "Le protocole UDP est plus léger mais ne garantit pas la livraison des paquets. Le modèle OSI comporte "
    "sept couches, de la couche physique à la couche application. Un pare-feu filtre le trafic réseau."
)
