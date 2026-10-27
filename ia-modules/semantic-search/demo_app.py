"""Démonstration Streamlit simplifiée du moteur de recherche sémantique."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import streamlit as st

from src.evaluate import (
    KeywordSearchEngine,
    evaluate_search,
    load_evaluation_cases,
)
from src.module import SemanticSearchEngine

MODEL_NAME = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
CHUNK_SIZE = 300
OVERLAP = 50
DATA_DIR = Path(__file__).parent / "data"
SAMPLE_NOTES = DATA_DIR / "notes_exemple.json"
EVALUATION_CASES = DATA_DIR / "evaluation_cases.json"


def _decode(content: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "latin-1"):
        try:
            return content.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Encodage du fichier non reconnu.")


def _notes_from_payload(payload: Any, source: str) -> list[dict[str, str]]:
    raw_notes = payload.get("notes") if isinstance(payload, dict) else payload
    if not isinstance(raw_notes, list):
        raise ValueError(f"{source} doit contenir une liste de notes.")

    notes: list[dict[str, str]] = []
    for position, raw in enumerate(raw_notes, start=1):
        if not isinstance(raw, dict):
            raise ValueError(f"Note {position} invalide dans {source}.")
        text = raw.get("text")
        if not isinstance(text, str) or not text.strip():
            raise ValueError(f"Note {position} sans texte dans {source}.")
        note_id = str(raw.get("id") or f"{Path(source).stem}-{position}")
        title = str(raw.get("title") or note_id)
        notes.append({"id": note_id, "title": title, "text": text})
    return notes


def _notes_from_text(text: str, source: str) -> list[dict[str, str]]:
    cleaned = text.strip()
    if not cleaned:
        raise ValueError(f"{source} est vide.")
    first_line = next(
        (line.strip() for line in cleaned.splitlines() if line.strip()),
        source,
    )
    return [
        {
            "id": Path(source).stem,
            "title": first_line[:120],
            "text": cleaned,
        }
    ]


def notes_from_file(path: Path) -> list[dict[str, str]]:
    content = path.read_bytes()
    if path.suffix.lower() == ".json":
        try:
            payload = json.loads(_decode(content))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalide : {path.name}.") from exc
        return _notes_from_payload(payload, path.name)
    return _notes_from_text(_decode(content), path.name)


def notes_from_upload(uploaded: Any) -> list[dict[str, str]]:
    content = uploaded.getvalue()
    if Path(uploaded.name).suffix.lower() == ".json":
        try:
            payload = json.loads(_decode(content))
        except json.JSONDecodeError as exc:
            raise ValueError(f"JSON invalide : {uploaded.name}.") from exc
        return _notes_from_payload(payload, uploaded.name)
    return _notes_from_text(_decode(content), uploaded.name)


def collect_notes(uploads: Any) -> tuple[list[dict[str, str]], bool]:
    if uploads:
        notes = [
            note
            for uploaded in uploads
            for note in notes_from_upload(uploaded)
        ]
        return notes, False
    if not SAMPLE_NOTES.is_file():
        raise ValueError("Les notes d'exemple sont absentes.")
    return notes_from_file(SAMPLE_NOTES), True


@st.cache_resource(show_spinner=False)
def build_engine(notes_json: str) -> SemanticSearchEngine:
    notes = json.loads(notes_json)
    engine = SemanticSearchEngine(model_name=MODEL_NAME)
    engine.index(notes, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    return engine


@st.cache_resource(show_spinner=False)
def build_baseline(notes_json: str) -> KeywordSearchEngine:
    notes = json.loads(notes_json)
    baseline = KeywordSearchEngine()
    baseline.index(notes, chunk_size=CHUNK_SIZE, overlap=OVERLAP)
    return baseline


def render_results(results: list[Any]) -> None:
    for position, result in enumerate(results, start=1):
        with st.container(border=True):
            header, score = st.columns([4, 1])
            with header:
                st.markdown(f"**{position}. {result.title}**")
                st.caption(f"Note : `{result.note_id}`")
            with score:
                st.metric("Similarité", f"{result.score:.3f}")
            st.write(result.passage)


def render_evaluation(
    engine: SemanticSearchEngine,
    notes_json: str,
    top_k: int,
    using_sample: bool,
) -> None:
    with st.expander("Évaluer le moteur sur les requêtes d'exemple"):
        if not using_sample:
            st.info(
                "L'évaluation utilise les notes d'exemple. "
                "Retirez les fichiers importés pour la lancer."
            )
            return
        if not EVALUATION_CASES.is_file():
            st.info("Aucun fichier data/evaluation_cases.json disponible.")
            return

        try:
            cases = load_evaluation_cases(EVALUATION_CASES)
        except (OSError, ValueError) as exc:
            st.warning(f"Jeu d'évaluation illisible : {exc}")
            return

        st.caption(
            "Comparaison entre la recherche sémantique et une baseline par mots-clés, "
            "calculée sur les notes d'exemple."
        )
        if st.button("Lancer l'évaluation"):
            with st.spinner("Calcul des métriques..."):
                baseline = build_baseline(notes_json)
                semantic_report = evaluate_search(engine, cases, k=top_k)
                keyword_report = evaluate_search(baseline, cases, k=top_k)

            st.dataframe(
                [
                    {
                        "Moteur": "Sémantique",
                        "Precision@k": round(semantic_report.precision_at_k, 3),
                        "Recall@k": round(semantic_report.recall_at_k, 3),
                        "MRR": round(semantic_report.mrr, 3),
                        "Requêtes": semantic_report.evaluated_queries,
                    },
                    {
                        "Moteur": "Mots-clés",
                        "Precision@k": round(keyword_report.precision_at_k, 3),
                        "Recall@k": round(keyword_report.recall_at_k, 3),
                        "MRR": round(keyword_report.mrr, 3),
                        "Requêtes": keyword_report.evaluated_queries,
                    },
                ],
                hide_index=True,
                width="stretch",
            )


def main() -> None:
    st.set_page_config(
        page_title="Recherche sémantique de notes",
        page_icon="🔎",
        layout="wide",
    )

    st.title("Recherche sémantique dans mes notes")

    with st.sidebar:
        uploads = st.file_uploader(
            "Importer mes notes (.json, .txt, .md)",
            type=["json", "txt", "md"],
            accept_multiple_files=True,
        )
        top_k = st.slider(
            "Nombre de résultats",
            min_value=1,
            max_value=10,
            value=5,
        )

    try:
        notes, using_sample = collect_notes(uploads)
    except ValueError as exc:
        st.error(str(exc))
        st.stop()

    if not notes:
        st.error("Aucune note exploitable.")
        st.stop()

    notes_json = json.dumps(notes, ensure_ascii=False, sort_keys=True)
    try:
        with st.spinner(
            "Chargement du modèle et construction de l'index. "
            "Le premier lancement peut prendre plusieurs minutes..."
        ):
            engine = build_engine(notes_json)
    except Exception as exc:
        st.error(f"Impossible de construire l'index : {exc}")
        st.stop()

    info_cols = st.columns(2)
    info_cols[0].metric("Notes", len(notes))
    info_cols[1].metric("Passages indexés", engine.size)
    if using_sample:
        st.caption(
            "Notes d'exemple chargées automatiquement. "
            "Importer un fichier pour les remplacer."
        )

    with st.form("search-form"):
        query = st.text_input(
            "Votre question",
            key="query",
            placeholder="Ex. : comment éviter le sur-apprentissage ?",
        )
        submitted = st.form_submit_button("Rechercher", type="primary")

    if submitted:
        try:
            results = engine.search(query, top_k=top_k)
        except (ValueError, RuntimeError) as exc:
            st.warning(str(exc))
            st.stop()

        st.subheader(f"Résultats pour « {query.strip()} »")
        if results:
            render_results(results)
        else:
            st.info("Aucun passage retourné.")

    render_evaluation(engine, notes_json, top_k, using_sample)


if __name__ == "__main__":
    main()
