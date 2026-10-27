<?php
require dirname(__DIR__).'/app/bootstrap.php';
require dirname(__DIR__).'/feedback/analyze.php';
header('Content-Type: application/json; charset=utf-8');
function respond(array $d, int $s = 200): never { http_response_code($s); echo json_encode($d, JSON_UNESCAPED_UNICODE); exit; }

if (!student_id()) respond(['error' => 'Connectez-vous pour continuer.'], 401);
if ($_SERVER['REQUEST_METHOD'] !== 'POST') respond(['error' => 'Méthode non autorisée.'], 405);
if (!valid_csrf()) respond(['error' => 'Session expirée. Rechargez la page.'], 403);

$f = $_FILES['quizpdf'] ?? null;
if (!is_array($f) || is_array($f['error']) || $f['error'] !== UPLOAD_ERR_OK)
    respond(['error' => 'Téléversement échoué. Choisissez un PDF de 5 Mo maximum.'], 422);
if ($f['size'] < 1 || $f['size'] > 5 * 1024 * 1024)
    respond(['error' => 'Le PDF doit peser 5 Mo maximum.'], 422);
if ((new finfo(FILEINFO_MIME_TYPE))->file($f['tmp_name']) !== 'application/pdf')
    respond(['error' => 'Format refusé : importez le PDF exporté depuis votre quiz.'], 422);

session_write_close();   // ne bloque pas le reste de l'app pendant l'appel IA
set_time_limit(120);
try {
    respond(['feedback' => feedback_analyze_pdf($f['tmp_name'])]);
} catch (RuntimeException $e) {
    error_log('Study feedback: '.$e->getMessage());
    respond(['error' => $e->getMessage()], 502);
} catch (Throwable $e) {
    error_log('Study feedback: '.$e->getMessage());
    respond(['error' => 'Analyse impossible pour le moment.'], 500);
}