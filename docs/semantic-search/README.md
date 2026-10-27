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

Le module est désormais **intégré à l'application PHP** : le bouton
**Recherche sémantique** du menu appelle `public/semantic-search-api.php`, qui
prépare les cours TXT et DOCX de l'étudiant et interroge un service Python local
sur `127.0.0.1:8002` (`modules/semantic_search/service.py`). La démonstration
Streamlit reste disponible pour la soutenance et l'évaluation du module.

L'intégration ne modifie aucun autre module : elle ajoute un bouton, une fenêtre
et une API isolée. Le service Python n'est pas exposé sur le réseau et exige un
jeton interne. Voir [`INTEGRATION_APP.md`](INTEGRATION_APP.md) pour
l'architecture, la configuration et les tests de bout en bout.

## Intégration dans l'application PHP

```powershell
# 1. Environnement Python du module (une seule fois)
cd modules\semantic_search
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
cd ..\..

# 2. Service local, à laisser ouvert pendant la démo
lancer-recherche-semantique.bat

# 3. Application PHP (XAMPP), puis connexion et import d'un cours TXT/DOCX
```

Le jeton et l'URL peuvent être personnalisés dans `config/semantic-search.php`
(copier `config/semantic-search.example.php`). Le jeton du service doit être le
même que celui du fichier PHP. La variable d'environnement `SEMANTIC_SEARCH_TOKEN`
est lue par le lanceur et par l'application.

## Lancement de la démonstration Streamlit

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
# Tous les tests du module 2 (Python, PHP et service HTTP)
lancer-tests-semantic-search.bat

# Ou uniquement les tests Python
cd modules\semantic_search
.\.venv\Scripts\python.exe -m pytest -q
```

Les 48 tests utilisent un embedder déterministe et un faux serveur Ollama : ils
passent sans télécharger de modèle ni lancer de service. FAISS est utilisé s'il est
disponible ; sinon le moteur bascule automatiquement sur NumPy. Le smoke test
`tests/smoke_semantic_search.py` démarre le service HTTP avec l'embedder de test,
vérifie `/health`, le jeton, le classement et la validation, puis l'arrête.

## Livrables

- `modules/semantic_search/service.py` : service HTTP local pour l'application PHP.
- `modules/semantic_search/demo_app.py` : interface Streamlit.
- `modules/semantic_search/src/module.py` : découpage, embeddings, index, recherche.
- `modules/semantic_search/src/evaluate.py` : métriques et baseline mots-clés.
- `modules/semantic_search/src/build_index.py` : génération de l'index sur disque.
- `public/semantic-search-api.php` : API JSON protégée par la session étudiante.
- `public/assets/semantic-search.js` / `.css` : bouton et fenêtre dans l'application.
- `app/semantic_search.php` : validation, extraction des cours et appel du service.
- `tests/semantic_search_test.php` / `tests/smoke_semantic_search.py` : tests d'intégration.
- `modules/semantic_search/search/README.md` : documentation technique complète.
- `modules/semantic_search/search/role-card.md` : carte de rôle.
- `modules/semantic_search/prompts.md` : journal des prompts et vérifications.
- `RAPPORT_PROJET_IA_RECHERCHE_SEMANTIQUE.pdf` : rapport de la tâche.
- `CLAUDE_AI_DISCUSSION_5_ETAPES_1PAGE.pdf` : synthèse de la discussion avec l'IA.
- `FICHE_ORAL_DEMO_6_NOTES.pdf` / `.docx` : fiche de préparation à l'oral.
