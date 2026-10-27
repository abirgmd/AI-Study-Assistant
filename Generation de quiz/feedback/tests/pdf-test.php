<?php
require dirname(__DIR__).'/analyze.php';
try {
    echo json_encode(feedback_analyze_pdf($argv[1] ?? ''), JSON_PRETTY_PRINT | JSON_UNESCAPED_UNICODE)."\n";
} catch (Throwable $e) { echo 'ERREUR : '.$e->getMessage()."\n"; }