# Rapport du module 3 — Assistant de cours RAG

Projet : AI Study Assistant  
Matière : IA for Software Engineering  
Module : 3 — Questions-réponses avec RAG

## 1. Objectif réel du module

Les supports de cours fournis servent à comprendre les techniques nécessaires pour construire le projet. Ils ne constituent pas les seules questions que l’étudiant doit poser dans l’application.

Dans l’application, chaque étudiant peut importer un cours quelconque : mathématiques, physique, informatique, sciences, etc. Il peut ensuite poser une question en langage naturel. Le module 3 doit retrouver les passages pertinents dans ses propres documents et produire une réponse accompagnée de sources.

Le principe est donc :

> cours de l’étudiant → recherche des passages pertinents → réponse contextualisée.

## 2. Fonctionnement actuel du RAG

### 2.1 Importation

PHP enregistre le document importé dans `storage/courses/`, puis appelle le service IA. Les formats acceptés sont PDF, DOCX et TXT.

### 2.2 Extraction et découpage

Le texte est nettoyé puis découpé en blocs. Les blocs se chevauchent légèrement afin de ne pas séparer une idée importante entre deux blocs. Pour les PDF, le numéro de page est conservé afin de pouvoir citer la source.

### 2.3 Vectorisation et index

Chaque bloc est transformé en embedding. Les vecteurs sont enregistrés dans un index FAISS propre à chaque étudiant. Les textes et leurs métadonnées sont conservés dans `chunks.json`.

Cette séparation empêche un étudiant de retrouver le contenu d’un autre étudiant.

### 2.4 Question

Quand l’étudiant pose une question, elle est transformée en vecteur puis comparée aux blocs de ses cours. Le système garde les passages les plus proches, selon le paramètre `top-k`.

### 2.5 Seuil d’abstention

Si aucun passage n’est trouvé, ou si le score de similarité est insuffisant, le système ne doit pas inventer une réponse. Il renvoie :

> Je ne trouve pas cette information dans vos cours.

Le modèle génératif n’est alors pas appelé, ce qui réduit les hallucinations et la consommation de tokens.

### 2.6 Prompt de production

Le prompt utilisé est [rag_v3.txt](./prompts/rag_v3.txt). Il demande au modèle :

- de répondre uniquement à partir du contexte fourni ;
- de répondre en français ;
- de citer les sources ;
- de s’abstenir si l’information est absente ;
- de traiter le contenu du document comme des données et non comme des instructions.

Les balises de contexte sont neutralisées pour limiter les attaques par injection de prompt.

### 2.7 Génération

Le projet possède un générateur extractif et des stratégies locales ou externes. L’intégration recommandée pour la démonstration est Ollama avec le modèle local installé sur la machine.

Configuration observée sur la machine :

- Ollama 0.40.10 ;
- `llama3:8b`, quantifié en `Q4_0` ;
- `nomic-embed-text` disponible pour une éventuelle comparaison d’embeddings.

Ollama doit être utilisé pour générer la réponse après la recherche RAG. Il ne doit pas recevoir un cours complet sans sélection préalable des passages pertinents.

## 3. Règle pour les questions hors cours

Il faut distinguer deux usages dans le rapport et dans l’interface.

### Mode « Mes cours »

C’est le mode principal et celui qui démontre le mieux le module 3. La réponse est basée uniquement sur les documents de l’étudiant. Une question absente du cours produit une abstention.

### Mode « Connaissance générale »

Pour une question comme « Combien y a-t-il de gouvernorats en France ? », le système peut appeler Ollama comme modèle général, mais cette réponse ne doit pas être présentée comme une réponse provenant des cours.

Le résultat doit afficher clairement :

- `Source : connaissance générale` ;
- absence de source dans les documents de l’étudiant ;
- avertissement demandant de vérifier les informations sensibles ou actuelles.

Pour une bonne note, il est préférable de présenter le mode « Mes cours » comme fonctionnalité principale et le mode général comme extension contrôlée. Mélanger silencieusement les deux modes affaiblirait la traçabilité du RAG.

## 4. Plan d’évaluation

L’évaluation doit utiliser des cours quelconques importés par l’étudiant, et non uniquement les supports de la matière.

Pour chaque cours, préparer :

1. des questions dont la réponse existe dans le document ;
2. des questions dont la réponse existe dans un autre document ;
3. des questions totalement absentes des documents ;
4. des questions ambiguës ou nécessitant plusieurs passages.

Mesures à présenter :

| Mesure | Ce qu’elle vérifie |
|---|---|
| Hit@k | Le bon passage apparaît-il parmi les k résultats ? |
| MRR | Le bon passage apparaît-il tôt dans le classement ? |
| Score de réponse | La réponse est-elle correcte, partielle ou fausse ? |
| Abstention correcte | Le système refuse-t-il les questions absentes ? |
| Latence moyenne et p95 | Le système est-il suffisamment rapide ? |
| Cache | Une question répétée est-elle plus rapide ? |
| Confidentialité | Un étudiant voit-il uniquement ses propres cours ? |

Les résultats du rapport doivent venir d’expériences exécutées, et non d’estimations.

## 5. Optimisations à justifier

- embeddings adaptés à la langue et au type de cours ;
- comparaison de `chunk_size` et `top-k` ;
- seuil d’abstention calibré sur des questions dans et hors cours ;
- prompt v1, v2 et v3 comparés ;
- cache des questions répétées ;
- Ollama local afin de préserver la confidentialité ;
- modèle `Q4_0` afin de réduire l’utilisation mémoire ;
- générateur extractif de secours si Ollama est arrêté ;
- limite du contexte envoyé au modèle afin de réduire la latence et les tokens.

## 6. Démonstration recommandée

1. Importer un cours de mathématiques ou de physique.
2. Poser une question dont la réponse est dans le cours.
3. Afficher la réponse et les sources utilisées.
4. Poser une question absente du cours.
5. Montrer l’abstention.
6. Reposer la première question et montrer le cache.
7. Tester un second étudiant pour montrer l’isolation des documents.
8. Présenter séparément une question générale traitée par Ollama, avec l’étiquette « connaissance générale ».

## 7. Estimation de la note

Cette estimation n’est pas une note officielle.

- état actuel documenté : environ **7/10** pour les critères directement liés au module 3 ;
- module 3 terminé avec Ollama, mesures réelles, rapport et démonstration : environ **9 à 10/10** sur cette partie ;
- estimation du projet complet après validation de tous les critères : environ **17 à 19/20**, si le rapport, la présentation et la collaboration sont également solides.

