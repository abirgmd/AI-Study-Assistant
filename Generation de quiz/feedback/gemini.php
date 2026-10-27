<?php
declare(strict_types=1);
function gemini_call(array $parts, string $system = '', bool $json = true): array|string {
    $path = dirname(__DIR__).'/config/gemini.php';
    $c = is_file($path) ? require $path : [];
    if (empty($c['api_key']) || $c['api_key'] === 'PASTE_YOUR_KEY_HERE') throw new RuntimeException('Clé IA absente.');
    $body = ['contents' => [['parts' => $parts]]];
    if ($system !== '') $body['systemInstruction'] = ['parts' => [['text' => $system]]];
    if ($json) $body['generationConfig'] = ['responseMimeType' => 'application/json'];
    $ch = curl_init('https://generativelanguage.googleapis.com/v1beta/models/'.$c['model'].':generateContent');
    curl_setopt_array($ch, [
        CURLOPT_POST => true, CURLOPT_RETURNTRANSFER => true, CURLOPT_TIMEOUT => 60,
        CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'x-goog-api-key: '.$c['api_key']],
        CURLOPT_POSTFIELDS => json_encode($body),
    ]);
    for ($try = 0; $try < 3; $try++) {
        $res = curl_exec($ch);
        $code = curl_getinfo($ch, CURLINFO_HTTP_CODE);
        if ($res !== false && !in_array($code, [500, 503], true)) break;
        sleep(2);
    }
        if ($res === false) throw new RuntimeException('Délai dépassé ou réseau indisponible.');
    if ($code === 429) throw new RuntimeException('Quota IA atteint, réessayez plus tard.');
    if ($code !== 200) throw new RuntimeException('Erreur du service IA ('.$code.').');
    $text = '';
    foreach (json_decode($res, true)['candidates'][0]['content']['parts'] ?? [] as $p) $text .= $p['text'] ?? '';
    if (!$json) return $text;
    $data = json_decode($text, true);
    if (!is_array($data)) throw new RuntimeException('Réponse IA invalide.');
    return $data;
}