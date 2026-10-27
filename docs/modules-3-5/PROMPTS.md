# Journal des prompts — modules 3 (RAG) et 5 (classification)

Étudiant(e) : ...................................................... Date : 25/10/2026
Assistant utilisé : **Claude Code** (modèle Claude Opus, Anthropic), dans un terminal sur le dépôt.

## Comment ce journal a été produit

- Le prompt complet envoyé à Claude Code est dans `docs/prompts/PROMPT_CLAUDE_CODE.md` (structure :
  contexte, architecture imposée, règles non négociables, 9 phases).
- Le prompt demandait de s'arrêter après chaque phase. **À la demande de l'étudiant(e)**
  (« fais tout le travail et donne-moi le zip »), les phases ont été enchaînées en une seule session :
  les verdicts ci-dessous doivent donc être remplis **après relecture**, phase par phase.
- La colonne « Verdict de l'étudiant » est volontairement vide : c'est elle qui est évaluée.
  Valeurs possibles : accepté / corrigé / rejeté, avec une phrase de justification.

## Tableau de bord

| # | Phase | Demande (résumée) | Ce que l'IA a produit | Problèmes rencontrés | Verdict de l'étudiant |
|---|---|---|---|---|---|
| 0 | Analyse et socle | Lire le code, créer `ai-service/` (config, jeton interne, /health), migration 002, `ai_request()` en PHP | Service FastAPI avec jeton comparé à temps constant, migration rejouable MySQL/MariaDB, client cURL PHP avec délais | **B1** : `/health` répondait 422 (annotation FastAPI) — trouvé par un test ; **B3** : accents doublement encodés dans `schema.sql` | |
| 1 | Socle partagé | Extraction PDF/DOCX/TXT, découpage avec chevauchement, embeddings MiniLM chargés une fois | `extraction.py`, `chunking.py`, `embeddings.py` + embedder « hashing » hors ligne ; 24 tests | **B2** : types float32/float64 incompatibles ; Hugging Face inaccessible dans l'environnement → ajout d'un backend hors ligne | |
| 2 | RAG de bout en bout | Index FAISS par étudiant, seuil d'abstention, prompt v1/v2/v3, Strategy (flan-t5 / API), cache | `store.py`, `prompt.py`, `generators.py` (3 stratégies + secours), `cache.py`, `service.py`, routes `/rag/*` | un test généré était faux (nombre de balises `<contexte>`) ; ajout d'un générateur **extractif** non demandé, utile comme secours | |
| 3 | RAG dans l'application | Indexation à l'import, action `ask`, limite de débit, interface, historique | `api.php` (ask, history, reindex, delete), `app.js` (assistant, sources, historique), test HTTP étendu | aucune régression du test d'origine ; service arrêté → import réussi + message clair (vérifié) | |
| 4 | Évaluation et optimisation RAG | 25 questions + 5 hors cours, Hit@k, MRR, seuil, prompts, k, taille des blocs, L2/IP, quantization, cache | `evaluate_rag.py`, `benchmark.py`, `rag_eval.csv` (sur les vrais chapitres 5, 6 et séance 4) | **B8** (seuil calibré sur une seule taille) ; **B4** (paramètres de flan-t5 sous-comptés) ; flan-t5 et MiniLM **non mesurables** ici (Hugging Face bloqué) | |
| 5 | Dataset et modèles scikit-learn | 60-80 paragraphes par catégorie, test réel, 5 modèles, GridSearchCV, seuil, explicabilité | 482 paragraphes générés, 83 extraits **réels** des supports du module, `train_classifier.py`, `evaluate_classifier.py` | le seuil 0,5 du prompt laissait 90 % des cours « À classer » → seuil choisi en validation croisée ; **B9** (choix du modèle instable) ; Wikipédia inutilisable comme « données réelles » (l'outil ne rend que des reformulations) | |
| 6 | Classification dans l'application | `/classify`, classement à l'import, badge, filtre, correction, réentraînement | badge + confiance, filtre, fenêtre de correction avec **suggestion** du modèle, `retrain_with_feedback.py` | **B5** : corrections comptées plusieurs fois | |
| 7 | Tests, revue, CI | Couverture ≥ 80 %, revue critique, BUG_REPORT, GitHub Actions | 92 tests, couverture 96 % (95 % sans torch), `ruff` propre, workflow CI, `BUG_REPORT.md` | **B6** et **B7** trouvés en revue, avec tests de régression qui échouent sur l'ancien code ; **B10** : `ai-service/.env` lisible par le web sous XAMPP, corrigé et vérifié avec Apache | |
| 8 | Documentation | Rapport individuel, README, INSTALLATION | `docs/DOCUMENTATION_INDIVIDUELLE.md`, READMEs, captures d'écran | les chiffres flan-t5 / MiniLM restent « à mesurer » sur votre machine | |

Messages de commit proposés (à faire vous-même, sur votre branche) :

```text
feat(ia): socle du service IA (FastAPI, jeton interne, migration 002)
feat(ia): extraction, découpage et embeddings partagés
feat(rag): index FAISS par étudiant, prompt v3, génération et cache
feat(rag): assistant de cours dans l'interface + test HTTP
test(rag): évaluation Hit@k/MRR, seuil, taille des blocs, quantization
feat(classification): dataset, comparaison de 5 modèles, seuil en validation croisée
feat(classification): catégorie à l'import, correction par l'étudiant, réentraînement
test: couverture 96 %, revue de code (BUG_REPORT), CI GitHub Actions
docs: documentation individuelle modules 3 et 5
```

## Prompts du produit (utilisés PAR l'application)

Ils sont versionnés dans `ai-service/prompts/` et décrits dans le rapport (section 5) :

| Fichier | Rôle | Statut |
|---|---|---|
| `rag_v1.txt` | prompt naïf (contexte + question) | conservé pour comparaison |
| `rag_v2.txt` | rôle, tâche, format, citations | conservé pour comparaison |
| `rag_v3.txt` | v2 + contexte isolé entre balises, anti-injection, abstention exacte | **production** |
| `rag_no_context.txt` | question seule (mesure « sans RAG ») | évaluation |
| `dataset_generation.txt` | génération du jeu d'entraînement du module 5 | exécuté une fois |

## À compléter par vous (obligatoire pour la note)

### Deux cas où l'IA s'est trompée (exemples réels de la session, à reformuler avec vos mots)

1. **Seuil de confiance 0,5 imposé au module 5** — appliqué tel quel, il laissait 90 % des cours
   non classés (probabilités diffuses sur 8 classes). Détecté en lisant `seuil_confiance.csv`.
   Correction : seuil choisi en validation croisée (0,75 pour le modèle retenu).
   *Votre analyse :* ...
2. **Test généré faux** (`test_document_piege...`) : il échouait sur un code correct.
   *Votre analyse :* ...

### Bilan (3 lignes)

- Le prompt qui a le mieux fonctionné, et pourquoi : ...
- Le prompt qui a échoué, et pourquoi : ...
- Ce que je ferais différemment la prochaine fois : ...
