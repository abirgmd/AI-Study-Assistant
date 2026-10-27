<?php
declare(strict_types=1);
require_once __DIR__.'/gemini.php';
require_once __DIR__.'/prompt.php';

function feedback_analyze_pdf(string $path): array {
    if (!is_file($path) || filesize($path) > 5 * 1024 * 1024)
        throw new RuntimeException('PDF introuvable ou trop lourd (5 Mo maximum).');
    $raw = file_get_contents($path);
    if (!str_starts_with($raw, '%PDF-'))
        throw new RuntimeException('Le fichier n’est pas un vrai PDF.');

    $parts = [
        ['inline_data' => ['mime_type' => 'application/pdf', 'data' => base64_encode($raw)]],
        ['text' => 'Analyse ces résultats de quiz.'],
    ];
    $out = gemini_call($parts, feedback_system_prompt());

    foreach (['score','niveau','points_forts','points_faibles','conseils','plan_revision'] as $k)
        if (!isset($out[$k])) throw new RuntimeException("Réponse IA incomplète : $k");
    return $out;
}