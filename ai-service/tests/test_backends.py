"""Backends lourds (sentence-transformers, flan-t5) testés avec des modules simulés.

Les vrais modèles sont téléchargés depuis Hugging Face : ils ne sont ni chargés en CI ni dans
ces tests. On vérifie ici le câblage (chargement unique, normalisation, sélection du backend).
"""

from __future__ import annotations

import sys
import types

import httpx
import numpy as np
import pytest

from app.core.embeddings import SentenceTransformerEmbedder
from app.errors import GenerationError
from Module_3.rag.generators import (
    ApiLLMGenerator,
    ExtractiveGenerator,
    LocalFlanT5Generator,
    OllamaGenerator,
    build_generator,
)
from tests.conftest import make_settings


class FakeSentenceTransformer:
    loads = 0

    def __init__(self, name, device="cpu"):
        FakeSentenceTransformer.loads += 1

    def get_sentence_embedding_dimension(self):
        return 4

    def encode(self, texts, **kwargs):
        return np.array([[len(t), 1.0, 0.0, 0.0] for t in texts], dtype=np.float32)


def test_sentence_transformer_charge_une_fois_et_normalise(monkeypatch):
    monkeypatch.setitem(sys.modules, "sentence_transformers",
                        types.SimpleNamespace(SentenceTransformer=FakeSentenceTransformer))
    FakeSentenceTransformer.loads = 0
    embedder = SentenceTransformerEmbedder("modele/test")
    a = embedder.encode(["abc", "abcdef"])
    embedder.encode(["x"])
    assert FakeSentenceTransformer.loads == 1
    assert embedder.dim == 4 and embedder.name == "st:modele/test"
    np.testing.assert_allclose(np.linalg.norm(a, axis=1), 1.0, rtol=1e-5)


def test_flan_t5_sans_transformers(monkeypatch):
    # Régression B6 : sans torch, generate() levait ImportError (erreur 500) au lieu de GenerationError.
    monkeypatch.setitem(sys.modules, "torch", None)
    monkeypatch.setitem(sys.modules, "transformers", None)
    generator = LocalFlanT5Generator("google/flan-t5-base", 50, quantize=True)
    assert generator.name == "local:flan-t5-base-int8"
    with pytest.raises(GenerationError):
        generator.generate("prompt", "q", [])


@pytest.mark.parametrize("backend, expected", [("extractive", ExtractiveGenerator),
                                               ("flan-t5", LocalFlanT5Generator),
                                               ("ollama", OllamaGenerator)])
def test_choix_du_backend(tmp_path, backend, expected):
    assert isinstance(build_generator(make_settings(tmp_path, llm_backend=backend)), expected)


def test_backend_api(tmp_path):
    generator = build_generator(make_settings(tmp_path, llm_backend="api", api_key="cle-test"))
    assert isinstance(generator, ApiLLMGenerator) and generator.name.startswith("api:anthropic")
    with pytest.raises(GenerationError):
        build_generator(make_settings(tmp_path, llm_backend="api"))  # pas de clé


def test_ollama_parse_la_reponse_sans_appel_reseau():
    client = httpx.Client(transport=httpx.MockTransport(
        lambda request: httpx.Response(200, json={"response": "Réponse locale [Source 1]",
                                                   "prompt_eval_count": 12, "eval_count": 7})
    ))
    generator = OllamaGenerator("http://ollama", "llama3:8b", 50, 0.2, 5, client=client)
    result = generator.generate("prompt", "question", [])
    assert result.text == "Réponse locale [Source 1]"
    assert (result.prompt_tokens, result.completion_tokens) == (12, 7)


def test_flan_t5_modele_introuvable(monkeypatch):
    """Régression B7 : un téléchargement impossible (OSError) doit déclencher le secours extractif."""
    def refuse(*args, **kwargs):
        raise OSError("pas de réseau")
    fake = types.SimpleNamespace(AutoTokenizer=types.SimpleNamespace(from_pretrained=refuse),
                                 AutoModelForSeq2SeqLM=types.SimpleNamespace(from_pretrained=refuse))
    monkeypatch.setitem(sys.modules, "transformers", fake)
    with pytest.raises(GenerationError):
        LocalFlanT5Generator("google/inexistant", 50).generate("prompt", "q", [])
