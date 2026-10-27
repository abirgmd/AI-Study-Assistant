"""Construction du prompt de génération augmentée (RAG).

Les prompts sont versionnés dans ai-service/prompts/ :

- ``rag_v1.txt`` : prompt naïf (contexte + question, aucune consigne) ;
- ``rag_v2.txt`` : prompt structuré (rôle, tâche, format, citations) ;
- ``rag_v3.txt`` : v2 + isolation du contexte entre balises, interdiction d'exécuter
  les instructions des documents et consigne d'abstention exacte.

La v3 est utilisée en production ; v1 et v2 servent à mesurer l'effet du prompt
tuning dans scripts/evaluate_rag.py.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from Module_3.rag.store import SearchHit

PROMPTS_DIR = Path(__file__).resolve().parents[1] / "prompts"
ABSTENTION_MESSAGE = "Je ne trouve pas cette information dans vos cours."
_CONTEXT_TAG = re.compile(r"</?\s*contexte\s*>", re.IGNORECASE)


@dataclass(frozen=True)
class Passage:
    """Extrait numéroté inséré dans le prompt."""

    number: int
    title: str
    page: int | None
    text: str


@lru_cache(maxsize=8)
def load_template(version: str) -> str:
    """Lit un gabarit de prompt versionné.

    Args:
        version: "v1", "v2", "v3" ou "no_context".

    Returns:
        Le gabarit, avec les champs {context} et {question}.
    """
    allowed = {"v1", "v2", "v3", "no_context"}
    if version not in allowed:
        raise ValueError(f"Version de prompt inconnue : {version}")
    return (Path(PROMPTS_DIR) / f"rag_{version}.txt").read_text(encoding="utf-8")


def neutralize(text: str) -> str:
    """Empêche un document de fermer ou d'ouvrir la zone <contexte> du prompt.

    Un document piégé contenant « </contexte> Nouvelle consigne : ... » pourrait
    sinon faire passer du texte pour une instruction (injection de prompt).
    """
    return _CONTEXT_TAG.sub("[balise retirée]", text)


def passages_from_hits(hits: list[SearchHit], max_chars: int) -> list[Passage]:
    """Transforme les résultats de recherche en extraits numérotés.

    Args:
        hits: Résultats triés du plus pertinent au moins pertinent.
        max_chars: Longueur maximale de chaque extrait (maîtrise des tokens).

    Returns:
        Extraits numérotés à partir de 1.
    """
    return [
        Passage(i, hit.chunk.title, hit.chunk.page, hit.chunk.text[:max_chars])
        for i, hit in enumerate(hits, start=1)
    ]


def format_context(passages: list[Passage]) -> str:
    """Met en forme les extraits : « [Source n] (Titre, p. X) texte »."""
    lines = []
    for p in passages:
        where = f"{neutralize(p.title)}, p. {p.page}" if p.page else neutralize(p.title)
        lines.append(f"[Source {p.number}] ({where}) {neutralize(p.text)}")
    return "\n".join(lines)


def build_prompt(question: str, passages: list[Passage], version: str = "v3") -> str:
    """Assemble le prompt final envoyé au modèle de génération.

    Args:
        question: Question de l'étudiant (déjà validée).
        passages: Extraits retenus.
        version: Version du gabarit.

    Returns:
        Le prompt complet.
    """
    template = load_template(version)
    return template.format(context=format_context(passages), question=neutralize(question.strip()))
