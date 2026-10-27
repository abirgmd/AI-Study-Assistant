"""Configuration du service IA, lue depuis les variables d'environnement et le fichier .env."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

SERVICE_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = SERVICE_DIR.parent
CATEGORIES_FILE = SERVICE_DIR / "app" / "modules" / "classification" / "categories.json"


def load_categories(path: Path = CATEGORIES_FILE) -> list[str]:
    """Lit la liste des catégories partagée avec l'application PHP.

    Args:
        path: Chemin du fichier JSON des catégories.

    Returns:
        La liste ordonnée des catégories.
    """
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data["categories"])


class Settings(BaseSettings):
    """Paramètres du service. Chaque champ peut être surchargé par une variable AI_<NOM>."""

    model_config = SettingsConfigDict(
        env_prefix="AI_",
        env_file=str(SERVICE_DIR / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    internal_token: SecretStr = Field(..., description="Jeton partagé avec PHP (32 caractères minimum).")
    storage_dir: Path = PROJECT_DIR / "storage"

    # Socle partagé (extraction, découpage, embeddings)
    embedding_backend: Literal["sentence-transformers", "hashing"] = "sentence-transformers"
    embedding_model: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    chunk_size: int = Field(800, ge=200, le=4000)
    chunk_overlap: int = Field(150, ge=0, le=1000)
    max_document_chars: int = Field(400_000, ge=10_000)

    # Module 3 : RAG
    rag_top_k: int = Field(3, ge=1, le=10)
    # Seuil mesuré avec scripts/evaluate_rag.py (embeddings hashing) ; à recalibrer pour MiniLM.
    rag_min_score: float = Field(0.15, ge=-1.0, le=1.0)
    rag_metric: Literal["ip", "l2"] = "ip"
    rag_prompt_version: Literal["v1", "v2", "v3"] = "v3"
    rag_max_passage_chars: int = Field(900, ge=200, le=4000)
    max_question_chars: int = Field(500, ge=10, le=2000)
    cache_size: int = Field(256, ge=0, le=10_000)

    llm_backend: Literal["extractive", "flan-t5", "ollama", "api"] = "extractive"
    local_model: str = "google/flan-t5-base"
    local_quantize: bool = False
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen2.5:3b-instruct-q4_K_M"
    ollama_timeout: float = Field(120.0, ge=1.0, le=600.0)
    max_new_tokens: int = Field(200, ge=16, le=1024)
    temperature: float = Field(0.2, ge=0.0, le=1.0)
    api_provider: Literal["anthropic", "openai"] = "anthropic"
    api_model: str = "claude-haiku-5-5"
    api_key: SecretStr | None = None
    api_timeout: float = Field(30.0, ge=1.0, le=120.0)
    api_max_retries: int = Field(1, ge=0, le=3)

    # Module 5 : classification
    classifier_path: Path = SERVICE_DIR / "models" / "classifier.joblib"
    # None : seuil choisi à l'entraînement (models/classifier_meta.json) ; une valeur le force.
    classifier_min_confidence: float | None = Field(None, ge=0.0, le=1.0)
    classifier_max_chars: int = Field(20_000, ge=500)
    feedback_file: Path = SERVICE_DIR / "data" / "classification" / "feedback.csv"

    @field_validator("internal_token")
    @classmethod
    def _token_long_enough(cls, value: SecretStr) -> SecretStr:
        if len(value.get_secret_value()) < 32:
            raise ValueError("AI_INTERNAL_TOKEN doit contenir au moins 32 caractères.")
        return value

    @model_validator(mode="after")
    def _overlap_smaller_than_chunk(self) -> Settings:
        if self.chunk_overlap >= self.chunk_size:
            raise ValueError("AI_CHUNK_OVERLAP doit être strictement inférieur à AI_CHUNK_SIZE.")
        return self

    @property
    def courses_dir(self) -> Path:
        """Dossier des documents importés par l'application PHP."""
        return self.storage_dir / "courses"

    @property
    def index_dir(self) -> Path:
        """Dossier racine des index FAISS (un sous-dossier par étudiant)."""
        return self.storage_dir / "indexes"

    @property
    def categories(self) -> list[str]:
        """Catégories de cours, partagées avec PHP."""
        return load_categories()


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Retourne la configuration (chargée une seule fois)."""
    return Settings()  # type: ignore[call-arg]
