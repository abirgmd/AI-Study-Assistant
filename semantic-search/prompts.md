# Journal des prompts — moteur de recherche sémantique

Ce document rend le travail assisté par IA **traçable et défendable**. Il contient
les prompts réellement utilisés, ce qui a été généré, et les vérifications effectuées
sur le résultat.

Le module est placé dans `ai-study-assistant/modules/semantic_search/` ; le template
PHP reste à la racine de `ai-study-assistant/`.

## Règles du workflow

1. L'outil d'IA est présenté comme un assistant de développement, pas comme un
   générateur de projet magique.
2. Chaque étape est découpée : cadrage, implémentation, tests, interface.
3. Une génération n'est acceptée qu'après relecture et vérification.
4. Je dois pouvoir expliquer chaque fichier, chaque dépendance et chaque choix.
5. Les prompts et les résultats des vérifications sont conservés dans ce fichier.

## Prompt 1 — Cadrage (utilisé)

```text
Tu es mon assistant de développement pour un projet de moteur de recherche
sémantique sur des notes de cours.

Stack imposée : Python 3, sentence-transformers, FAISS, Streamlit, pytest.

Crée uniquement la structure suivante, sans écrire la logique de recherche :

- search/README.md
- requirements.txt
- prompts.md
- data/
- src/module.py
- src/evaluate.py
- tests/test_search.py
- demo_app.py

Contraintes :
- pas d'implémentation du moteur, des embeddings, de l'index FAISS ni de l'UI fonctionnelle ;
- des contrats clairs (signatures, docstrings, modèles de données) et des TODO ;
- des tests marqués comme skipped tant que la logique n'existe pas ;
- documenter l'objectif, le pipeline prévu, les limites et la méthode d'évaluation ;
- écrire en français et rester honnête sur ce qui n'est pas encore fait.
```

### Résultat produit

- arborescence et fichiers de cadrage ;
- contrats `SemanticSearchEngine` et `SearchResult` dans `src/module.py` ;
- contrat d'évaluation dans `src/evaluate.py` ;
- tests de spécification dans `tests/test_search.py` ;
- interface Streamlit volontairement non fonctionnelle dans `demo_app.py` ;
- documentation du pipeline et de la stratégie d'évaluation dans `search/README.md`.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Version de Python | `python --version` | Python 3.12.10 |
| Arborescence demandée | inspection des dossiers et fichiers | présente |
| Absence de logique de recherche | inspection de `src/module.py` | méthodes en `NotImplementedError` |
| Tests non trompeurs | inspection de `tests/test_search.py` | tests marqués `skip` |
| Syntaxe Python | `python -m compileall -q src tests demo_app.py` | OK |
| Dépendances lourdes non installées | `python -c "import pytest"` | environnement de base sans pytest ; installation via `requirements.txt` à faire |

### Limites assumées à ce stade

- aucun embedding n'est calculé ;
- aucun index FAISS n'est construit ;
- aucune note réelle n'est chargée ;
- aucun test ne passe encore : ils sont seulement spécifiés ;
- l'interface ne fait qu'annoncer le futur comportement.

## Prompt 2 — Implémentation du moteur (utilisé)

```text
Implémente src/module.py en respectant les contrats existants.

Contraintes :
- charger des notes depuis data/ ;
- découper en passages avec chevauchement ;
- utiliser un modèle sentence-transformers multilingue adapté au français ;
- normaliser les vecteurs et utiliser un index FAISS ;
- retourner des SearchResult triés par score décroissant ;
- gérer les erreurs : corpus vide, requête vide, top_k invalide ;
- ne pas ajouter d'API externe à cette étape ;
- expliquer chaque choix et signaler les limites.

Ne modifie pas les tests pour les faire passer artificiellement.
```

## Prompt 3 — Tests et évaluation (utilisé)

```text
Écris les tests de tests/test_search.py et implémente src/evaluate.py.

Contraintes :
- cas nominal, corpus vide, requête vide, top_k invalide ;
- vérifier le tri, la taille de sortie et la présence des champs ;
- créer un petit jeu de requêtes annotées ;
- calculer Recall@k, Precision@k et MRR ;
- comparer à une baseline par mots-clés ;
- les tests doivent échouer si la recherche ne respecte pas le contrat.
```

## Prompt 4 — Interface de démonstration (utilisé)

```text
Implémente demo_app.py avec Streamlit.

Contraintes :
- chargement des notes et indexation avec mise en cache ;
- champ de question et sélection du nombre de résultats ;
- affichage du titre, de l'extrait et du score ;
- message explicite si aucune note n'est chargée ;
- aucun appel réseau obligatoire pour le MVP ;
- l'interface ne doit pas masquer les erreurs du moteur.
```

### Résultat produit pour les prompts 2 à 4

- `src/module.py` : validation des notes, découpage par phrases avec chevauchement,
  embeddings multilingues, index FAISS et repli NumPy ;
- `src/evaluate.py` : Precision@k, Recall@k, MRR, chargement du jeu annoté et
  baseline lexicale pondérée par IDF ;
- `tests/test_search.py` : 15 tests avec un embedder déterministe ;
- `demo_app.py` : interface Streamlit avec exemples, résultats réels et évaluation ;
- `data/notes_exemple.json` et `data/evaluation_cases.json` : corpus de démonstration.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Syntaxe Python | `python -m compileall -q src tests demo_app.py` | OK |
| Tests unitaires | `python -m pytest -q` avec dépendances de test isolées | 15 passed à cette étape, 20 après ajout du client Ollama |
| Chargement du corpus | script sur `data/notes_exemple.json` | 6 notes, 18 passages |
| Jeu d'évaluation | `load_evaluation_cases` | 6 requêtes valides |
| Baseline mots-clés | `python -m src.evaluate --baseline-only --k 3` | Precision@3 = 0.389, Recall@3 = 1.000, MRR = 0.806 |
| Absence de service cloud | inspection des imports et du code | modèles locaux uniquement |
| Résultats non inventés | inspection de la démo | scores calculés à l'exécution |

### Limites constatées

- l'installation de `sentence-transformers` et `faiss-cpu` a dépassé le temps
  imparti dans cet environnement ; la démo sémantique réelle n'a donc pas été
  exécutée ici, seuls les tests avec embedder de test l'ont été ;
- aucun score sémantique n'est affirmé sans exécution réelle ;
- la démo Python accepte JSON, TXT et Markdown, pas encore PDF/DOCX ;
- l'index n'était pas persisté à cette étape ; il peut maintenant l'être via
  `python -m src.build_index` ;
- le template PHP existant et les cartes des autres modules n'ont pas été modifiés.

## Prompt 5 — Relecture critique (prévu)

```text
Agis comme un relecteur critique de mon projet de recherche sémantique.

Cherche :
- les affirmations non démontrées ;
- les fuites de données dans l'évaluation ;
- les cas où le système semble meilleur qu'il ne l'est ;
- les choix techniques que je ne pourrais pas expliquer à l'oral ;
- les tests manquants.

Ne réécris pas le projet : liste les problèmes et les vérifications à faire.
```

## Prompt 6 — Adaptation au rôle du projet (utilisé)

```text
Adapte le contenu du template du projet à mon rôle : Semantic Search.

Mission : construire un moteur de recherche sémantique avec des embeddings et une
recherche par similarité pour retrouver le contenu le plus pertinent de notes de cours.

Compétences IA / tech : embeddings, recherche vectorielle, métriques de similarité.
Livrables : fonctionnalité de recherche, requêtes d'exemple, résultats.

Ne change pas le design du template existant. Prépare un contenu de carte de rôle
prêt à intégrer, avec les exemples de requêtes et les critères d'acceptation.
Ne fabrique aucun résultat : les scores et extraits devront venir de la démo réelle.
```

### Résultat produit

- `search/role-card.md` : carte de rôle prête à coller dans le template ;
- section « Rôle dans le projet » ajoutée au README du module ;
- exemples de requêtes et critères d'acceptation explicités ;
- aucun fichier de template HTML/CSS existant modifié.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Contenu aligné avec la mission | relecture de `role-card.md` | embeddings, vector search, similarité, livrables présents |
| Aucun résultat inventé | relecture des exemples | résultats réels calculés par la démo, aucun score prérempli |
| Template non modifié | inspection des fichiers existants | aucun design HTML/CSS touché |
| Limite assumée | relecture du statut | à cette étape, seule la carte était produite ; le MVP est implémenté depuis |

Depuis cette étape, le moteur et la démo ont été implémentés sans modifier le
template ni les cartes des autres modules.

## Prompt 7 — Ajout d'un LLM local avec Ollama (utilisé)

```text
Ajoute une couche de génération RAG optionnelle avec Ollama.

Contraintes :
- ne pas remplacer la recherche sémantique : elle reste la source des passages ;
- envoyer la question et les extraits à Ollama, sans clé cloud ;
- demander une réponse uniquement fondée sur les extraits, avec citations [1], [2] ;
- prévoir un mode sans Ollama et un message clair si le service est arrêté ;
- ne pas fabriquer de réponse et ne pas masquer les erreurs ;
- tester le prompt et le parsing avec un faux serveur HTTP.
```

### Résultat produit

- `src/llm.py` : construction du contexte, prompt système, appel local à
  `/api/chat`, gestion des erreurs et parsing de la réponse ;
- `demo_app.py` à cette étape (avant la simplification) : case à cocher, modèle et
  URL Ollama, réponse affichée avec les extraits sources, repli si Ollama est
  indisponible ;
- `tests/test_llm.py` : 5 tests avec un faux serveur, sans appel réseau réel.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Syntaxe Python | `python -m compileall -q src tests demo_app.py` | OK |
| Tests unitaires | `python -m pytest -q` | 20 passed à cette étape, 27 après ajout de l'index |
| Prompt RAG | inspection de `build_messages` | question, extraits, citations et refus d'invention demandés |
| Parsing de la réponse | test avec `post_json` factice | contenu extrait correctement |
| Erreur Ollama absente | test de réponse sans contenu | `OllamaError` levée |
| Modèle réel | lancement d'Ollama | non exécuté dans cet environnement |

### Limites constatées

- la couche Ollama est testée avec un faux serveur HTTP, pas avec un modèle réel ;
- un LLM peut encore mal interpréter un extrait : les sources doivent être vérifiées ;
- la qualité de la réponse dépend du modèle choisi et des passages retrouvés ;
- l'option est désactivée par défaut : la recherche sémantique fonctionne sans LLM.

## Prompt 8 — Embeddings et index persistants (utilisé)

```text
Ajoute une étape de création explicite des embeddings et de l'index.

Contraintes :
- réutiliser le chargement des notes et le découpage déjà présents dans src ;
- sauvegarder les passages, le modèle et les vecteurs sur disque ;
- recharger l'index sans recalculer les embeddings ;
- utiliser FAISS si disponible, sinon NumPy ;
- ajouter une commande CLI ;
- tester la sauvegarde, le rechargement et les fichiers invalides avec pytest ;
- ne pas inventer de vecteurs : sans modèle installé, seuls les tests avec un
  embedder factice peuvent tourner.
```

### Résultat produit

- `src/corpus.py` : chargement JSON commun, utilisé par `evaluate.py` et
  `build_index.py` ;
- `SemanticSearchEngine.save_index` et `load_index` : écriture de `index.json`,
  `embeddings.npy` et `faiss.index` si FAISS est disponible ;
- `src/build_index.py` : commande de création des embeddings et de l'index ;
- `tests/test_index.py` et `tests/test_corpus.py` : sauvegarde, rechargement,
  incohérences de forme et chargement du corpus.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Syntaxe Python | `python -m compileall -q src tests demo_app.py` | OK |
| Tests pytest | `python -m pytest -q` | 27 passed |
| Aller-retour index | sauvegarde puis rechargement dans un dossier temporaire | mêmes passages retrouvés |
| Fichiers produits | inspection du dossier temporaire | `index.json` et `embeddings.npy` présents |
| Embeddings incohérents | suppression d'une ligne de `embeddings.npy` | erreur explicite |
| Modèle réel | exécution du moteur dans `.venv` | 6 notes → 6 passages, backend NumPy |

### Limites constatées

- les embeddings réels ont été générés pour les 6 notes d'exemple ; FAISS n'a pas
  pu se charger sur cette machine (DLL bloquée), le repli NumPy a fonctionné ;
- la démo Streamlit reconstruit encore l'index en mémoire ; elle ne recharge pas
  automatiquement `data/index/` ;
- le fichier `faiss.index` n'est créé que si `faiss-cpu` est installé ; sinon le
  rechargement utilise NumPy ;
- un index sauvegardé doit rester associé au même modèle d'embedding.

## Prompt 9 — Simplification de la démo Streamlit (utilisé)

```text
Simplifie demo_app.py. Supprime de la sidebar le choix du modèle, les sliders de
taille de passage et de chevauchement, ainsi que la case notes d'exemple. Fixe le
modèle à paraphrase-multilingual-MiniLM-L12-v2, les passages à 300 mots et le
chevauchement à 50 mots. Garde uniquement l'import de notes, le slider du nombre de
résultats et la barre de recherche. Supprime le sous-titre « Module 2... ».
```

### Résultat produit

- `demo_app.py` : modèle, découpage et chevauchement fixés ; titre conservé ;
  sous-titre, sélecteur de modèle et sliders de découpage supprimés ;
- notes d'exemple chargées quand aucun fichier n'est importé ; un import remplace
  ce corpus ;
- compteurs « Notes » et « Passages indexés » restaurés, sans affichage du backend
  ni du nom du modèle dans l'interface ;
- évaluation intégrée restaurée sur les notes d'exemple ; import et slider du
  nombre de résultats conservés ;
- contrôles Ollama retirés de l'interface ; `src/llm.py` et ses tests restent
  disponibles pour un usage programmatique ;
- index mis en cache par contenu.

### Vérifications humaines effectuées

| Vérification | Méthode | Résultat |
|---|---|---|
| Syntaxe | `python -m compileall -q src demo_app.py` | OK |
| Tests | `python -m pytest -q` | 27 passed |
| Démarrage Streamlit | lancement headless et requête HTTP | HTTP 200 |
| Interface sans fichier | `AppTest` | 6 notes, 6 passages, recherche et évaluation visibles, aucune exception |
| Recherche | `AppTest` sur une question de test | 5 résultats, meilleur score 0.683 |
| Évaluation | `AppTest` avec k=5 | sémantique 0.233/1.000/0.889 ; mots-clés 0.233/1.000/0.639 |
| Import | `AppTest` avec `notes_exemple.json` | index construit, notes d'exemple remplacées |
| Modèle réel | index de `notes_exemple.json` en 300/50 | 6 passages, backend NumPy |
| FAISS | import dans `.venv` | DLL bloquée par Windows, repli NumPy |

### Limites constatées

- le premier chargement du modèle peut prendre du temps ;
- l'évaluation intégrée n'est disponible que sur les notes d'exemple ; elle est
  désactivée dès qu'un fichier est importé ;
- FAISS n'est pas actif sur cette machine, mais la recherche NumPy fonctionne.

## Défense orale — points à maîtriser

- **Pourquoi du sémantique plutôt que des mots-clés ?** Les embeddings rapprochent
  des formulations différentes ; un moteur par mots-clés rate les synonymes et les
  paraphrases.
- **Comment ça marche réellement ?** Chaque passage et la requête sont transformés
  en vecteurs ; on compare ces vecteurs avec une similarité, puis on récupère les
  plus proches. FAISS accélère cette recherche.
- **Comment sont créés les embeddings ?** Le corpus est chargé, découpé en passages,
  encodé par le modèle multilingue, normalisé, puis stocké dans une matrice. La
  commande `python -m src.build_index` sauvegarde les passages et les vecteurs pour
  éviter de tout recalculer.
- **Est-ce que j'utilise une API de LLM ?** J'utilise deux couches locales :
  un modèle d'embeddings pour la recherche, puis Ollama (optionnel) pour générer
  une réponse à partir des extraits. Aucun cloud ni clé API. Le LLM ne remplace pas
  la recherche : il ne voit que les passages retrouvés.
- **Quelles sont les limites ?** Découpage imparfait, faux positifs, modèle pas
  forcément spécialisé sur le cours, dépendance à la qualité des notes, évaluation
  sur un petit jeu de requêtes.
- **Comment je vérifie que ça marche ?** Jeu de requêtes annoté, Recall@k,
  Precision@k, MRR, baseline mots-clés, tests du contrat et analyse des erreurs.
- **Quelle est la part de l'IA ?** L'IA a produit le squelette, l'implémentation,
  les tests, l'interface et le client Ollama ; les prompts, les choix et les
  vérifications sont documentés. Je dois pouvoir expliquer le chunking, les
  embeddings, FAISS, la similarité cosinus, le prompt RAG et le calcul des métriques.
- **Pourquoi Ollama ?** Il permet une génération locale, sans clé API, et les notes
  ne sont pas envoyées à un service cloud. C'est une couche optionnelle : si Ollama
  est arrêté, la recherche et les extraits restent disponibles.
- **Qu'est-ce qui n'est pas encore démontré ?** La démo avec le vrai modèle
  d'embeddings n'a pas tourné dans cet environnement (installation lourde
  indisponible), et Ollama a été testé avec un faux serveur HTTP. Les tests
  unitaires ne doivent pas être présentés comme une preuve de qualité sémantique
  ou de qualité de génération.
