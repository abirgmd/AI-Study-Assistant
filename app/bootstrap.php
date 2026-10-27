<?php
declare(strict_types=1);
ini_set('display_errors', '0');
ini_set('log_errors', '1');
ini_set('session.use_strict_mode', '1');
ini_set('session.use_only_cookies', '1');
$https = !empty($_SERVER['HTTPS']) && $_SERVER['HTTPS'] !== 'off';
session_name('study_student_session');
session_set_cookie_params(['lifetime'=>0,'path'=>'/','secure'=>$https,'httponly'=>true,'samesite'=>'Lax']);
session_start();
header('X-Content-Type-Options: nosniff');
header('X-Frame-Options: DENY');
header('Referrer-Policy: same-origin');
header("Content-Security-Policy: default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; base-uri 'self'; form-action 'self'; frame-ancestors 'none'; object-src 'none'");
header('Cache-Control: no-store');
function h(string $value): string { return htmlspecialchars($value, ENT_QUOTES | ENT_SUBSTITUTE, 'UTF-8'); }
function db(): PDO {
    static $pdo = null;
    if ($pdo instanceof PDO) return $pdo;
    $path = dirname(__DIR__).'/config/database.php';
    if (!is_file($path)) throw new RuntimeException('Configuration manquante.');
    $c = require $path;
    $pdo = new PDO('mysql:host='.$c['host'].';port='.(int)$c['port'].';dbname='.$c['database'].';charset=utf8mb4',
        $c['username'], $c['password'], [PDO::ATTR_ERRMODE=>PDO::ERRMODE_EXCEPTION, PDO::ATTR_DEFAULT_FETCH_MODE=>PDO::FETCH_ASSOC, PDO::ATTR_EMULATE_PREPARES=>false]);
    $pdo->exec("SET time_zone = '+00:00'");
    return $pdo;
}
function csrf(): string {
    if (empty($_SESSION['csrf'])) $_SESSION['csrf'] = bin2hex(random_bytes(32));
    return $_SESSION['csrf'];
}
function valid_csrf(): bool {
    $token = $_POST['csrf'] ?? $_SERVER['HTTP_X_CSRF_TOKEN'] ?? '';
    return is_string($token) && hash_equals(csrf(), $token);
}
function require_csrf(): void {
    if (!valid_csrf()) { http_response_code(403); exit('Session expirée. Rechargez la page puis réessayez.'); }
}
function student_id(): int { return (int)($_SESSION['student_id'] ?? 0); }
function redirect(string $path): never { header('Location: '.$path); exit; }
function require_student(): void { if (!student_id()) redirect('login.php'); }
function sign_in(int $id, string $name): void {
    session_regenerate_id(true);
    $_SESSION = ['student_id'=>$id, 'student_name'=>$name, 'csrf'=>bin2hex(random_bytes(32))];
}
function database_failure(Throwable $e): string {
    error_log('Study Assistant: '.$e->getMessage());
    return 'Service indisponible. Vérifiez la configuration MySQL et l’import du fichier database/schema.sql.';
}
function request_text(string $name): string { return is_string($_POST[$name] ?? null) ? trim($_POST[$name]) : ''; }
function attempt_key(): string { return hash('sha256', (string)($_SERVER['REMOTE_ADDR'] ?? 'local')); }
function too_many_attempts(PDO $db): bool {
    $q=$db->prepare('SELECT attempts FROM auth_attempts WHERE attempt_key=? AND window_start > UTC_TIMESTAMP() - INTERVAL 15 MINUTE');
    $q->execute([attempt_key()]);
    return (int)$q->fetchColumn() >= 10;
}
function record_attempt(PDO $db): void {
    $q=$db->prepare('INSERT INTO auth_attempts(attempt_key,attempts,window_start) VALUES (?,1,UTC_TIMESTAMP()) ON DUPLICATE KEY UPDATE attempts=IF(window_start < UTC_TIMESTAMP() - INTERVAL 15 MINUTE,1,attempts+1), window_start=IF(window_start < UTC_TIMESTAMP() - INTERVAL 15 MINUTE,UTC_TIMESTAMP(),window_start)');
    $q->execute([attempt_key()]);
}
