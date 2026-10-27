"""Mesure taille et latence de flan-t5, avec et sans quantization dynamique int8.

Reprend la partie 3 du TP : torch.quantization.quantize_dynamic sur les couches
Linear, en CPU uniquement.

Deux modes :
  python scripts/benchmark.py --model google/flan-t5-base
      vrai modèle (téléchargé depuis Hugging Face) : taille, latence ET réponses
      à 5 questions RAG, pour comparer la qualité avant / après quantization.
  python scripts/benchmark.py --random-weights
      même architecture que flan-t5-base (d_model 768, 12 couches, 12 têtes),
      poids aléatoires, sans téléchargement. Mesure UNIQUEMENT la taille et la
      latence (qui ne dépendent pas de la valeur des poids). La qualité n'a aucun
      sens dans ce mode et n'est pas mesurée.

Résultats : reports/benchmark/quantization_<mode>.csv et .png
"""

from __future__ import annotations

import argparse
import copy
import csv
import io
import json
import statistics
import sys
import time
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(SERVICE_DIR))


def serialized_size_mb(model) -> float:
    """Taille du state_dict sérialisé (Mo) : compte aussi les poids int8 empaquetés."""
    import torch

    buffer = io.BytesIO()
    torch.save(model.state_dict(), buffer)
    return buffer.getbuffer().nbytes / 1024**2


def flan_t5_base_config():
    """Hyperparamètres publiés de google/flan-t5-base (architecture T5 v1.1)."""
    from transformers import T5Config

    return T5Config(vocab_size=32128, d_model=768, d_kv=64, d_ff=2048, num_layers=12, num_decoder_layers=12,
                    num_heads=12, feed_forward_proj="gated-gelu", tie_word_embeddings=False,
                    decoder_start_token_id=0, pad_token_id=0, eos_token_id=1)


def time_generation(model, input_ids, new_tokens: int, repeats: int) -> list[float]:
    import torch

    timings = []
    with torch.inference_mode():
        model.generate(input_ids=input_ids, max_new_tokens=4, min_new_tokens=4, do_sample=False)  # échauffement
        for _ in range(repeats):
            start = time.perf_counter()
            model.generate(input_ids=input_ids, max_new_tokens=new_tokens, min_new_tokens=new_tokens,
                           do_sample=False, num_beams=1)
            timings.append((time.perf_counter() - start) * 1000)
    return timings


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--model", default="google/flan-t5-base")
    parser.add_argument("--random-weights", action="store_true")
    parser.add_argument("--input-tokens", type=int, default=400, help="taille du prompt (k=3 blocs ≈ 400 tokens)")
    parser.add_argument("--new-tokens", type=int, default=60)
    parser.add_argument("--repeats", type=int, default=5)
    parser.add_argument("--threads", type=int, default=0, help="threads torch (0 = valeur par défaut)")
    args = parser.parse_args()

    import torch
    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer, T5ForConditionalGeneration

    if args.threads:
        torch.set_num_threads(args.threads)
    torch.manual_seed(0)
    if args.random_weights:
        mode, tokenizer = "poids_aleatoires", None
        model = T5ForConditionalGeneration(flan_t5_base_config()).eval()
        if model.lm_head.weight.data_ptr() == model.shared.weight.data_ptr():
            # flan-t5 (T5 v1.1) n'a PAS de couche de sortie liée aux embeddings ; certaines versions de
            # transformers la lient quand même à la construction : on la délie (cf. BUG_REPORT.md).
            model.lm_head.weight = torch.nn.Parameter(model.shared.weight.detach().clone())
            model.config.tie_word_embeddings = False
    else:
        mode = args.model.split("/")[-1]
        tokenizer = AutoTokenizer.from_pretrained(args.model)
        model = AutoModelForSeq2SeqLM.from_pretrained(args.model).eval()

    quantized = torch.quantization.quantize_dynamic(copy.deepcopy(model), {torch.nn.Linear}, dtype=torch.qint8)
    input_ids = torch.randint(5, 32000, (1, args.input_tokens))

    rows = []
    for label, candidate in (("float32", model), ("int8 dynamique", quantized)):
        timings = time_generation(candidate, input_ids, args.new_tokens, args.repeats)
        params = sum(p.numel() for p in model.parameters())
        rows.append({"version": label, "parametres_millions": round(params / 1e6, 1),
                     "taille_mo": round(serialized_size_mb(candidate), 1),
                     "latence_moy_ms": round(statistics.mean(timings), 1),
                     "latence_min_ms": round(min(timings), 1), "latence_max_ms": round(max(timings), 1),
                     "tokens_entree": args.input_tokens, "tokens_generes": args.new_tokens,
                     "repetitions": args.repeats, "threads": torch.get_num_threads()})

    answers = []
    if tokenizer is not None:
        import tempfile

        from Module_3.rag.prompt import build_prompt, passages_from_hits
        from scripts.evaluate_rag import COURSES, build_index, load_questions  # noqa: F401

        questions = [q for q in load_questions(SERVICE_DIR / "data" / "rag_eval.csv") if q.kind == "in"][:5]
        with tempfile.TemporaryDirectory() as tmp:
            service, _ = build_index(Path(tmp), "hashing", 800)
            for q in questions:
                hits, _ = service.retrieve(1, q.text, 3)
                prompt = build_prompt(q.text, passages_from_hits(hits, 900), "v3")
                encoded = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=512)
                row = {"id": q.qid, "question": q.text}
                for label, candidate in (("float32", model), ("int8", quantized)):
                    with torch.inference_mode():
                        out = candidate.generate(**encoded, max_new_tokens=80, do_sample=False)
                    row[label] = tokenizer.decode(out[0], skip_special_tokens=True)
                answers.append(row)

    out_dir = SERVICE_DIR / "reports" / "benchmark"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / f"quantization_{mode}.csv").open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
    if answers:
        (out_dir / f"reponses_{mode}.json").write_text(json.dumps(answers, ensure_ascii=False, indent=2),
                                                        encoding="utf-8")

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    fig, axes = plt.subplots(1, 2, figsize=(8, 3.5))
    labels = [r["version"] for r in rows]
    axes[0].bar(labels, [r["taille_mo"] for r in rows], color=["#227cff", "#4ed7a3"])
    axes[0].set_title("Taille sérialisée (Mo)")
    axes[1].bar(labels, [r["latence_moy_ms"] for r in rows], color=["#227cff", "#4ed7a3"])
    axes[1].set_title(f"Génération de {args.new_tokens} tokens (ms)")
    suffix = " — poids aléatoires" if args.random_weights else ""
    fig.suptitle(f"flan-t5-base : quantization dynamique int8{suffix}")
    fig.tight_layout()
    fig.savefig(out_dir / f"quantization_{mode}.png", dpi=130)
    print(json.dumps(rows, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
