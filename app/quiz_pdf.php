<?php
declare(strict_types=1);
// Export PDF des réponses d’un quiz. La correction est recalculée ici, à partir du quiz enregistré :
// le navigateur ne fournit que le choix de l’étudiant. PDF écrit sans bibliothèque (Helvetica, encodage WinAnsi).
// Dépend de app/quiz.php (QuizException). Ne démarre pas la session.
require_once __DIR__ . '/quiz.php';

const QUIZ_PDF_PAGE_WIDTH = 595;   // A4 en points
const QUIZ_PDF_PAGE_HEIGHT = 842;
const QUIZ_PDF_MARGIN = 56;
const QUIZ_PDF_LINE_CHARS = 88;    // longueur de ligne en Helvetica 10 pt
const QUIZ_PDF_LEADING = 1.45;     // interligne, en multiple de la taille

/** Texte pour le PDF : encodage WinAnsi (cp1252). Un caractère absent de cette table devient « ? ». */
function quiz_pdf_text(string $text): string {
    $encoded = mb_convert_encoding($text, 'Windows-1252', 'UTF-8');
    return $encoded === false ? '' : $encoded;
}

/** Échappe une chaîne PDF entre parenthèses. */
function quiz_pdf_escape(string $text): string {
    return str_replace(['\\', '(', ')'], ['\\\\', '\\(', '\\)'], $text);
}

/** Découpe un texte en lignes de $width caractères au plus, aux espaces quand c’est possible. */
function quiz_pdf_wrap(string $text, int $width = QUIZ_PDF_LINE_CHARS): array {
    $lines = [];
    foreach (preg_split('/\R/u', $text) ?: [''] as $paragraph) {
        $words = preg_split('/\s+/u', trim($paragraph), -1, PREG_SPLIT_NO_EMPTY) ?: [];
        if ($words === []) {
            $lines[] = '';
            continue;
        }
        $line = '';
        foreach ($words as $word) {
            while (mb_strlen($word) > $width) {
                if ($line !== '') {
                    $lines[] = $line;
                    $line = '';
                }
                $lines[] = mb_substr($word, 0, $width);
                $word = mb_substr($word, $width);
            }
            $candidate = $line === '' ? $word : $line . ' ' . $word;
            if (mb_strlen($candidate) > $width) {
                $lines[] = $line;
                $line = $word;
            } else {
                $line = $candidate;
            }
        }
        if ($line !== '') $lines[] = $line;
    }
    return $lines;
}

/**
 * Réponses de l’étudiant, normalisées : QCM et vrai/faux = index ou null ; questions reliées = un index (ou null) par couple ; fiches = null.
 * @return array<int, int|array<int, int|null>|null>
 */
function quiz_pdf_answers(array $questions, mixed $raw): array {
    if (!is_array($raw) || !array_is_list($raw) || count($raw) !== count($questions)) {
        throw new QuizException('Les réponses ne correspondent pas à ce quiz. Rechargez le quiz et réessayez.', 422);
    }
    $answers = [];
    foreach ($questions as $i => $q) {
        $type = $q['type'] ?? 'mcq';
        $value = $raw[$i];
        if ($type === 'flashcard') {
            $answers[] = null;
        } elseif ($type === 'matching') {
            $list = [];
            foreach ($q['left'] as $j => $_left) {
                $choice = is_array($value) ? ($value[$j] ?? null) : null;
                $list[] = is_int($choice) && $choice >= 0 && $choice < count($q['right']) ? $choice : null;
            }
            $answers[] = $list;
        } else {
            $answers[] = is_int($value) && $value >= 0 && $value < count($q['options']) ? $value : null;
        }
    }
    return $answers;
}

/** Score comme à l’écran : fiches non notées ; une question reliée est juste si toutes ses associations le sont. */
function quiz_pdf_score(array $questions, array $answers): array {
    $scored = 0;
    $score = 0;
    foreach ($questions as $i => $q) {
        $type = $q['type'] ?? 'mcq';
        if ($type === 'flashcard') continue;
        $scored++;
        $answer = $answers[$i];
        if ($type === 'matching') {
            $all = true;
            foreach ($q['answer'] as $j => $expected) {
                if (($answer[$j] ?? null) !== $expected) {
                    $all = false;
                    break;
                }
            }
            if ($all) $score++;
        } elseif ($answer !== null && $answer === $q['correct']) {
            $score++;
        }
    }
    return ['scored' => $scored, 'score' => $score];
}

/**
 * Lignes du rapport : titre, score, puis chaque question avec la réponse de l’étudiant, la bonne réponse et l’explication.
 * @return array<int, array{text:string, size:int, bold:bool, space:float}>
 */
function quiz_pdf_lines(string $title, string $course, string $date, array $questions, array $answers): array {
    $lines = [];
    $add = static function (string $text, int $size, bool $bold, float $space) use (&$lines): void {
        $parts = quiz_pdf_wrap($text, (int)floor(QUIZ_PDF_LINE_CHARS * 10 / $size));
        foreach ($parts as $index => $part) {
            $lines[] = ['text' => $part, 'size' => $size, 'bold' => $bold, 'space' => $index === 0 ? $space : 0.0];
        }
    };
    $score = quiz_pdf_score($questions, $answers);
    $add($title, 16, true, 0);
    $add('Cours : ' . $course, 10, false, 6);
    $add('Exporté le ' . $date, 10, false, 2);
    $add(sprintf('Score : %d / %d', $score['score'], $score['scored']), 13, true, 14);

    foreach ($questions as $i => $q) {
        $number = $i + 1;
        $type = $q['type'] ?? 'mcq';
        if ($type === 'flashcard') {
            $add($number . '. Fiche : ' . $q['front'], 11, true, 16);
            $add('Réponse : ' . $q['back'], 10, false, 3);
            continue;
        }
        $add($number . '. ' . $q['question'], 11, true, 16);
        if (isset($q['image'])) {
            $add('(Question liée à une image du cours : image non incluse dans le PDF.)', 9, false, 2);
        }
        $answer = $answers[$i];
        if ($type === 'matching') {
            foreach ($q['left'] as $j => $left) {
                $choice = $answer[$j] ?? null;
                $expected = $q['answer'][$j];
                $chosenText = $choice === null ? 'pas de réponse' : $q['right'][$choice];
                $verdict = $choice === $expected ? 'correct' : 'faux';
                $add('   ' . $left . ' : votre choix « ' . $chosenText . ' » (' . $verdict . ')', 10, false, $j === 0 ? 3 : 1);
                if ($choice !== $expected) {
                    $add('      Bonne association : « ' . $q['right'][$expected] . ' »', 10, false, 0);
                }
            }
        } else {
            foreach ($q['options'] as $j => $option) {
                $label = $type === 'true_false' ? $option : chr(65 + $j) . '. ' . $option;
                $tags = [];
                if ($j === $q['correct']) $tags[] = 'bonne réponse';
                if ($answer === $j) $tags[] = 'votre réponse';
                $suffix = $tags === [] ? '' : ' [' . implode(', ', $tags) . ']';
                $add('   ' . $label . $suffix, 10, $j === $q['correct'], $j === 0 ? 3 : 1);
            }
            if ($answer === null) {
                $verdict = 'Pas de réponse.';
            } else {
                $verdict = $answer === $q['correct'] ? 'Réponse correcte.' : 'Réponse fausse.';
            }
            $add($verdict, 10, true, 4);
        }
        if (($q['explanation'] ?? '') !== '') {
            $add('Explication : ' . $q['explanation'], 10, false, 4);
        }
    }
    return $lines;
}

/**
 * Assemble le fichier PDF : catalogue, pages, deux polices (normale et grasse), puis une page et son contenu par feuille.
 * @param array<int, array{text:string, size:int, bold:bool, space:float}> $lines
 */
function quiz_pdf_document(array $lines): string {
    $pages = [[]];
    $cursor = QUIZ_PDF_PAGE_HEIGHT - QUIZ_PDF_MARGIN;
    foreach ($lines as $line) {
        $cursor -= $line['space'];
        if ($cursor < QUIZ_PDF_MARGIN + $line['size']) {
            $pages[] = [];
            $cursor = QUIZ_PDF_PAGE_HEIGHT - QUIZ_PDF_MARGIN;
        }
        $pages[count($pages) - 1][] = ['y' => $cursor, 'size' => $line['size'], 'bold' => $line['bold'], 'text' => $line['text']];
        $cursor -= $line['size'] * QUIZ_PDF_LEADING;
    }

    // Numéros d’objets : 1 catalogue, 2 pages, 3 Helvetica, 4 Helvetica-Bold, puis page (5, 7, …) et contenu (6, 8, …).
    $objects = [];
    $kids = [];
    foreach ($pages as $index => $items) {
        $pageNumber = 5 + 2 * $index;
        $contentNumber = $pageNumber + 1;
        $content = '';
        foreach ($items as $item) {
            $content .= sprintf(
                "BT /%s %d Tf %.2F %.2F Td (%s) Tj ET\n",
                $item['bold'] ? 'F2' : 'F1',
                $item['size'],
                QUIZ_PDF_MARGIN,
                $item['y'],
                quiz_pdf_escape(quiz_pdf_text($item['text']))
            );
        }
        $objects[$pageNumber] = sprintf(
            '<< /Type /Page /Parent 2 0 R /MediaBox [0 0 %d %d] /Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> /Contents %d 0 R >>',
            QUIZ_PDF_PAGE_WIDTH,
            QUIZ_PDF_PAGE_HEIGHT,
            $contentNumber
        );
        $objects[$contentNumber] = sprintf("<< /Length %d >>\nstream\n%s\nendstream", strlen($content), $content);
        $kids[] = $pageNumber . ' 0 R';
    }
    $objects[1] = '<< /Type /Catalog /Pages 2 0 R >>';
    $objects[2] = sprintf('<< /Type /Pages /Kids [%s] /Count %d >>', implode(' ', $kids), count($pages));
    $objects[3] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>';
    $objects[4] = '<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>';
    ksort($objects);

    $pdf = "%PDF-1.4\n%\xE2\xE3\xCF\xD3\n";
    $offsets = [];
    foreach ($objects as $number => $body) {
        $offsets[$number] = strlen($pdf);
        $pdf .= $number . " 0 obj\n" . $body . "\nendobj\n";
    }
    $size = count($objects) + 1;
    $xref = strlen($pdf);
    $pdf .= "xref\n0 " . $size . "\n0000000000 65535 f \n";
    for ($n = 1; $n < $size; $n++) {
        $pdf .= sprintf("%010d 00000 n \n", $offsets[$n]);
    }
    $pdf .= "trailer\n<< /Size " . $size . " /Root 1 0 R >>\nstartxref\n" . $xref . "\n%%EOF\n";
    return $pdf;
}
