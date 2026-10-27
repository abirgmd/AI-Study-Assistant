<?php
require dirname(__DIR__).'/app/bootstrap.php';
require_student();
$id=filter_var($_GET['id'] ?? null,FILTER_VALIDATE_INT);
if (!$id || $id<1) { http_response_code(404); exit('Document introuvable.'); }
try {
 $q=db()->prepare('SELECT original_name,stored_name FROM courses WHERE id=? AND student_id=?'); $q->execute([$id,student_id()]); $file=$q->fetch();
 if (!$file) { http_response_code(404); exit('Document introuvable.'); }
 $path=dirname(__DIR__).'/storage/courses/'.basename($file['stored_name']);
 if (!is_file($path)) { http_response_code(404); exit('Document introuvable.'); }
 header('Content-Type: application/octet-stream');
 header("Content-Disposition: attachment; filename=\"cours\"; filename*=UTF-8''".rawurlencode($file['original_name']));
 header('Content-Length: '.filesize($path));
 session_write_close(); readfile($path);
} catch (Throwable $e) { http_response_code(503); echo h(database_failure($e)); }
