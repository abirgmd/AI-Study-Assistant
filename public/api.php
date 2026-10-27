<?php
require dirname(__DIR__).'/app/bootstrap.php';
require_once dirname(__DIR__).'/app/quiz.php';
require_once dirname(__DIR__).'/app/study.php';
require_once dirname(__DIR__).'/app/quiz_pdf.php';
require_once dirname(__DIR__).'/ia-modules/service.php';
require_once dirname(__DIR__).'/ia-modules/courses.php';
header('Content-Type: application/json; charset=utf-8');
function respond(array $data, int $status=200): never { http_response_code($status); echo json_encode($data,JSON_UNESCAPED_UNICODE); exit; }
if (!student_id()) respond(['error'=>'Connectez-vous pour continuer.'],401);
$action=is_string($_GET['action'] ?? null) ? $_GET['action'] : '';
$method=$_SERVER['REQUEST_METHOD'];
if (!in_array($method,['GET','POST'],true)) respond(['error'=>'Méthode non autorisée.'],405);
if ($method==='POST' && !valid_csrf()) respond(['error'=>'Session expirée. Rechargez la page.'],403);
function goal_date(): string {
 $date=is_string($_GET['date'] ?? null) ? $_GET['date'] : '';
 $parsed=DateTimeImmutable::createFromFormat('!Y-m-d',$date);
 if (!$parsed || $parsed->format('Y-m-d')!==$date) respond(['error'=>'Date invalide.'],422);
 return $date;
}
try {
 $conn=db(); $id=student_id();
 if ($action==='courses' && $method==='GET') {
   $q=$conn->prepare('SELECT id,title AS name,category AS type,original_name,file_size,created_at FROM courses WHERE student_id=? ORDER BY created_at DESC,id DESC'); $q->execute([$id]);
   respond(['courses'=>$q->fetchAll()]);
 }
 if ($action==='upload' && $method==='POST') {
   if (!isset($_FILES['course']) || !is_array($_FILES['course']) || is_array($_FILES['course']['error'])) respond(['error'=>'Sélectionnez un fichier PDF, TXT ou DOCX (10 Mo maximum).'],422);
   $f=$_FILES['course'];
   if ($f['error']!==UPLOAD_ERR_OK) respond(['error'=>'Téléversement échoué. Vérifiez la taille du fichier et les limites PHP.'],422);
   if ($f['size']<1 || $f['size']>10*1024*1024) respond(['error'=>'Le fichier doit peser entre 1 octet et 10 Mo.'],422);
   $original=basename(str_replace('\\','/',(string)$f['name']));
   if (strlen($original)>240 || !preg_match('//u',$original)) respond(['error'=>'Raccourcissez le nom du fichier (240 octets maximum).'],422);
   $ext=strtolower(pathinfo($original,PATHINFO_EXTENSION));
   $mime=(new finfo(FILEINFO_MIME_TYPE))->file($f['tmp_name']);
   $allowed=['pdf'=>['application/pdf'],'txt'=>['text/plain'],'docx'=>['application/zip','application/vnd.openxmlformats-officedocument.wordprocessingml.document']];
   if (!isset($allowed[$ext]) || !in_array($mime,$allowed[$ext],true)) respond(['error'=>'Format refusé. Utilisez un véritable PDF, TXT ou DOCX.'],422);
   if ($ext==='docx') {
     $zip=new ZipArchive();
     if ($zip->open($f['tmp_name'])!==true) respond(['error'=>'Document DOCX invalide.'],422);
     $valid=$zip->locateName('[Content_Types].xml')!==false && $zip->locateName('word/document.xml')!==false;
     $zip->close();
     if (!$valid) respond(['error'=>'Document DOCX invalide.'],422);
   }
   $stored=bin2hex(random_bytes(24)).'.'.$ext;
   $path=dirname(__DIR__).'/storage/courses/'.$stored;
   if (!move_uploaded_file($f['tmp_name'],$path)) throw new RuntimeException('Écriture fichier impossible.');
   try {
      $q=$conn->prepare('INSERT INTO courses(student_id,title,original_name,stored_name,mime_type,file_size) VALUES (?,?,?,?,?,?)');
      $q->execute([$id,pathinfo($original,PATHINFO_FILENAME),$original,$stored,$mime,(int)$f['size']]);
   } catch (Throwable $e) { @unlink($path); throw $e; }
   // Modules 3 et 5 : indexation et classification. Le cours est déjà enregistré : une panne de l'IA ne fait pas échouer l'import.
   $newId=(int)$conn->lastInsertId();
   set_time_limit(200);
   session_write_close();
   $course=owned_course($conn,$newId);
   $ai=$course ? process_course_ai($conn,$course) : ['indexed'=>false,'classified'=>false,'message'=>''];
   $note=$ai['indexed'] ? ' Il est prêt pour l’Assistant IA 2.' : ($ai['message']!=='' ? ' '.$ai['message'] : '');
   respond(['message'=>'Cours importé. Le document est conservé dans votre espace.'.$note,'course_id'=>$newId,'indexed'=>$ai['indexed'],'classified'=>$ai['classified']],201);
 }
 if ($action==='goals' && $method==='GET') {
   $date=goal_date(); $q=$conn->prepare('SELECT goal_index,completed FROM daily_goals WHERE student_id=? AND goal_date=?'); $q->execute([$id,$date]);
   $goals=[false,false,false]; foreach ($q as $row) { $i=(int)$row['goal_index']; if($i>=0 && $i<3) $goals[$i]=(bool)$row['completed']; }
   respond(['goals'=>$goals]);
 }
 if ($action==='goals' && $method==='POST') {
   $date=goal_date(); $index=filter_var($_POST['index'] ?? null,FILTER_VALIDATE_INT); $done=$_POST['completed'] ?? null;
   if ($index===false || $index===null || $index<0 || $index>2 || !in_array($done,['0','1'],true)) respond(['error'=>'Objectif invalide.'],422);
   $q=$conn->prepare('INSERT INTO daily_goals(student_id,goal_date,goal_index,completed) VALUES (?,?,?,?) ON DUPLICATE KEY UPDATE completed=VALUES(completed)'); $q->execute([$id,$date,$index,(int)$done]);
   respond(['ok'=>true]);
 }
 if ($action==='quiz_generate' && $method==='POST') {
   set_time_limit(150);
   $courseId=filter_var($_POST['course_id'] ?? null,FILTER_VALIDATE_INT);
   $count=filter_var($_POST['count'] ?? null,FILTER_VALIDATE_INT);
   if ($courseId===false || $courseId<1) respond(['error'=>'Choisissez un cours.'],422);
   if ($count===false || $count<QUIZ_MIN_QUESTIONS || $count>QUIZ_MAX_QUESTIONS) respond(['error'=>'Choisissez entre '.QUIZ_MIN_QUESTIONS.' et '.QUIZ_MAX_QUESTIONS.' questions.'],422);
   $kind=is_string($_POST['kind'] ?? null) ? $_POST['kind'] : 'mcq';
   if (!in_array($kind,QUIZ_KINDS,true)) respond(['error'=>'Type de quiz inconnu.'],422);
   $q=$conn->prepare('SELECT id,title,original_name,stored_name FROM courses WHERE id=? AND student_id=?'); $q->execute([$courseId,$id]);
   $course=$q->fetch();
   if (!$course) respond(['error'=>'Cours introuvable.'],404);
   try {
     $ext=strtolower(pathinfo((string)$course['original_name'],PATHINFO_EXTENSION));
     $path=dirname(__DIR__).'/storage/courses/'.basename((string)$course['stored_name']);
     $source=quiz_source_text($path,$ext);
     $images=in_array($kind,['image','mixed'],true) ? quiz_source_images($path,$ext) : [];
     if ($kind==='image' && $images===[]) throw new QuizException('Ce cours ne contient pas d’image exploitable. Importez un DOCX avec des images PNG ou JPEG de 1 Mo au plus.',422);
     $result=quiz_validate_questions(quiz_request_questions($source['text'],$count,$kind,$images),$count,$kind,$images);
     $title=mb_substr('Quiz · '.$course['title'],0,255);
     $q=$conn->prepare('INSERT INTO quizzes(student_id,course_id,title,questions) VALUES (?,?,?,?)');
     $q->execute([$id,(int)$course['id'],$title,json_encode($result['questions'],JSON_UNESCAPED_UNICODE)]);
     respond(['quiz'=>['id'=>(int)$conn->lastInsertId(),'title'=>$title,'course_name'=>$course['title'],'questions'=>$result['questions']],'rejected'=>$result['rejected'],'with_image'=>$result['with_image'],'source_truncated'=>$source['truncated']],201);
   } catch (QuizException $e) { respond(['error'=>$e->getMessage()],$e->getCode() ?: 422); }
 }
 if ($action==='search' && $method==='GET') {
   $query=trim(is_string($_GET['q'] ?? null) ? $_GET['q'] : '');
   $length=mb_strlen($query);
   if ($length<STUDY_QUERY_MIN_CHARS || $length>STUDY_QUERY_MAX_CHARS) respond(['error'=>'Saisissez entre '.STUDY_QUERY_MIN_CHARS.' et '.STUDY_QUERY_MAX_CHARS.' caractères.'],422);
   $q=$conn->prepare('SELECT id,title,original_name,stored_name FROM courses WHERE student_id=? ORDER BY created_at DESC,id DESC'); $q->execute([$id]);
   respond(study_search($q->fetchAll(),$query));
 }
 if ($action==='assistant' && $method==='POST') {
   $courseId=filter_var($_POST['course_id'] ?? null,FILTER_VALIDATE_INT);
   $question=trim(is_string($_POST['question'] ?? null) ? $_POST['question'] : '');
   if ($courseId===false || $courseId<1) respond(['error'=>'Choisissez un cours.'],422);
   $length=mb_strlen($question);
   if ($length<STUDY_QUESTION_MIN_CHARS || $length>STUDY_QUESTION_MAX_CHARS) respond(['error'=>'Posez une question de '.STUDY_QUESTION_MIN_CHARS.' à '.STUDY_QUESTION_MAX_CHARS.' caractères.'],422);
   $q=$conn->prepare('SELECT id,title,original_name,stored_name FROM courses WHERE id=? AND student_id=?'); $q->execute([$courseId,$id]);
   $course=$q->fetch();
   if (!$course) respond(['error'=>'Cours introuvable.'],404);
   try {
     $ext=strtolower(pathinfo((string)$course['original_name'],PATHINFO_EXTENSION));
     $path=dirname(__DIR__).'/storage/courses/'.basename((string)$course['stored_name']);
     $reply=study_ask(study_relevant_text(study_course_text($path,$ext),$question),$question);
     respond(['answer'=>$reply['answer'],'found_in_course'=>$reply['found_in_course'],'course_name'=>$course['title']]);
   } catch (QuizException $e) { respond(['error'=>$e->getMessage()],$e->getCode() ?: 422); }
 }
 if ($action==='quiz_pdf' && $method==='POST') {
   $quizId=filter_var($_POST['quiz_id'] ?? null,FILTER_VALIDATE_INT);
   if ($quizId===false || $quizId<1) respond(['error'=>'Quiz introuvable.'],404);
   $q=$conn->prepare('SELECT q.title,q.created_at,c.title AS course_name,q.questions FROM quizzes q JOIN courses c ON c.id=q.course_id WHERE q.id=? AND q.student_id=?'); $q->execute([$quizId,$id]);
   $quiz=$q->fetch();
   if (!$quiz) respond(['error'=>'Quiz introuvable.'],404);
   $questions=json_decode((string)$quiz['questions'],true);
   if (!is_array($questions) || $questions===[]) respond(['error'=>'Ce quiz ne contient aucune question.'],422);
   try {
     $answers=quiz_pdf_answers($questions,json_decode(is_string($_POST['answers'] ?? null) ? $_POST['answers'] : 'null',true));
   } catch (QuizException $e) { respond(['error'=>$e->getMessage()],$e->getCode() ?: 422); }
   $pdf=quiz_pdf_document(quiz_pdf_lines((string)$quiz['title'],(string)$quiz['course_name'],date('d/m/Y H:i'),$questions,$answers));
   header('Content-Type: application/pdf');
   header('Content-Disposition: attachment; filename="quiz-reponses-'.$quizId.'.pdf"');
   header('Content-Length: '.strlen($pdf));
   echo $pdf; exit;
 }
 if ($action==='quiz_score' && $method==='POST') {
   $quizId=filter_var($_POST['quiz_id'] ?? null,FILTER_VALIDATE_INT);
   if ($quizId===false || $quizId<1) respond(['error'=>'Quiz introuvable.'],404);
   $q=$conn->prepare('SELECT questions FROM quizzes WHERE id=? AND student_id=?'); $q->execute([$quizId,$id]);
   $questions=json_decode((string)$q->fetchColumn(),true);
   if (!is_array($questions) || $questions===[]) respond(['error'=>'Quiz introuvable.'],404);
   try {
     $answers=quiz_pdf_answers($questions,json_decode(is_string($_POST['answers'] ?? null) ? $_POST['answers'] : 'null',true));
   } catch (QuizException $e) { respond(['error'=>$e->getMessage()],$e->getCode() ?: 422); }
   // Le score est recalculé ici, à partir du quiz enregistré : le navigateur n’envoie que les choix.
   $result=quiz_pdf_score($questions,$answers);
   if ($result['scored']<1) respond(['error'=>'Ce quiz n’est pas noté.'],422);
   $q=$conn->prepare('INSERT INTO quiz_attempts(student_id,quiz_id,score,total) VALUES (?,?,?,?)'); $q->execute([$id,$quizId,$result['score'],$result['scored']]);
   respond(['score'=>$result['score'],'total'=>$result['scored']],201);
 }
 if ($action==='stats' && $method==='GET') {
   $q=$conn->prepare('SELECT COUNT(*) AS attempts, ROUND(AVG(score*100/total)) AS average FROM quiz_attempts WHERE student_id=?'); $q->execute([$id]);
   $row=$q->fetch();
   respond(['attempts'=>(int)$row['attempts'],'average'=>$row['average']===null?null:(int)$row['average']]);
 }
 if ($action==='quiz_kinds' && $method==='GET') {
   respond(['kinds'=>QUIZ_KIND_OPTIONS]);
 }
 if ($action==='quizzes' && $method==='GET') {
   $q=$conn->prepare('SELECT q.id,q.title,q.created_at,c.title AS course_name,JSON_LENGTH(q.questions) AS question_count FROM quizzes q JOIN courses c ON c.id=q.course_id WHERE q.student_id=? ORDER BY q.created_at DESC,q.id DESC'); $q->execute([$id]);
   respond(['quizzes'=>$q->fetchAll()]);
 }
 if ($action==='quiz' && $method==='GET') {
   $quizId=filter_var($_GET['id'] ?? null,FILTER_VALIDATE_INT);
   if ($quizId===false || $quizId<1) respond(['error'=>'Quiz introuvable.'],404);
   $q=$conn->prepare('SELECT q.id,q.title,q.created_at,c.title AS course_name,q.questions FROM quizzes q JOIN courses c ON c.id=q.course_id WHERE q.id=? AND q.student_id=?'); $q->execute([$quizId,$id]);
   $quiz=$q->fetch();
   if (!$quiz) respond(['error'=>'Quiz introuvable.'],404);
   $quiz['questions']=json_decode((string)$quiz['questions'],true) ?: [];
   respond(['quiz'=>$quiz]);
 }
 respond(['error'=>'Action inconnue.'],404);
} catch (Throwable $e) { error_log('Study API: '.$e->getMessage()); respond(['error'=>'Service indisponible. Vérifiez la configuration MySQL et les droits du dossier storage/courses.'],503); }
