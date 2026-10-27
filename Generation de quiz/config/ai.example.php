<?php
declare(strict_types=1);
// Copiez ce fichier vers ai.php et renseignez votre clé API.
// ai.php est ignoré par Git : ne le publiez jamais.
// Sans clé ici, la variable d’environnement OPENAI_API_KEY est utilisée si elle existe.
return [
    'api_key' => '',
    'model' => 'gpt-4o-mini',
    // Modèle capable de lire les images (quiz « Questions avec image »). Par défaut, le modèle ci-dessus.
    'vision_model' => 'gpt-4o-mini',
    'base_url' => 'https://api.openai.com/v1',
];
