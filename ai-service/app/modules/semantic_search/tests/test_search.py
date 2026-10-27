"""Tests du moteur sémantique, de l'évaluation et de la baseline lexicale."""

from __future__ import annotations

import json
from typing import Any, Sequence

import numpy as np
import pytest

from src.evaluate import (
    EvaluationCase,
    KeywordSearchEngine,
    evaluate_search,
    load_evaluation_cases,
)
from src.module import (
    SearchResult,
    SemanticSearchEngine,
    chunk_text,
    chunk_notes,
)


NOTES = [
    {
        "id": "n1",
        "title": "Sur-apprentissage et régularisation",
        "text": (
            "Le sur-apprentissage apparaît quand un modèle apprend trop les détails "
            "des données d'entraînement. La régularisation limite ce phénomène et "
            "améliore la généralisation."
        ),
    },
    {
        "id": "n2",
        "title": "Embeddings",
        "text": (
            "Un embedding est une représentation vectorielle d'un texte. "
            "Deux textes de sens proche ont des vecteurs proches."
        ),
    },
    {
        "id": "n3",
        "title": "Quiz de révision",
        "text": (
            "Un quiz de révision propose des questions à choix multiples. "
            "Il aide à vérifier la mémorisation active."
        ),
    },
]


class TopicEmbedder:
    """Embedder déterministe pour tester sans télécharger de modèle."""

    def encode(self, sentences: Sequence[str], **_: Any) -> np.ndarray:
        vectors: list[list[float]] = []
        for sentence in sentences:
            text = sentence.lower()
            if any(
                term in text
                for term in (
                    "sur-apprentissage",
                    "régularisation",
                    "apprendre par cœur",
                    "généralisation",
                )
            ):
                vectors.append([1.0, 0.0, 0.0])
            elif "embedding" in text or "vecteur" in text:
                vectors.append([0.0, 1.0, 0.0])
            elif "quiz" in text or "question" in text:
                vectors.append([0.0, 0.0, 1.0])
            else:
                vectors.append([0.2, 0.2, 0.2])
        return np.asarray(vectors, dtype=np.float32)


@pytest.fixture
def engine() -> SemanticSearchEngine:
    search = SemanticSearchEngine(embedder=TopicEmbedder())
    search.index(NOTES)
    return search


def test_search_returns_relevant_note_first(engine: SemanticSearchEngine) -> None:
    results = engine.search("Comment éviter que le modèle apprenne par cœur ?")

    assert results
    assert results[0].note_id == "n1"


def test_search_returns_at_most_top_k_results(engine: SemanticSearchEngine) -> None:
    results = engine.search("régularisation", top_k=2)

    assert len(results) == 2


def test_results_are_sorted_by_descending_score(
    engine: SemanticSearchEngine,
) -> None:
    results = engine.search("sur-apprentissage", top_k=3)
    scores = [result.score for result in results]

    assert scores == sorted(scores, reverse=True)


def test_result_contains_expected_fields(engine: SemanticSearchEngine) -> None:
    result = engine.search("embedding", top_k=1)[0]

    assert isinstance(result, SearchResult)
    assert result.note_id == "n2"
    assert result.title == "Embeddings"
    assert result.passage
    assert np.isfinite(result.score)


def test_empty_query_is_rejected(engine: SemanticSearchEngine) -> None:
    with pytest.raises(ValueError):
        engine.search("   ", top_k=5)


def test_invalid_top_k_is_rejected(engine: SemanticSearchEngine) -> None:
    with pytest.raises(ValueError):
        engine.search("régularisation", top_k=0)


def test_empty_corpus_is_rejected() -> None:
    search = SemanticSearchEngine(embedder=TopicEmbedder())

    with pytest.raises(ValueError):
        search.index([])


def test_search_before_index_is_rejected() -> None:
    search = SemanticSearchEngine(embedder=TopicEmbedder())

    with pytest.raises(RuntimeError):
        search.search("régularisation")


def test_notes_without_text_are_rejected() -> None:
    with pytest.raises(ValueError):
        chunk_notes([{"id": "n1", "title": "Vide", "text": "   "}])


def test_chunk_text_respects_chunk_size_and_overlap() -> None:
    text = " ".join(f"mot{i}" for i in range(30))
    chunks = chunk_text(text, chunk_size=8, overlap=2)

    assert len(chunks) > 1
    assert all(chunk.strip() for chunk in chunks)
    assert all(len(chunk.split()) <= 8 for chunk in chunks)


class StubRetriever:
    def __init__(self, results: dict[str, list[SearchResult]]) -> None:
        self._results = results

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        return self._results.get(query, [])[:top_k]


def result(note_id: str) -> SearchResult:
    return SearchResult(
        note_id=note_id,
        title=note_id,
        passage=f"passage {note_id}",
        score=1.0,
    )


def test_evaluate_search_computes_metrics() -> None:
    retriever = StubRetriever(
        {
            "q1": [result("n1"), result("n2")],
            "q2": [result("n1"), result("n2")],
        }
    )
    cases = [
        EvaluationCase("q1", ("n1",)),
        EvaluationCase("q2", ("n3",)),
    ]

    report = evaluate_search(retriever, cases, k=2)

    assert report.precision_at_k == pytest.approx(0.25)
    assert report.recall_at_k == pytest.approx(0.5)
    assert report.mrr == pytest.approx(0.5)
    assert report.evaluated_queries == 2


def test_evaluate_search_counts_a_duplicate_note_once() -> None:
    retriever = StubRetriever({"q1": [result("n1"), result("n1")]})

    report = evaluate_search(
        retriever,
        [EvaluationCase("q1", ("n1",))],
        k=2,
    )

    assert report.precision_at_k == pytest.approx(0.5)
    assert report.recall_at_k == pytest.approx(1.0)
    assert report.mrr == pytest.approx(1.0)


def test_load_evaluation_cases(tmp_path: Any) -> None:
    path = tmp_path / "cases.json"
    path.write_text(
        json.dumps(
            {
                "cases": [
                    {"query": "question", "relevant_note_ids": ["n1", "n2"]}
                ]
            }
        ),
        encoding="utf-8",
    )

    cases = load_evaluation_cases(path)

    assert cases == [EvaluationCase("question", ("n1", "n2"))]


def test_load_evaluation_cases_rejects_invalid_payload(tmp_path: Any) -> None:
    path = tmp_path / "cases.json"
    path.write_text("{}", encoding="utf-8")

    with pytest.raises(ValueError):
        load_evaluation_cases(path)


def test_keyword_baseline_retrieves_exact_term() -> None:
    baseline = KeywordSearchEngine()
    baseline.index(NOTES)

    results = baseline.search("régularisation", top_k=3)

    assert results
    assert results[0].note_id == "n1"
