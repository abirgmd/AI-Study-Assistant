<?php
// Tests unitaires de l’export PDF des réponses de quiz, sans base ni serveur web.
// Usage : php tests/pdf_test.php
declare(strict_types=1);
require dirname(__DIR__) . '/app/quiz_pdf.php';

$failures = 0;

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

$questions = [
    ['type' => 'mcq', 'question' => 'Quelle tâche prédit une valeur continue ?', 'options' => ['Classification', 'Régression', 'Clustering', 'Réduction'], 'correct' => 1, 'explanation' => 'La régression prédit une valeur numérique.'],
    ['type' => 'true_false', 'question' => 'Le surapprentissage est souhaitable.', 'options' => ['Vrai', 'Faux'], 'correct' => 1, 'explanation' => 'Il nuit à la généralisation.'],
    ['type' => 'matching', 'question' => 'Associez chaque terme à sa définition.', 'explanation' => 'Correspondances tirées du cours.', 'left' => ['Étiquette', 'Modèle'], 'right' => ['Réponse attendue', 'Fonction apprise'], 'answer' => [0, 1]],
    ['type' => 'flashcard', 'front' => 'Surapprentissage', 'back' => 'Le modèle mémorise le bruit.'],
];

// 1. Découpage des lignes.
$wrapped = quiz_pdf_wrap(str_repeat('mot ', 60), 20);
expect(count(array_filter($wrapped, static fn(string $l): bool => mb_strlen($l) > 20)) === 0 && count($wrapped) > 1, 'Découpage : aucune ligne au-delà de la largeur');
expect(array_map('mb_strlen', quiz_pdf_wrap(str_repeat('a', 50), 20)) === [20, 20, 10], 'Découpage : un mot trop long est coupé');

// 2. Encodage et échappement.
expect(bin2hex(quiz_pdf_text('é’«»')) === 'e992abbb', 'Encodage : accents, apostrophe et guillemets en WinAnsi');
expect(quiz_pdf_text('→') === '?', 'Encodage : caractère absent de WinAnsi remplacé par ?');
expect(quiz_pdf_escape('a (b) \\c') === 'a \\(b\\) \\\\c', 'Échappement : parenthèses et antislash');

// 3. Réponses de l’étudiant : validées et normalisées.
expect(quiz_pdf_answers($questions, [1, 0, [0, 1], null]) === [1, 0, [0, 1], null], 'Réponses : valeurs valides conservées');
expect(quiz_pdf_answers($questions, [9, null, [5, null], 3]) === [null, null, [null, null], null], 'Réponses : valeurs hors limites ramenées à null');
expect(throws_quiz_error(fn() => quiz_pdf_answers($questions, [1, 0]), 422), 'Réponses : nombre incorrect refusé (422)');
expect(throws_quiz_error(fn() => quiz_pdf_answers($questions, ['a' => 1, 'b' => 0, 'c' => [], 'd' => null]), 422), 'Réponses : tableau associatif refusé (422)');
expect(throws_quiz_error(fn() => quiz_pdf_answers($questions, null), 422), 'Réponses : absentes refusées (422)');

// 4. Score comme à l’écran : fiches non notées, questions reliées juste seulement si toutes les associations le sont.
expect(quiz_pdf_score($questions, [1, 0, [0, 1], null]) === ['scored' => 3, 'score' => 2], 'Score : 2 bonnes réponses sur 3 questions notées');
expect(quiz_pdf_score($questions, [1, 0, [0, 0], null]) === ['scored' => 3, 'score' => 1], 'Score : une association fausse rend la question reliée fausse');

// 5. Contenu du rapport.
$lines = quiz_pdf_lines('Quiz · test', 'Cours test', '25/10/2026 17:00', $questions, [1, 0, [0, 0], null]);
$texts = array_column($lines, 'text');
expect(in_array('Score : 1 / 3', $texts, true), 'Rapport : score affiché');
expect(in_array('Réponse fausse.', $texts, true) && in_array('Réponse correcte.', $texts, true), 'Rapport : verdict par question');
expect(count(array_filter($texts, static fn(string $t): bool => str_contains($t, 'Bonne association'))) === 1, 'Rapport : bonne association affichée pour la question reliée fausse');
expect(in_array('Réponse : Le modèle mémorise le bruit.', $texts, true), 'Rapport : verso de la fiche affiché');
expect(count(array_filter($texts, static fn(string $t): bool => str_contains($t, 'votre réponse'))) === 2, 'Rapport : votre réponse marquée sur les QCM');

// 6. Fichier PDF : en-tête, pages, et tableau xref qui pointe exactement sur chaque objet.
$pdf = quiz_pdf_document($lines);
expect(str_starts_with($pdf, '%PDF-1.4') && str_ends_with($pdf, "%%EOF\n"), 'PDF : en-tête et fin de fichier');
expect(preg_match('/\/Count (\d+)/', $pdf, $count) === 1 && (int)$count[1] === 1, 'PDF : une page pour un quiz court');
preg_match('/startxref\n(\d+)\n/', $pdf, $startxref);
$xrefAt = (int)$startxref[1];
expect(substr($pdf, $xrefAt, 4) === 'xref', 'PDF : startxref pointe sur la table xref');
preg_match_all('/^(\d{10}) 00000 n $/m', $pdf, $entries);
$valid = count($entries[1]) >= 5;
foreach ($entries[1] as $index => $offset) {
    $number = $index + 1;
    if (substr($pdf, (int)$offset, strlen("$number 0 obj")) !== "$number 0 obj") $valid = false;
}
expect($valid, 'PDF : chaque décalage de la table xref pointe sur son objet');

$many = [];
for ($i = 0; $i < 200; $i++) $many[] = ['text' => 'Ligne numéro ' . $i, 'size' => 10, 'bold' => false, 'space' => 0.0];
$long = quiz_pdf_document($many);
preg_match('/\/Count (\d+)/', $long, $longCount);
expect((int)$longCount[1] >= 2, 'PDF : un long rapport est réparti sur plusieurs pages');

echo PHP_EOL . ($failures === 0 ? 'Tous les tests sont passés.' : $failures . ' test(s) en échec.') . PHP_EOL;
exit($failures === 0 ? 0 : 1);
