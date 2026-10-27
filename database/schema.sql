-- MySQL 8+ ou MariaDB 10.4+ (XAMPP). Aucun compte étudiant de démonstration.
-- Non destructif : ce script ne supprime aucune table existante.
SET NAMES utf8mb4;
CREATE DATABASE IF NOT EXISTS ai_study_assistant CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE ai_study_assistant;
CREATE TABLE IF NOT EXISTS students (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 full_name VARCHAR(100) NOT NULL,
 email VARCHAR(254) NOT NULL,
 password_hash VARCHAR(255) NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 UNIQUE KEY students_email_unique(email)
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS courses (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 student_id BIGINT UNSIGNED NOT NULL,
 title VARCHAR(255) NOT NULL,
 original_name VARCHAR(255) NOT NULL,
 stored_name VARCHAR(100) NOT NULL,
 mime_type VARCHAR(100) NOT NULL,
 file_size INT UNSIGNED NOT NULL,
 category VARCHAR(80) NOT NULL DEFAULT 'À classer',
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY courses_student_created(student_id,created_at),
 CONSTRAINT courses_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS daily_goals (
 student_id BIGINT UNSIGNED NOT NULL,
 goal_date DATE NOT NULL,
 goal_index TINYINT UNSIGNED NOT NULL,
 completed TINYINT(1) NOT NULL DEFAULT 0,
 PRIMARY KEY(student_id,goal_date,goal_index),
 CONSTRAINT goals_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS auth_attempts (
 attempt_key CHAR(64) PRIMARY KEY,
 attempts INT UNSIGNED NOT NULL DEFAULT 1,
 window_start DATETIME NOT NULL
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS quizzes (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 student_id BIGINT UNSIGNED NOT NULL,
 course_id BIGINT UNSIGNED NOT NULL,
 title VARCHAR(255) NOT NULL,
 questions JSON NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY quizzes_student_created(student_id,created_at),
 CONSTRAINT quizzes_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
 CONSTRAINT quizzes_course_fk FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE CASCADE
) ENGINE=InnoDB;
CREATE TABLE IF NOT EXISTS quiz_attempts (
 id BIGINT UNSIGNED AUTO_INCREMENT PRIMARY KEY,
 student_id BIGINT UNSIGNED NOT NULL,
 quiz_id BIGINT UNSIGNED NOT NULL,
 score TINYINT UNSIGNED NOT NULL,
 total TINYINT UNSIGNED NOT NULL,
 created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
 KEY attempts_student_created(student_id,created_at),
 CONSTRAINT attempts_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
 CONSTRAINT attempts_quiz_fk FOREIGN KEY(quiz_id) REFERENCES quizzes(id) ON DELETE CASCADE
) ENGINE=InnoDB;

-- ---------------------------------------------------------------------------
-- Modules 3 (Assistant IA 2 : questions sur les cours) et 5 (classification des cours).
-- Non destructif et rejouable : chaque colonne n'est ajoutée que si elle n'existe pas encore
-- (MySQL 8 et MariaDB 10.4+ n'ont pas la même syntaxe pour ADD COLUMN IF NOT EXISTS).
-- ---------------------------------------------------------------------------
SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN text_extracted_at TIMESTAMP NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'text_extracted_at');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN indexed_at TIMESTAMP NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'indexed_at');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN chunk_count INT UNSIGNED NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'chunk_count');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_confidence DECIMAL(5,4) NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_confidence');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_source ENUM(''auto'',''etudiant'') NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_source');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

SET @add_column = (SELECT IF(COUNT(*) = 0,
  'ALTER TABLE courses ADD COLUMN category_suggestion VARCHAR(80) NULL DEFAULT NULL', 'DO 0')
  FROM information_schema.COLUMNS WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'courses' AND COLUMN_NAME = 'category_suggestion');
PREPARE statement FROM @add_column; EXECUTE statement; DEALLOCATE PREPARE statement;

-- Historique des questions posées à l'Assistant IA 2 (module 3). Supprimé avec l'étudiant.
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
 KEY rag_queries_student_created(student_id,created_at),
 CONSTRAINT rag_queries_student_fk FOREIGN KEY(student_id) REFERENCES students(id) ON DELETE CASCADE,
 CONSTRAINT rag_queries_course_fk FOREIGN KEY(course_id) REFERENCES courses(id) ON DELETE SET NULL
) ENGINE=InnoDB;

-- Corrections de matière faites par les étudiants (module 5).
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
