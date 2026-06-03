@echo off
echo ========================================
echo   Neo Learner - Local Backup from Neon
echo ========================================
echo.

REM Ensure we're in the project directory
cd /d "%~dp0"

echo Step 1: Pulling data from Neon database...
python manage.py local_backup

if %errorlevel% neq 0 (
    echo.
    echo [ERROR] Backup failed! Make sure DATABASE_URL is set in your .env file.
    pause
    exit /b 1
)

echo.
echo ========================================
echo   Backup completed successfully!
echo   Data saved in: local_backups\ folder
echo ========================================
echo.
echo You can restore later with:
echo   python manage.py local_restore
echo.
pause
