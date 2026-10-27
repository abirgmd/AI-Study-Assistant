"""Découpage du texte en blocs (« chunks ») qui se chevauchent.

Principe du cours (séance 4) : un long document est découpé en petits blocs qui
se chevauchent légèrement, pour ne pas couper une idée en deux. On coupe de
préférence en fin de phrase ; une phrase trop longue (fréquent dans les diapositives)
est coupée entre deux mots.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.core.extraction import Page

_SENTENCE_END = re.compile(r"(?<=[.!?…;:])\s+|\n+")


@dataclass(frozen=True)
class Chunk:
    """Bloc de texte prêt à être vectorisé."""

    text: str
    rank: int
    page: int | None
    start: int


def split_sentences(text: str) -> list[str]:
    """Découpe un texte en phrases (ou en lignes, pour les diapositives).

    Args:
        text: Texte nettoyé.

    Returns:
        Phrases non vides, dans l'ordre.
    """
    return [s.strip() for s in _SENTENCE_END.split(text) if s and s.strip()]


def _split_long(sentence: str, size: int) -> list[str]:
    """Coupe une phrase plus longue que `size` entre deux mots."""
    words = sentence.split()
    pieces: list[str] = []
    current = ""
    for word in words:
        candidate = f"{current} {word}".strip()
        if len(candidate) > size and current:
            pieces.append(current)
            current = word
        else:
            current = candidate
    if current:
        pieces.append(current)
    return pieces


def chunk_text(text: str, size: int = 800, overlap: int = 150, page: int | None = None,
               first_rank: int = 0) -> list[Chunk]:
    """Découpe un texte en blocs d'environ `size` caractères avec chevauchement.

    Chaque bloc commence par les dernières phrases du bloc précédent, dans la
    limite de `overlap` caractères.

    Args:
        text: Texte à découper.
        size: Taille cible d'un bloc, en caractères.
        overlap: Taille maximale du chevauchement, en caractères.
        page: Numéro de page associé (None si inconnu).
        first_rank: Rang du premier bloc produit.

    Returns:
        Liste de blocs, éventuellement vide si le texte est vide.

    Raises:
        ValueError: Si les paramètres sont incohérents.
    """
    if size <= 0:
        raise ValueError("La taille des blocs doit être positive.")
    if not 0 <= overlap < size:
        raise ValueError("Le chevauchement doit être compris entre 0 et la taille des blocs.")

    units: list[str] = []
    for sentence in split_sentences(text):
        units.extend(_split_long(sentence, size) if len(sentence) > size else [sentence])

    chunks: list[Chunk] = []
    current: list[str] = []
    current_len = 0
    position = 0
    start = 0

    def flush() -> None:
        nonlocal start
        body = " ".join(current).strip()
        if body:
            chunks.append(Chunk(body, first_rank + len(chunks), page, start))

    for unit in units:
        added = len(unit) + (1 if current else 0)
        if current and current_len + added > size:
            flush()
            # Chevauchement : on reprend les dernières phrases du bloc précédent.
            kept: list[str] = []
            kept_len = 0
            for previous in reversed(current):
                if kept_len + len(previous) + 1 > overlap:
                    break
                kept.insert(0, previous)
                kept_len += len(previous) + 1
            current = kept
            current_len = max(kept_len - 1, 0)
            start = max(position - current_len, 0)
            added = len(unit) + (1 if current else 0)
        if not current:
            start = position
        current.append(unit)
        current_len += added
        position += len(unit) + 1
    flush()
    return chunks


def chunk_pages(pages: list[Page], size: int = 800, overlap: int = 150) -> list[Chunk]:
    """Découpe un document page par page (un bloc ne mélange jamais deux pages).

    Args:
        pages: Pages extraites.
        size: Taille cible d'un bloc.
        overlap: Chevauchement maximal.

    Returns:
        Blocs numérotés de 0 à n-1 sur tout le document.
    """
    chunks: list[Chunk] = []
    for page in pages:
        chunks.extend(chunk_text(page.text, size, overlap, page.number, first_rank=len(chunks)))
    return chunks
