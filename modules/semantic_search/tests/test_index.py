from __future__ import annotations

import json
from typing import Any, Sequence

import numpy as np
import pytest

from src.module import SemanticSearchEngine

NOTES = [
    {
        "id": "n1",
        "title": "Sur-apprentissage",
        "text": "La régularisation limite le sur-apprentissage et améliore la généralisation.",
    },
    {
        "id": "n2",
        "title": "Embeddings",
        "text": "Un embedding est un vecteur dense qui représente le sens d'un texte.",
    },
]


class FakeEmbedder:
    model_name = "fake-model"

    def encode(self, sentences: Sequence[str], **_: Any) -> np.ndarray:
        vectors: list[list[float]] = []
        for sentence in sentences:
            text = sentence.lower()
            if "régularisation" in text or "généralisation" in text:
                vectors.append([1.0, 0.0, 0.0])
            elif "embedding" in text or "vecteur" in text:
                vectors.append([0.0, 1.0, 0.0])
            else:
                vectors.append([0.2, 0.2, 0.2])
        return np.asarray(vectors, dtype=np.float32)


def _engine() -> SemanticSearchEngine:
    engine = SemanticSearchEngine(model_name="fake-model", embedder=FakeEmbedder())
    engine.index(NOTES)
    return engine


def test_save_and_load_index_roundtrip(tmp_path) -> None:
    engine = _engine()
    expected = engine.search("comment éviter le sur-apprentissage ?", top_k=2)

    target = engine.save_index(tmp_path / "index")
    loaded = SemanticSearchEngine(model_name="autre-modèle")
    count = loaded.load_index(target, embedder=FakeEmbedder())

    assert count == engine.size
    assert loaded.size == engine.size
    assert loaded.model_name == "fake-model"
    assert (target / "index.json").is_file()
    assert (target / "embeddings.npy").is_file()
    assert [result.note_id for result in loaded.search("régularisation", top_k=2)] == [
        result.note_id for result in expected
    ]


def test_save_index_rejects_empty_engine(tmp_path) -> None:
    engine = SemanticSearchEngine(model_name="fake-model", embedder=FakeEmbedder())

    with pytest.raises(RuntimeError, match="vide"):
        engine.save_index(tmp_path / "index")


def test_load_index_rejects_missing_directory(tmp_path) -> None:
    engine = SemanticSearchEngine(model_name="fake-model", embedder=FakeEmbedder())

    with pytest.raises(RuntimeError, match="introuvable"):
        engine.load_index(tmp_path / "absent")


def test_load_index_rejects_mismatched_embeddings(tmp_path) -> None:
    target = _engine().save_index(tmp_path / "index")
    embeddings = np.load(target / "embeddings.npy")
    np.save(target / "embeddings.npy", embeddings[:1])
    metadata = json.loads((target / "index.json").read_text(encoding="utf-8"))
    assert len(metadata["chunks"]) > 1

    engine = SemanticSearchEngine(model_name="fake-model", embedder=FakeEmbedder())
    with pytest.raises(RuntimeError, match="forme"):
        engine.load_index(target, embedder=FakeEmbedder())
