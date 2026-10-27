<?php
require dirname(__DIR__).'/gemini.php';

$system = <<<'TXT'
Tu es un coach pédagogique expert en accompagnement d'étudiants.
On te fournit les résultats anonymes d'un quiz : pour chaque question, le sujet,
la réponse de l'étudiant, la bonne réponse et si c'est correct.
Analyse ces résultats et réponds UNIQUEMENT en JSON, en français, avec ce format :
{
  "score": "X/Y",
  "niveau": "débutant | intermédiaire | avancé",
  "points_forts": ["..."],
  "points_faibles": [{"sujet": "...", "reussite": "1/3", "explication": "..."}],
  "erreurs_recurrentes": ["..."],
  "conseils": ["conseil concret et court"],
  "plan_revision": [{"etape": 1, "action": "...", "duree_min": 20}]
}
Règles : ton encourageant, factuel, ne rien inventer qui ne soit pas dans les résultats.
Un sujet ne peut apparaître qu'une seule fois : en point fort s'il a au moins 75% de réussite,
sinon en point faible. Classe les points faibles du plus urgent au moins urgent
et ajoute "reussite" (ex: "1/3") à chaque point faible.
3 à 5 conseils maximum, plan de 3 étapes maximum, chaque étape liée à un point faible.
TXT;

$results = <<<'TXT'
Quiz : Introduction au Machine Learning
Q1 | Apprentissage supervisé | réponse: B | correcte: A | FAUX
Q2 | Apprentissage supervisé | réponse: C | correcte: C | JUSTE
Q3 | Réseaux de neurones | réponse: A | correcte: D | FAUX
Q4 | Réseaux de neurones | réponse: B | correcte: B | JUSTE
Q5 | Évaluation de modèles | réponse: A | correcte: A | JUSTE
Q6 | Évaluation de modèles | réponse: D | correcte: A | FAUX
Q7 | Prétraitement | réponse: C | correcte: C | JUSTE
Q8 | Apprentissage supervisé | réponse: A | correcte: B | FAUX
TXT;

try {
    $out = gemini_call([['text' => $results]], $system);
    foreach (['score','points_forts','points_faibles','conseils','plan_revision'] as $k)
        if (!isset($out[$k])) throw new RuntimeException("Champ manquant : $k");
    echo json_encode($out, JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)."\n";
} catch (Throwable $e) { echo 'ERREUR : '.$e->getMessage()."\n"; }