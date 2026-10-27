from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest

MODULE_DIR = Path(__file__).resolve().parents[1]
if str(MODULE_DIR) not in sys.path:
    sys.path.insert(0, str(MODULE_DIR))

import service  # noqa: E402
from service import (  # noqa: E402
    EngineCache,
    HashingEmbedder,
    ServiceError,
    validate_notes,
    validate_query,
    validate_top_k,
)

NOTES = [
    {
        "id": "n1",
        "title": "Régularisation",
        "text": "La régularisation L2 pénalise les grands poids et limite le sur-apprentissage.",
    },
    {
        "id": "n2",
        "title": "Bases de données",
        "text": "Une base de données relationnelle organise les tables et les clés étrangères.",
    },
]

TOPICS = {
    "n1": "regularisation sur apprentissage poids modele",
    "n2": "base donnees relationnelle tables cle etrangere",
}


class TopicEmbedder:
    """Embedder minimaliste pour vérifier le classement sans modèle externe."""

    def encode(self, sentences, **_):
        vectors = np.zeros((len(sentences), 2), dtype=np.float32)
        for row, sentence in enumerate(sentences):
            normalized = sentence.lower()
            vectors[row, 0] = sum(
                normalized.count(word) for word in TOPICS["n1"].split()
            )
            vectors[row, 1] = sum(
                normalized.count(word) for word in TOPICS["n2"].split()
            )
        return vectors


@pytest.fixture
def cache():
    return EngineCache(TopicEmbedder())


def test_validate_query_trims_and_accepts_short_text():
    assert validate_query("  régularisation  ") == "régularisation"


@pytest.mark.parametrize("value", ["", "a", "x" * 201, None, 42])
def test_validate_query_rejects_invalid_values(value):
    with pytest.raises(ServiceError):
        validate_query(value)


def test_validate_notes_accepts_valid_courses():
    notes = validate_notes(NOTES)
    assert [note["id"] for note in notes] == ["n1", "n2"]
    assert notes[0]["title"] == "Régularisation"


def test_validate_notes_rejects_empty_or_textless_course():
    with pytest.raises(ServiceError):
        validate_notes([])
    with pytest.raises(ServiceError):
        validate_notes([{"id": "n1", "title": "Vide", "text": "   "}])


def test_validate_notes_truncates_text():
    notes = validate_notes(
        [{"id": "n1", "title": "Long", "text": "a" * (service.MAX_TEXT_CHARS + 20)}]
    )
    assert len(notes[0]["text"]) == service.MAX_TEXT_CHARS


@pytest.mark.parametrize("value, expected", [(None, 5), (1, 1), ("10", 10)])
def test_validate_top_k_accepts_valid_values(value, expected):
    assert validate_top_k(value) == expected


@pytest.mark.parametrize("value", [0, 11, -1, True, "abc"])
def test_validate_top_k_rejects_invalid_values(value):
    with pytest.raises(ServiceError):
        validate_top_k(value)


def test_search_returns_best_course_first(cache):
    data = cache.search("régularisation", NOTES, 1)
    assert data["results"][0]["note_id"] == "n1"
    assert data["backend"] in {"faiss", "numpy"}
    assert data["passages"] >= 1
    assert data["notes"] == 2


def test_search_returns_data_discipline(cache):
    data = cache.search("base de données relationnelle", NOTES, 1)
    assert data["results"][0]["note_id"] == "n2"


def test_cache_reuses_engine_for_same_notes(cache):
    first = cache.engine_for(NOTES)
    second = cache.engine_for(NOTES)
    assert first is second


def test_hashing_embedder_is_deterministic_and_normalized():
    embedder = HashingEmbedder()
    first = embedder.encode(["régularisation", "base de données"])
    second = embedder.encode(["régularisation", "base de données"])
    assert np.allclose(first, second)
    assert np.allclose(np.linalg.norm(first, axis=1), 1.0)
