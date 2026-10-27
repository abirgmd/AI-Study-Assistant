<?php
require dirname(__DIR__).'/gemini.php';
print_r(gemini_call([['text' => 'Reply with JSON: {"ok": true, "msg": "salut"}']]));