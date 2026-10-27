"""Évaluation et optimisation du module 3 (RAG).

Toutes les valeurs écrites dans reports/rag/ sont MESURÉES par ce script sur le
jeu data/rag_eval.csv (25 questions sur 3 cours réels + 5 questions hors cours),
avec les cours de data/sample_courses/ (le 4e cours sert de distracteur).

Expériences :
  E1  taille des blocs (400, 800, 1200) × k (1, 3, 5) : Hit@k, MRR
  E2  métrique FAISS : produit scalaire (cosinus) contre distance L2
  E3  calibrage du seuil d'abstention (score du meilleur bloc, dans / hors cours)
  E4  génération : backends disponibles × versions du prompt, et sans RAG
  E5  cache LRU : latence d'une question posée une seconde fois

Exemples :
  python scripts/evaluate_rag.py --embedding hashing
  python scripts/evaluate_rag.py --embedding sentence-transformers --generators extractive flan-t5-small flan-t5-base
  python scripts/evaluate_rag.py --embedding sentence-transformers --generators api   (clé dans .env)
"""

from __future__ import annotations

import argparse
import csv
import json
import logging
import secrets
import shutil
import statistics
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))

from app.config import Settings  # noqa: E402
from app.core.embeddings import build_embedder  # noqa: E402
from app.core.text import normalize  # noqa: E402
from app.errors import GenerationError  # noqa: E402
from Module_3.rag.generators import (  # noqa: E402
    ApiLLMGenerator,
    ExtractiveGenerator,
    Generator,
    LocalFlanT5Generator,
    OllamaGenerator,
)
from Module_3.rag.prompt import ABSTENTION_MESSAGE, build_prompt, passages_from_hits  # noqa: E402
from Module_3.rag.service import RagService  # noqa: E402
from Module_3.rag.store import IndexRepository  # noqa: E402

logger = logging.getLogger("evaluate_rag")
DATA = SERVICE_DIR / "data"
COURSES = DATA / "sample_courses"
STUDENT = 1


@dataclass
class Question:
    qid: str
    kind: str
    text: str
    course_file: str
    evidence: str
    keywords: list[str]


def load_questions(path: Path) -> list[Question]:
    with path.open(encoding="utf-8") as handle:
        return [Question(r["id"], r["type"], r["question"], r["course_file"], r["evidence"],
                         [k for k in r["keywords"].split(";") if k]) for r in csv.DictReader(handle)]


def make_settings(storage: Path, embedding: str, **overrides) -> Settings:
    values = {"internal_token": "evaluation-" + "x" * 32, "storage_dir": storage, "embedding_backend": embedding,
              "llm_backend": "extractive", "cache_size": 0}
    values.update(overrides)
    return Settings(_env_file=None, **values)  # type: ignore[call-arg]


def build_index(storage: Path, embedding: str, chunk_size: int, metric: str = "ip") -> tuple[RagService, dict]:
    """Indexe les cours d'exemple dans un stockage temporaire. Retourne le service et les titres."""
    overlap = min(150, chunk_size // 4)
    settings = make_settings(storage, embedding, chunk_size=chunk_size, chunk_overlap=overlap, rag_metric=metric)
    settings.courses_dir.mkdir(parents=True, exist_ok=True)
    embedder = build_embedder(embedding, settings.embedding_model)
    dim = embedder.encode(["dimension"]).shape[1]
    service = RagService(settings, embedder, IndexRepository(settings.index_dir, embedder.name, dim, metric),
                         ExtractiveGenerator())
    titles = {}
    for course_id, path in enumerate(sorted(COURSES.glob("*.txt")), start=1):
        stored = f"{secrets.token_hex(24)}.txt"
        shutil.copy(path, settings.courses_dir / stored)
        service.index_course(STUDENT, course_id, stored, path.stem)
        titles[path.name] = path.stem
    return service, titles


def first_relevant_rank(service: RagService, q: Question, depth: int = 10) -> tuple[int | None, float]:
    """Rang (1..depth) du premier bloc contenant la preuve, et score du meilleur bloc."""
    hits, _ = service.retrieve(STUDENT, q.text, depth)
    evidence = normalize(q.evidence)
    rank = next((i for i, h in enumerate(hits, 1) if evidence and evidence in normalize(h.chunk.text)), None)
    return rank, (hits[0].score if hits else float("nan"))


def retrieval_metrics(service: RagService, questions: list[Question]) -> tuple[dict, list[dict]]:
    rows = []
    for q in questions:
        start = time.perf_counter()
        rank, top = first_relevant_rank(service, q)
        rows.append({"id": q.qid, "kind": q.kind, "rank": rank, "top_score": top,
                     "retrieval_ms": (time.perf_counter() - start) * 1000})
    inside = [r for r in rows if r["kind"] == "in"]
    metrics = {f"hit@{k}": sum(1 for r in inside if r["rank"] and r["rank"] <= k) / len(inside) for k in (1, 3, 5)}
    metrics["mrr@10"] = sum(1 / r["rank"] for r in inside if r["rank"]) / len(inside)
    metrics["retrieval_ms_mean"] = statistics.mean(r["retrieval_ms"] for r in rows)
    return metrics, rows


def keyword_score(answer: str, keywords: list[str]) -> int:
    """Grille 0/1/2 par recouvrement de mots-clés (approximation automatique, à vérifier à la main)."""
    if not keywords:
        return 0
    text = normalize(answer)
    found = sum(1 for k in keywords if normalize(k) in text)
    ratio = found / len(keywords)
    return 2 if ratio >= 0.67 else 1 if ratio >= 0.34 else 0


def p95(values: list[float]) -> float:
    return float(np.percentile(values, 95)) if values else float("nan")


def calibrate_threshold(rows: list[dict]) -> tuple[dict, list[dict]]:
    """Seuil qui maximise l'exactitude équilibrée « répondre / s'abstenir », et le balayage complet."""
    inside = [r["top_score"] for r in rows if r["kind"] == "in"]
    outside = [r["top_score"] for r in rows if r["kind"] == "out"]
    best = None
    sweep = []
    for t in np.round(np.arange(0.0, 1.0, 0.01), 2):
        tpr = sum(s >= t for s in inside) / len(inside)
        tnr = sum(s < t for s in outside) / len(outside)
        balanced = (tpr + tnr) / 2
        sweep.append({"seuil": float(t), "repond_dans_cours": tpr, "abstient_hors_cours": tnr,
                      "exactitude_equilibree": balanced})
        # À égalité, on garde le seuil le plus bas (on préfère répondre que s'abstenir à tort).
        if best is None or balanced > best["balanced_accuracy"]:
            best = {"threshold": float(t), "balanced_accuracy": balanced, "answered_in": tpr, "abstained_out": tnr}
    best.update({"min_in": min(inside), "mean_in": statistics.mean(inside), "max_out": max(outside),
                 "mean_out": statistics.mean(outside)})
    return best, sweep


def make_generator(name: str, settings: Settings) -> Generator:
    if name == "extractive":
        return ExtractiveGenerator()
    if name.startswith("flan-t5"):
        quantize = name.endswith("-int8")
        model = "google/" + name.removesuffix("-int8")
        return LocalFlanT5Generator(model, settings.max_new_tokens, quantize)
    if name == "ollama":
        return OllamaGenerator(settings.ollama_url, settings.ollama_model, settings.max_new_tokens,
                               settings.temperature, settings.ollama_timeout, settings.api_max_retries)
    if name == "api":
        key = settings.api_key.get_secret_value() if settings.api_key else ""
        return ApiLLMGenerator(settings.api_provider, settings.api_model, key, settings.max_new_tokens,
                               settings.temperature, settings.api_timeout, settings.api_max_retries)
    raise ValueError(name)


def evaluate_generation(service: RagService, questions: list[Question], generator: Generator, prompt_version: str,
                        k: int, threshold: float, use_rag: bool = True) -> tuple[dict, list[dict]]:
    """Pose toutes les questions et note les réponses (mots-clés, abstention, latence, taille du prompt)."""
    rows = []
    for q in questions:
        start = time.perf_counter()
        hits, _ = service.retrieve(STUDENT, q.text, k)
        abstained_early = use_rag and (not hits or hits[0].score < threshold)
        passages = passages_from_hits(hits, service.settings.rag_max_passage_chars) if use_rag else []
        prompt = build_prompt(q.text, passages, prompt_version if use_rag else "no_context")
        if abstained_early:
            answer, prompt_tokens, chars = ABSTENTION_MESSAGE, 0, 0
        else:
            generation = generator.generate(prompt, q.text, passages)
            answer, prompt_tokens, chars = generation.text, generation.prompt_tokens, len(prompt)
        latency = (time.perf_counter() - start) * 1000
        abstained = normalize(answer).startswith(normalize(ABSTENTION_MESSAGE))
        rows.append({"id": q.qid, "kind": q.kind, "answer": answer, "abstained": abstained,
                     "keyword_score": keyword_score(answer, q.keywords) if q.kind == "in" else None,
                     "latency_ms": latency, "prompt_chars": chars, "prompt_tokens": prompt_tokens,
                     "llm_called": not abstained_early})
    inside = [r for r in rows if r["kind"] == "in"]
    outside = [r for r in rows if r["kind"] == "out"]
    called = [r for r in rows if r["llm_called"]]
    metrics = {
        "score_moyen_0_2": statistics.mean(r["keyword_score"] for r in inside),
        "reponses_score_2": sum(r["keyword_score"] == 2 for r in inside) / len(inside),
        "abstention_a_tort_dans_cours": sum(r["abstained"] for r in inside) / len(inside),
        "abstention_correcte_hors_cours": sum(r["abstained"] for r in outside) / len(outside),
        "latence_moy_ms": statistics.mean(r["latency_ms"] for r in rows),
        "latence_p95_ms": p95([r["latency_ms"] for r in rows]),
        "appels_llm": len(called),
        "caracteres_prompt_moy": statistics.mean(r["prompt_chars"] for r in called) if called else 0,
        "tokens_prompt_moy": statistics.mean(r["prompt_tokens"] for r in called) if called else 0,
    }
    return metrics, rows


def cache_experiment(service: RagService, questions: list[Question]) -> dict:
    """Latence d'une question posée une première fois, puis une seconde fois (servie par le cache)."""
    service.cache = type(service.cache)(256)
    first, second = [], []
    for q in questions:
        t0 = time.perf_counter()
        a = service.ask(STUDENT, q.text)
        t1 = time.perf_counter()
        b = service.ask(STUDENT, q.text)
        t2 = time.perf_counter()
        assert not a.cache_hit and b.cache_hit
        first.append((t1 - t0) * 1000)
        second.append((t2 - t1) * 1000)
    return {"sans_cache_moy_ms": statistics.mean(first), "avec_cache_moy_ms": statistics.mean(second),
            "acceleration": statistics.mean(first) / max(statistics.mean(second), 1e-6)}


def write_csv(path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def plots(out: Path, retrieval: list[dict], calib_rows: list[dict], balanced: float, configured: float,
          label: str) -> None:
    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, ax = plt.subplots(figsize=(7, 4))
    sizes = sorted({r["chunk_size"] for r in retrieval if r["metric"] == "ip"})
    width = 0.25
    for i, k in enumerate((1, 3, 5)):
        values = [next(r[f"hit@{k}"] for r in retrieval if r["chunk_size"] == s and r["metric"] == "ip")
                  for s in sizes]
        ax.bar(np.arange(len(sizes)) + (i - 1) * width, values, width, label=f"Hit@{k}")
    ax.set_xticks(np.arange(len(sizes)), [f"{s} car." for s in sizes])
    ax.set_ylim(0, 1)
    ax.set_ylabel("Proportion de questions")
    ax.set_title(f"Recherche : taille des blocs et k ({label})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "hit_at_k.png", dpi=130)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(7, 4))
    inside = [r["top_score"] for r in calib_rows if r["kind"] == "in"]
    outside = [r["top_score"] for r in calib_rows if r["kind"] == "out"]
    ax.hist(inside, bins=15, alpha=0.7, label="Questions dans les cours")
    ax.hist(outside, bins=15, alpha=0.7, label="Questions hors cours")
    ax.axvline(balanced, color="black", linestyle="--", label=f"Seuil équilibré = {balanced:.2f}")
    ax.axvline(configured, color="red", linestyle=":", label=f"Seuil configuré = {configured:.2f}")
    ax.set_xlabel("Similarité cosinus du meilleur bloc")
    ax.set_ylabel("Nombre de questions")
    ax.set_title(f"Calibrage du seuil d'abstention ({label})")
    ax.legend()
    fig.tight_layout()
    fig.savefig(out / "seuil_abstention.png", dpi=130)
    plt.close(fig)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--embedding", default="hashing", choices=["hashing", "sentence-transformers"])
    parser.add_argument("--generators", nargs="+", default=["extractive"],
                        help="extractive, flan-t5-small, flan-t5-base, flan-t5-base-int8, ollama, api")
    parser.add_argument("--out", default=str(SERVICE_DIR / "reports" / "rag"))
    parser.add_argument("--threshold", type=float, default=0.15,
                        help="seuil d'abstention configuré (AI_RAG_MIN_SCORE) à comparer au seuil équilibré")
    args = parser.parse_args()
    logging.basicConfig(level=logging.WARNING)
    label = "embeddings lexicaux (hashing)" if args.embedding == "hashing" else "MiniLM multilingue"
    out = Path(args.out) / args.embedding
    shutil.rmtree(out, ignore_errors=True)  # aucun résultat périmé d'une exécution précédente
    out.mkdir(parents=True, exist_ok=True)
    questions = load_questions(DATA / "rag_eval.csv")
    summary: dict = {"embedding": args.embedding, "seuil_configure": args.threshold, "questions": len(questions),
                     "dans_les_cours": sum(q.kind == "in" for q in questions)}

    with tempfile.TemporaryDirectory() as tmp:
        # E1 + E2 : recherche
        retrieval_rows, per_question = [], {}
        for metric in ("ip", "l2"):
            for size in (400, 800, 1200):
                if metric == "l2" and size != 800:
                    continue
                storage = Path(tmp) / f"{metric}-{size}"
                start = time.perf_counter()
                service, _ = build_index(storage, args.embedding, size, metric)
                index_s = time.perf_counter() - start
                metrics, rows = retrieval_metrics(service, questions)
                n_chunks = service.repository.load(STUDENT).index.ntotal
                retrieval_rows.append({"metric": metric, "chunk_size": size, "chunks": n_chunks,
                                       "indexation_s": round(index_s, 3),
                                       **{k: round(v, 4) for k, v in metrics.items()}})
                per_question[(metric, size)] = rows
        write_csv(out / "recherche.csv", retrieval_rows)
        summary["recherche"] = retrieval_rows
        same_ranking = [r["rank"] for r in per_question[("ip", 800)]] == [r["rank"] for r in per_question[("l2", 800)]]
        summary["ip_vs_l2_meme_classement"] = same_ranking

        # E3 : seuil (blocs de 800 caractères, cosinus)
        calib_rows = per_question[("ip", 800)]
        calibration, sweep = calibrate_threshold(calib_rows)
        summary["seuil"] = calibration
        write_csv(out / "seuil_balayage.csv", [{k: round(v, 4) for k, v in r.items()} for r in sweep])
        write_csv(out / "scores_par_question.csv", [{**r, "top_score": round(r["top_score"], 4)} for r in calib_rows])
        plots(out, retrieval_rows, calib_rows, calibration["threshold"], args.threshold, label)

        # E4 : génération
        service, _ = build_index(Path(tmp) / "gen", args.embedding, 800)
        # Les paramètres d'API (clé, modèle) sont lus dans ai-service/.env s'il existe.
        settings_env = Settings() if (SERVICE_DIR / ".env").exists() else None  # type: ignore[call-arg]
        generation_rows, skipped = [], []
        for name in args.generators:
            try:
                generator = make_generator(name, settings_env or service.settings)
                if name == "extractive":
                    # Le générateur extractif n'utilise pas le prompt : on mesure plutôt l'effet du
                    # seuil d'abstention et de la taille des blocs sur la qualité des réponses.
                    for size in (400, 800, 1200):
                        sized, _ = build_index(Path(tmp) / f"gen-{size}", args.embedding, size)
                        # Le seuil équilibré est recalibré pour chaque taille : les scores en dépendent.
                        balanced_t = calibrate_threshold(per_question[("ip", size)])[0]["threshold"]
                        for slug, label_t, t in (("equilibre", f"seuil équilibré {balanced_t:.2f}", balanced_t),
                                                 ("retenu", f"seuil retenu {args.threshold:.2f}", args.threshold),
                                                 ("sans_seuil", "sans seuil", -1.0)):
                            metrics, rows = evaluate_generation(sized, questions, generator, "v3", 3, t)
                            generation_rows.append({"generateur": name, "prompt": f"blocs {size} / {label_t}",
                                                    "rag": "oui", **{k: round(v, 4) for k, v in metrics.items()}})
                            write_csv(out / f"reponses_{name}_{size}_{slug}.csv", rows)
                    continue
                for version in ["v1", "v2", "v3"]:
                    metrics, rows = evaluate_generation(service, questions, generator, version, 3,
                                                        args.threshold)
                    generation_rows.append({"generateur": name, "prompt": version, "rag": "oui",
                                            **{k: round(v, 4) for k, v in metrics.items()}})
                    write_csv(out / f"reponses_{name}_{version}.csv", rows)
                if name != "extractive":
                    metrics, rows = evaluate_generation(service, questions, generator, "v3", 3, 0.0, use_rag=False)
                    generation_rows.append({"generateur": name, "prompt": "sans contexte", "rag": "non",
                                            **{k: round(v, 4) for k, v in metrics.items()}})
                    write_csv(out / f"reponses_{name}_sans_rag.csv", rows)
            except (GenerationError, OSError, ImportError, ValueError) as exc:
                skipped.append({"generateur": name, "raison": f"{type(exc).__name__}: {str(exc)[:200]}"})
        if generation_rows:
            write_csv(out / "generation.csv", generation_rows)
        summary["generation"] = generation_rows
        summary["generateurs_non_mesures"] = skipped

        # E5 : cache
        summary["cache"] = cache_experiment(service, [q for q in questions if q.kind == "in"])

    (out / "resume.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(summary, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
