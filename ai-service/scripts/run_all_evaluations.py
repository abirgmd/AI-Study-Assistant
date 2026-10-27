"""Relance toutes les mesures du rapport, avec les modèles du cours, sur VOTRE machine.

Dans l'environnement de préparation du projet, Hugging Face n'était pas accessible : les
mesures de MiniLM (embeddings) et de flan-t5 (génération, vraie quantization) n'ont donc pas
pu être faites. Ce script les produit (connexion Internet nécessaire au premier lancement,
environ 1,5 Go de modèles téléchargés) :

    python scripts/run_all_evaluations.py            # tout
    python scripts/run_all_evaluations.py --quick    # sans flan-t5-base (plus rapide)

Les résultats sont écrits dans reports/ ; reportez-les ensuite dans
docs/DOCUMENTATION_INDIVIDUELLE.md (les cases « à mesurer » du rapport).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path

SERVICE_DIR = Path(__file__).resolve().parent.parent


def run(*args: str) -> None:
    print("\n$ python " + " ".join(args), flush=True)
    result = subprocess.run([sys.executable, *args], cwd=SERVICE_DIR, check=False)
    if result.returncode != 0:
        print(f"⚠ échec (code {result.returncode}) : la suite continue.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--quick", action="store_true")
    parser.add_argument("--api", action="store_true", help="inclure le LLM par API (clé dans .env)")
    args = parser.parse_args()

    generators = ["extractive", "flan-t5-small"] + ([] if args.quick else ["flan-t5-base", "flan-t5-base-int8"])
    if args.api:
        generators.append("api")
    run("scripts/evaluate_rag.py", "--embedding", "hashing")
    run("scripts/evaluate_rag.py", "--embedding", "sentence-transformers", "--generators", *generators)
    if not args.quick:
        run("scripts/benchmark.py", "--model", "google/flan-t5-base")
    run("scripts/build_dataset.py")
    run("scripts/train_classifier.py", "--embedding", "sentence-transformers")
    run("scripts/evaluate_classifier.py")


if __name__ == "__main__":
    main()
