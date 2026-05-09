@echo off
REM ============================================================
REM Luganda AI Studio — Local Startup Script
REM Run this from the project root: D:\projects\Luganda_AI_Studio\
REM ============================================================

echo.
echo  Starting Luganda AI Studio...
echo  API:      http://127.0.0.1:8000
echo  UI:       http://127.0.0.1:8000/app/index.html
echo  API Docs: http://127.0.0.1:8000/docs
echo.
echo  Press Ctrl+C to stop.
echo.

REM Activate virtual environment
call venv\Scripts\activate.bat

REM Start FastAPI with uvicorn
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
