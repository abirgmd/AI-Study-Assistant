<?php
// Configuration locale de la recherche sémantique (module 2).
// Copiez ce fichier vers config/semantic-search.php pour personnaliser le service.
// Le jeton doit être identique à SEMANTIC_SEARCH_TOKEN au lancement du service.
return [
    'url' => 'http://127.0.0.1:8002',
    'token' => 'demo-semantic-search-token',
    'timeout' => 120,
];
