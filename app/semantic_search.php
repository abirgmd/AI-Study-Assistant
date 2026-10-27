<?php
declare(strict_types=1);
// Recherche sémantique (module 2) : préparation des cours et appel du service Python local.
// Dépend de app/quiz.php pour la lecture des cours TXT et DOCX. Ne démarre pas la session.

const SEMANTIC_SEARCH_QUERY_MIN_CHARS = 2;
const SEMANTIC_SEARCH_QUERY_MAX_CHARS = 200;
const SEMANTIC_SEARCH_MAX_COURSES = 30;
const SEMANTIC_SEARCH_MAX_TEXT_CHARS = 24000;
const SEMANTIC_SEARCH_MAX_RESULTS = 10;
const SEMANTIC_SEARCH_DEFAULT_TOP_K = 5;
const SEMANTIC_SEARCH_DEFAULT_URL = 'http://127.0.0.1:8002';
const SEMANTIC_SEARCH_DEFAULT_TOKEN = 'demo-semantic-search-token';

/**
 * Configuration du service local. Le fichier config/semantic-search.php est
 * prioritaire, puis les variables d'environnement, puis les valeurs de démo.
 * @return array{url:string, token:string, timeout:int}
 */
function semantic_search_config(): array {
    $config = [
        'url' => SEMANTIC_SEARCH_DEFAULT_URL,
        'token' => SEMANTIC_SEARCH_DEFAULT_TOKEN,
        'timeout' => 120,
    ];
    $file = dirname(__DIR__) . '/config/semantic-search.php';
    if (is_file($file)) {
        $custom = require $file;
        if (is_array($custom)) {
            if (is_string($custom['url'] ?? null) && $custom['url'] !== '') $config['url'] = $custom['url'];
            if (is_string($custom['token'] ?? null) && $custom['token'] !== '') $config['token'] = $custom['token'];
            if (is_int($custom['timeout'] ?? null) && $custom['timeout'] > 0) $config['timeout'] = $custom['timeout'];
        }
    }
    $url = getenv('SEMANTIC_SEARCH_URL');
    if (is_string($url) && $url !== '') $config['url'] = $url;
    $token = getenv('SEMANTIC_SEARCH_TOKEN');
    if (is_string($token) && $token !== '') $config['token'] = $token;
    $config['url'] = rtrim($config['url'], '/');
    $config['timeout'] = max(5, min(300, $config['timeout']));
    return $config;
}

/** Valide la question de l'étudiant (2 à 200 caractères). */
function semantic_search_validate_query(mixed $value): string {
    if (!is_string($value)) {
        throw new QuizException('La recherche doit être un texte.', 422);
    }
    $query = trim($value);
    $length = mb_strlen($query);
    if ($length < SEMANTIC_SEARCH_QUERY_MIN_CHARS || $length > SEMANTIC_SEARCH_QUERY_MAX_CHARS) {
        throw new QuizException(
            'La recherche doit contenir entre ' . SEMANTIC_SEARCH_QUERY_MIN_CHARS
            . ' et ' . SEMANTIC_SEARCH_QUERY_MAX_CHARS . ' caractères.',
            422
        );
    }
    return $query;
}

/** Nombre de passages demandés (1 à 10). */
function semantic_search_validate_top_k(mixed $value): int {
    if ($value === null || $value === '') return SEMANTIC_SEARCH_DEFAULT_TOP_K;
    if (is_bool($value) || !is_numeric($value)) {
        throw new QuizException('Le nombre de résultats doit être un entier.', 422);
    }
    $topK = (int)$value;
    if ($topK < 1 || $topK > SEMANTIC_SEARCH_MAX_RESULTS) {
        throw new QuizException(
            'Le nombre de résultats doit être compris entre 1 et '
            . SEMANTIC_SEARCH_MAX_RESULTS . '.',
            422
        );
    }
    return $topK;
}

/**
 * Extrait le texte des cours TXT et DOCX de l'étudiant.
 * Les PDF, les fichiers vides et les cours illisibles sont comptés dans skipped.
 *
 * @param array<int, array{id?:int|string, title?:string, original_name?:string, stored_name?:string}> $courses
 * @return array{notes: array<int, array{id:string, title:string, text:string}>, skipped:int}
 */
function semantic_search_notes(array $courses, string $root): array {
    $skipped = max(0, count($courses) - SEMANTIC_SEARCH_MAX_COURSES);
    $notes = [];
    foreach (array_slice($courses, 0, SEMANTIC_SEARCH_MAX_COURSES) as $course) {
        $id = isset($course['id']) ? trim((string)$course['id']) : '';
        $stored = isset($course['stored_name']) ? basename((string)$course['stored_name']) : '';
        $original = isset($course['original_name']) ? (string)$course['original_name'] : '';
        $ext = strtolower(pathinfo($original, PATHINFO_EXTENSION));
        if ($id === '' || $stored === '' || !in_array($ext, ['txt', 'docx'], true)) {
            $skipped++;
            continue;
        }
        $path = $root . '/storage/courses/' . $stored;
        try {
            $text = quiz_read_text($path, $ext);
        } catch (QuizException $e) {
            error_log('Semantic search: ' . $e->getMessage());
            $skipped++;
            continue;
        }
        $text = trim((string)preg_replace('/[ \t]+/u', ' ', str_replace(["\r\n", "\r"], "\n", $text)));
        $text = trim((string)preg_replace('/\n{3,}/u', "\n\n", $text));
        if ($text === '') {
            $skipped++;
            continue;
        }
        if (mb_strlen($text) > SEMANTIC_SEARCH_MAX_TEXT_CHARS) {
            $text = mb_substr($text, 0, SEMANTIC_SEARCH_MAX_TEXT_CHARS);
        }
        $title = isset($course['title']) ? trim((string)preg_replace('/\s+/u', ' ', strip_tags((string)$course['title']))) : '';
        if ($title === '') $title = 'Cours';
        if (mb_strlen($title) > 200) $title = mb_substr($title, 0, 200);
        $notes[] = ['id' => $id, 'title' => $title, 'text' => $text];
    }
    return ['notes' => $notes, 'skipped' => $skipped];
}

/**
 * Appelle le service Python local et convertit les passages en lignes prêtes
 * pour l'interface. Le texte renvoyé est toujours traité comme du texte brut.
 *
 * @param array<int, array{id:string, title:string, text:string}> $notes
 * @return array{results: array<int, array{course_id:int, course_name:string, passage:string, score:float}>, skipped:int, backend:string, passages:int}
 */
function semantic_search_request(array $notes, string $query, int $topK, int $skipped): array {
    if ($notes === []) {
        throw new QuizException('Aucun cours TXT ou DOCX lisible. Importez un cours texte pour utiliser la recherche sémantique.', 422);
    }
    $config = semantic_search_config();
    $payload = json_encode(
        ['query' => $query, 'top_k' => $topK, 'notes' => $notes],
        JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES
    );
    if ($payload === false) {
        throw new QuizException('Impossible de préparer la recherche.', 500);
    }
    $ch = curl_init($config['url'] . '/search');
    if ($ch === false) {
        throw new QuizException('Le service de recherche sémantique est indisponible.', 503);
    }
    curl_setopt_array($ch, [
        CURLOPT_POST => true,
        CURLOPT_HTTPHEADER => [
            'Content-Type: application/json; charset=utf-8',
            'Accept: application/json',
            'Authorization: Bearer ' . $config['token'],
        ],
        CURLOPT_POSTFIELDS => $payload,
        CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => min(10, $config['timeout']),
        CURLOPT_TIMEOUT => $config['timeout'],
    ]);
    $body = curl_exec($ch);
    $status = (int)curl_getinfo($ch, CURLINFO_RESPONSE_CODE);
    $errno = curl_errno($ch);
    $error = curl_error($ch);
    curl_close($ch);

    if ($body === false) {
        error_log('Semantic search transport: ' . $errno . ' ' . $error);
        throw new QuizException(
            'Service de recherche sémantique indisponible. Lancez lancer-recherche-semantique.bat puis réessayez.',
            503
        );
    }
    $data = json_decode((string)$body, true);
    if ($status === 401 || $status === 403) {
        throw new QuizException(
            'Service de recherche sémantique : jeton invalide. Vérifiez config/semantic-search.php.',
            503
        );
    }
    if ($status !== 200 || !is_array($data) || !is_array($data['results'] ?? null)) {
        error_log('Semantic search HTTP ' . $status . ': ' . mb_substr((string)$body, 0, 500));
        $message = is_array($data) && is_string($data['error'] ?? null) && $data['error'] !== ''
            ? $data['error']
            : 'Le service de recherche sémantique a renvoyé une réponse invalide.';
        throw new QuizException($message, $status >= 400 && $status < 500 ? 422 : 502);
    }

    $titles = [];
    foreach ($notes as $note) $titles[$note['id']] = $note['title'];
    $results = [];
    foreach (array_slice($data['results'], 0, SEMANTIC_SEARCH_MAX_RESULTS) as $hit) {
        if (!is_array($hit)) continue;
        $noteId = isset($hit['note_id']) ? trim((string)$hit['note_id']) : '';
        $passage = isset($hit['passage']) && is_string($hit['passage'])
            ? trim($hit['passage'])
            : '';
        if ($noteId === '' || $passage === '') continue;
        if (mb_strlen($passage) > 700) $passage = mb_substr($passage, 0, 700) . '…';
        $results[] = [
            'course_id' => ctype_digit($noteId) ? (int)$noteId : 0,
            'course_name' => $titles[$noteId] ?? (isset($hit['title']) && is_string($hit['title']) ? $hit['title'] : 'Cours'),
            'passage' => $passage,
            'score' => round((float)($hit['score'] ?? 0), 3),
        ];
    }
    return [
        'results' => $results,
        'skipped' => $skipped,
        'backend' => is_string($data['backend'] ?? null) ? $data['backend'] : '',
        'passages' => (int)($data['passages'] ?? 0),
    ];
}

/**
 * Recherche sémantique complète : validation, extraction des cours, appel HTTP.
 * @param array<int, array<string, mixed>> $courses
 * @return array{results: array<int, array{course_id:int, course_name:string, passage:string, score:float}>, skipped:int, backend:string, passages:int}
 */
function semantic_search_courses(array $courses, mixed $queryValue, mixed $topKValue, string $root): array {
    $query = semantic_search_validate_query($queryValue);
    $topK = semantic_search_validate_top_k($topKValue);
    $prepared = semantic_search_notes($courses, $root);
    return semantic_search_request($prepared['notes'], $query, $topK, $prepared['skipped']);
}
