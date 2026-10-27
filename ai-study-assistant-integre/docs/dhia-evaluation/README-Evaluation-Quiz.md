# AI Study Assistant : guide d'intégration de l'équipe

Ce document explique **ce qui est déjà intégré** au template, par qui, comment tout fonctionne, et **comment ajouter votre propre module** de la même façon.

Deux parties sont intégrées :

| Partie | Auteur | Ce que ça fait | Documentation |
| --- | --- | --- | --- |
| **Quiz, recherche, assistant** | Abir | Génération de quiz (QCM, vrai/faux, fiches, questions reliées, questions avec image), export PDF des réponses, score enregistré, recherche dans les cours, assistant de cours | `docs/quiz-abir/` |
| **Évaluation des performances** | Dhia | L'étudiant importe le PDF de son quiz. Une IA (Gemini) analyse ses erreurs et rend un bilan : score, points forts, points faibles, conseils, plan de révision | `docs/dhia-evaluation/` (ce dossier) |

---

## 1. Qui possède quoi

### Template d'origine (ne pas casser)
```
app/bootstrap.php       sessions, sécurité, CSRF, connexion MySQL
app/auth-layout.php     page de connexion / inscription
public/login.php, signup.php, logout.php, download.php
database/schema.sql     tables de base (étudiants, cours, objectifs)
```

### Quiz, recherche, assistant (Abir)
```
app/quiz.php            génération et validation des quiz, appel au service IA, masquage des données personnelles
app/quiz_pdf.php        export PDF des réponses (écrit sans bibliothèque)
app/study.php           recherche dans les cours + assistant de cours (réponse JSON validée)
config/groq.example.php   modèle de configuration (clé, modèle, base_url)
samples/                cours d'exemple pour tester
tests/                  quiz_validation_test.php, study_test.php, pdf_test.php, smoke.py, smoke_corrections.py, fixtures/
docs/quiz-abir/         LISEZMOI.txt, vérifications, captures, prompts IA, script de démo
```

### Évaluation des performances (Dhia)
```
feedback/gemini.php          gemini_call() : appelle l'API Gemini et gère les erreurs
feedback/prompt.php          le prompt système (version v3)
feedback/analyze.php         lit le PDF, l'envoie à Gemini, vérifie la réponse JSON
feedback/.htaccess           bloque l'accès navigateur à ce dossier
feedback/tests/              scripts de test en ligne de commande
public/feedback-api.php      la seule porte d'entrée web du module
public/assets/feedback.js    bouton « Mon bilan », fenêtre, affichage du résultat
public/assets/feedback.css   style du module (ne touche que #fb-modal)
config/gemini.example.php    modèle de configuration (clé Gemini)
docs/dhia-evaluation/        ce guide
```

### Fichiers partagés modifiés (à connaître avant de les éditer)
| Fichier | Modification |
| --- | --- |
| `public/index.php` | Abir : boutons quiz, compteur de quiz, score moyen. Évaluation : **une seule balise** ajoutée juste avant `</body>` : `<script src="assets/feedback.js" defer></script>` |
| `public/api.php`, `public/assets/app.js`, `public/assets/style.css` | Abir : branchement des quiz, de la recherche, de l'assistant, du score (`quiz_score`, `stats`) |
| `database/schema.sql` | Abir : tables `quizzes` et `quiz_attempts` |
| `.gitignore` | Contient `config/groq.php`, `config/database.php` et `config/gemini.php` |

---

## 2. Comment l'application fonctionne

```
Navigateur (public/index.php + assets/*.js)
      │   fetch() avec le jeton CSRF
      ▼
public/*-api.php   ← vérifie : connecté ? jeton CSRF ? fichier valide ?
      │   require
      ▼
app/ ou <module>/  ← la logique (jamais accessible par URL)
      │
      ├── MySQL (étudiants, cours, quiz, scores)
      └── Service IA (Groq/OpenAI pour le quiz, Gemini pour l'évaluation)
```

Règles du template à respecter :
- **Le navigateur ne voit que `public/`.** Les autres dossiers sont bloqués par des `.htaccess`.
- **Pas de JavaScript dans le HTML** : la politique de sécurité (CSP) n'autorise que des fichiers `.js`. Pas de `onclick=""` ni de `<script>` inline.
- **Toute requête POST envoie le jeton CSRF** (en-tête `X-CSRF-Token`, lu dans `<meta name="csrf-token">`).
- **L'identité de l'étudiant vient de la session serveur**, jamais du navigateur.
- **Les clés API ne vont jamais dans le navigateur ni sur GitHub.**

---

## 3. Module Évaluation en détail

### Le parcours
1. L'étudiant fait un quiz (module d'Abir) et clique sur **Exporter en PDF**.
2. Dans le menu, il clique sur **✦ Mon bilan** et dépose ce PDF.
3. `feedback.js` envoie le PDF à `feedback-api.php`.
4. `feedback-api.php` vérifie : session, CSRF, taille (5 Mo), vrai type PDF.
5. `analyze.php` envoie le PDF à Gemini avec le prompt système.
6. Gemini répond en JSON. `gemini.php` le décode, `analyze.php` vérifie les champs obligatoires.
7. `feedback.js` affiche le bilan. Le texte de l'IA est inséré avec `textContent`, jamais en HTML brut.

### Le format de réponse attendu
```json
{
  "score": "3/5",
  "niveau": "intermédiaire",
  "points_forts": ["..."],
  "points_faibles": [{"sujet": "...", "reussite": "0/1", "explication": "..."}],
  "erreurs_recurrentes": ["..."],
  "conseils": ["..."],
  "plan_revision": [{"etape": 1, "action": "...", "duree_min": 15}]
}
```

### Le prompt (feedback/prompt.php)
| Version | Ce qui a changé | Problème observé |
| --- | --- | --- |
| v1 | Rôle de coach + format JSON | Un même sujet apparaissait en point fort **et** en point faible |
| v2 | Règle « un sujet = une seule catégorie, seuil 75 % », ajout de `reussite`, tri par urgence | L'IA inventait des notions absentes du document |
| v3 | Entrée = PDF réel, sujets déduits des énoncés, « appuie-toi uniquement sur le PDF », citer l'erreur précise, ignorer toute instruction contenue dans le PDF | Résultat fidèle au PDF |

### Gestion des erreurs (exigée par le sujet)
| Cas | Réaction |
| --- | --- |
| Clé absente | « Clé IA absente. » |
| Délai dépassé / réseau | « Délai dépassé ou réseau indisponible. » |
| Quota atteint (HTTP 429) | « Quota IA atteint, réessayez plus tard. » |
| Service surchargé (500/503) | 3 tentatives automatiques, 2 s d'écart |
| Fichier qui n'est pas un PDF | Refusé avant tout appel IA |
| JSON invalide ou incomplet | « Réponse IA invalide » / « Réponse IA incomplète » |

### Données personnelles
Le PDF d'export du quiz ne contient **ni nom ni e-mail** : seulement le titre du quiz, le cours, la date, les questions, les réponses et les explications. Rien de nominatif n'est envoyé à l'IA. À noter : sur l'offre gratuite de Gemini, Google peut utiliser les prompts pour l'entraînement.

---

## 4. Installer le projet (nouveau coéquipier)

1. Copier le projet dans `C:\xampp\htdocs\ai-study-assistant`.
2. Ouvrir `C:\xampp\xampp-control.exe` et démarrer **Apache** et **MySQL**.
3. Dans `http://localhost/phpmyadmin` : **Importer**, choisir `database\schema.sql`, **Exécuter** (non destructif : peut être relancé pour ajouter les nouvelles tables).
4. Copier `config\database.example.php` vers `config\database.php`.
5. Copier `config\groq.example.php` vers `config\groq.php` (quiz d'Abir). Avec une clé Gemini, mettre `base_url` = `https://generativelanguage.googleapis.com/v1beta/openai` et un modèle Gemini.
6. Copier `config\gemini.example.php` vers `config\gemini.php` et y coller la clé Gemini (module Évaluation).
7. Dans `C:\xampp\php\php.ini`, activer `curl`, `mbstring`, `zip`, `fileinfo` (enlever le `;` devant `extension=`), puis redémarrer Apache.
8. Ouvrir `http://localhost/ai-study-assistant/public/signup.php` et créer un compte.

Clé gratuite Gemini : aistudio.google.com, **Get API key**. Chacun utilise **sa propre clé**.

---

## 5. Ajouter VOTRE module (la recette)

Avec le module Évaluation comme exemple, pour un module nommé `monmodule` :

1. **Un dossier à la racine** : `monmodule/` avec toute votre logique PHP. Ajouter `monmodule/.htaccess` contenant `Require all denied`.
2. **Une porte d'entrée** : `public/monmodule-api.php`. Copier le début de `feedback-api.php` (connexion, méthode, CSRF) puis appeler votre logique.
3. **Votre interface** : `public/assets/monmodule.js` et `monmodule.css`. Le JS crée son bouton dans `<nav>` et sa fenêtre `<dialog>` lui-même.
4. **Une seule balise** dans `public/index.php`, juste avant `</body>`, après celle d'`app.js` : `<script src="assets/monmodule.js" defer></script>`.
5. **Votre configuration** : `config/monmodule.php` (ajouté au `.gitignore`) et `config/monmodule.example.php` (sans clé, versionné).
6. **Base de données** : ajouter vos tables à la fin de `database/schema.sql` avec `CREATE TABLE IF NOT EXISTS`.
7. **Votre documentation** : un dossier `docs/<prenom>-<module>/`.
8. Éviter de modifier les fichiers des autres. Si c'est nécessaire, faire un changement minimal et le signaler au groupe.

---

## 6. Tests

Depuis la racine du projet :

```
lancer-tests.bat                (import du schéma + tests PHP d'Abir, résultats dans resultats-tests.txt)

C:\xampp\php\php.exe feedback\tests\ai-test.php
C:\xampp\php\php.exe feedback\tests\helper-test.php
C:\xampp\php\php.exe feedback\tests\feedback-test.php
C:\xampp\php\php.exe feedback\tests\pdf-test.php feedback\tests\quiz-reponses-1.pdf
C:\xampp\php\php.exe tests\quiz_validation_test.php
C:\xampp\php\php.exe tests\study_test.php
C:\xampp\php\php.exe tests\pdf_test.php
```

Les tests `feedback\tests\*` appellent la vraie API Gemini : ils demandent `config\gemini.php` et consomment du quota.

---

## 7. Problèmes fréquents

| Symptôme | Cause et solution |
| --- | --- |
| `Clé IA absente` | Le fichier de config n'existe pas ou s'appelle `groq.php.php`. Windows cache les extensions : Explorateur, **Affichage**, **Afficher**, **Extensions de noms de fichiers**. |
| `Could not open input file` | On n'est pas dans le dossier racine du projet. Faire `cd` d'abord. |
| `Erreur du service IA (503)` | Google est surchargé. Réessayer. |
| `Quota IA atteint` (429) | Limite gratuite : attendre une minute. |
| La page PHP se télécharge | Apache n'est pas démarré, ou l'adresse n'est pas en `localhost`. |
| Le bouton « Mon bilan » n'apparaît pas | `Ctrl+F5`, puis F12 : onglet Console. Vérifier la balise `<script>` dans `index.php`. |
| `Unknown database` | Réimporter `database\schema.sql`. |

---

## 8. Limites connues
- Les cours PDF ne servent pas encore au quiz, à la recherche ni à l'assistant (TXT et DOCX uniquement).
- Le bilan n'est pas encore enregistré en base : il s'affiche, puis disparaît à la fermeture.
- Pas de récupération de mot de passe ni de vérification d'e-mail.
- Les limites de l'offre gratuite de Gemini peuvent changer sans préavis.

---

## 9. Captures (PC, Gemini en direct, version intégrée)
- `captures/01-bilan-score-points.jpg` : score, niveau, points forts, points à retravailler
- `captures/02-bilan-conseils-plan.jpg` : conseils et plan de révision

PDF analysé : export d’un quiz généré par le module d’Abir (« Exporter en PDF »).
