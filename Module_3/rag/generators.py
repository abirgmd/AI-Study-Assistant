"""Modèles de génération de la réponse (pattern Strategy).

Trois stratégies interchangeables, choisies par AI_LLM_BACKEND :

- ``ExtractiveGenerator`` (``extractive``) : aucune IA générative ; sélectionne
  les phrases des extraits les plus proches de la question. Gratuit, instantané,
  ne peut pas inventer. Sert aussi de solution de secours.
- ``LocalFlanT5Generator`` (``flan-t5``) : modèle du TP ``google/flan-t5-base``,
  exécuté en local, décodage glouton (déterministe), quantization int8 optionnelle.
- ``ApiLLMGenerator`` (``api``) : grand modèle par API (Anthropic ou OpenAI),
  avec délai maximal, nouvelle tentative limitée et comptage des tokens.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Protocol

import httpx

from app.config import Settings
from app.core.chunking import split_sentences
from app.core.text import content_words, stem
from app.errors import GenerationError
from Module_3.rag.prompt import ABSTENTION_MESSAGE, Passage

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class Generation:
    """Texte produit et consommation de tokens (0 si non applicable)."""

    text: str
    prompt_tokens: int = 0
    completion_tokens: int = 0


class Generator(Protocol):
    """Interface commune des stratégies de génération."""

    name: str

    def generate(self, prompt: str, question: str, passages: list[Passage]) -> Generation:
        """Produit la réponse à partir du prompt (ou directement des extraits)."""
        ...


class ExtractiveGenerator:
    """Réponse construite uniquement avec des phrases recopiées des extraits."""

    name = "extractif"

    def __init__(self, max_sentences: int = 3, max_chars: int = 700, min_overlap: int = 1) -> None:
        self.max_sentences = max_sentences
        self.max_chars = max_chars
        self.min_overlap = min_overlap

    def generate(self, prompt: str, question: str, passages: list[Passage]) -> Generation:
        """Sélectionne les phrases qui partagent le plus de mots avec la question."""
        terms = {stem(w) for w in content_words(question)}
        # Une phrase est retenue si elle partage au moins `min_overlap` mots avec la question.
        # Mesuré (reports/rag/iterations) : 2 mots évitent toute réponse hors cours mais font
        # s'abstenir à tort 28 % des questions du cours, contre 4 % avec 1 mot. On garde 1.
        required = min(self.min_overlap, len(terms)) if terms else 1
        candidates: list[tuple[int, int, int, str]] = []
        for p in passages:
            for position, sentence in enumerate(split_sentences(p.text)):
                if len(sentence) < 25:
                    continue
                overlap = len(terms & {stem(w) for w in content_words(sentence)})
                if overlap >= required:
                    candidates.append((overlap, p.number, position, sentence))
        if not candidates:
            return Generation(ABSTENTION_MESSAGE)
        # Plus fort recouvrement d'abord ; à égalité, meilleur extrait puis première phrase.
        chosen = sorted(candidates, key=lambda c: (-c[0], c[1], c[2]))[: self.max_sentences]
        chosen.sort(key=lambda c: (c[1], c[2]))
        parts: list[str] = []
        length = 0
        for _, number, _, sentence in chosen:
            piece = f"{sentence.rstrip()} [Source {number}]"
            if length + len(piece) > self.max_chars and parts:
                break
            parts.append(piece)
            length += len(piece) + 1
        return Generation("D'après vos cours : " + " ".join(parts))


class LocalFlanT5Generator:
    """google/flan-t5 exécuté localement avec transformers (chargé une seule fois)."""

    def __init__(self, model_name: str, max_new_tokens: int, quantize: bool = False,
                 max_input_tokens: int = 512) -> None:
        self.model_name = model_name
        self.max_new_tokens = max_new_tokens
        self.quantize = quantize
        self.max_input_tokens = max_input_tokens
        self.name = f"local:{model_name.split('/')[-1]}{'-int8' if quantize else ''}"
        self._tokenizer = None
        self._model = None
        self._lock = threading.Lock()

    def _load(self):
        with self._lock:
            if self._model is None:
                try:
                    import torch
                    from transformers import AutoModelForSeq2SeqLM, AutoTokenizer
                except ImportError as exc:
                    raise GenerationError("transformers et torch ne sont pas installés.") from exc
                logger.info("Chargement de %s (quantization=%s)", self.model_name, self.quantize)
                try:
                    tokenizer = AutoTokenizer.from_pretrained(self.model_name)
                    model = AutoModelForSeq2SeqLM.from_pretrained(self.model_name).to("cpu").eval()
                except (OSError, ValueError) as exc:  # modèle introuvable, pas de réseau, cache corrompu
                    logger.warning("Chargement de %s impossible : %s", self.model_name, type(exc).__name__)
                    raise GenerationError("Le modèle local n'a pas pu être chargé.") from exc
                if self.quantize:
                    # Quantization dynamique int8 des couches Linear : CPU uniquement (cf. TP).
                    model = torch.quantization.quantize_dynamic(model, {torch.nn.Linear}, dtype=torch.qint8)
                self._tokenizer, self._model = tokenizer, model
        return self._tokenizer, self._model

    def generate(self, prompt: str, question: str, passages: list[Passage]) -> Generation:
        """Génère la réponse avec un décodage glouton (reproductible)."""
        tokenizer, model = self._load()  # lève GenerationError si torch/transformers manquent
        import torch

        encoded = tokenizer(prompt, return_tensors="pt", truncation=True, max_length=self.max_input_tokens)
        prompt_tokens = int(encoded["input_ids"].shape[1])
        if prompt_tokens >= self.max_input_tokens:
            logger.warning("Prompt tronqué à %d tokens : réduisez k ou la taille des blocs.", self.max_input_tokens)
        with torch.inference_mode():
            output = model.generate(**encoded, max_new_tokens=self.max_new_tokens, do_sample=False, num_beams=1)
        text = tokenizer.decode(output[0], skip_special_tokens=True).strip()
        return Generation(text, prompt_tokens, int(output.shape[1]))


class OllamaGenerator:
    """Génération locale via l'API HTTP d'Ollama.

    Ollama gère le chargement et la quantification du modèle. Le service RAG
    ne transmet que le prompt contenant les passages retrouvés.
    """

    def __init__(self, base_url: str, model: str, max_new_tokens: int, temperature: float,
                 timeout: float, max_retries: int = 1, client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.name = f"ollama:{model}"
        self._client = client or httpx.Client(timeout=timeout)

    def generate(self, prompt: str, question: str, passages: list[Passage]) -> Generation:
        last_error = "erreur inconnue"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._client.post(
                    f"{self.base_url}/api/generate",
                    json={"model": self.model, "prompt": prompt, "stream": False,
                          "options": {"temperature": self.temperature, "num_predict": self.max_new_tokens}},
                )
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            else:
                if response.status_code == 200:
                    try:
                        data = response.json()
                        text = str(data["response"]).strip()
                        return Generation(text, int(data.get("prompt_eval_count", 0)),
                                          int(data.get("eval_count", 0)))
                    except (KeyError, TypeError, ValueError) as exc:
                        raise GenerationError("Réponse inattendue d'Ollama.") from exc
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in (408, 429, 500, 502, 503, 504):
                    break
            if attempt < self.max_retries:
                time.sleep(1.0 * (attempt + 1))
        logger.warning("Échec de l'appel Ollama : %s", last_error)
        raise GenerationError("Ollama est indisponible ou le modèle n'est pas chargé.")


class ApiLLMGenerator:
    """Grand modèle de langage par API HTTP (Anthropic Messages ou OpenAI Chat)."""

    ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
    OPENAI_URL = "https://api.openai.com/v1/chat/completions"

    def __init__(self, provider: str, model: str, api_key: str, max_new_tokens: int, temperature: float,
                 timeout: float, max_retries: int, client: httpx.Client | None = None) -> None:
        if not api_key:
            raise GenerationError("Aucune clé API configurée (AI_API_KEY).")
        self.provider = provider
        self.model = model
        self._api_key = api_key
        self.max_new_tokens = max_new_tokens
        self.temperature = temperature
        self.max_retries = max_retries
        self.name = f"api:{provider}:{model}"
        self._client = client or httpx.Client(timeout=timeout)

    def _request(self, prompt: str) -> httpx.Response:
        if self.provider == "anthropic":
            return self._client.post(
                self.ANTHROPIC_URL,
                headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": self.max_new_tokens, "temperature": self.temperature,
                      "messages": [{"role": "user", "content": prompt}]},
            )
        return self._client.post(
            self.OPENAI_URL,
            headers={"Authorization": f"Bearer {self._api_key}"},
            json={"model": self.model, "max_tokens": self.max_new_tokens, "temperature": self.temperature,
                  "messages": [{"role": "user", "content": prompt}]},
        )

    def generate(self, prompt: str, question: str, passages: list[Passage]) -> Generation:
        """Appelle l'API ; une nouvelle tentative en cas d'erreur temporaire (429, 5xx, délai)."""
        last_error = "erreur inconnue"
        for attempt in range(self.max_retries + 1):
            try:
                response = self._request(prompt)
            except httpx.HTTPError as exc:
                last_error = type(exc).__name__
            else:
                if response.status_code == 200:
                    return self._parse(response.json())
                last_error = f"HTTP {response.status_code}"
                if response.status_code not in (408, 429, 500, 502, 503, 504, 529):
                    break
            if attempt < self.max_retries:
                time.sleep(1.5 * (attempt + 1))
        logger.warning("Échec de l'appel %s : %s", self.name, last_error)
        raise GenerationError("Le service de génération externe ne répond pas.")

    def _parse(self, data: dict) -> Generation:
        try:
            if self.provider == "anthropic":
                text = "".join(block.get("text", "") for block in data["content"] if block.get("type") == "text")
                usage = data.get("usage", {})
                return Generation(text.strip(), int(usage.get("input_tokens", 0)), int(usage.get("output_tokens", 0)))
            text = data["choices"][0]["message"]["content"] or ""
            usage = data.get("usage", {})
            return Generation(text.strip(), int(usage.get("prompt_tokens", 0)), int(usage.get("completion_tokens", 0)))
        except (KeyError, IndexError, TypeError) as exc:
            raise GenerationError("Réponse inattendue du service de génération.") from exc


def build_generator(settings: Settings) -> Generator:
    """Construit la stratégie de génération demandée par la configuration."""
    if settings.llm_backend == "flan-t5":
        return LocalFlanT5Generator(settings.local_model, settings.max_new_tokens, settings.local_quantize)
    if settings.llm_backend == "ollama":
        return OllamaGenerator(settings.ollama_url, settings.ollama_model, settings.max_new_tokens,
                               settings.temperature, settings.ollama_timeout, settings.api_max_retries)
    if settings.llm_backend == "api":
        key = settings.api_key.get_secret_value() if settings.api_key else ""
        return ApiLLMGenerator(settings.api_provider, settings.api_model, key, settings.max_new_tokens,
                               settings.temperature, settings.api_timeout, settings.api_max_retries)
    return ExtractiveGenerator()
