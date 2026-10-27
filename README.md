# AI Study Assistant — espace étudiant

Projet PHP 8.1+ / MySQL 8+ (ou MariaDB 10.4+) sans dépendance Composer.
Consultez **INSTALLATION.txt** pour XAMPP et le démarrage local.

## Modules et documentation

| Module | Auteur | Code | Documentation |
| --- | --- | --- | --- |
| Quiz, recherche, assistant de cours | Abir | `app/quiz.php`, `app/quiz_pdf.php`, `app/study.php`, `public/api.php`, `public/assets/app.js` | [`docs/quiz-abir/`](docs/quiz-abir/) |
| Évaluation des performances (« Mon bilan ») | Dhia | `feedback/`, `public/feedback-api.php`, `public/assets/feedback.js`, `public/assets/feedback.css` | [`docs/dhia-evaluation/`](docs/dhia-evaluation/) |
| Assistant IA 2 (module 3 : questions sur les cours, sources) et matière des cours (module 5 : classification) | Modules 3 et 5 | `ai-service/`, `ia-modules/`, `public/ia-api.php`, `public/assets/ia-modules.js`, `public/assets/ia-modules.css` | [`docs/modules-3-5/`](docs/modules-3-5/) |

Le guide d’intégration de l’équipe (comment ajouter un module) est dans `docs/dhia-evaluation/README-Evaluation-Quiz.md`.

## Structure

- `public/` : pages publiques, accueil protégé, API et ressources CSS/JS.
- `app/` : connexion PDO, sessions, fonctions de sécurité et gabarit d’authentification.
  `app/quiz.php` : génération et validation des QCM (extraction du cours, appel IA, contrôles).
  `app/study.php` : recherche dans les cours et assistant de cours (réponse fondée sur un cours).
- `config/database.example.php` : configuration à copier vers `database.php`.
- `config/groq.example.php` : clé et modèle du service IA (quiz), à copier vers `groq.php`.
- `database/schema.sql` : base et tables, sans compte prédéfini.
- `storage/courses/` : documents privés (accès via `download.php`).
- `samples/` : cours d’exemple et quiz de référence (contrôlés par les tests).
- `tests/` : tests unitaires du quiz et de l’assistant, tests HTTP d’intégration.
- `feedback/` : module Évaluation (Gemini), bloqué au navigateur ; tests dans `feedback/tests/`.
- `config/gemini.example.php` : clé Gemini du module Évaluation, à copier vers `gemini.php`.
- `docs/` : documentation par membre (`quiz-abir/`, `dhia-evaluation/`).
- `lancer-tests.bat` : import du schéma + tous les tests PHP sous XAMPP (Windows).

## API authentifiée

| Route | Méthode | Fonction |
| --- | --- | --- |
| `api.php?action=courses` | GET | Cours du compte connecté |
| `api.php?action=upload` | POST | Import multipart, champ `course` |
| `api.php?action=goals&date=YYYY-MM-DD` | GET | Objectifs de cette date (plus utilisé par l’accueil) |
| `api.php?action=goals&date=YYYY-MM-DD` | POST | Champs `index` (0 à 2), `completed` (0 ou 1) |
| `api.php?action=quiz_generate` | POST | Génère un quiz depuis un cours TXT ou DOCX : champs `course_id`, `count` (3 à 10), `kind` (`mixed`, `mcq`, `true_false`, `flashcard`, `matching`, `image`) |
| `api.php?action=quizzes` | GET | Quiz enregistrés du compte |
| `api.php?action=quiz&id=ID` | GET | Un quiz du compte, avec ses questions |
| `api.php?action=search&q=TEXTE` | GET | Recherche dans les cours TXT et DOCX (2 à 100 caractères) : passages et nombre de cours ignorés |
| `api.php?action=assistant` | POST | Réponse JSON validée (`answer`, `found_in_course`) à une question sur un cours TXT ou DOCX : champs `course_id`, `question` (3 à 500 caractères) |
| `api.php?action=quiz_score` | POST | Enregistre le score d’un quiz corrigé (recalculé côté serveur) : champs `quiz_id`, `answers` (JSON) |
| `api.php?action=stats` | GET | Nombre de quiz corrigés et score moyen du compte |
| `download.php?id=ID` | GET | Téléchargement du document appartenant au compte |

Toute mutation exige le jeton CSRF de la session. L’identifiant étudiant provient
uniquement de la session serveur. Aucun rôle transmis par le navigateur n’est accepté.

## Quiz IA

Le modèle reçoit le cours, délimité comme donnée, et doit répondre selon un schéma JSON
strict. Types proposés : QCM (quatre propositions), vrai/faux, fiches recto/verso (non
notées), questions reliées (3 à 4 couples, menus de choix), questions avec image (images
PNG ou JPEG tirées d’un DOCX, lues par `vision_model`), ou un mélange. Chaque élément est
contrôlé côté serveur : propositions distinctes, lettre de bonne réponse valide, pas de
« toutes les réponses », pas de doublon, longueurs raisonnables, une image par question.
Les éléments défectueux sont écartés, et les propositions sont mélangées pour que la bonne
réponse ne soit pas toujours A.

## Service IA des modules 3 et 5 (Assistant IA 2)

Le bouton **Assistant IA 2** (menu, à côté d'« Assistant IA ») pose des questions sur vos cours et affiche les sources. La matière de chaque cours est détectée à l'import et peut être corrigée. Les deux fonctions s'appuient sur un service Python local, `ai-service/`, qui écoute sur `127.0.0.1:8001`.

1. Dans `ai-service/`, créer l'environnement : `python -m venv .venv`, puis `.venv\Scripts\activate` et `pip install -r requirements-ci.txt` (version légère ; `requirements.txt` ajoute les modèles complets).
2. Copier `ai-service/.env.example` vers `ai-service/.env` et `config/ia-service.example.php` vers `config/ia-service.php`. Le **même** jeton doit figurer dans les deux fichiers (32 caractères minimum).
3. Lancer le service : `cd ai-service` puis `uvicorn app.main:create_app --factory --host 127.0.0.1 --port 8001`.
4. Importer `database/schema.sql` dans phpMyAdmin (non destructif : il ajoute les colonnes et tables du module).
5. Facultatif : Ollama (`ollama pull qwen2.5:3b`) pour des réponses rédigées. Sans Ollama, l'assistant répond par extraits du cours (mention « extractif (secours) »).

Si le service est arrêté, l'import reste valide : le cours est simplement marqué « Non indexé », à indexer depuis la fenêtre Assistant IA 2.

Tests : `lancer-tests-ia.bat` (syntaxe, tests unitaires, pytest). Test HTTP de bout en bout, service démarré : `python tests\smoke_ia.py http://localhost/ai-study-assistant-integre/public/`.

## Recherche et assistant

`search` cherche les mots, sans accents ni casse, dans le texte des cours TXT et DOCX, sans IA. `assistant` envoie la question et les passages utiles du cours au service IA avec un schéma JSON strict (`answer`, `found_in_course`) et la consigne de répondre uniquement à partir du cours ; la réponse est validée côté serveur avant affichage. Les PDF ne sont lus ni par la recherche ni par l’assistant.

## Règles IA respectées

- **Données personnelles** : `ai_mask_personal_data()` (app/quiz.php) remplace e-mails, téléphones, IBAN et liens par `[EMAIL]`, `[TÉLÉPHONE]`, `[IBAN]`, `[LIEN]` avant tout appel au modèle.
- **Sortie validée** : quiz et assistant répondent selon un schéma JSON strict, contrôlé côté serveur ; une sortie non conforme n’est jamais affichée.
- **Erreurs d’appel API** : clé absente (503), clé refusée, crédit épuisé (402), limite de débit (429), requête trop lourde (413), délai dépassé (504), service injoignable (502).
- **Clé API** : `config/groq.php` est exclu du dépôt (`.gitignore`) ; seul `config/groq.example.php` est versionné.

## Validation

Les scripts Python `tests/smoke.py` (test HTTP d’origine) et `tests/smoke_corrections.py` (corrections : assistant, isolation) doivent être lancés sur une installation locale isolée,
avec une base importée et le serveur actif. Ils créent des comptes de test et un document.
Ils utilisent uniquement la bibliothèque standard Python. Vérifications manuelles : `docs/quiz-abir/VERIFICATIONS.md`.

Les tests du quiz et de la recherche ne demandent ni base ni serveur : `php tests/quiz_validation_test.php` et `php tests/study_test.php`.
