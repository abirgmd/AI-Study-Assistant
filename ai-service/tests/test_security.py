"""Phase 0 : santé du service et contrôle du jeton interne."""

from __future__ import annotations

import pytest

from app.config import Settings
from app.errors import InvalidInputError
from app.security import validate_stored_name


def test_health_avec_jeton(client):
    response = client.get("/health")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["embedding_backend"] == "hashing"


def test_jeton_absent_refuse(client):
    response = client.get("/health", headers={"X-Internal-Token": ""})
    assert response.status_code == 401
    assert "jeton" in response.json()["detail"]


def test_jeton_faux_refuse(client):
    response = client.get("/health", headers={"X-Internal-Token": "faux" * 10})
    assert response.status_code == 401


def test_toutes_les_routes_exigent_le_jeton(client):
    for method, url in [("post", "/rag/ask"), ("post", "/rag/index"), ("post", "/classify"),
                        ("get", "/classify/categories"), ("delete", "/rag/index/1/1")]:
        response = getattr(client, method)(url, headers={"X-Internal-Token": "mauvais"})
        assert response.status_code == 401, url


@pytest.mark.parametrize("name", [
    "../../config/database.php",
    "a" * 48 + ".php",
    "A" * 48 + ".pdf",
    "a" * 47 + ".pdf",
    "a" * 48 + ".pdf\n",
    "a" * 48 + ".pdf/../x",
    "",
])
def test_nom_de_fichier_malveillant_refuse(name):
    with pytest.raises(InvalidInputError):
        validate_stored_name(name)


def test_nom_de_fichier_valide_accepte():
    name = "0123456789abcdef" * 3 + ".docx"
    assert validate_stored_name(name) == name


def test_jeton_trop_court_refuse(tmp_path):
    with pytest.raises(ValueError):
        Settings(_env_file=None, internal_token="court", storage_dir=tmp_path)  # type: ignore[call-arg]


def test_chevauchement_superieur_a_la_taille_refuse(tmp_path):
    with pytest.raises(ValueError):
        Settings(_env_file=None, internal_token="x" * 40, chunk_size=300, chunk_overlap=300)  # type: ignore[call-arg]
