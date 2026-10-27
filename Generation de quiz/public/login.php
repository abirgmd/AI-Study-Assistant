<?php
require dirname(__DIR__).'/app/bootstrap.php';
if (student_id()) redirect('index.php');
$error=''; $name=''; $email=''; $mode='login';
if ($_SERVER['REQUEST_METHOD']==='POST') {
    require_csrf();
    $email=strtolower(request_text('email'));
    $password=is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
    if (!filter_var($email,FILTER_VALIDATE_EMAIL) || strlen($email)>254 || $password==='' || strlen($password)>1024) $error='E-mail ou mot de passe incorrect.';
    else try {
        $conn=db();
        if (too_many_attempts($conn)) { http_response_code(429); $error='Trop de tentatives. Réessayez dans 15 minutes.'; }
        else {
            record_attempt($conn);
            $q=$conn->prepare('SELECT id,full_name,password_hash FROM students WHERE email=?'); $q->execute([$email]); $student=$q->fetch();
            // Hachage valide de comparaison pour ne pas répondre immédiatement aux comptes absents.
            $hash=$student ? $student['password_hash'] : '$2y$10$92IXUNpkjO0rOQ5byMi.Ye4oKoEa3Ro9llC/.og/at2uheWG/igi.';
            $valid=password_verify($password,$hash);
            if (!$student || !$valid) $error='E-mail ou mot de passe incorrect.';
            else {
                if (password_needs_rehash($student['password_hash'],PASSWORD_DEFAULT)) {
                    $q=$conn->prepare('UPDATE students SET password_hash=? WHERE id=?'); $q->execute([password_hash($password,PASSWORD_DEFAULT),$student['id']]);
                }
                sign_in((int)$student['id'],$student['full_name']); redirect('index.php');
            }
        }
    } catch (Throwable $e) { $error=database_failure($e); }
}
require dirname(__DIR__).'/app/auth-layout.php';
