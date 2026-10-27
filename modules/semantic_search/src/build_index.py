"""Génère et sauvegarde les embeddings et l'index d'un corpus de notes."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Sequence

from src.corpus import load_notes
from src.module import (
    DEFAULT_CHUNK_SIZE,
    DEFAULT_MODEL_NAME,
    DEFAULT_OVERLAP,
    SemanticSearchEngine,
)

DEFAULT_NOTES = Path(__file__).resolve().parent.parent / "data" / "notes_exemple.json"
DEFAULT_OUTPUT = Path(__file__).resolve().parent.parent / "data" / "index"


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Crée les embeddings et l'index sémantique du corpus."
    )
    parser.add_argument("--notes", type=Path, default=DEFAULT_NOTES)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    parser.add_argument("--model", default=DEFAULT_MODEL_NAME)
    parser.add_argument("--chunk-size", type=int, default=DEFAULT_CHUNK_SIZE)
    parser.add_argument("--overlap", type=int, default=DEFAULT_OVERLAP)
    args = parser.parse_args(argv)

    try:
        notes = load_notes(args.notes)
        engine = SemanticSearchEngine(model_name=args.model)
        engine.index(
            notes,
            chunk_size=args.chunk_size,
            overlap=args.overlap,
        )
        target = engine.save_index(args.output)
    except (OSError, ValueError, RuntimeError) as exc:
        print(f"Création de l'index impossible : {exc}", file=sys.stderr)
        return 1

    print(f"Embeddings et index créés dans : {target}")
    print(f"  Passages : {engine.size}")
    print(f"  Modèle   : {engine.model_name}")
    print(f"  Backend  : {engine.backend}")
    print("  Fichiers : index.json, embeddings.npy, faiss.index (si FAISS)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
