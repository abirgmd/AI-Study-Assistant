"""Chargement commun d'un corpus de notes JSON."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping


def load_notes(path: str | Path) -> list[Mapping[str, Any]]:
    """Charge une liste de notes depuis un fichier JSON.

    Formats acceptés : une liste directe ou un objet avec la clé ``notes``.
    """
    source = Path(path)
    if not source.is_file():
        raise FileNotFoundError(f"Fichier de notes introuvable : {source}")

    try:
        payload = json.loads(source.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ValueError(f"JSON invalide dans {source}.") from exc

    notes = payload.get("notes") if isinstance(payload, dict) else payload
    if not isinstance(notes, list) or not notes:
        raise ValueError("Le fichier de notes doit contenir une liste non vide.")
    return notes
