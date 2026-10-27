"""Exceptions métier du service IA.

Chaque exception porte un code HTTP et un message en français destiné à PHP.
Les messages ne contiennent jamais de chemin de fichier ni de détail interne.
"""

from __future__ import annotations


class ServiceError(Exception):
    """Erreur métier de base."""

    status_code: int = 400
    default_message: str = "Requête invalide."

    def __init__(self, message: str | None = None) -> None:
        self.message = message or self.default_message
        super().__init__(self.message)


class InvalidInputError(ServiceError):
    """Entrée refusée (nom de fichier, question, identifiant...)."""

    status_code = 422


class DocumentNotFoundError(ServiceError):
    """Le document demandé n'existe pas dans le dossier de stockage."""

    status_code = 404
    default_message = "Document introuvable."


class ExtractionError(ServiceError):
    """Le texte du document ne peut pas être extrait."""

    status_code = 422
    default_message = "Impossible d'extraire le texte de ce document."


class IndexMismatchError(ServiceError):
    """L'index existant a été construit avec un autre modèle d'embeddings."""

    status_code = 409
    default_message = (
        "L'index de cet étudiant a été créé avec un autre modèle d'embeddings. "
        "Relancez l'indexation de ses cours."
    )


class GenerationError(ServiceError):
    """Le modèle de génération n'a pas pu répondre."""

    status_code = 503
    default_message = "Le modèle de génération est indisponible."


class ModelNotReadyError(ServiceError):
    """Le modèle demandé n'a pas encore été entraîné ou chargé."""

    status_code = 503
    default_message = "Le modèle n'est pas disponible. Lancez l'entraînement."
