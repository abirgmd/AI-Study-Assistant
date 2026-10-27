"""Évaluation du moteur sémantique et baseline par mots-clés.

Le module fournit :
- le chargement d'un jeu de requêtes annotées ;
- Precision@k, Recall@k et MRR ;
- une baseline lexicale pour vérifier que le sémantique apporte un gain réel.
"""

from __future__ import annotations

import argparse
import json
import math
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Protocol, Sequence

from src.corpus import load_notes
from src.module import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MODEL_NAME,
    DEFAULT_OVERLAP,
    NoteChunk,
    SearchResult,
    SemanticSearchEngine,
    chunk_notes,
)

_TOKEN_RE = re.compile(r"[a-zàâäçéèêëîïôöùûüÿœæ0-9]+", re.IGNORECASE)


@dataclass(frozen=True)
class EvaluationCase:
    """Requête annotée avec les identifiants de notes pertinentes."""

    query: str
    relevant_note_ids: tuple[str, ...]


@dataclass(frozen=True)
class EvaluationReport:
    """Résultat agrégé d'une campagne d'évaluation."""

    precision_at_k: float
    recall_at_k: float
    mrr: float
    evaluated_queries: int


class Retriever(Protocol):
    """Interface minimale attendue par l'évaluation."""

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        """Retourne des résultats triés par pertinence."""


def load_evaluation_cases(path: str | Path) -> list[EvaluationCase]:
    """Charge les cas d'évaluation depuis un fichier JSON.

    Format accepté : une liste d'objets, ou un objet avec la clé ``cases``.
    Chaque cas contient ``query`` et ``relevant_note_ids``.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Fichier d'évaluation introuvable : {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans {source}.") from exc

    raw_cases = payload.get("cases") if isinstance(payload, dict) else payload
    if not isinstance(raw_cases, list) or not raw_cases:
        raise ValueError("Le fichier d'évaluation doit contenir au moins un cas.")

    cases: list[EvaluationCase] = []
    for position, item in enumerate(raw_cases):
        if not isinstance(item, dict):
            raise ValueError(f"Le cas {position} doit être un objet JSON.")
        query = item.get("query")
        relevant = item.get("relevant_note_ids")
        if not isinstance(query, str) or not query.strip():
            raise ValueError(f"Le cas {position} n'a pas de requête valide.")
        if not isinstance(relevant, list) or not relevant:
            raise ValueError(
                f"Le cas {position} doit contenir relevant_note_ids non vide."
            )
        cases.append(
            EvaluationCase(
                query=query.strip(),
                relevant_note_ids=tuple(str(note_id) for note_id in relevant),
            )
        )
    return cases


def evaluate_search(
    retriever: Retriever,
    cases: Sequence[EvaluationCase],
    *,
    k: int = 5,
) -> EvaluationReport:
    """Calcule Precision@k, Recall@k et MRR, moyennés sur les cas."""
    if not cases:
        raise ValueError("Aucun cas d'évaluation fourni.")
    if not isinstance(k, int) or isinstance(k, bool) or k < 1:
        raise ValueError("k doit être un entier supérieur ou égal à 1.")

    precision_sum = 0.0
    recall_sum = 0.0
    reciprocal_rank_sum = 0.0

    for case in cases:
        relevant = set(case.relevant_note_ids)
        if not relevant:
            raise ValueError("Un cas d'évaluation ne peut pas avoir zéro note pertinente.")

        results = retriever.search(case.query, top_k=k)
        seen: set[str] = set()
        hits = 0
        first_rank: int | None = None

        for rank, result in enumerate(results, start=1):
            if result.note_id in relevant and result.note_id not in seen:
                seen.add(result.note_id)
                hits += 1
                if first_rank is None:
                    first_rank = rank

        precision_sum += hits / k
        recall_sum += hits / len(relevant)
        if first_rank is not None:
            reciprocal_rank_sum += 1.0 / first_rank

    count = len(cases)
    return EvaluationReport(
        precision_at_k=precision_sum / count,
        recall_at_k=recall_sum / count,
        mrr=reciprocal_rank_sum / count,
        evaluated_queries=count,
    )


def _tokens(text: str) -> set[str]:
    return set(_TOKEN_RE.findall(text.lower()))


class KeywordSearchEngine:
    """Baseline lexicale : similarité cosinus pondérée par l'IDF."""

    def __init__(self) -> None:
        self._chunks: list[NoteChunk] = []
        self._tokens: list[set[str]] = []
        self._norms: list[float] = []
        self._idf: dict[str, float] = {}
        self._default_idf = 1.0

    @property
    def size(self) -> int:
        return len(self._chunks)

    def index(
        self,
        notes: Sequence[Mapping[str, Any]],
        *,
        chunk_size: int = DEFAULT_CHUNK_SIZE,
        overlap: int = DEFAULT_OVERLAP,
    ) -> None:
        chunks = chunk_notes(notes, chunk_size=chunk_size, overlap=overlap)
        token_sets = [_tokens(chunk.passage) for chunk in chunks]

        document_frequency: dict[str, int] = {}
        for tokens in token_sets:
            for token in tokens:
                document_frequency[token] = document_frequency.get(token, 0) + 1

        total = len(chunks)
        self._idf = {
            token: math.log((total + 1) / (frequency + 1)) + 1.0
            for token, frequency in document_frequency.items()
        }
        self._default_idf = math.log(total + 1) + 1.0
        self._chunks = chunks
        self._tokens = token_sets
        self._norms = [
            math.sqrt(sum(self._idf.get(token, self._default_idf) ** 2 for token in tokens))
            or 1.0
            for tokens in token_sets
        ]

    def search(self, query: str, top_k: int = 5) -> list[SearchResult]:
        if not isinstance(query, str) or not query.strip():
            raise ValueError("La requête ne peut pas être vide.")
        if not isinstance(top_k, int) or isinstance(top_k, bool) or top_k < 1:
            raise ValueError("top_k doit être un entier supérieur ou égal à 1.")
        if not self._chunks:
            raise RuntimeError("L'index est vide : appelez index() avant search().")

        query_tokens = _tokens(query)
        if not query_tokens:
            raise ValueError("La requête ne contient aucun terme exploitable.")

        query_norm = math.sqrt(
            sum(self._idf.get(token, self._default_idf) ** 2 for token in query_tokens)
        ) or 1.0

        scored: list[tuple[float, int]] = []
        for index, tokens in enumerate(self._tokens):
            common = query_tokens & tokens
            if not common:
                continue
            score = sum(
                self._idf.get(token, self._default_idf) for token in common
            ) / (query_norm * self._norms[index])
            scored.append((score, index))

        scored.sort(reverse=True)
        return [
            SearchResult(
                note_id=self._chunks[index].note_id,
                title=self._chunks[index].title,
                passage=self._chunks[index].passage,
                score=float(score),
            )
            for score, index in scored[:top_k]
        ]


def _print_report(name: str, report: EvaluationReport, k: int) -> None:
    print(f"{name}")
    print(f"  Precision@{k} : {report.precision_at_k:.3f}")
    print(f"  Recall@{k}    : {report.recall_at_k:.3f}")
    print(f"  MRR          : {report.mrr:.3f}")
    print(f"  Requêtes     : {report.evaluated_queries}")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Évalue la recherche sémantique et la baseline mots-clés."
    )
    parser.add_argument("--notes", default="data/notes_exemple.json")
    parser.add_argument("--cases", default="data/evaluation_cases.json")
    parser.add_argument("--k", type=int, default=3)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    parser.add_argument(
        "--baseline-only",
        action="store_true",
        help="N'exécute que la baseline mots-clés, sans charger le modèle.",
    )
    args = parser.parse_args()

    notes = load_notes(args.notes)
    cases = load_evaluation_cases(args.cases)

    baseline = KeywordSearchEngine()
    baseline.index(notes, chunk_size=args.chunk_size, overlap=args.overlap)
    _print_report(
        "Baseline mots-clés",
        evaluate_search(baseline, cases, k=args.k),
        args.k,
    )

    if args.baseline_only:
        return

    try:
        engine = SemanticSearchEngine(model_name=args.model)
        engine.index(notes, chunk_size=args.chunk_size, overlap=args.overlap)
        _print_report(
            f"Recherche sémantique ({args.model})",
            evaluate_search(engine, cases, k=args.k),
            args.k,
        )
    except (ImportError, RuntimeError) as exc:
        raise SystemExit(str(exc)) from exc


if __name__ == "__main__":
    main()
