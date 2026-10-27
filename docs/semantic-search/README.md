# Module 2 — Recherche sémantique

## Objectif

Retrouver les passages les plus pertinents de notes de cours à partir du **sens** de la
question, et non uniquement de mots-clés identiques. Le module fournit un moteur
d'embeddings, une recherche vectorielle, une baseline lexicale, des métriques
d'évaluation et une démonstration Streamlit.

## Emplacement dans le projet intégré

```text
ai-study-assistant-integre/
├── modules/
│   └── semantic_search/          # code, tests, corpus et démo Streamlit
├── docs/
│   └── semantic-search/          # cette documentation et les fiches
└── RAPPORT_PROJET_IA_RECHERCHE_SEMANTIQUE.pdf
```

Le module reste **autonome** : il n'est pas branché aux pages PHP et n'appelle pas le
service FastAPI. Le socle partagé `ai-service/app/core/` (extraction, découpage,
embeddings) peut être réutilisé plus tard pour une intégration dans l'interface web,
mais la démonstration livrée est volontairement séparée pour ne pas modifier les
modules existants.

## Lancement de la démonstration

Depuis la racine du projet intégré :

```powershell
cd modules\semantic_search
python -m venv .venv
.\.venv\Scripts\activate
pip install -r requirements.txt
python -m streamlit run demo_app.py
```

Pour réutiliser directement l'environnement du service IA intégré :

```powershell
cd ai-service
python -m pip install -r requirements.txt -r ..\modules\semantic_search\requirements-demo.txt
cd ..\modules\semantic_search
python -m streamlit run demo_app.py
```

`requirements.txt` contient les dépendances complètes de la démo autonome ;
`requirements-demo.txt` ajoute uniquement Streamlit à l'environnement déjà installé
par `ai-service/requirements.txt`. Cette séparation évite d'écraser les versions
épinglées du service (`sentence-transformers==6.2.0`, `numpy==2.5.4`,
`faiss-cpu==1.15.1`, `pytest==9.1.1`).

## Démonstration

La page charge six notes d'exemple, autorise l'import d'un fichier JSON, TXT ou
Markdown, règle le nombre de résultats et affiche les passages, les scores et les
métriques d'évaluation. Le modèle est
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, avec des passages de
300 mots et un chevauchement de 50 mots.

Résultats mesurés sur le corpus de démonstration :

| Mesure | Recherche sémantique | Baseline mots-clés |
| --- | --- | --- |
| Démo, k = 5 : Precision@5 | 0,233 | 0,233 |
| Démo, k = 5 : Recall@5 | 1,000 | 1,000 |
| Démo, k = 5 : MRR | 0,889 | 0,639 |
| CLI 80/15, k = 3 : Precision@3 | 0,333 | 0,389 |
| CLI 80/15, k = 3 : Recall@3 | 0,833 | 1,000 |
| CLI 80/15, k = 3 : MRR | 0,722 | 0,806 |

Six notes produisent six passages ; le meilleur score de similarité observé est
0,683. La recherche sémantique améliore surtout le rang du premier résultat
pertinent (MRR), tandis que la baseline lexicale reste compétitive sur les requêtes
qui reprennent les mots du cours.

## Tests

```powershell
cd modules\semantic_search
python -m pytest -q
```

Les 27 tests utilisent un embedder déterministe et un faux serveur Ollama : ils
passent sans télécharger de modèle ni lancer de service. FAISS est utilisé s'il est
disponible ; sinon le moteur bascule automatiquement sur NumPy.

## Livrables

- `modules/semantic_search/demo_app.py` : interface Streamlit.
- `modules/semantic_search/src/module.py` : découpage, embeddings, index, recherche.
- `modules/semantic_search/src/evaluate.py` : métriques et baseline mots-clés.
- `modules/semantic_search/src/build_index.py` : génération de l'index sur disque.
- `modules/semantic_search/search/README.md` : documentation technique complète.
- `modules/semantic_search/search/role-card.md` : carte de rôle.
- `modules/semantic_search/prompts.md` : journal des prompts et vérifications.
- `RAPPORT_PROJET_IA_RECHERCHE_SEMANTIQUE.pdf` : rapport de la tâche.
- `CLAUDE_AI_DISCUSSION_5_ETAPES_1PAGE.pdf` : synthèse de la discussion avec l'IA.
- `FICHE_ORAL_DEMO_6_NOTES.pdf` / `.docx` : fiche de préparation à l'oral.
