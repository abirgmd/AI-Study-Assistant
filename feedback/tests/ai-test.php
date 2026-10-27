<?php
$c = require dirname(__DIR__,2).'/config/gemini.php';
$url = 'https://generativelanguage.googleapis.com/v1beta/models/'.$c['model'].':generateContent';
$body = ['contents'=>[['parts'=>[['text'=>'Say hello in one short French sentence.']]]]];
$ch = curl_init($url);
curl_setopt_array($ch, [
  CURLOPT_POST => true,
  CURLOPT_RETURNTRANSFER => true,
  CURLOPT_TIMEOUT => 30,
  CURLOPT_HTTPHEADER => ['Content-Type: application/json', 'x-goog-api-key: '.$c['api_key']],
  CURLOPT_POSTFIELDS => json_encode($body),
]);
echo curl_exec($ch)."\n";
echo 'HTTP '.curl_getinfo($ch, CURLINFO_HTTP_CODE)."\n";