<?php
declare(strict_types=1);
// Modules 3 et 5 : client HTTP du service IA Python (ai-service/).
// Ne démarre pas la session : ce fichier est chargé par public/ia-api.php et public/api.php (après app/bootstrap.php).
// Le service n'écoute que sur 127.0.0.1 et exige le jeton interne défini dans config/ia-service.php.
// Ce fichier n'utilise PAS config/ai.php : ce fichier-là contient la configuration Groq du quiz.

final class AiServiceUnavailable extends RuntimeException {}

function ai_config(): array {
    static $config = null;
    if ($config !== null) return $config;
    $path = dirname(__DIR__).'/config/ia-service.php';
    $file = is_file($path) ? require $path : [];
    $config = array_merge(
        ['base_url' => 'http://127.0.0.1:8001', 'token' => '', 'connect_timeout' => 2, 'timeout' => 60, 'index_timeout' => 180],
        is_array($file) ? $file : []
    );
    $env = getenv('AI_INTERNAL_TOKEN');
    if ($config['token'] === '' && is_string($env)) $config['token'] = $env;
    return $config;
}

/**
 * Appelle le service IA. Retourne ['status' => code HTTP, 'data' => tableau JSON].
 * Lève AiServiceUnavailable si le service est arrêté, injoignable ou mal configuré :
 * l'appelant affiche alors un message clair, jamais une trace d'erreur.
 */
function ai_request(string $method, string $path, ?array $payload = null, ?int $timeout = null): array {
    $c = ai_config();
    if (!extension_loaded('curl')) throw new AiServiceUnavailable('Extension PHP curl absente.');
    if (strlen((string)$c['token']) < 32) throw new AiServiceUnavailable('Jeton du service IA non configuré.');
    $curl = curl_init(rtrim((string)$c['base_url'], '/').$path);
    $headers = ['Accept: application/json', 'X-Internal-Token: '.$c['token']];
    $options = [
        CURLOPT_CUSTOMREQUEST => $method, CURLOPT_RETURNTRANSFER => true,
        CURLOPT_CONNECTTIMEOUT => (int)$c['connect_timeout'], CURLOPT_TIMEOUT => $timeout ?? (int)$c['timeout'],
        CURLOPT_FOLLOWLOCATION => false, CURLOPT_PROXY => '', CURLOPT_NOPROXY => '*',
    ];
    if ($payload !== null) {
        $options[CURLOPT_POSTFIELDS] = json_encode($payload, JSON_UNESCAPED_UNICODE | JSON_THROW_ON_ERROR);
        $headers[] = 'Content-Type: application/json';
    }
    $options[CURLOPT_HTTPHEADER] = $headers;
    curl_setopt_array($curl, $options);
    $body = curl_exec($curl);
    $status = (int)curl_getinfo($curl, CURLINFO_RESPONSE_CODE);
    $error = curl_errno($curl);
    curl_close($curl);
    if ($body === false || $error !== 0) throw new AiServiceUnavailable('Service IA injoignable (code cURL '.$error.').');
    $data = json_decode((string)$body, true);
    if (!is_array($data)) throw new AiServiceUnavailable('Réponse invalide du service IA (HTTP '.$status.').');
    if ($status === 401) throw new AiServiceUnavailable('Jeton du service IA refusé : vérifiez config/ia-service.php et ai-service/.env.');
    if ($status >= 500) throw new AiServiceUnavailable((string)($data['detail'] ?? 'Erreur du service IA.'));
    return ['status' => $status, 'data' => $data];
}

function ai_unavailable_message(): string {
    return 'L’Assistant IA 2 est momentanément indisponible. Vérifiez que le service IA (ai-service) est démarré, puis réessayez.';
}
