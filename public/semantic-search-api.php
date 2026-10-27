<?php
// API JSON de la recherche sémantique (module 2).
// Session obligatoire, lecture seule (GET), puis appel du service Python local.
// Le dossier modules/semantic_search/ n'est jamais exposé par URL.
require dirname(__DIR__) . '/app/bootstrap.php';
require_once dirname(__DIR__) . '/app/quiz.php';
require_once dirname(__DIR__) . '/app/semantic_search.php';
header('Content-Type: application/json; charset=utf-8');
header('Cache-Control: no-store');

function semantic_search_respond(array $data, int $status = 200): never {
    http_response_code($status);
    echo json_encode($data, JSON_UNESCAPED_UNICODE | JSON_UNESCAPED_SLASHES);
    exit;
}

if (!student_id()) {
    semantic_search_respond(['error' => 'Connectez-vous pour continuer.'], 401);
}
if ($_SERVER['REQUEST_METHOD'] !== 'GET') {
    semantic_search_respond(['error' => 'Méthode non autorisée.'], 405);
}
session_write_close();   // la recherche ne modifie pas la session : les autres onglets restent fluides
set_time_limit(150);     // le premier appel peut charger le modèle local

try {
    $db = db();
    $q = $db->prepare(
        'SELECT id, title, original_name, stored_name FROM courses '
        . 'WHERE student_id = ? ORDER BY created_at DESC, id DESC'
    );
    $q->execute([student_id()]);
    $data = semantic_search_courses(
        $q->fetchAll(),
        $_GET['q'] ?? null,
        $_GET['top_k'] ?? null,
        dirname(__DIR__)
    );
    semantic_search_respond($data);
} catch (QuizException $e) {
    $status = $e->getCode();
    if ($status < 400 || $status > 599) $status = 422;
    semantic_search_respond(['error' => $e->getMessage()], $status);
} catch (Throwable $e) {
    error_log('Semantic search API: ' . $e->getMessage());
    semantic_search_respond([
        'error' => 'Service de recherche sémantique indisponible. Vérifiez MySQL, les droits de storage/courses et le service local.',
    ], 503);
}
