# Service IA — AI Study Assistant

Micro-service Python (FastAPI) appelé par l'application PHP. Il porte :

- le **socle partagé** (`app/core/`) : extraction PDF/DOCX/TXT, découpage, embeddings — réutilisé par le module 2 ;
- le **module 3** (`Module_3/rag/`) : questions-réponses RAG sur les cours de chaque étudiant ;
- le **module 5** (`app/modules/classification/`) : classification des cours par matière (scikit-learn).

Le service écoute **uniquement sur 127.0.0.1** et exige l'en-tête `X-Internal-Token` sur chaque route.

## Installation (Python 3.12 ou 3.13)

```bash
cd ai-service
python -m venv .venv
.venv\Scripts\activate                 # Windows
source .venv/bin/activate              # Linux / macOS
pip install -r requirements.txt        # complet : MiniLM, flan-t5 (torch ≈ 1 Go)
# ou : pip install -r requirements-ci.txt   (léger : mode hors ligne, sans torch)
copy .env.example .env                 # Windows (cp sous Linux/macOS), puis renseigner AI_INTERNAL_TOKEN
```

Générer le jeton (à recopier aussi dans `config/ai.php` côté PHP) :

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

## Lancement

```bash
uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001
```

Un seul worker (les index sont protégés par des verrous en mémoire). Au premier appel, les modèles
du cours sont téléchargés depuis Hugging Face (connexion Internet requise une fois).
Sans Internet : `AI_EMBEDDING_BACKEND=hashing` et `AI_LLM_BACKEND=extractive` dans `.env`.

Documentation interactive : http://127.0.0.1:8001/docs (le bouton « Authorize » n'existe pas :
ajoutez l'en-tête `X-Internal-Token` avec un client HTTP).

## Routes

| Méthode | Route | Rôle |
|---|---|---|
| GET | `/health` | état, backends actifs, modèle de classification disponible |
| POST | `/rag/index` | `{student_id, course_id, stored_name, title}` → indexe (ou réindexe) un cours |
| DELETE | `/rag/index/{student_id}/{course_id}` | retire un cours de l'index de l'étudiant |
| POST | `/rag/ask` | `{student_id, question, course_id?, k?}` → `{answer, sources, backend, latency_ms, cache_hit, abstained, reason}` |
| GET | `/classify/categories` | catégories (fichier partagé avec PHP) |
| POST | `/classify` | `{text}` ou `{stored_name}` → `{category, confidence, accepted, top, explanation, model_version}` |
| POST | `/classify/feedback` | `{stored_name, predicted, corrected}` → enregistre une correction d'étudiant |

Erreurs : `401` jeton, `404` document introuvable, `409` index créé avec un autre modèle, `422` entrée
refusée, `503` modèle indisponible. Corps : `{"detail": "message en français"}`.

## Configuration

Toutes les variables sont documentées dans `.env.example` (préfixe `AI_`). Les principales :
`AI_EMBEDDING_BACKEND`, `AI_LLM_BACKEND` (`extractive` | `flan-t5` | `ollama` | `api`), `AI_RAG_MIN_SCORE`,
`AI_RAG_TOP_K`, `AI_CHUNK_SIZE`, `AI_LOCAL_QUANTIZE`, `AI_API_KEY`.

## Scripts

| Script | Rôle |
|---|---|
| `scripts/evaluate_rag.py` | Hit@k, MRR, seuil d'abstention, taille des blocs, L2/IP, générateurs, prompts, cache |
| `scripts/benchmark.py` | taille et latence de flan-t5 avec et sans quantization int8 |
| `scripts/build_dataset.py` | nettoyage et dédoublonnage du jeu d'entraînement, contrôle de fuite |
| `scripts/train_classifier.py` | comparaison de 5 modèles (GridSearchCV), choix, seuil, sauvegarde |
| `scripts/evaluate_classifier.py` | test réel : matrice de confusion, rapport par classe, seuil, prédictions |
| `scripts/retrain_with_feedback.py` | réentraînement avec les corrections des étudiants (remplace seulement si meilleur) |
| `scripts/add_real_documents.py` | ajoute vos vrais cours d'autres matières au test réel |
| `scripts/run_all_evaluations.py` | relance toutes les mesures avec les modèles du cours |

Résultats : `reports/`. Modèle de classification : `models/classifier.joblib` + `classifier_meta.json`.

## Tests

```bash
ruff check .
pytest --cov=app --cov-report=term-missing
```

92 tests, 96 % de couverture. Les modèles lourds sont simulés : la suite tourne sans torch ni réseau.

## Pour le membre 2 (recherche sémantique)

Réutilisez directement :

```python
from app.core.extraction import extract_pages
from app.core.chunking import chunk_pages
from app.core.embeddings import build_embedder
```

L'index de chaque étudiant (`storage/indexes/<id>/`) peut être interrogé avec
`RagService.retrieve(student_id, question, k)` sans passer par la génération.
