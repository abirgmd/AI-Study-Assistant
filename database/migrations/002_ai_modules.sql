-- Migration 002 : modules IA (module 3 RAG, module 5 classification).
-- À importer APRÈS database/schema.sql. Non destructive et rejouable :
-- chaque colonne n'est ajoutée que si elle n'existe pas encore (compatible
-- MySQL 8 et MariaDB 10.4+, qui n'ont pas la même syntaxe IF NOT EXISTS).
USE ai_study_assistant;
SET NAMES utf8mb4;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN text_extracted_at TIMESTAMP NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'text_extracted_at');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN indexed_at TIMESTAMP NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'indexed_at');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN chunk_count INT UNSIGNED NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'chunk_count');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_confidence DECIMAL(5,4) NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_confidence');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_source ENUM(''auto'',''etudiant'') NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_source');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_suggestion VARCHAR(80) NULL DEFAULT NULL',
  'DO 0') FROM information_schema.COLUMNS
  WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_suggestion');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

-- Historique des questions posées à l'assistant (module 3). Supprimé avec l'étudiant.
CREATE TABLE IF NOT EXISTS rag_queries (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 student_id BIGINT UNSIGNED NOT NULL,
 course_id BIGINT UNSIGNED NULL,
 question VARCHAR(500) NOT NULL,
 answer TEXT NOT NULL,
 sources JSON NULL,
 backend VARCHAR(80) NOT NULL,
 latency_ms INT UNSIGNED NOT NULL,
 cache_hit TINYINT(1) NOT NULL DEFAULT 0,
 abstained TINYINT(1) NOT NULL DEFAULT 0,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY rag_queries_student_created(student_id, created_at),
 CONSTRAINT rag_queries_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
 CONSTRAINT rag_queries_course_fk FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Corrections de catégorie faites par les étudiants (module 5).
CREATE TABLE IF NOT EXISTS classification_feedback (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 course_id BIGINT UNSIGNED NOT NULL,
 student_id BIGINT UNSIGNED NOT NULL,
 predicted VARCHAR(80) NOT NULL,
 corrected VARCHAR(80) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 CONSTRAINT feedback_course_fk FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE,
 CONSTRAINT feedback_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB;
