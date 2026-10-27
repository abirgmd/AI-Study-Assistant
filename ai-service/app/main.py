"""Point d'entrée du service IA (FastAPI).

Lancement :  uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
Le service n'est destiné qu'à l'application PHP : il écoute en local et exige le
jeton interne sur chaque route.
"""

from __future__ import annotations

import logging
import threading
from contextlib import asynccontextmanager
from typing import Annotated, Literal

from fastapi import Depends, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.config import Settings, get_settings
from app.core.embeddings import Embedder, build_embedder
from app.core.extraction import extract_text
from app.errors import DocumentNotFoundError, InvalidInputError, ServiceError
from app.modules.classification.classifier import UNCLASSIFIED, CourseClassifier, FeedbackStore
from app.security import validate_stored_name, verify_internal_token
from Module_3.rag.cache import LRUCache
from Module_3.rag.generators import build_generator
from Module_3.rag.service import RagService
from Module_3.rag.store import IndexRepository

logger = logging.getLogger("ai_service")


class Container:
    """Instances partagées du service, créées à la première utilisation (modèles lourds)."""

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self._lock = threading.Lock()
        self._embedder: Embedder | None = None
        self._rag: RagService | None = None
        self._classifier: CourseClassifier | None = None
        self.feedback = FeedbackStore(settings.feedback_file)

    @property
    def embedder(self) -> Embedder:
        """Modèle d'embeddings partagé (modules 2, 3 et 5)."""
        with self._lock:
            if self._embedder is None:
                self._embedder = build_embedder(self.settings.embedding_backend, self.settings.embedding_model)
            return self._embedder

    @property
    def rag(self) -> RagService:
        """Service RAG (module 3)."""
        embedder = self.embedder
        with self._lock:
            if self._rag is None:
                dim = embedder.encode(["dimension"]).shape[1]
                repository = IndexRepository(self.settings.index_dir, embedder.name, dim, self.settings.rag_metric)
                self._rag = RagService(self.settings, embedder, repository, build_generator(self.settings),
                                       LRUCache(self.settings.cache_size))
            return self._rag

    @property
    def classifier(self) -> CourseClassifier:
        """Modèle de classification (module 5)."""
        with self._lock:
            if self._classifier is None:
                self._classifier = CourseClassifier.load(self.settings.classifier_path,
                                                         self.settings.classifier_min_confidence,
                                                         self.settings.classifier_max_chars)
            return self._classifier

    def classifier_ready(self) -> bool:
        """Indique si un modèle de classification est disponible."""
        return self._classifier is not None or self.settings.classifier_path.is_file()


def get_container(request: Request) -> Container:
    """Dépendance FastAPI : instances partagées attachées à l'application."""
    return request.app.state.container


# Défini au niveau du module : avec « from __future__ import annotations », FastAPI
# résout les annotations dans les variables globales du module (voir BUG_REPORT.md, B1).
ContainerDep = Annotated[Container, Depends(get_container)]


# --- schémas d'entrée -------------------------------------------------------
class IndexRequest(BaseModel):
    student_id: int = Field(..., gt=0)
    course_id: int = Field(..., gt=0)
    stored_name: str = Field(..., max_length=60)
    title: str = Field("", max_length=255)


class AskRequest(BaseModel):
    student_id: int = Field(..., gt=0)
    question: str = Field(..., min_length=1, max_length=2000)
    course_id: int | None = Field(None, gt=0)
    k: int | None = Field(None, ge=1, le=10)
    scope: Literal["course", "general"] = "course"


class ClassifyRequest(BaseModel):
    text: str | None = Field(None, max_length=500_000)
    stored_name: str | None = Field(None, max_length=60)


class FeedbackRequest(BaseModel):
    stored_name: str = Field(..., max_length=60)
    predicted: str = Field(..., max_length=80)
    corrected: str = Field(..., max_length=80)


def create_app(settings: Settings | None = None, container: Container | None = None) -> FastAPI:
    """Crée l'application FastAPI.

    Args:
        settings: Configuration (par défaut, lue depuis l'environnement).
        container: Instances partagées (les tests peuvent en fournir une).
    """
    settings = settings or get_settings()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s : %(message)s")

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        app.state.container = container or Container(settings)
        logger.info("Service IA prêt (embeddings=%s, génération=%s)", settings.embedding_backend,
                    settings.llm_backend)
        yield

    app = FastAPI(title="AI Study Assistant — service IA", version="1.0.0", lifespan=lifespan,
                  dependencies=[Depends(verify_internal_token)])
    app.dependency_overrides[get_settings] = lambda: settings

    @app.exception_handler(ServiceError)
    async def service_error_handler(_: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(status_code=exc.status_code, content={"detail": exc.message})

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(_: Request, exc: RequestValidationError) -> JSONResponse:
        fields = sorted({".".join(str(p) for p in e.get("loc", [])[1:]) for e in exc.errors()})
        return JSONResponse(status_code=422, content={"detail": "Requête invalide.", "fields": fields})

    @app.exception_handler(Exception)
    async def unexpected_error_handler(_: Request, exc: Exception) -> JSONResponse:
        logger.exception("Erreur inattendue : %s", type(exc).__name__)
        return JSONResponse(status_code=500, content={"detail": "Erreur interne du service IA."})

    @app.get("/health")
    def health(c: ContainerDep) -> dict:
        """État du service et configuration active."""
        return {"status": "ok", "embedding_backend": settings.embedding_backend,
                "llm_backend": settings.llm_backend, "classifier_ready": c.classifier_ready()}

    # --- module 3 : RAG ------------------------------------------------------
    @app.post("/rag/index")
    def rag_index(body: IndexRequest, c: ContainerDep) -> dict:
        """Indexe (ou réindexe) un cours de l'étudiant."""
        report = c.rag.index_course(body.student_id, body.course_id, body.stored_name, body.title)
        return {"course_id": report.course_id, "chunks": report.chunks, "pages": report.pages,
                "characters": report.characters}

    @app.delete("/rag/index/{student_id}/{course_id}")
    def rag_unindex(student_id: int, course_id: int, c: ContainerDep) -> dict:
        """Retire un cours de l'index de l'étudiant."""
        if student_id < 1 or course_id < 1:
            raise InvalidInputError("Identifiant invalide.")
        return {"removed_chunks": c.rag.remove_course(student_id, course_id)}

    @app.post("/rag/ask")
    def rag_ask(body: AskRequest, c: ContainerDep) -> dict:
        """Répond à une question à partir des cours de l'étudiant."""
        if body.scope == "general":
            return c.rag.ask_general(body.question).to_dict()
        return c.rag.ask(body.student_id, body.question, body.course_id, body.k).to_dict()

    # --- module 5 : classification --------------------------------------------
    def _document_text(stored_name: str) -> str:
        path = settings.courses_dir / validate_stored_name(stored_name)
        if not path.is_file():
            raise DocumentNotFoundError()
        return extract_text(path, settings.classifier_max_chars)

    @app.get("/classify/categories")
    def classify_categories() -> dict:
        """Catégories reconnues par le modèle."""
        return {"categories": settings.categories, "unclassified": UNCLASSIFIED}

    @app.post("/classify")
    def classify(body: ClassifyRequest, c: ContainerDep) -> dict:
        """Prédit la catégorie d'un cours (texte fourni ou document importé)."""
        if body.stored_name:
            text = _document_text(body.stored_name)
        elif body.text:
            text = body.text
        else:
            raise InvalidInputError("Fournissez un texte ou un document.")
        return c.classifier.predict(text).to_dict()

    @app.post("/classify/feedback")
    def classify_feedback(body: FeedbackRequest, c: ContainerDep) -> dict:
        """Enregistre la correction d'un étudiant pour le prochain réentraînement."""
        if body.corrected not in settings.categories:
            raise InvalidInputError("Catégorie inconnue.")
        c.feedback.add(_document_text(body.stored_name), body.corrected, body.predicted)
        return {"saved": True}

    return app
