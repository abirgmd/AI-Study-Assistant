# Fiche de bugs — modules 3 (RAG) et 5 (classification)

Projet AI Study Assistant · IA for Software Engineering · A.U 2026-2027
Binôme / auteur : ...................................................... (à compléter)

Méthode suivie (atelier 4) : **un bug = un test qui le reproduit = un correctif = le test relancé**.
Les bugs ci-dessous ont tous été réellement rencontrés pendant le développement assisté par IA
(Claude Code). Pour chacun : comment il a été détecté, sa cause racine, le correctif et la preuve.

## 1. Bugs réels trouvés et corrigés

| # | Fichier / fonction | Symptôme | Cause racine (une phrase) | Détecté par | Correctif | Preuve |
|---|---|---|---|---|---|---|
| B1 | `ai-service/app/main.py` (dépendance `ContainerDep`) | `GET /health` répondait **422** au lieu de 200, avec `fields: ["c"]` | Avec `from __future__ import annotations`, FastAPI résout les annotations dans les variables **globales** du module ; l'alias `ContainerDep` défini *dans* `create_app` était introuvable, le paramètre était pris pour un paramètre de requête | test `test_health_avec_jeton` (pytest) | `get_container` et `ContainerDep` déplacés au niveau du module | `tests/test_security.py` passe |
| B2 | `app/core/embeddings.py` (`HashingEmbedder.encode`) | `ValueError: Dtype of A and B must be the same` | La projection aléatoire était ajustée en float32 alors que les n-grammes hachés arrivaient en float64 | tests `test_hashing_*` | conversion explicite `.astype(np.float32)` avant projection | `tests/test_core.py` passe |
| B3 | `database/schema.sql` (projet de départ) | catégorie par défaut stockée « Ã€ classer » au lieu de « À classer » après un import en ligne de commande | le script ne fixait pas l'encodage de la connexion (`SET NAMES`) : un client `mysql` en latin1 double-encode les accents | test d'intégration HTTP + lecture de la base (`HEX(COLUMN_DEFAULT)`) | `SET NAMES utf8mb4;` ajouté en tête de `schema.sql` et de la migration 002 | valeur hexadécimale `C3 80` = « À » après réimport |
| B4 | `ai-service/scripts/benchmark.py` (mode `--random-weights`) | 222,9 M de paramètres mesurés au lieu des 247,6 M de la fiche officielle de flan-t5-base | la version installée de `transformers` lie la couche de sortie aux embeddings même si `tie_word_embeddings=False` ; flan-t5 (T5 v1.1) ne les lie pas | comparaison du nombre de paramètres mesuré avec la fiche du modèle | la couche `lm_head` est déliée explicitement | 247,6 M paramètres, taille 944,6 Mo (`reports/benchmark/`) |
| B5 | `ai-service/scripts/retrain_with_feedback.py` | 3 « corrections » ajoutées alors qu'un seul cours avait été corrigé | chaque exécution du test d'intégration réenregistrait la même correction ; le script comptait les doublons, donnant trop de poids à un seul document | exécution manuelle du script en `--dry-run` | dédoublonnage par texte (dernière correction gagnante) | `corrections_ajoutees: 1` après correctif |
| B6 | `app/modules/rag/generators.py` (`LocalFlanT5Generator.generate`) | sur une machine sans `torch`, une question renvoyait **500** au lieu d'utiliser la solution de secours | `import torch` était exécuté *avant* `_load()`, donc une `ImportError` brute sortait au lieu d'une `GenerationError` | revue de code (phase 7) | `_load()` appelé en premier (il convertit l'absence de dépendance en `GenerationError`) | `test_flan_t5_sans_transformers` : échoue sur l'ancien code, passe sur le nouveau |
| B7 | même fonction (`_load`) | un modèle introuvable ou un téléchargement impossible renvoyait **500** | `from_pretrained` lève `OSError`, non interceptée, donc le secours extractif n'était jamais déclenché | revue de code (phase 7) | `OSError`/`ValueError` converties en `GenerationError` | `test_flan_t5_modele_introuvable` : échoue sur l'ancien code, passe sur le nouveau |
| B8 | `ai-service/scripts/evaluate_rag.py` | les résultats « seuil calibré » des blocs de 400 et 1200 caractères étaient faussés | le seuil était calibré sur les scores des blocs de 800 caractères puis appliqué aux autres tailles, alors que la distribution des scores dépend de la taille | relecture critique des résultats | recalibrage du seuil pour chaque taille de bloc | colonnes « seuil équilibré » distinctes dans `reports/rag/hashing/generation.csv` |
| B9 | `ai-service/scripts/train_classifier.py` (règle de choix) | deux exécutions identiques ont choisi deux modèles différents (régression logistique puis Naive Bayes) | le départage se faisait sur la latence, dont les écarts (≈ 1 ms) sont du bruit de mesure | relance de l'entraînement | départage par la log-loss en validation croisée (qualité des probabilités, utilisées pour le seuil) | deux relances successives choisissent le même modèle |
| B10 | `ai-service/` servi par Apache (installation XAMPP) | `http://localhost/ai-study-assistant/ai-service/.env` renvoyait **le jeton interne en clair** (HTTP 200) | sous XAMPP, tout le dossier du projet est dans `htdocs` ; le nouveau dossier `ai-service/` (avec `.env`, modèles, données) n'était protégé par aucun `.htaccess`, contrairement à `app/`, `config/`, `storage/` | revue de sécurité (phase 7), vérifiée avec un vrai Apache | `ai-service/.htaccess` et `docs/.htaccess` : `Require all denied` | même requête : 403 ; le dossier `public/` reste accessible (200) |

## 2. Erreurs dans les tests générés par l'IA (faux positifs des tests)

| Test | Problème | Correction |
|---|---|---|
| `test_document_piege_ne_peut_pas_sortir_du_contexte` | le test exigeait **une seule** balise `</contexte>`, alors que la consigne du prompt v3 en contient légitimement une deuxième (« entre les balises <contexte> et </contexte> ») ; le test échouait sur un code correct | le test compare désormais le nombre de balises à celui du gabarit |
| `test_prediction_et_explication` | assertion vide `abs(...) >= 0`, toujours vraie : le test ne vérifiait rien | remplacée par deux vérifications réelles (confiance = 1re probabilité, probabilités triées) |
| `test_pretraitement` | a révélé des espaces multiples dans le texte prétraité (sans effet sur les vecteurs TF-IDF, mais non conforme à la spécification) | `preprocess` réduit maintenant les espaces |

## 3. Revue de code critique (phase 7) : remarques non corrigées

Classement : **bug réel** (corrigé ci-dessus), **risque** (documenté, accepté pour le projet), **préférence** (style).

| Remarque | Classement | Décision |
|---|---|---|
| Les verrous d'écriture des index sont des `threading.Lock` : avec plusieurs workers uvicorn, deux processus pourraient écrire le même index | risque | le service se lance avec **un seul worker** (documenté) ; un verrou de fichier serait nécessaire au-delà |
| `RagService.ask` relit l'index sur le disque deux fois (version, puis recherche) | risque (performance) | négligeable pour quelques milliers de blocs ; à mettre en cache mémoire si le volume augmente |
| L'indexation est synchrone pendant l'import : un gros PDF avec MiniLM sur CPU peut prendre plusieurs dizaines de secondes | risque | délai PHP de 180 s ; une file de tâches (worker) serait la solution en production |
| `joblib.load` repose sur pickle (exécution de code possible) | risque (sécurité) | seul le fichier produit par nos scripts est chargé, jamais un fichier reçu |
| `rag_queries` conserve les questions des étudiants (donnée personnelle) | risque (RGPD) | suppression en cascade avec le compte ; une durée de conservation reste à définir |
| `feedback.csv` copie 3 000 caractères du cours corrigé | risque (confidentialité) | fichier ignoré par Git ; à anonymiser ou supprimer après réentraînement |
| Avec les embeddings « hashing », une question hors cours a reçu une réponse extractive hors sujet (1 sur 5) | limite mesurée | voir le rapport ; le passage à MiniLM et le recalibrage du seuil sont la piste prévue |
| `Container` prend un verrou à chaque accès aux propriétés | préférence | conservé : simple et sûr |
| Avertissement de dépréciation `httpx` du `TestClient` de Starlette | préférence | sans effet sur les tests ; à suivre lors d'une mise à jour |

## 4. Bilan

- **Le type de bug le plus facile à trouver pour l'IA** : les erreurs d'enchaînement (ordre des imports, exceptions non converties, B6 et B7) — repérées en relisant le code avec la question « que se passe-t-il si cette dépendance manque ? ».
- **Le type de bug le plus difficile pour elle** : les bugs qui ne cassent rien mais faussent les résultats (B4, B8, B9). Aucun test unitaire ne les détecte ; il a fallu comparer les chiffres à une référence externe ou relancer les expériences.
- **Habitude gardée** : écrire le test qui reproduit le bug *avant* le correctif, puis vérifier qu'il échoue bien sur l'ancien code (fait pour B6 et B7).

*À compléter par l'étudiant : un correctif proposé par l'IA que vous avez refusé, et pourquoi.*
