# Semantic Search — Project role card

> Ready-to-paste content for the project/team template. It adds only this module's
> role, skills, deliverables and demo plan; it does not change the template design.
>
> Module location: `ai-study-assistant/modules/semantic_search/`.

## Role

**Semantic Search Engineer**

## Mission

Build a semantic search engine using embeddings and similarity search to find the
most relevant content from course notes.

The system must retrieve passages by **meaning**, not only by exact keywords. For
example, a question about “avoiding memorization” should find notes about
overfitting, regularization or generalization.

## Key AI skills / tech

- **Embeddings** — encode passages and queries as dense vectors with
  `sentence-transformers`.
- **Vector search** — index and query passage vectors with FAISS.
- **Similarity metrics** — cosine similarity / inner product, plus retrieval
  metrics such as Recall@k, Precision@k and MRR.
- **Evaluation** — annotated example queries, a keyword-search baseline and error
  analysis.
- **Index persistence** — save passages, embeddings and the FAISS/NumPy index, then
  reload them without re-encoding the corpus.
- **Optional RAG layer** — a local Ollama LLM generates a grounded answer from the
  retrieved passages, with source citations.

## Deliverables

1. **Search feature** — index course notes, submit a natural-language query and
   return the top-k relevant passages.
2. **Example queries** — a small, documented set of questions covering synonyms,
   paraphrases and course-specific concepts.
3. **Results** — real output from the demo (titles, passages, scores), plus the
   evaluation report. Results must be measured, not invented.
4. **Optional RAG answer** — a local Ollama client answers from the retrieved
   passages only and cites `[1]`, `[2]`, etc. It remains available in code but is
   not exposed in the simplified demo.
5. **Transparent AI workflow** — prompts used and human verification recorded in
   `prompts.md`.

## Example queries and expected behaviour

These examples define what the demo must show. They are not fabricated results;
the Streamlit demo computes the actual passages and scores at run time.

| Query | Expected relevant themes | What the demo shows |
| --- | --- | --- |
| Comment éviter que le modèle apprenne par cœur ? | overfitting, regularization, generalization | top-k passages with similarity scores |
| Qu’est-ce qu’un embedding ? | vector representation, semantic proximity | passages containing the idea, even with different wording |
| Comment évaluer un moteur de recherche ? | Recall@k, MRR, annotated queries | retrieval results; metrics via the evaluation CLI |
| Différence entre recherche par mots-clés et recherche sémantique ? | lexical matching limits, synonyms, paraphrases | side-by-side comparison or explanation |

## Acceptance criteria

- A semantically equivalent query can retrieve a relevant passage without sharing
  its exact keywords.
- Results are sorted by descending similarity score.
- `top_k` is respected and invalid inputs produce explicit errors.
- Each result exposes the note title, the relevant passage and a score.
- Evaluation includes Precision@k, Recall@k, MRR and a keyword baseline.
- If the LLM is enabled, the answer is limited to retrieved sources, cites them,
  and a failure of Ollama leaves the search results available.
- The interface does not hide engine errors or empty-corpus states.
- I can explain the embedding → index → query → ranking pipeline, and why the LLM
  is only an optional generation layer, at the oral exam.

## AI-assisted workflow

- The project starts with a cadrage prompt that creates the structure.
- Implementation, tests, evaluation and UI are generated step by step.
- An optional local RAG layer was added with Ollama, after the core search.
- Every generated file is reviewed before acceptance.
- The prompts and verification steps are recorded in `prompts.md`.

## Status

**MVP implemented.** The search engine, metrics, keyword baseline, optional Ollama
client, tests and simplified Streamlit demo are present. The demo loads sample notes
by default (an upload replaces them), uses fixed 300/50 chunks, shows notes/passages
counters and an integrated evaluation. Tests pass with a deterministic test embedder
and a fake Ollama HTTP response. No results are pre-filled or invented.
