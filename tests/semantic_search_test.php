<?php
// Tests unitaires de l'intégration PHP du module 2 (recherche sémantique).
// Aucun service Python, aucune base de données : uniquement validation et lecture des cours.
// Usage : php tests/semantic_search_test.php
declare(strict_types=1);
require dirname(__DIR__) . '/app/quiz.php';
require dirname(__DIR__) . '/app/semantic_search.php';

$failures = 0;
$temporary = [];

function expect(bool $ok, string $label): void {
    global $failures;
    echo ($ok ? 'PASS' : 'FAIL') . ': ' . $label . PHP_EOL;
    if (!$ok) $failures++;
}

function throws_semantic_error(callable $call, int $code): bool {
    try {
        $call();
        return false;
    } catch (QuizException $e) {
        return $e->getCode() === $code;
    }
}

/** Fichier temporaire dans le dossier des cours (la recherche lit ce dossier). */
function semantic_course_file(string $content, string $suffix): string {
    global $temporary;
    $name = bin2hex(random_bytes(12)) . '.' . $suffix;
    $path = dirname(__DIR__) . '/storage/courses/' . $name;
    file_put_contents($path, $content);
    $temporary[] = $path;
    return $name;
}

$root = dirname(__DIR__);

// 1. Configuration : valeurs présentes et URL utilisable.
$config = semantic_search_config();
expect($config['url'] !== '' && str_starts_with($config['url'], 'http'), 'Configuration : URL du service renseignée');
expect($config['token'] !== '' && $config['timeout'] >= 5, 'Configuration : jeton et délai renseignés');

// 2. Question : espaces retirés, 2 à 200 caractères.
expect(semantic_search_validate_query('  régression  ') === 'régression', 'Question : espaces retirés');
expect(throws_semantic_error(fn() => semantic_search_validate_query('a'), 422), 'Question : un caractère refusé (422)');
expect(throws_semantic_error(fn() => semantic_search_validate_query(str_repeat('é', 201)), 422), 'Question : plus de 200 caractères refusé (422)');
expect(semantic_search_validate_query(str_repeat('é', 200)) === str_repeat('é', 200), 'Question : 200 caractères acceptés');
expect(throws_semantic_error(fn() => semantic_search_validate_query(['x']), 422), 'Question : tableau refusé (422)');

// 3. Nombre de passages : 1 à 10, valeur par défaut 5.
expect(semantic_search_validate_top_k(null) === 5, 'Passages : valeur par défaut 5');
expect(semantic_search_validate_top_k('3') === 3, 'Passages : valeur texte convertie');
expect(throws_semantic_error(fn() => semantic_search_validate_top_k('11'), 422), 'Passages : plus de 10 refusé (422)');
expect(throws_semantic_error(fn() => semantic_search_validate_top_k('abc'), 422), 'Passages : texte non numérique refusé (422)');
expect(throws_semantic_error(fn() => semantic_search_validate_top_k(true), 422), 'Passages : booléen refusé (422)');

// 4. Cours : TXT lu, PDF et cours vide comptés à part.
$txtName = semantic_course_file("La régularisation limite le sur-apprentissage.\nUne autre ligne.", 'txt');
$emptyName = semantic_course_file('   ', 'txt');
$courses = [
    ['id' => 1, 'title' => 'Apprentissage', 'original_name' => 'cours.txt', 'stored_name' => $txtName],
    ['id' => 2, 'title' => 'Maths', 'original_name' => 'maths.pdf', 'stored_name' => 'inexistant.pdf'],
    ['id' => 3, 'title' => 'Vide', 'original_name' => 'vide.txt', 'stored_name' => $emptyName],
];
$prepared = semantic_search_notes($courses, $root);
expect(count($prepared['notes']) === 1, 'Cours : seul le TXT lisible est indexé');
expect($prepared['skipped'] === 2, 'Cours : PDF et cours vide comptés comme ignorés');
expect($prepared['notes'][0]['id'] === '1' && $prepared['notes'][0]['title'] === 'Apprentissage', 'Cours : identifiant et titre conservés');
expect(str_contains($prepared['notes'][0]['text'], 'régularisation'), 'Cours : texte lu et normalisé');

// 5. Texte limité à 24 000 caractères, même pour un cours très long.
$hugeName = semantic_course_file(str_repeat('abcdefghij ', 3000), 'txt');
$huge = semantic_search_notes([
    ['id' => 4, 'title' => 'Long', 'original_name' => 'long.txt', 'stored_name' => $hugeName],
], $root);
expect(mb_strlen($huge['notes'][0]['text']) === SEMANTIC_SEARCH_MAX_TEXT_CHARS, 'Cours : texte limité à 24 000 caractères');

// 6. Au plus 30 cours sont traités ; le reste est signalé comme ignoré.
$many = array_fill(0, 31, ['id' => 5, 'title' => 'Répété', 'original_name' => 'cours.txt', 'stored_name' => $txtName]);
$limited = semantic_search_notes($many, $root);
expect(count($limited['notes']) === 30 && $limited['skipped'] === 1, 'Cours : limite de 30 cours et compteur des cours ignorés');

// 7. Sans cours lisible, la recherche s'arrête avant tout appel réseau.
expect(throws_semantic_error(fn() => semantic_search_request([], 'test', 5, 0), 422), 'Recherche : aucun cours lisible refusé (422)');

// 8. La variable d'environnement peut remplacer l'URL du service (sans config locale).
putenv('SEMANTIC_SEARCH_URL=http://127.0.0.1:9999/');
$envConfig = semantic_search_config();
expect($envConfig['url'] === 'http://127.0.0.1:9999', 'Configuration : variable d’environnement prioritaire et sans slash final');
putenv('SEMANTIC_SEARCH_URL');

foreach ($temporary as $path) @unlink($path);

echo PHP_EOL . ($failures === 0 ? 'Tous les tests PHP de la recherche sémantique sont passés.' : $failures . ' test(s) en échec.') . PHP_EOL;
exit($failures === 0 ? 0 : 1);
