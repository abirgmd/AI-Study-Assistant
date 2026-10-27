# Intégration du module 2 dans l'application PHP

## Principe

La recherche sémantique est un outil du menu de l'application étudiante. Elle
cherche par le sens dans les cours **TXT** et **DOCX** de l'étudiant connecté.

```text
Navigateur
  └─ public/index.php
       └─ public/assets/semantic-search.js
            └─ GET public/semantic-search-api.php?q=...&top_k=...
                 └─ app/semantic_search.php
                      ├─ lit les cours TXT/DOCX (app/quiz.php)
                      └─ POST http://127.0.0.1:8002/search
                           └─ modules/semantic_search/service.py
                                └─ sentence-transformers + FAISS
```

Le service Python est **local** : il écoute sur `127.0.0.1` et n'est pas joignable
depuis le réseau. L'API PHP vérifie la session étudiante et ne renvoie que les
cours de l'étudiant connecté. Aucun extrait de cours n'est envoyé à un service
externe ; seul le modèle est téléchargé depuis Hugging Face au premier lancement.

## Fichiers ajoutés

| Fichier | Rôle |
| --- | --- |
| `modules/semantic_search/service.py` | Service HTTP `/health` et `/search`, cache des index, jeton. |
| `app/semantic_search.php` | Validation, extraction des cours, appel HTTP, mise en forme. |
| `public/semantic-search-api.php` | API JSON protégée par la session étudiante. |
| `public/assets/semantic-search.js` | Bouton **Recherche sémantique** et fenêtre de recherche. |
| `public/assets/semantic-search.css` | Style isolé de la fenêtre. |
| `config/semantic-search.example.php` | Exemple de configuration locale. |
| `lancer-recherche-semantique.bat` | Démarre le service Python sur le port 8002. |
| `lancer-tests-semantic-search.bat` | Lance pytest, le test PHP et le smoke test HTTP. |
| `tests/semantic_search_test.php` | Tests unitaires de l'intégration PHP. |
| `tests/smoke_semantic_search.py` | Test HTTP du service avec l'embedder de test. |
| `modules/semantic_search/tests/test_service.py` | Tests du cache, de la validation et du service. |

Le seul fichier existant modifié est `public/index.php` : une balise
`<script src="assets/semantic-search.js" defer></script>` a été ajoutée. Les
autres modules ne sont pas touchés.

## Installation

### 1. Dépendances Python

Le lanceur crée l'environnement virtuel du module s'il n'existe pas :

```powershell
lancer-recherche-semantique.bat
```

Sinon, manuellement :

```powershell
cd modules\semantic_search
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

### 2. Application PHP

MySQL doit être démarré et le schéma importé :

```powershell
C:\xampp\mysql\bin\mysql.exe -uroot --default-character-set=utf8mb4 < database\schema.sql
```

Puis lancer Apache/XAMPP et ouvrir l'application, se connecter et importer un
cours **TXT** ou **DOCX** (les PDF sont ignorés par ce module pour le moment).

### 3. Service de recherche

Dans une fenêtre séparée, à laisser ouverte :

```powershell
lancer-recherche-semantique.bat
```

Le premier démarrage télécharge le modèle
`sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` et peut prendre
plusieurs minutes. Les démarrages suivants utilisent le cache local.

## Configuration

Valeurs par défaut :

- URL : `http://127.0.0.1:8002`
- Jeton : `demo-semantic-search-token`
- Délai maximal : 120 secondes

Pour personnaliser, copier l'exemple :

```powershell
copy config\semantic-search.example.php config\semantic-search.php
```

Le fichier `config/semantic-search.php` est ignoré par Git. Le jeton doit être
identique à la variable `SEMANTIC_SEARCH_TOKEN` utilisée au lancement :

```powershell
set SEMANTIC_SEARCH_TOKEN=mon-jeton-local
lancer-recherche-semantique.bat
```

L'application lit aussi `SEMANTIC_SEARCH_URL` et `SEMANTIC_SEARCH_TOKEN` dans
l'environnement, ce qui est pratique pour un poste de démonstration.

## Contrat HTTP du service

### `GET /health`

```json
{"status": "ok", "service": "semantic-search", "embedder": "sentence-transformers", "model": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"}
```

### `POST /search`

En-tête obligatoire :

```text
Authorization: Bearer <jeton>
```

Corps :

```json
{
  "query": "comment éviter le sur-apprentissage ?",
  "top_k": 5,
  "notes": [
    {"id": "12", "title": "Apprentissage automatique", "text": "..."}
  ]
}
```

Réponse :

```json
{
  "results": [
    {"note_id": "12", "title": "Apprentissage automatique", "passage": "...", "score": 0.73}
  ],
  "backend": "faiss",
  "notes": 1,
  "passages": 4
}
```

Limites : question de 2 à 200 caractères, 1 à 10 passages, 30 cours au plus,
24 000 caractères par cours, 50 cours au plus pour le service. Une requête sans
jeton reçoit `401` ; une requête invalide reçoit `422`.

## Tests

```powershell
lancer-tests-semantic-search.bat
```

Le script lance :

1. les tests Python du module (`pytest`) ;
2. le test PHP d'intégration (`tests/semantic_search_test.php`) ;
3. le smoke test HTTP du service (`tests/smoke_semantic_search.py`).

Le smoke test démarre un service temporaire avec l'embedder de test (aucun
téléchargement de modèle), vérifie `/health`, le refus sans jeton, le classement
et la validation, puis arrête le service. Il ne nécessite ni MySQL ni serveur PHP.

Pour un test complet avec l'interface :

1. démarrer MySQL et importer `database/schema.sql` ;
2. démarrer Apache/XAMPP (ou `php -S 127.0.0.1:8000 -t public`) ;
3. lancer `lancer-recherche-semantique.bat` ;
4. se connecter, importer un cours TXT/DOCX contenant un paragraphe sur le sujet ;
5. cliquer sur **Recherche sémantique**, poser une question et vérifier le nom du
   cours et le passage affichés ;
6. arrêter le service et vérifier que l'application affiche un message explicite
   sans bloquer les autres modules.

## Dépannage

| Symptôme | Cause probable | Solution |
| --- | --- | --- |
| « Service de recherche sémantique indisponible » | Service arrêté ou port occupé | Lancer `lancer-recherche-semantique.bat`, vérifier le port 8002. |
| « jeton invalide » | Jeton différent entre PHP et service | Aligner `config/semantic-search.php` et `SEMANTIC_SEARCH_TOKEN`. |
| « Aucun cours TXT ou DOCX lisible » | Cours PDF uniquement ou fichiers vides | Importer un TXT ou un DOCX non vide. |
| Le premier appel est très long | Téléchargement du modèle | Attendre la fin du téléchargement ; les appels suivants sont plus rapides. |
| Le service démarre puis s'arrête | Dépendances manquantes | Relancer le lanceur, vérifier `pip install -r requirements.txt`. |

## Limites connues

- Les PDF ne sont pas lus par ce module ; la recherche lexicale existante continue
  de les gérer selon les modules.
- Le service construit un index en mémoire par contenu de cours (cache de 8
  contenus) ; un changement de cours est détecté automatiquement.
- Le modèle multilingue privilégie le français et l'anglais ; les résultats restent
  indicatifs et doivent être vérifiés dans le cours.
- Le service n'est pas conçu pour être exposé sur Internet : garder
  `127.0.0.1` et un jeton local.
