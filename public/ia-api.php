<?php
// Passerelle du module « Assistant IA 2 » (modules 3 et 5), sur le modèle de feedback-api.php :
// session, méthode HTTP, jeton CSRF, puis la logique du dossier ia-modules/ (jamais accessible par URL).
require dirname(__DIR__).'/app/bootstrap.php';
require dirname(__DIR__).'/ia-modules/service.php';
require dirname(__DIR__).'/ia-modules/courses.php';
require dirname(__DIR__).'/ia-modules/rag.php';
header('Content-Type: application/json; charset=utf-8');
function respond(array $d, int $s = 200): never { http_response_code($s); echo json_encode($d, JSON_UNESCAPED_UNICODE); exit; }

if (!student_id()) respond(['error' => 'Connectez-vous pour continuer.'], 401);
$method = $_SERVER['REQUEST_METHOD'];
if (!in_array($method, ['GET', 'POST'], true)) respond(['error' => 'Méthode non autorisée.'], 405);
if ($method === 'POST' && !valid_csrf()) respond(['error' => 'Session expirée. Rechargez la page.'], 403);
session_write_close();   // cette API ne modifie pas la session : les autres requêtes ne attendent pas l'appel IA
$action = is_string($_GET['action'] ?? null) ? $_GET['action'] : '';
$studentId = student_id();

/** Cours désigné par course_id : il doit appartenir à l'étudiant connecté, sinon 404. */
function posted_course(PDO $db): array {
    $courseId = filter_var($_POST['course_id'] ?? null, FILTER_VALIDATE_INT);
    $course = $courseId ? owned_course($db, (int)$courseId) : null;
    if (!$course) respond(['error' => 'Cours introuvable.'], 404);
    return $course;
}

try {
    $db = db();

    // Cours de l'étudiant avec leur état IA (indexation et matière). Ne touche pas à api.php.
    if ($action === 'courses' && $method === 'GET') {
        $q = $db->prepare('SELECT id,title AS name,category AS type,category_confidence,category_source,category_suggestion AS suggestion,indexed_at IS NOT NULL AS indexed,chunk_count FROM courses WHERE student_id=? ORDER BY created_at DESC,id DESC');
        $q->execute([$studentId]);
        $courses = array_map(static function (array $c): array {
            $c['id'] = (int)$c['id'];
            $c['indexed'] = (bool)$c['indexed'];
            $c['category_confidence'] = $c['category_confidence'] === null ? null : (float)$c['category_confidence'];
            $c['chunk_count'] = $c['chunk_count'] === null ? null : (int)$c['chunk_count'];
            return $c;
        }, $q->fetchAll());
        respond(['courses' => $courses]);
    }

    if ($action === 'categories' && $method === 'GET') {
        respond(course_categories());
    }

    // Module 3 : question sur les cours (scope « course » ou « general » = connaissance générale via Ollama).
    if ($action === 'ask' && $method === 'POST') {
        $question = ia_clean_question((string)($_POST['question'] ?? ''));
        $scope = $_POST['scope'] ?? 'course';
        if (!in_array($scope, ['course', 'general'], true)) respond(['error' => 'Mode de question invalide.'], 422);
        $courseId = null;
        $rawCourse = $_POST['course_id'] ?? '';
        if ($scope === 'course' && $rawCourse !== '' && $rawCourse !== 'all') $courseId = (int)posted_course($db)['id'];
        if (ia_recent_questions($db, $studentId) >= IA_ASK_LIMIT) {
            respond(['error' => 'Vous avez posé beaucoup de questions. Réessayez dans quelques minutes.'], 429);
        }
        respond(ia_ask($db, $studentId, $question, $scope, $courseId));
    }

    if ($action === 'history' && $method === 'GET') {
        respond(['history' => ia_history($db, $studentId)]);
    }

    // Module 3 : (ré)indexation d'un cours. Module 5 : la classification est relancée dans le même appel.
    if ($action === 'reindex' && $method === 'POST') {
        $ai = process_course_ai($db, posted_course($db));
        if (!$ai['indexed']) respond(['error' => $ai['message'] ?: ai_unavailable_message()], 503);
        respond(['message' => 'Cours indexé : il est prêt pour l’Assistant IA 2.', 'classified' => $ai['classified']]);
    }

    // Module 5 : correction de la matière par l'étudiant. Son choix est gardé et sert au réentraînement.
    if ($action === 'category' && $method === 'POST') {
        $course = posted_course($db);
        $category = trim((string)($_POST['category'] ?? ''));
        if (!in_array($category, course_categories()['categories'], true)) respond(['error' => 'Catégorie inconnue.'], 422);
        $previous = (string)$course['category'];
        $db->prepare('UPDATE courses SET category=?, category_confidence=NULL, category_source=\'etudiant\' WHERE id=? AND student_id=?')
           ->execute([$category, (int)$course['id'], $studentId]);
        if ($previous !== $category) {
            $db->prepare('INSERT INTO classification_feedback(course_id,student_id,predicted,corrected) VALUES (?,?,?,?)')
               ->execute([(int)$course['id'], $studentId, $previous, $category]);
            try {
                ai_request('POST', '/classify/feedback', ['stored_name' => $course['stored_name'], 'predicted' => $previous, 'corrected' => $category]);
            } catch (AiServiceUnavailable $e) {
                error_log('IA 2 feedback: '.$e->getMessage());   // la correction est gardée en base même si le service est arrêté
            }
        }
        respond(['message' => 'Catégorie enregistrée. Merci, votre correction aidera à améliorer le modèle.']);
    }

    // Suppression d'un cours : retire son index (module 3), sa ligne en base et le fichier stocké.
    // Une panne du service IA n'empêche pas la suppression.
    if ($action === 'delete' && $method === 'POST') {
        $course = posted_course($db);
        try {
            ai_request('DELETE', '/rag/index/'.$studentId.'/'.(int)$course['id']);
        } catch (AiServiceUnavailable $e) {
            error_log('IA 2 unindex: '.$e->getMessage());
        }
        $db->prepare('DELETE FROM courses WHERE id=? AND student_id=?')->execute([(int)$course['id'], $studentId]);
        $file = dirname(__DIR__).'/storage/courses/'.basename((string)$course['stored_name']);
        if (is_file($file)) @unlink($file);
        respond(['message' => 'Cours supprimé.']);
    }

    respond(['error' => 'Action inconnue.'], 404);
} catch (InvalidArgumentException $e) {
    respond(['error' => $e->getMessage()], 422);
} catch (AiServiceUnavailable $e) {
    error_log('IA 2: '.$e->getMessage());
    respond(['error' => ai_unavailable_message()], 503);
} catch (Throwable $e) {
    error_log('IA 2 API: '.$e->getMessage());
    respond(['error' => 'Service indisponible. Vérifiez la configuration MySQL et l’import de database/schema.sql.'], 503);
}
