"""Service RAG : indexation des cours et réponse aux questions.

Pipeline (séance 4, diapos 27 à 30) :
    extraction → découpage → vectorisation → index FAISS → recherche top-k
    → seuil d'abstention → prompt structuré → génération → réponse sourcée
"""

from __future__ import annotations

import logging
import time
from dataclasses import asdict, dataclass, field, replace

from app.config import Settings
from app.core.chunking import chunk_pages
from app.core.embeddings import Embedder
from app.core.extraction import extract_pages
from app.errors import DocumentNotFoundError, GenerationError, InvalidInputError
from app.security import validate_stored_name
from Module_3.rag.cache import LRUCache, cache_key
from Module_3.rag.generators import ExtractiveGenerator, Generator
from Module_3.rag.prompt import ABSTENTION_MESSAGE, build_prompt, passages_from_hits
from Module_3.rag.store import IndexRepository, SearchHit

logger = logging.getLogger(__name__)


@dataclass
class Source:
    """Source citée dans la réponse."""

    number: int
    course_id: int
    title: str
    page: int | None
    excerpt: str
    score: float


@dataclass
class Answer:
    """Réponse complète renvoyée à PHP."""

    answer: str
    sources: list[Source] = field(default_factory=list)
    backend: str = ""
    latency_ms: int = 0
    cache_hit: bool = False
    abstained: bool = False
    reason: str = ""
    prompt_tokens: int = 0
    completion_tokens: int = 0

    def to_dict(self) -> dict:
        """Sérialisation JSON."""
        return asdict(self)


@dataclass(frozen=True)
class IndexReport:
    """Résultat d'une indexation."""

    course_id: int
    chunks: int
    pages: int
    characters: int


class RagService:
    """Orchestre l'indexation et la génération augmentée pour tous les étudiants."""

    def __init__(self, settings: Settings, embedder: Embedder, repository: IndexRepository,
                 generator: Generator, cache: LRUCache | None = None,
                 fallback: Generator | None = None) -> None:
        self.settings = settings
        self.embedder = embedder
        self.repository = repository
        self.generator = generator
        self.fallback = fallback or ExtractiveGenerator()
        self.cache = cache or LRUCache(settings.cache_size)

    # --- indexation --------------------------------------------------------
    def index_course(self, student_id: int, course_id: int, stored_name: str, title: str) -> IndexReport:
        """Extrait, découpe, vectorise et indexe un cours (remplace l'ancienne version).

        Raises:
            InvalidInputError: Nom de fichier ou titre refusé.
            DocumentNotFoundError: Le fichier n'existe pas.
            ExtractionError: Le texte n'a pas pu être extrait.
        """
        path = self.settings.courses_dir / validate_stored_name(stored_name)
        if not path.is_file():
            raise DocumentNotFoundError()
        title = title.strip()[:255] or "Cours sans titre"
        pages = extract_pages(path, self.settings.max_document_chars)
        chunks = chunk_pages(pages, self.settings.chunk_size, self.settings.chunk_overlap)
        vectors = self.embedder.encode([c.text for c in chunks])
        with self.repository.lock(student_id):
            index = self.repository.load(student_id)
            count = index.add_course(course_id, title, [(c.text, c.page, c.rank) for c in chunks], vectors)
            index.save()
        logger.info("Cours %d indexé pour l'étudiant %d : %d blocs", course_id, student_id, count)
        return IndexReport(course_id, count, len(pages), sum(len(p.text) for p in pages))

    def remove_course(self, student_id: int, course_id: int) -> int:
        """Retire un cours de l'index de l'étudiant. Retourne le nombre de blocs retirés."""
        with self.repository.lock(student_id):
            index = self.repository.load(student_id)
            removed = index.remove_course(course_id)
            if removed:
                index.save()
        return removed

    # --- questions ---------------------------------------------------------
    def ask_general(self, question: str) -> Answer:
        """Répond en connaissance générale, séparément de l'index des cours.

        Ce mode est volontairement distinct du RAG : aucune source de cours
        n'est affichée et Ollama doit être explicitement sélectionné.
        """
        started = time.perf_counter()
        question = " ".join(question.split())
        if not question or len(question) > self.settings.max_question_chars:
            raise InvalidInputError("Question générale invalide.")
        if not self.generator.name.startswith("ollama:"):
            return Answer("Le mode connaissance générale nécessite Ollama.", backend=self.generator.name,
                          abstained=True, reason="ollama_requis",
                          latency_ms=int((time.perf_counter() - started) * 1000))
        prompt = (
            "Tu es un assistant généraliste. Réponds en français à la question suivante. "
            "Cette réponse ne provient pas des cours de l'étudiant : ne cite aucune source de cours. "
            "Si le fait dépend de l'actualité ou est incertain, indique qu'il doit être vérifié.\n\n"
            f"Question : {question}\nRéponse :"
        )
        try:
            generation = self.generator.generate(prompt, question, [])
        except GenerationError:
            return Answer("Le mode connaissance générale est indisponible.", backend=self.generator.name,
                          abstained=True, reason="service_indisponible",
                          latency_ms=int((time.perf_counter() - started) * 1000))
        return Answer(generation.text.strip() or "Réponse indisponible.", backend=self.generator.name,
                      latency_ms=int((time.perf_counter() - started) * 1000),
                      reason="connaissance_generale", prompt_tokens=generation.prompt_tokens,
                      completion_tokens=generation.completion_tokens)

    def retrieve(self, student_id: int, question: str, k: int, course_id: int | None = None
                 ) -> tuple[list[SearchHit], int]:
        """Recherche les k blocs les plus proches. Retourne aussi la version de l'index."""
        index = self.repository.load(student_id)
        if index.index.ntotal == 0:
            return [], index.version
        vector = self.embedder.encode([question])[0]
        return index.search(vector, k, course_id), index.version

    def ask(self, student_id: int, question: str, course_id: int | None = None, k: int | None = None) -> Answer:
        """Répond à une question à partir des cours de l'étudiant uniquement.

        Args:
            student_id: Étudiant (fourni par la session PHP).
            question: Question en langage naturel.
            course_id: Limite la recherche à un cours, ou None pour tous.
            k: Nombre d'extraits à utiliser (défaut : configuration).

        Returns:
            La réponse, ses sources et les mesures (latence, tokens, cache).
        """
        started = time.perf_counter()
        question = " ".join(question.split())
        if not question:
            raise InvalidInputError("La question est vide.")
        if len(question) > self.settings.max_question_chars:
            raise InvalidInputError(f"La question dépasse {self.settings.max_question_chars} caractères.")
        k = k or self.settings.rag_top_k

        index_version = self.repository.load(student_id).version
        key = cache_key(student_id, index_version, question, course_id, k, self.generator.name,
                        self.settings.rag_prompt_version)
        cached = self.cache.get(key)
        if cached is not None:
            return replace(cached, cache_hit=True, latency_ms=int((time.perf_counter() - started) * 1000))

        hits, _ = self.retrieve(student_id, question, k, course_id)
        if not hits:
            answer = Answer(ABSTENTION_MESSAGE, backend="aucun", abstained=True, reason="aucun_document")
        elif hits[0].score < self.settings.rag_min_score:
            # Rien d'assez proche : on s'abstient SANS appeler le LLM (zéro token consommé).
            answer = Answer(ABSTENTION_MESSAGE, backend="aucun", abstained=True, reason="score_insuffisant",
                            sources=self._sources(hits[:1]))
        else:
            answer = self._generate(question, hits)

        answer.latency_ms = int((time.perf_counter() - started) * 1000)
        self.cache.set(key, answer)
        return answer

    def _generate(self, question: str, hits: list[SearchHit]) -> Answer:
        passages = passages_from_hits(hits, self.settings.rag_max_passage_chars)
        prompt = build_prompt(question, passages, self.settings.rag_prompt_version)
        try:
            generation = self.generator.generate(prompt, question, passages)
            backend = self.generator.name
        except GenerationError as exc:
            logger.warning("Génération principale indisponible (%s) : solution de secours extractive", exc)
            generation = self.fallback.generate(prompt, question, passages)
            backend = f"{self.fallback.name} (secours)"
        text = generation.text.strip() or ABSTENTION_MESSAGE
        abstained = text.startswith(ABSTENTION_MESSAGE)
        return Answer(text, self._sources(hits), backend, abstained=abstained,
                      reason="modele" if abstained else "", prompt_tokens=generation.prompt_tokens,
                      completion_tokens=generation.completion_tokens)

    @staticmethod
    def _sources(hits: list[SearchHit]) -> list[Source]:
        return [
            Source(i, h.chunk.course_id, h.chunk.title, h.chunk.page,
                   h.chunk.text[:300] + ("…" if len(h.chunk.text) > 300 else ""), round(h.score, 3))
            for i, h in enumerate(hits, start=1)
        ]
