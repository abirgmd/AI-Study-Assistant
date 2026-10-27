# Rapport des prompts et des bugs — Module 3

## 1. Rôle du rapport

Ce document garde la trace des prompts utilisés pendant la conception du module 3. Les supports de cours ont servi à comprendre les notions de RAG, de prompt engineering, de génération et d’optimisation. Ils servent aussi à justifier les choix techniques du projet.

Les prompts de développement ne sont pas les mêmes que le prompt utilisé par l’assistant pour répondre aux étudiants.

## 2. Prompt de production du module 3

Le prompt de production est [rag_v3.txt](./prompts/rag_v3.txt).

Son utilité est de contrôler la réponse du modèle :

- le rôle est celui d’un assistant pédagogique ;
- le contexte est limité aux passages retrouvés ;
- les documents sont considérés comme des données ;
- le modèle doit refuser si la réponse n’est pas dans le contexte ;
- la langue, la longueur et le format des citations sont imposés.

Ce prompt est adapté au mode « Mes cours ». Il ne doit pas être utilisé pour faire croire qu’une réponse générale provient d’un document de l’étudiant.

## 3. Prompts envoyés pendant cette conversation

| Prompt ou demande | Utilité dans le projet | Résultat attendu |
|---|---|---|
| « Lire le projet et expliquer le module 3 sans coder » | Comprendre le pipeline existant avant toute modification | Description de l’extraction, du découpage, des embeddings, de FAISS, du seuil et des sources |
| « Brièvement, que fait le module 3 ? » | Préparer une explication courte pour la présentation | Définition simple du RAG et de son rôle dans l’application |
| « Peut-on utiliser RAG + Ollama avec des techniques d’optimisation ? » | Choisir un modèle local et relier le projet aux notions du cours | Ollama pour la génération, quantification, cache, réglage des blocs et évaluation |
| « Lire le cours et la grille d’évaluation » | Relier les fonctionnalités aux critères de notation | Plan de démonstration, mesures, documentation et justification des choix |
| « Les supports sont nécessaires pour créer le projet, pas pour créer les questions du site » | Corriger l’interprétation du besoin | Les questions du site peuvent porter sur n’importe quel cours importé par l’étudiant |
| « L’étudiant ajoute un cours et pose une question » | Définir le comportement fonctionnel principal | Réponse basée sur les propres documents de l’étudiant |
| « Une question sans cours peut utiliser Ollama » | Définir un second mode contrôlé | Réponse étiquetée « connaissance générale », séparée des sources RAG |
| « Créer un rapport du module et un rapport des bugs » | Préparer les livrables individuels | Documentation du fonctionnement, des prompts, des décisions et des bugs rencontrés |

## 4. Prompts proposés pour obtenir de bonnes réponses du système

### Question avec réponse dans le cours

« Réponds à cette question uniquement avec les passages de mon cours. Donne une réponse courte, cite le titre et la page de chaque passage utilisé, et indique clairement si l’information est absente. »

### Question absente du cours

« Vérifie d’abord mes cours. Si l’information n’y existe pas, ne présente pas une connaissance générale comme une information provenant de mes documents. Réponds que l’information n’est pas trouvée dans mes cours. »

### Mode connaissance générale avec Ollama

« Réponds à cette question en connaissance générale. N’utilise pas les documents de l’étudiant comme source implicite. Marque la réponse comme “connaissance générale” et signale que les faits actuels doivent être vérifiés. »

## 5. Bugs réellement rencontrés

Les bugs ci-dessous viennent de [BUG_REPORT.md](../../BUG_REPORT.md) et sont regroupés ici selon leur lien avec le module 3.

| Bug | Symptôme | Cause | Correction ou décision |
|---|---|---|---|
| B1 | `/health` retournait 422 | Annotation FastAPI définie au mauvais niveau avec les annotations différées | Dépendance déplacée au niveau du module et test de régression ajouté |
| B2 | Erreur de type dans les embeddings hashing | Mélange float32/float64 | Conversion explicite avant la projection |
| B6 | Absence de torch provoquait une erreur 500 | Import effectué avant la conversion vers `GenerationError` | Déclenchement du secours extractif |
| B7 | Modèle local introuvable provoquait une erreur 500 | `OSError` non interceptée pendant le chargement | Erreur convertie et secours extractif activé |
| B8 | Seuil incorrect pour certaines tailles de blocs | Seuil calibré uniquement sur les blocs de 800 caractères | Recalibrage pour chaque taille de bloc |
| B10 | Jeton interne visible sous Apache/XAMPP | Dossier `ai-service` non protégé par `.htaccess` | Accès web interdit au dossier du service |
| Tests générés par IA | Test des balises du contexte faux | Le test comptait mal les balises légitimes du gabarit | Comparaison avec le gabarit réel |
| Réorganisation interrompue | Certains tests et scripts référençaient `app.modules.rag` alors que le code était dans `Module_3` | Déplacement interrompu avant la mise à jour de toutes les références | Références Python mises à jour vers `Module_3.rag`; tests ciblés relancés avec succès |

## 6. Méthode de correction

Pour chaque bug :

1. reproduire le problème ;
2. identifier la cause racine ;
3. écrire ou vérifier un test de régression ;
4. appliquer le correctif ;
5. relancer le test ;
6. documenter la preuve.

Cette méthode correspond à l’objectif du cours sur la détection intelligente des bugs : l’IA peut proposer une solution, mais la solution doit être vérifiée par des tests et une revue humaine.

## 7. Trace complete de notre discussion

Cette section conserve les demandes qui ont guide la conception et les essais du module 3, depuis la comprehension du besoin jusqu a l optimisation.

| Demande de la discussion | Decision prise | Preuve dans le projet |
|---|---|---|
| Expliquer le module 3 sans coder | Comprendre le fonctionnement avant toute modification | Ce rapport et RAPPORT_MODULE_3.md |
| Le cours sert a comprendre la matiere, pas a limiter les questions du site | Accepter des cours arbitraires : mathematiques, physique, sciences, etc. | Import et index individuel par etudiant |
| Un etudiant ajoute un cours et pose une question | Utiliser extraction, decoupage, embeddings, FAISS, recherche et generation | Module_3/rag/service.py |
| Une question sans cours peut utiliser Ollama | Ajouter un mode Connaissance generale separe des sources RAG | Champ scope dans l API et selecteur dans l interface |
| Utiliser RAG + Ollama avec optimisation | Ajouter un generateur Ollama et comparer les modeles | Module_3/rag/generators.py et .env |
| Viser 10/10 selon la grille | Documenter choix, prompts, bugs, tests, limites et performances | Rapports du dossier Module_3 |
| Les reponses Ollama sont lentes | Comparer llama3:8b et qwen2.5:3b et reduire la longueur des sorties | qwen2.5:3b et 80 tokens |
| Redemarrer le service | Recharger la configuration puis verifier /health | Service FastAPI sur 127.0.0.1:8001 |

## 8. Bugs et incidents rencontres pendant le lancement reel

| Incident | Symptome observe | Cause | Solution appliquee | Statut |
|---|---|---|---|---|
| Configuration locale absente | Le service IA ne demarrait pas correctement | ai-service/.env et config/ai.php absents | Creation des fichiers locaux ignores par Git avec un jeton commun | Resolu |
| Migration de base absente | L interface affichait une erreur 503 | Les tables RAG n existaient pas | Import de database/migrations/002_ai_modules.sql | Resolu |
| PHP absent du PATH | php -S ne fonctionnait pas directement | PHP etait installe dans XAMPP | Utilisation de C:\\xampp\\php\\php.exe | Resolu |
| Embeddings indisponibles | L indexation retournait 503 | sentence-transformers absent de l interpreteur utilise | Passage temporaire a AI_EMBEDDING_BACKEND=hashing | Resolu pour le test |
| Question absente du cours | Le systeme repondait qu il ne trouvait pas l information | La question ne figurait pas dans le document indexe | Abstention conservee contre les hallucinations | Comportement valide |
| Reponse Ollama lente | L interface restait en attente avec llama3:8b | Modele de 8B lourd pour la machine et aucune diffusion progressive | Installation de qwen2.5:3b, limite a 80 tokens et redemarrage | Configuration appliquee |
| Acces sans jeton | /health retournait 401 sans en-tete interne | Protection volontaire du service IA | Test relance avec X-Internal-Token | Comportement valide |

## 9. Preuves de validation

- Ollama contient llama3:8b, qwen2.5:3b et nomic-embed-text.
- Le service IA a repondu status: ok apres le redemarrage.
- Le modele actif est configure dans ai-service/.env avec AI_OLLAMA_MODEL=qwen2.5:3b.
- Le site PHP a repondu HTTP 200 sur le port 8000.
- Un cours a ete indexe et affiche comme Pret pour l assistant.
- Une question hors contexte a ete refusee au lieu d etre inventee.
- La suite de tests Python a ete executee avec succes apres la reorganisation.

Les temps exacts doivent etre mesures sur la machine lors de la presentation. Il faut distinguer le chargement initial du modele, la recherche RAG, la generation et le temps total affiche par l interface.

## 10. Limites et transparence

- Une réponse Ollama n’est pas automatiquement vraie parce qu’elle est générée localement.
- Une réponse sans source de cours doit être signalée comme connaissance générale.
- Les questions d’actualité ou les faits sensibles doivent être vérifiés séparément.
- Le rapport final doit distinguer les mesures réellement exécutées des objectifs proposés.
- Les bugs B6, B7 et B8 montrent qu’une réponse ou un résultat plausible peut être incorrect sans test adapté.

