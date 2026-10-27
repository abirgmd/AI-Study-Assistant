<?php
require dirname(__DIR__).'/app/bootstrap.php';
if (student_id()) redirect('index.php');
$error=''; $name=''; $email=''; $mode='signup';
if ($_SERVER['REQUEST_METHOD']==='POST') {
    require_csrf();
    $name=request_text('name'); $email=strtolower(request_text('email'));
    $password=is_string($_POST['password'] ?? null) ? $_POST['password'] : '';
    $confirm=is_string($_POST['confirm'] ?? null) ? $_POST['confirm'] : '';
    if (strlen($name)<2 || strlen($name)>100) $error='Le nom doit contenir entre 2 et 100 octets.';
    elseif (!filter_var($email,FILTER_VALIDATE_EMAIL) || strlen($email)>254) $error='Saisissez une adresse e-mail valide.';
    elseif (strlen($password)<8 || strlen($password)>72 || str_contains($password, "\0")) $error='Choisissez un mot de passe de 8 à 72 octets, sans caractère nul.';
    elseif ($password!==$confirm) $error='Les deux mots de passe ne correspondent pas.';
    else try {
        $conn=db();
        if (too_many_attempts($conn)) { http_response_code(429); $error='Trop de tentatives. Réessayez dans 15 minutes.'; }
        else {
            record_attempt($conn);
            $q=$conn->prepare('INSERT INTO students(full_name,email,password_hash) VALUES (?,?,?)');
            $q->execute([$name,$email,password_hash($password,PASSWORD_DEFAULT)]);
            sign_in((int)$conn->lastInsertId(),$name);
            redirect('index.php');
        }
    } catch (PDOException $e) {
        if (($e->errorInfo[1] ?? 0)===1062) $error='Cette adresse est déjà utilisée. Connectez-vous avec votre compte.';
        else $error=database_failure($e);
    } catch (Throwable $e) { $error=database_failure($e); }
}
require dirname(__DIR__).'/app/auth-layout.php';
