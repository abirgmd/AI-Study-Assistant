@echo off
chcp 65001 >nul
cd /d "%~dp0"
echo === Import du schema (non destructif) === > resultats-tests.txt
C:\xampp\mysql\bin\mysql.exe -uroot --default-character-set=utf8mb4 < database\schema.sql >> resultats-tests.txt 2>&1
echo OK import >> resultats-tests.txt
echo. >> resultats-tests.txt
echo === tests/quiz_validation_test.php === >> resultats-tests.txt
C:\xampp\php\php.exe tests\quiz_validation_test.php >> resultats-tests.txt 2>&1
echo. >> resultats-tests.txt
echo === tests/study_test.php === >> resultats-tests.txt
C:\xampp\php\php.exe tests\study_test.php >> resultats-tests.txt 2>&1
echo. >> resultats-tests.txt
echo === tests/pdf_test.php === >> resultats-tests.txt
C:\xampp\php\php.exe tests\pdf_test.php >> resultats-tests.txt 2>&1
echo. >> resultats-tests.txt
echo === Version PHP === >> resultats-tests.txt
C:\xampp\php\php.exe -v >> resultats-tests.txt 2>&1
echo FIN >> resultats-tests.txt
type resultats-tests.txt
pause
