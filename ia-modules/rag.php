<?php
declare(strict_types=1);
// Module 3 : questions-réponses sur les cours (bouton « Assistant IA 2 »).
// La réponse vient du service IA (RAG : recherche dans les cours de l'étudiant, sources citées, abstention).
// Dépend de ia-modules/service.php.

const IA_QUESTION_MIN_CHARS = 3;
const IA_QUESTION_MAX_CHARS = 500;
const IA_ASK_LIMIT = 20;            // questions autorisées…
const IA_ASK_WINDOW_MINUTES = 10;   // …par fenêtre glissante de 10 minutes

/** Question nettoyée (espaces réduits). Lève InvalidArgumentException si elle est trop courte ou trop longue. */
function ia_clean_question(string $raw): string {
    $question = trim((string)preg_replace('/\s+/u', ' ', $raw));
    $length = mb_strlen($question, 'UTF-8');
    if ($length < IA_QUESTION_MIN_CHARS || $length > IA_QUESTION_MAX_CHARS) {
        throw new InvalidArgumentException('Votre question doit contenir entre '.IA_QUESTION_MIN_CHARS.' et '.IA_QUESTION_MAX_CHARS.' caractères.');
    }
    return $question;
}

/** Sources renvoyées au navigateur : seuls les champs utiles, types contrôlés. */
function ia_sources(array $raw): array {
    return array_map(static fn(array $s): array => [
        'number' => (int)$s['number'],
        'course_id' => (int)$s['course_id'],
        'title' => (string)$s['title'],
        'page' => $s['page'] === null ? null : (int)$s['page'],
        'excerpt' => (string)$s['excerpt'],
        'score' => (float)$s['score'],
    ], $raw);
}

/** Nombre de questions posées par l'étudiant dans la fenêtre glissante. */
function ia_recent_questions(PDO $db, int $studentId): int {
    $q = $db->prepare('SELECT COUNT(*) FROM rag_queries WHERE student_id=? AND created_at > UTC_TIMESTAMP() - INTERVAL '.IA_ASK_WINDOW_MINUTES.' MINUTE');
    $q->execute([$studentId]);
    return (int)$q->fetchColumn();
}

/**
 * Pose la question au service IA et enregistre l'échange dans l'historique.
 * Lève AiServiceUnavailable si le service est indisponible, InvalidArgumentException si la question est refusée.
 */
function ia_ask(PDO $db, int $studentId, string $question, string $scope, ?int $courseId): array {
    $r = ai_request('POST', '/rag/ask', ['student_id' => $studentId, 'question' => $question, 'course_id' => $courseId, 'scope' => $scope]);
    if ($r['status'] !== 200) throw new InvalidArgumentException((string)($r['data']['detail'] ?? 'Question refusée.'));
    $a = $r['data'];
    $sources = ia_sources($a['sources'] ?? []);
    $db->prepare('INSERT INTO rag_queries(student_id,course_id,question,answer,sources,backend,latency_ms,cache_hit,abstained) VALUES (?,?,?,?,?,?,?,?,?)')
       ->execute([$studentId, $courseId, $question, (string)$a['answer'], json_encode($sources, JSON_UNESCAPED_UNICODE),
                  mb_substr((string)$a['backend'], 0, 80), (int)$a['latency_ms'], (int)(bool)$a['cache_hit'], (int)(bool)$a['abstained']]);
    return [
        'answer' => (string)$a['answer'], 'sources' => $sources, 'backend' => (string)$a['backend'],
        'latency_ms' => (int)$a['latency_ms'], 'cache_hit' => (bool)$a['cache_hit'], 'abstained' => (bool)$a['abstained'],
    ];
}

/** Dix dernières questions de l'étudiant. */
function ia_history(PDO $db, int $studentId): array {
    $q = $db->prepare('SELECT r.question,r.answer,r.created_at,r.abstained,c.title AS course FROM rag_queries r LEFT JOIN courses c ON c.id=r.course_id WHERE r.student_id=? ORDER BY r.created_at DESC,r.id DESC LIMIT 10');
    $q->execute([$studentId]);
    return array_map(static function (array $h): array {
        $h['abstained'] = (bool)$h['abstained'];
        return $h;
    }, $q->fetchAll());
}
