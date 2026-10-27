"""Contrôle d'accès du service IA : seul PHP, qui connaît le jeton interne, peut l'appeler."""

from __future__ import annotations

import hmac
import re
from typing import Annotated

from fastapi import Depends, Header, HTTPException, status

from app.config import Settings, get_settings
from app.errors import InvalidInputError

STORED_NAME_PATTERN = re.compile(r"^[a-f0-9]{48}\.(pdf|txt|docx)$")


def verify_internal_token(
    settings: Annotated[Settings, Depends(get_settings)],
    x_internal_token: Annotated[str | None, Header()] = None,
) -> None:
    """Refuse toute requête dont l'en-tête X-Internal-Token est absent ou faux.

    La comparaison est faite à temps constant (hmac.compare_digest) pour ne rien
    révéler du jeton attendu par la durée de la réponse.

    Raises:
        HTTPException: 401 si le jeton est absent ou invalide.
    """
    expected = settings.internal_token.get_secret_value()
    if not x_internal_token or not hmac.compare_digest(
        x_internal_token.encode("utf-8"), expected.encode("utf-8")
    ):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Accès refusé : jeton interne absent ou invalide.",
        )


def validate_stored_name(stored_name: str) -> str:
    """Vérifie qu'un nom de fichier correspond exactement au format produit par PHP.

    PHP nomme chaque fichier importé avec 48 caractères hexadécimaux aléatoires
    suivis de l'extension. Tout autre nom (chemin, « .. », barre oblique) est refusé
    avant toute lecture sur le disque.

    Args:
        stored_name: Nom reçu dans la requête.

    Returns:
        Le nom validé.

    Raises:
        InvalidInputError: Si le nom ne respecte pas le format attendu.
    """
    if not STORED_NAME_PATTERN.fullmatch(stored_name):
        raise InvalidInputError("Nom de fichier refusé.")
    return stored_name
