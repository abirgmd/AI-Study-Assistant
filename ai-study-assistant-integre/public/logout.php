<?php
require dirname(__DIR__).'/app/bootstrap.php';
if ($_SERVER['REQUEST_METHOD']!=='POST') { http_response_code(405); header('Allow: POST'); exit; }
require_csrf();
$_SESSION=[];
$p=session_get_cookie_params();
setcookie(session_name(),'', ['expires'=>time()-42000,'path'=>$p['path'],'secure'=>$p['secure'],'httponly'=>true,'samesite'=>'Lax']);
session_destroy();
redirect('login.php');
