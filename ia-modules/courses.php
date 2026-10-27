<?php
declare(strict_types=1);
// Module 5 (classification) et indexation des cours pour le module 3.
// Dépend de app/bootstrap.php (db(), student_id()) et de ia-modules/service.php.

/** Catégories de cours, lues dans le fichier partagé avec le service IA (une seule source de vérité). */
function course_categories(): array {
    static $data = null;
    if ($data === null) {
        $json = file_get_contents(dirname(__DIR__).'/ai-service/app/modules/classification/categories.json');
        $data = is_string($json) ? json_decode($json, true) : null;
        if (!is_array($data) || !isset($data['categories'], $data['unclassified'])) {
            $data = ['categories' => [], 'unclassified' => 'À classer'];
        }
    }
    return $data;
}

/** Cours de l'étudiant connecté, ou null s'il n'existe pas ou appartient à un autre compte. */
function owned_course(PDO $db, int $courseId): ?array {
    if ($courseId < 1) return null;
    $q = $db->prepare('SELECT id,title,stored_name,category,category_source FROM courses WHERE id=? AND student_id=?');
    $q->execute([$courseId, student_id()]);
    $row = $q->fetch();
    return $row ?: null;
}

/**
 * Indexe (module 3) puis classe (module 5) un cours. Ne lève jamais d'exception : l'import reste valide,
 * même si le service IA est arrêté (le cours pourra être indexé plus tard, depuis « Assistant IA 2 »).
 */
function process_course_ai(PDO $db, array $course): array {
    $status = ['indexed' => false, 'classified' => false, 'message' => ''];
    try {
        $r = ai_request('POST', '/rag/index', [
            'student_id' => student_id(), 'course_id' => (int)$course['id'],
            'stored_name' => $course['stored_name'], 'title' => $course['title'],
        ], (int)ai_config()['index_timeout']);
        if ($r['status'] === 200) {
            $db->prepare('UPDATE courses SET indexed_at=UTC_TIMESTAMP(), text_extracted_at=UTC_TIMESTAMP(), chunk_count=? WHERE id=? AND student_id=?')
               ->execute([(int)$r['data']['chunks'], (int)$course['id'], student_id()]);
            $status['indexed'] = true;
        } else {
            $status['message'] = (string)($r['data']['detail'] ?? 'Indexation impossible.');
        }
    } catch (AiServiceUnavailable $e) {
        error_log('IA 2 index: '.$e->getMessage());
        $status['message'] = 'Assistant IA 2 indisponible : le cours sera indexé plus tard (bouton « Indexer »).';
        return $status;
    }
    if (($course['category_source'] ?? null) === 'etudiant') return $status; // ne jamais écraser une correction
    try {
        $r = ai_request('POST', '/classify', ['stored_name' => $course['stored_name']]);
        if ($r['status'] === 200) {
            // Sous le seuil de confiance, le cours reste « À classer » mais la meilleure catégorie
            // est gardée comme suggestion : l'IA propose, l'étudiant décide.
            $source = $r['data']['accepted'] ? 'auto' : null;
            $suggestion = (string)($r['data']['top'][0]['category'] ?? '');
            $db->prepare('UPDATE courses SET category=?, category_confidence=?, category_source=?, category_suggestion=? WHERE id=? AND student_id=?')
               ->execute([(string)$r['data']['category'], (float)$r['data']['confidence'], $source,
                          $suggestion !== '' ? $suggestion : null, (int)$course['id'], student_id()]);
            $status['classified'] = true;
        }
    } catch (AiServiceUnavailable $e) {
        error_log('IA 2 classify: '.$e->getMessage());
    }
    return $status;
}
