<?php
declare(strict_types=1);
// Copiez ce fichier vers ia-service.php (ignoré par Git).
// Le jeton doit être identique à AI_INTERNAL_TOKEN dans ai-service/.env, 32 caractères minimum.
// Générez-le avec : python -c "import secrets; print(secrets.token_hex(32))"
return [
    'base_url' => 'http://127.0.0.1:8001',
    'token' => '',
    'connect_timeout' => 2,
    'timeout' => 120,
    'index_timeout' => 180,
];
