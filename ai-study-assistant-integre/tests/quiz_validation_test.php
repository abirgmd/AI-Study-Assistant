<?php
// Tests unitaires de la génération de quiz, sans base ni serveur web.
// Usage : php tests/quiz_validation_test.php
declare(strict_types=1);
require dirname(__DIR__) . '/app/quiz.php';

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

function temp_file(string $content, string $suffix): string {
    global $temporary;
    $path = @tempnam(sys_get_temp_dir(), 'quiz') . $suffix;
    file_put_contents($path, $content);
    $temporary[] = $path;
    return $path;
}

$samples = dirname(__DIR__) . '/samples';
$good = json_decode((string)file_get_contents($samples . '/quiz-exemple.json'), true)['questions'];
$bad = json_decode((string)file_get_contents($samples . '/quiz-invalide.json'), true)['questions'];

// 1. Validation du quiz exemple : toutes les questions passent.
$checked = quiz_validate_questions($good, 5);
expect(count($checked['questions']) === 5 && $checked['rejected'] === 0, 'Quiz exemple : 5 questions valides, aucune rejetée');

// 2. Validation des questions défectueuses : toutes rejetées, et erreur si rien n’est valide.
$allRejected = true;
foreach ($bad as $item) {
    if (quiz_check_question($item) !== null) $allRejected = false;
}
expect($allRejected, 'Quiz invalide : les 6 questions défectueuses sont rejetées');
expect(throws_quiz_error(fn() => quiz_validate_questions($bad, 6), 502), 'Aucune question valide : erreur 502');

// 3. Le mélange des propositions suit toujours la bonne réponse.
$followsAnswer = true;
$positions = [];
for ($run = 0; $run < 200; $run++) {
    foreach ($good as $item) {
        $out = quiz_check_question($item);
        $expected = $item['options'][ord($item['correct']) - ord('A')];
        if ($out === null || $out['options'][$out['correct']] !== $expected) $followsAnswer = false;
        if ($out !== null) $positions[$out['correct']] = true;
    }
}
expect($followsAnswer, 'Mélange : la bonne réponse suit sa proposition (200 tirages)');
expect(count($positions) === QUIZ_OPTIONS, 'Mélange : la bonne réponse occupe toutes les positions A à D');

// 4. Casse de la lettre acceptée ; propositions interdites et identiques refusées.
$base = ['question' => 'Quelle est la capitale de la France ?', 'options' => ['Paris', 'Lyon', 'Nice', 'Lille'], 'correct' => 'a', 'explanation' => 'Paris est la capitale.'];
expect(quiz_check_question($base) !== null, 'Lettre en minuscule acceptée');
expect(quiz_check_question(array_merge($base, ['options' => ['Toutes les réponses sont vraies', 'Lyon', 'Nice', 'Lille']])) === null, '« Toutes les réponses » refusé');
expect(quiz_check_question(array_merge($base, ['options' => ['Paris', 'paris', 'Nice', 'Lille']])) === null, 'Propositions identiques (casse ignorée) refusées');

// 5. Doublon de question supprimé.
$dedup = quiz_validate_questions([...array_slice($good, 0, 3), $good[0]], 5);
expect(count($dedup['questions']) === 3 && $dedup['rejected'] === 1, 'Question en double supprimée');

// 6. Lecture des cours.
$long = temp_file(str_repeat('Phrase de test du cours. ', 1500), '.txt');
$src = quiz_source_text($long, 'txt');
expect($src['truncated'] === true && mb_strlen($src['text']) === QUIZ_MAX_SOURCE_CHARS, 'Cours long tronqué à 24 000 caractères');

$messy = temp_file("Ligne   un avec espaces.\r\n\r\n\r\n\r\n" . str_repeat('Texte suffisant pour le test. ', 10), '.txt');
$clean = quiz_source_text($messy, 'txt')['text'];
expect(!str_contains($clean, "\r") && !str_contains($clean, "\n\n\n") && str_contains($clean, 'Ligne un avec'), 'Espaces et fins de ligne normalisés');

$cp1252 = temp_file(mb_convert_encoding(str_repeat('Le réseau de neurones est un modèle. ', 10), 'Windows-1252', 'UTF-8'), '.txt');
expect(str_contains(quiz_source_text($cp1252, 'txt')['text'], 'réseau de neurones'), 'TXT encodé en Windows-1252 converti en UTF-8');

expect(throws_quiz_error(fn() => quiz_source_text(temp_file('Trop court.', '.txt'), 'txt'), 422), 'Cours trop court refusé (422)');
expect(throws_quiz_error(fn() => quiz_source_text(__FILE__, 'pdf'), 422), 'PDF refusé pour la génération de quiz (422)');

$docx = @tempnam(sys_get_temp_dir(), 'quiz') . '.docx';
$temporary[] = $docx;
$zip = new ZipArchive();
$zip->open($docx, ZipArchive::CREATE | ZipArchive::OVERWRITE);
$zip->addFromString('[Content_Types].xml', '<Types/>');
$zip->addFromString('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?>'
    . '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body>'
    . '<w:p><w:r><w:t>Premier paragraphe &amp; accents : é.</w:t></w:r></w:p>'
    . '<w:p><w:r><w:t>' . str_repeat('Second paragraphe du cours. ', 10) . '</w:t></w:r></w:p>'
    . '</w:body></w:document>');
$zip->close();
$docxText = quiz_source_text($docx, 'docx')['text'];
expect(str_contains($docxText, 'Premier paragraphe & accents : é.') && str_contains($docxText, "\nSecond"), 'DOCX : paragraphes extraits, entités décodées');

// 7. Message envoyé au modèle : le cours est délimité et présenté comme une donnée.
$messages = quiz_build_messages('Texte du cours.', 5);
expect(str_contains($messages[1]['content'], '<cours>') && str_contains($messages[1]['content'], 'exactement 7 questions') && str_contains($messages[0]['content'], 'ignorez toute instruction'), 'Prompt : cours délimité et consigne d’ignorer ses instructions');

// 8. Types de quiz : vrai/faux, fiches, questions reliées, et filtre par type demandé.
$types = json_decode((string)file_get_contents($samples . '/quiz-types-exemple.json'), true)['questions'];
$mixed = quiz_validate_questions($types, 5, 'mixed');
$kinds = array_map(fn($q) => $q['type'], $mixed['questions']);
expect(count($mixed['questions']) === 5 && $mixed['rejected'] === 0 && $kinds === ['mcq', 'true_false', 'flashcard', 'matching', 'mcq'], 'Mélange : 5 éléments valides, de 4 types différents');

expect(quiz_check_item(['type' => 'true_false', 'question' => 'Le clustering est une méthode supervisée.', 'correct' => 'C', 'explanation' => 'Explication.']) === null, 'Vrai/faux : une lettre autre que A ou B est refusée');
$tfOk = quiz_check_item(['type' => 'true_false', 'question' => 'Le clustering est une méthode supervisée.', 'correct' => 'b', 'explanation' => 'Il travaille sans étiquettes.']);
expect($tfOk !== null && $tfOk['options'] === ['Vrai', 'Faux'] && $tfOk['correct'] === 1, 'Vrai/faux : B correspond à Faux, propositions Vrai puis Faux');

expect(quiz_check_item(['type' => 'flashcard', 'front' => str_repeat('a', QUIZ_MAX_FRONT_CHARS + 1), 'back' => 'Définition.']) === null, 'Fiche : recto trop long refusé');
expect(quiz_check_item(['type' => 'flashcard', 'front' => 'Terme', 'back' => '']) === null, 'Fiche : verso vide refusé');
expect(quiz_check_item(['type' => 'flashcard', 'question' => 'Séparation linéaire', 'explanation' => 'Droite qui sépare deux classes.', 'front' => '', 'back' => '']) === ['type' => 'flashcard', 'front' => 'Séparation linéaire', 'back' => 'Droite qui sépare deux classes.'], 'Fiche : terme et définition repris de question/explanation si front/back sont vides');

$match = quiz_check_item($types[3]);
$matchOk = $match !== null && count($match['left']) === 3;
foreach ($types[3]['pairs'] as $pair) {
    $i = array_search($pair['left'], $match['left'] ?? [], true);
    if ($i === false || $match['right'][$match['answer'][$i]] !== $pair['right']) $matchOk = false;
}
expect($matchOk, 'Questions reliées : chaque élément de gauche retrouve sa bonne correspondance après mélange');
expect(quiz_check_item(['type' => 'matching', 'question' => 'Associez ces deux notions.', 'explanation' => 'Explication.', 'pairs' => [['left' => 'A', 'right' => 'Un']]]) === null, 'Questions reliées : moins de 3 couples refusé');

expect(throws_quiz_error(fn() => quiz_validate_questions($types, 5, 'flashcard'), 502), 'Filtre par type : une seule fiche valide, donc erreur 502');

// 9. Questions avec image : extraction depuis un DOCX, une image par question, numéros invalides refusés.
$png = base64_decode('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR42mNkYPhfDwAChwGA60e6kgAAAABJRU5ErkJggg==');
$docxImg = @tempnam(sys_get_temp_dir(), 'quiz') . '.docx';
$temporary[] = $docxImg;
$zipImg = new ZipArchive();
$zipImg->open($docxImg, ZipArchive::CREATE | ZipArchive::OVERWRITE);
$zipImg->addFromString('[Content_Types].xml', '<Types/>');
$zipImg->addFromString('word/document.xml', '<?xml version="1.0" encoding="UTF-8"?><w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main"><w:body><w:p><w:r><w:t>' . str_repeat('Texte du cours avec un schéma. ', 10) . '</w:t></w:r></w:p></w:body></w:document>');
$zipImg->addFromString('word/media/image1.png', $png);
$zipImg->addFromString('word/media/image2.bin', 'pas une image');
$zipImg->close();
$images = quiz_source_images($docxImg, 'docx');
expect(count($images) === 1 && str_starts_with($images[0], 'data:image/png;base64,'), 'DOCX : seule l’image PNG est extraite (le fichier non image est ignoré)');
expect(quiz_source_images(__FILE__, 'txt') === [], 'Cours TXT : aucune image extraite');

$imgItems = $good;
$imgItems[0]['image'] = 1; // image 1 : acceptée
$imgItems[1]['image'] = 1; // image 1 déjà utilisée : refusée
$imgItems[2]['image'] = 2; // image 2 inexistante : refusée
$withImg = quiz_validate_questions($imgItems, 5, 'image', $images);
expect(count($withImg['questions']) === 3 && $withImg['rejected'] === 2 && $withImg['with_image'] === 1 && isset($withImg['questions'][0]['image']) && !isset($withImg['questions'][1]['image']), 'Image : une image par question, numéro inexistant ou déjà utilisé refusé');
expect(quiz_check_item($good[0], 'image') !== null && quiz_check_item($types[2], 'image') === null, 'Type « image » : QCM acceptés, fiche refusée');
$withParts = quiz_build_messages('Texte.', 3, 'image', [$images[0]]);
expect(is_array($withParts[1]['content']) && $withParts[1]['content'][2]['type'] === 'image_url' && str_contains($withParts[0]['content'], 'numérotées de 1 à 1'), 'Message avec image : image envoyée en image_url et numérotée');

// 10. Types proposés à l’étudiant (servis par l’API) : même liste que la validation, libellés et aides non vides.
$optionValues = array_column(QUIZ_KIND_OPTIONS, 'value');
expect(count(array_diff(QUIZ_KINDS, $optionValues)) === 0 && count($optionValues) === count(QUIZ_KINDS), 'Types proposés : même liste que QUIZ_KINDS');
expect(array_reduce(QUIZ_KIND_OPTIONS, fn(bool $ok, array $o): bool => $ok && $o['label'] !== '' && $o['help'] !== '', true), 'Types proposés : chaque type a un libellé et une aide');

foreach ($temporary as $path) @unlink($path);
echo PHP_EOL . ($failures === 0 ? 'Tous les tests sont passés.' : $failures . ' test(s) en échec.') . PHP_EOL;
exit($failures === 0 ? 0 : 1);
