<?php
// Tests unitaires de la recherche et de l’assistant de cours, sans base ni serveur web.
// Usage : php tests/study_test.php
declare(strict_types=1);
require dirname(__DIR__) . '/app/quiz.php';
require dirname(__DIR__) . '/app/study.php';

$failures = 0;
$temporary = [];

function expect(bool $ok, string $label): void {
    global $failures;
    echo ($ok ? 'PASS' : 'FAIL') . ': ' . $label . PHP_EOL;
    if (!$ok) $failures++;
}

function throws_quiz_error(callable $call, int $code): bool {
    try {
        $call();
        return false;
    } catch (QuizException $e) {
        return $e->getCode() === $code;
    }
}

/** Fichier temporaire dans le dossier des cours (la recherche lit ce dossier). */
function course_file(string $content, string $suffix): string {
    global $temporary;
    $name = bin2hex(random_bytes(12)) . '.' . $suffix;
    $path = dirname(__DIR__) . '/storage/courses/' . $name;
    file_put_contents($path, $content);
    $temporary[] = $path;
    return $name;
}

// 1. Accents et casse : la recherche ignore les accents, la casse et garde la même longueur.
expect(study_fold('Régression ÉLÈVE çà') === 'regression eleve ca', 'Recherche : accents et casse ignorés');
expect(mb_strlen(study_fold('Éçà’ABC')) === mb_strlen('Éçà’ABC'), 'Recherche : même nombre de caractères après normalisation');

// 2. Mots de la recherche : au moins 2 caractères, sans doublon.
expect(study_query_words('Régression  linéaire, a régression') === ['regression', 'lineaire'], 'Mots de recherche : un seul caractère ignoré, doublons retirés');
expect(study_query_words('a ?') === [], 'Mots de recherche : rien d’utilisable');

// 3. Passages : une ligne par résultat, tous les mots doivent être présents.
$text = "La régression linéaire prédit une valeur continue.\nLa classification prédit une classe.\n\nRégression logistique : classification binaire.";
expect(count(study_find_passages($text, 'REGRESSION')) === 2, 'Passages : mot trouvé sans tenir compte des accents ni de la casse');
expect(count(study_find_passages($text, 'regression classification')) === 1, 'Passages : tous les mots doivent figurer dans la même ligne');
expect(study_find_passages($text, 'inconnu') === [], 'Passages : aucun résultat si le mot est absent');
expect(study_find_passages($text, 'a') === [], 'Passages : une recherche d’un seul caractère ne renvoie rien');

// 4. Extrait : au plus 320 caractères (plus les points de suite), et le mot reste visible.
$long = 'x ' . str_repeat('abc ', 300) . 'cible';
$hits = study_find_passages($long, 'cible');
expect(count($hits) === 1 && str_contains($hits[0], 'cible') && mb_strlen($hits[0]) <= STUDY_SNIPPET_CHARS + 4, 'Extrait : longueur limitée et mot recherché visible');

// 5. Limite de résultats.
expect(count(study_find_passages(str_repeat("mot\n", 30), 'mot', 5)) === 5, 'Passages : nombre maximal de résultats respecté');

// 6. Recherche dans les cours : TXT lu, PDF compté à part, passages avec le nom du cours.
$txtName = course_file("La régression linéaire prédit une valeur.\nAutre ligne sans rapport.", 'txt');
$courses = [
    ['id' => 1, 'title' => 'Apprentissage', 'original_name' => 'cours.txt', 'stored_name' => $txtName],
    ['id' => 2, 'title' => 'Maths', 'original_name' => 'maths.pdf', 'stored_name' => 'inexistant.pdf'],
];
$found = study_search($courses, 'Regression');
expect(count($found['results']) === 1 && $found['results'][0]['course_name'] === 'Apprentissage' && $found['results'][0]['course_id'] === 1, 'Recherche cours : passage trouvé dans le TXT avec le nom du cours');
expect($found['skipped'] === 1, 'Recherche cours : PDF compté comme non pris en compte');
$none = study_search($courses, 'introuvable');
expect($none['results'] === [] && $none['skipped'] === 1, 'Recherche cours : aucun passage quand le mot est absent');

// 7. Texte du cours pour l’assistant : TXT accepté, PDF et cours vide refusés, texte limité.
$txtPath = dirname(__DIR__) . '/storage/courses/' . $txtName;
expect(str_contains(study_course_text($txtPath, 'txt'), 'valeur'), 'Assistant : texte d’un TXT lu');
expect(throws_quiz_error(fn() => study_course_text($txtPath, 'pdf'), 422), 'Assistant : PDF refusé avec un message (422)');
$emptyName = course_file('   ', 'txt');
expect(throws_quiz_error(fn() => study_course_text(dirname(__DIR__) . '/storage/courses/' . $emptyName, 'txt'), 422), 'Assistant : cours sans texte refusé (422)');
$hugeName = course_file(str_repeat('abcdefghij ', 3000), 'txt');
$huge = study_course_text(dirname(__DIR__) . '/storage/courses/' . $hugeName, 'txt');
expect(mb_strlen($huge) > 0 && mb_strlen($huge) <= QUIZ_MAX_SOURCE_CHARS, 'Assistant : texte limité à 24 000 caractères');

// 8. Messages envoyés au modèle : règles de réponse et cours entre balises, question séparée.
$messages = study_answer_messages('Le cours parle de régression.', 'Qu’est-ce que la régression ?');
expect(count($messages) === 2 && $messages[0]['role'] === 'system' && $messages[1]['role'] === 'user', 'Messages assistant : un message système puis un message utilisateur');
expect(str_contains($messages[0]['content'], 'uniquement') && str_contains($messages[0]['content'], 'n’inventez rien'), 'Messages assistant : réponse limitée au cours');
expect(str_contains($messages[1]['content'], '<cours>') && str_contains($messages[1]['content'], 'Le cours parle de régression.') && str_contains($messages[1]['content'], 'Question : Qu’est-ce que la régression ?'), 'Messages assistant : cours et question dans le message utilisateur');

// 9. Passages pertinents : le passage qui répond à la question est gardé, même loin dans un long cours ; la limite est respectée.
$long = '';
for ($i = 1; $i <= 40; $i++) $long .= "Ligne $i : remplissage sans rapport avec le sujet, ce texte allonge le cours.\n";
$long .= "La validation croisée estime la qualité d’un modèle.\n";
$relevant = study_relevant_text($long, 'validation croisée', 400);
expect(str_contains($relevant, 'validation croisée') && mb_strlen($relevant) <= 400, 'Assistant : passage pertinent gardé dans un long cours, limite respectée');
expect(study_relevant_text('Court.', 'x y', 400) === 'Court.', 'Assistant : cours court renvoyé tel quel');
expect(str_starts_with(study_relevant_text($long, 'zzz', 400), 'Ligne 1 :'), 'Assistant : sans mot en commun, début du cours gardé');

// 10. Erreurs du service IA : message selon la cause, sans jamais afficher la clé.
expect(quiz_ai_http_error(429, '{"error":{"code":"rate_limit_exceeded"}}')->getCode() === 429 && str_contains(quiz_ai_http_error(429, '')->getMessage(), 'Attendez une minute'), 'Erreur IA 429 : message d’attente (limite de débit)');
expect(str_contains(quiz_ai_http_error(401, '{"error":{"code":"invalid_api_key"}}')->getMessage(), 'config/groq.php'), 'Erreur IA 401 : clé refusée, renvoi vers config/groq.php');
expect(quiz_ai_http_error(413, '')->getCode() === 413, 'Erreur IA 413 : requête trop lourde');
expect(str_contains(quiz_ai_http_error(400, '{"error":{"code":"model_not_found"}}')->getMessage(), 'erreur 400'), 'Erreur IA autre : code HTTP indiqué');

// 11. Données personnelles masquées avant l’envoi au modèle.
$masked = ai_mask_personal_data("Contact : abir.test@esprit.tn, tél. +216 98 765 432 ou 06 12 34 56 78, voir https://exemple.tn/x?token=1. Mobile 55 123 456. IBAN FR76 3000 6000 0112 3456 7890 189. Le modèle date de 1995 et la loi 2004-63.");
expect(!str_contains($masked, 'abir.test@esprit.tn') && str_contains($masked, '[EMAIL]'), 'Données perso : e-mail masqué');
expect(!str_contains($masked, '98 765 432') && !str_contains($masked, '06 12 34 56 78') && !str_contains($masked, '55 123 456'), 'Données perso : téléphones masqués (international, FR, TN)');
expect(str_contains($masked, '[LIEN]') && str_contains($masked, '[IBAN]'), 'Données perso : lien et IBAN masqués');
expect(str_contains($masked, '1995') && str_contains($masked, '2004-63'), 'Données perso : années et numéros courts conservés');
expect(ai_mask_personal_data('La régression logistique est une classification.') === 'La régression logistique est une classification.', 'Données perso : texte de cours sans donnée personnelle inchangé');

// 12. Sortie de l’assistant validée avant affichage.
$ok = study_validate_answer('{"answer":"La régression prédit une valeur continue.","found_in_course":true}');
expect($ok['answer'] === 'La régression prédit une valeur continue.' && $ok['found_in_course'] === true, 'Sortie IA : JSON conforme accepté');
expect(study_validate_answer('{"answer":"<b>Non traité</b> dans le cours.","found_in_course":false}')['answer'] === 'Non traité dans le cours.', 'Sortie IA : balises HTML retirées');
expect(throws_quiz_error(fn() => study_validate_answer('texte libre'), 502), 'Sortie IA : texte non JSON refusé (502)');
expect(throws_quiz_error(fn() => study_validate_answer('{"answer":"ok"}'), 502), 'Sortie IA : champ manquant refusé (502)');
expect(throws_quiz_error(fn() => study_validate_answer('{"answer":"","found_in_course":true}'), 502), 'Sortie IA : réponse vide refusée (502)');
expect(throws_quiz_error(fn() => study_validate_answer(json_encode(['answer' => str_repeat('a', 2500), 'found_in_course' => true])), 502), 'Sortie IA : réponse trop longue refusée (502)');
expect(study_answer_schema()['required'] === ['answer', 'found_in_course'], 'Schéma assistant : deux champs obligatoires');

// 13. Délai dépassé et service injoignable : messages distincts.
expect(quiz_ai_transport_error(28, 'Operation timed out', 'test')->getCode() === 504, 'Erreur IA : délai dépassé (timeout) → 504');
expect(quiz_ai_transport_error(6, 'Could not resolve host', 'test')->getCode() === 502, 'Erreur IA : service injoignable → 502');

foreach ($temporary as $path) @unlink($path);
echo PHP_EOL . ($failures === 0 ? 'Tous les tests sont passés.' : $failures . ' test(s) en échec.') . PHP_EOL;
exit($failures === 0 ? 0 : 1);
