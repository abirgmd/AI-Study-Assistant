# Module 2 — Recherche sémantique dans des notes de cours

## Objectif

Retrouver les passages les plus pertinents d'un ensemble de notes de cours à partir
du **sens** d'une question, et non uniquement de mots-clés identiques.

Exemple : la question « comment éviter que le modèle apprenne par cœur ? » doit
pouvoir retrouver un passage qui parle de « sur-apprentissage », de
« régularisation » ou de « capacité de généralisation », même sans reprendre les
mêmes mots.

## Rôle dans le projet

**Semantic Search Engineer.** Construire un moteur de recherche sémantique fondé sur
les embeddings et la recherche vectorielle pour retrouver les passages les plus
pertinents de notes de cours. Compétences IA associées : embeddings, recherche
vectorielle, métriques de similarité. Livrables : fonctionnalité de recherche,
requêtes d'exemple et résultats réels.

La carte de rôle prête à intégrer au template du projet se trouve dans
`search/role-card.md`.

## Emplacement

Le module est autonome dans le projet :

```text
ai-study-assistant/
└── modules/
    └── semantic_search/
        ├── search/README.md
        ├── search/role-card.md
        ├── data/
        ├── src/
        ├── tests/
        ├── demo_app.py
        ├── requirements.txt
        └── prompts.md
```

Le template PHP (`app/`, `public/`, `config/`, `database/`, `storage/`) reste à la
racine de `ai-study-assistant/` et n'est pas modifié par ce module. La démonstration
est **100 % Python + Streamlit** ; aucun branchement PHP n'est nécessaire.

## Statut

**MVP implémenté.** Le moteur, l'évaluation, les tests et la démo Streamlit sont
présents. La recherche utilise un modèle d'embeddings local ; une couche de
génération RAG optionnelle peut utiliser **Ollama** en local. Aucun service cloud
et aucune clé API ne sont nécessaires.

Les tests unitaires utilisent un embedder déterministe et un faux serveur Ollama :
ils passent sans télécharger de modèle ni lancer Ollama. La démo réelle nécessite
`sentence-transformers` et télécharge le modèle d'embeddings au premier lancement.
Les résultats affichés sont toujours calculés : aucun score n'est prérempli. Les
embeddings et l'index peuvent aussi être générés sur disque avec
`python -m src.build_index`. **27 tests pytest passent** dans l'environnement isolé.

La démo Streamlit simplifiée charge les notes d'exemple quand aucun fichier n'est
importé ; un import remplace ce corpus. Le modèle est fixé à
`paraphrase-multilingual-MiniLM-L12-v2`, avec des passages de 300 mots et un
chevauchement de 50 mots.

## Fonctionnalités livrées

- chargement de notes JSON, TXT ou Markdown ;
- découpage en passages avec chevauchement, en respectant les phrases ;
- embeddings multilingues avec `sentence-transformers` ;
- index vectoriel FAISS, avec repli NumPy si FAISS est absent ;
- sauvegarde et rechargement des embeddings et de l'index (`index.json`,
  `embeddings.npy`, `faiss.index` si disponible) ;
- recherche `top_k` triée par similarité cosinus ;
- erreurs explicites : corpus vide, requête vide, `top_k` invalide, index absent ;
- métriques Precision@k, Recall@k et MRR ;
- baseline lexicale pondérée par IDF pour comparer ;
- client de réponse RAG optionnel via Ollama, limité aux extraits retrouvés et avec
  citations (non exposé dans la démo simplifiée) ;
- démo Streamlit simplifiée : notes d'exemple par défaut, import de notes, réglage
  du nombre de résultats, compteurs et évaluation intégrée.

## Stack

- Python 3.10+
- `sentence-transformers` pour les embeddings
- `faiss-cpu` pour l'index vectoriel
- `streamlit` pour la démonstration
- `pytest` pour les tests
- `numpy` pour les calculs de similarité et le repli sans FAISS
- Ollama (optionnel) pour la génération RAG locale, sans dépendance Python ajoutée

## Arborescence

```text
.
├── search/
│   ├── README.md                   # ce document
│   └── role-card.md                # carte de rôle prête à intégrer au template
├── data/
│   ├── notes_exemple.json          # corpus de démonstration
│   └── evaluation_cases.json       # requêtes annotées pour l'évaluation
├── src/
│   ├── __init__.py
│   ├── corpus.py                   # chargement commun des notes JSON
│   ├── module.py                   # chunking, embeddings, index, recherche
│   ├── build_index.py              # CLI de création des embeddings/index
│   ├── evaluate.py                 # métriques et baseline mots-clés
│   └── llm.py                      # client Ollama et prompt RAG
├── tests/
│   ├── test_search.py              # moteur et évaluation
│   ├── test_llm.py                 # client Ollama
│   ├── test_index.py               # sauvegarde et rechargement de l'index
│   └── test_corpus.py              # chargement des notes JSON
├── demo_app.py                     # interface Streamlit
├── requirements.txt
└── prompts.md                      # journal des prompts et des vérifications
```

## Contrat d'utilisation

### Entrée d'indexation

Une collection de notes, chaque note contenant au minimum :

```python
{
    "id": "note-001",
    "title": "Régularisation et sur-apprentissage",
    "text": "Contenu de la note...",
}
```

### Sortie de recherche

Une liste de `SearchResult` triée par score décroissant :

```python
SearchResult(
    note_id="note-001",
    title="Régularisation et sur-apprentissage",
    passage="Extrait pertinent...",
    score=0.82,
)
```

### Interface du moteur

```python
engine = SemanticSearchEngine(model_name=...)
engine.index(notes, chunk_size=300, overlap=50)
engine.save_index("data/index")
results = engine.search("comment éviter le sur-apprentissage ?", top_k=5)

reloaded = SemanticSearchEngine(model_name=...)
reloaded.load_index("data/index")
results = reloaded.search("comment éviter le sur-apprentissage ?", top_k=5)
```

Le score est une similarité cosinus. Les passages peuvent provenir d'une même note
plusieurs fois s'ils correspondent à des extraits différents.

## Pipeline implémenté

1. Valider et normaliser les notes.
2. Découper le texte en passages. Le moteur utilise 80 mots et 15 mots de
   chevauchement par défaut ; la démo fixe 300 mots et 50 mots de chevauchement.
3. Encoder les passages avec un modèle multilingue adapté au français.
4. Normaliser les vecteurs et construire un index FAISS `IndexFlatIP` (ou NumPy).
5. Sauvegarder éventuellement les passages, les embeddings et l'index.
6. Encoder la requête et récupérer les `top_k` passages les plus proches.
7. Afficher le titre, l'extrait et le score dans Streamlit.
8. Optionnellement, envoyer la question et les extraits à Ollama pour produire une
   réponse ancrée, avec citations.

Le modèle par défaut est
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`. Il est chargé
paresseusement, lors de la première indexation ou du premier encodage de requête.

## Utilisation

```powershell
cd D:\ai-study-assistant\ai-study-assistant\modules\semantic_search
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pytest -q
streamlit run demo_app.py
```

Toutes les commandes du module se lancent depuis
`ai-study-assistant/modules/semantic_search/`.

Sans import, la démo utilise les notes d'exemple et affiche directement la recherche,
les compteurs et l'évaluation. Importer un fichier `.json`, `.txt` ou `.md` remplace
ces notes ; le slider règle le nombre de résultats. L'index est construit avec le
modèle et les paramètres fixés ci-dessus.

Pour créer explicitement les embeddings et l'index :

```powershell
python -m src.build_index --notes data/notes_exemple.json --output data/index
```

Le dossier `data/index/` contient alors :

- `index.json` : modèle utilisé et passages indexés ;
- `embeddings.npy` : matrice NumPy des vecteurs normalisés ;
- `faiss.index` : index FAISS, uniquement si `faiss-cpu` est installé.

Cette étape télécharge le modèle au premier lancement. Elle est optionnelle : la
démo Streamlit reconstruit son index en mémoire. Le dossier `data/index/` est ignoré
par Git.

Pour reproduire l'évaluation en ligne de commande :

```powershell
python -m src.evaluate --baseline-only
python -m src.evaluate
```

Le premier lancement de la démo télécharge le modèle d'embeddings. Une connexion
Internet est donc nécessaire à cette étape, mais pas pour les recherches suivantes.

### Réponse RAG avec Ollama (optionnel)

La démo simplifiée n'expose plus cette option. Le client reste disponible dans
`src/llm.py` pour un appel programmatique.

1. Installer Ollama et lancer le service (`ollama serve`, généralement déjà actif).
2. Télécharger un modèle, par exemple `ollama pull llama3.2`.
3. Appeler `generate_answer(question, results, model="llama3.2")`.

La question et les extraits retrouvés sont envoyés à `/api/chat`. Le prompt impose
de répondre uniquement à partir des extraits, de signaler une information
insuffisante et de citer les sources avec `[1]`, `[2]`, etc. Si Ollama est arrêté ou
si le modèle manque, la recherche sémantique reste utilisable.

## Requêtes d'exemple

Le fichier `data/evaluation_cases.json` contient des questions formulées sans
nécessairement reprendre les mots des notes :

- « Comment éviter qu'un modèle apprenne par cœur ? »
- « Que représente un vecteur d'embedding ? »
- « Comment retrouver un passage par le sens plutôt que par les mots exacts ? »
- « Quel est l'intérêt du RAG pour répondre à une question ? »
- « Comment mesurer la qualité d'un moteur de recherche ? »
- « Comment réviser activement avec des questions ? »

Chaque requête est associée aux identifiants des notes réellement pertinentes.
La démo charge ces notes par défaut et permet de lancer l'évaluation. Dès qu'un
fichier est importé, les notes d'exemple sont remplacées et l'évaluation intégrée
indique qu'il faut retirer les fichiers importés pour l'utiliser.

## Évaluation

L'évaluation compare le moteur sémantique à une baseline par mots-clés sur les
mêmes requêtes :

- **Precision@k** : proportion de résultats pertinents parmi les k premiers ;
- **Recall@k** : proportion de notes pertinentes retrouvées ;
- **MRR** : rang du premier résultat pertinent.

Avec le modèle réel sur ce petit jeu de 6 requêtes :

| Réglages | Moteur | Precision | Recall | MRR |
|---|---|---|---|---|
| CLI, 80/15, k=3 | Sémantique | 0.333 | 0.833 | 0.722 |
| CLI, 80/15, k=3 | Mots-clés | 0.389 | 1.000 | 0.806 |
| Démo, 300/50, k=5 | Sémantique | 0.233 | 1.000 | 0.889 |
| Démo, 300/50, k=5 | Mots-clés | 0.233 | 1.000 | 0.639 |

Ces valeurs sont mesurées, pas inventées. La baseline lexicale reste forte sur ce
corpus très petit, où les questions partagent souvent des mots avec les notes. Le
jeu est trop réduit pour conclure à une supériorité générale du sémantique.

## Limites

- Le corpus fourni est un petit corpus de démonstration, pas les notes réelles.
- Le découpage peut couper une idée ; la taille et le chevauchement sont réglables
  dans le moteur, mais fixés à 300/50 dans la démo.
- Le modèle n'est pas spécialisé sur le cours et peut produire des faux positifs.
- Aucun reranking ni filtre par cours n'est appliqué dans ce MVP.
- L'index peut être sauvegardé avec `python -m src.build_index`, mais la démo
  Streamlit le reconstruit encore en mémoire et ne recharge pas `data/index/`.
- Les métriques portent sur un petit jeu de requêtes et ne remplacent pas une
  évaluation à plus grande échelle.
- Le modèle réel a été exécuté dans le `.venv` du module : 6 notes ont produit 6
  passages et une requête de test a retourné 5 résultats. FAISS n'a pas pu se
  charger sur cette machine (DLL bloquée par une stratégie Windows), donc le
  backend NumPy a été utilisé.
- La couche Ollama a été testée avec un faux serveur HTTP, pas avec un modèle réel
  lancé ici. Une réponse de LLM peut rester imparfaite malgré le prompt : les
  extraits et les citations doivent être vérifiés.
- Le LLM ne remplace pas la recherche : si les bons passages ne sont pas retrouvés,
  la réponse sera mauvaise ou incomplète. La génération reste désactivable.

## Transparence sur l'usage de l'IA

Le cadrage, l'implémentation, les tests et l'interface ont été produits dans un
workflow assisté par IA. Les prompts utilisés, les vérifications et les limites
sont consignés dans `prompts.md`. Chaque choix technique doit pouvoir être expliqué
et défendu à l'oral ; l'IA n'est pas présentée comme un outil magique.
