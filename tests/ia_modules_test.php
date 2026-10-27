<?php
// Tests unitaires du module « Assistant IA 2 » (modules 3 et 5), sans base ni serveur web ni service IA.
// Usage : php tests/ia_modules_test.php
declare(strict_types=1);
require dirname(__DIR__) . '/ia-modules/service.php';
require dirname(__DIR__) . '/ia-modules/courses.php';
require dirname(__DIR__) . '/ia-modules/rag.php';

$failures = 0;

function expect(bool $ok, string $label): void {
    global $failures;
    echo ($ok ? 'PASS' : 'FAIL') . ': ' . $label . PHP_EOL;
    if (!$ok) $failures++;
}

function throws(callable $call, string $class): bool {
    try {
        $call();
        return false;
    } catch (Throwable $e) {
        return $e instanceof $class;
    }
}

// 1. Catégories : une seule source de vérité (categories.json, partagé avec le service Python).
$categories = course_categories();
expect(count($categories['categories']) === 8, 'Catégories : 8 matières lues depuis categories.json');
expect($categories['unclassified'] === 'À classer', 'Catégories : « À classer » est la valeur par défaut');
expect(!in_array('À classer', $categories['categories'], true), 'Catégories : l’étudiant ne peut pas choisir « À classer »');
expect(in_array('Réseaux et sécurité', $categories['categories'], true), 'Catégories : « Réseaux et sécurité » présente');

// 2. Configuration : le module lit config/ia-service.php, jamais config/ai.php (configuration Groq du quiz).
$source = (string)file_get_contents(dirname(__DIR__) . '/ia-modules/service.php');
expect(str_contains($source, "'/config/ia-service.php'"), 'Config : le module lit config/ia-service.php');
expect(!str_contains($source, "'/config/ai.php'"), 'Config : le module ne lit jamais config/ai.php (conflit évité)');
$config = ai_config();
expect(isset($config['base_url'], $config['token'], $config['timeout'], $config['index_timeout']), 'Config : clés base_url, token, timeout, index_timeout');

// 3. Question : espaces réduits, longueur de 3 à 500 caractères.
expect(ia_clean_question("  Quelle   est la\n\nquestion ?  ") === 'Quelle est la question ?', 'Question : espaces réduits et bords supprimés');
expect(ia_clean_question('abc') === 'abc', 'Question : 3 caractères acceptés');
expect(throws(fn() => ia_clean_question('ab'), InvalidArgumentException::class), 'Question : 2 caractères refusés (422)');
expect(throws(fn() => ia_clean_question('   '), InvalidArgumentException::class), 'Question : espaces seuls refusés (422)');
expect(throws(fn() => ia_clean_question(str_repeat('a', 501)), InvalidArgumentException::class), 'Question : 501 caractères refusés (422)');
expect(ia_clean_question(str_repeat('é', 500)) !== '', 'Question : 500 caractères accentués acceptés (compte en caractères, pas en octets)');

// 4. Sources : types contrôlés, champs inutiles écartés.
$raw = [[
    'number' => '1', 'course_id' => '7', 'title' => 'Cycle de vie', 'page' => null,
    'excerpt' => 'Le cycle comprend cinq étapes.', 'score' => '0.42', 'champ_inattendu' => 'x',
]];
$sources = ia_sources($raw);
expect($sources === [[
    'number' => 1, 'course_id' => 7, 'title' => 'Cycle de vie', 'page' => null,
    'excerpt' => 'Le cycle comprend cinq étapes.', 'score' => 0.42,
]], 'Sources : types entiers, flottants et nuls respectés, champs inconnus retirés');
expect(ia_sources([[
    'number' => 2, 'course_id' => 3, 'title' => 'TCP', 'page' => '4', 'excerpt' => 'x', 'score' => 0.9,
]])[0]['page'] === 4, 'Sources : numéro de page converti en entier');

// 5. Garde-fous : limites et constantes attendues par la passerelle.
expect(IA_ASK_LIMIT === 20 && IA_ASK_WINDOW_MINUTES === 10, 'Limite : 20 questions par 10 minutes');
expect(IA_QUESTION_MIN_CHARS === 3 && IA_QUESTION_MAX_CHARS === 500, 'Limite : question de 3 à 500 caractères');

// 6. Message d'erreur lisible, sans détail technique.
expect(!str_contains(ai_unavailable_message(), 'cURL') && str_contains(ai_unavailable_message(), 'ai-service'), 'Message : indisponibilité expliquée sans détail technique');

echo PHP_EOL . ($failures === 0 ? 'Tous les tests sont passés.' : $failures . ' test(s) en échec.') . PHP_EOL;
exit($failures === 0 ? 0 : 1);
