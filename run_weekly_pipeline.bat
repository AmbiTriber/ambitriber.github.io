@echo off
REM ============================================================
REM Weekly Pipeline: fetch eToro portfolio, update holdings,
REM generate content, push to GitHub.
REM Run this weekly via Task Scheduler or manually.
REM ============================================================
setlocal enabledelayedexpansion

cd /d "%~dp0"

REM -- Load API keys from .env.web if present --
if exist ".env.web" (
    for /f "usebackq tokens=1,2 delims==" %%a in (".env.web") do (
        set "line=%%a"
        if not "!line:~0,1!"=="#" (
            if not "%%b"=="" set "%%a=%%b"
        )
    )
)

REM -- Find Python --
set PYTHON=
where python3 >nul 2>&1 && set PYTHON=python3
if "%PYTHON%"=="" where python >nul 2>&1 && set PYTHON=python
if "%PYTHON%"=="" (
    echo ERROR: Python not found
    exit /b 1
)
echo Using Python: %PYTHON%

echo ============================================
echo   Ambitriber Weekly Pipeline
echo   %date% %time%
echo ============================================

REM -- Step 0: Fetch eToro portfolio --
echo.
echo [0/6] Fetching eToro portfolio...
%PYTHON% etoro_portfolio.py -o portfolio-holdings.json
if %errorlevel% neq 0 (
    echo ERROR: eToro portfolio fetch failed
    exit /b 1
)

REM -- Step 1: Generate top 10 holdings --
echo.
echo [1/6] Generating top 10 holdings...
%PYTHON% generate_top10.py
if %errorlevel% neq 0 (
    echo ERROR: Top 10 generation failed
    exit /b 1
)

REM -- Step 2: Generate strategy breakdown --
echo.
echo [2/7] Generating strategy breakdown...
%PYTHON% generate_strategy.py
if %errorlevel% neq 0 echo WARNING: Strategy generation failed (non-critical)

REM -- Step 3: Generate market updates --
echo.
echo [3/7] Generating market updates...
%PYTHON% generate_market_updates.py
if %errorlevel% neq 0 echo WARNING: Market updates failed (non-critical)

REM -- Step 4: Generate weekly post --
echo.
echo [4/7] Generating weekly post...
%PYTHON% generate_weekly_post.py
if %errorlevel% neq 0 echo WARNING: Weekly post failed (non-critical)

REM -- Step 5: Backup existing files --
echo.
echo [5/7] Backing up existing data...
if not exist "backups" mkdir backups
if exist "market-updates.json" (
    for /f "tokens=1-6 delims=/-:. " %%a in ('echo %date% %time%') do (
        set "ts=%%a-%%b-%%c_%%d-%%e-%%f"
    )
    copy /Y "market-updates.json" "backups\market-updates-!ts!.json" >nul
)

REM -- Step 6: Git add, commit, push --
echo.
echo [6/7] Committing and pushing to GitHub...
git config user.email "yiannis_90@hotmail.com" 2>nul
git config user.name "Ambitriber" 2>nul

REM Use GITHUB_TOKEN for authenticated push if available
if not "%GITHUB_TOKEN%"=="" (
    git remote set-url origin "https://%GITHUB_TOKEN%@github.com/AmbiTriber/ambitriber.github.io.git" 2>nul
    echo   Using GITHUB_TOKEN for authentication
)

git add portfolio-holdings.json top10.json strategy.json market-updates.json weekly-post.json posts-archive.json index.html tribercss.css
git commit -m "Weekly update: %date%" 2>nul || echo Nothing to commit

REM Push (token is in remote URL if GITHUB_TOKEN was set)
git push origin main

REM Restore remote URL without token for safety
if not "%GITHUB_TOKEN%"=="" (
    git remote set-url origin "https://github.com/AmbiTriber/ambitriber.github.io.git" 2>nul
)

echo.
echo [7/7] Pipeline complete!
echo ============================================
endlocal