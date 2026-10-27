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
