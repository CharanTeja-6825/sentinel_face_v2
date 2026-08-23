@echo off
setlocal

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is required but was not found in PATH.
  exit /b 1
)

if not exist .env (
  copy /Y .env.example .env >nul
  echo Created .env from .env.example.
)

echo Building Docker images...
docker compose build
if errorlevel 1 exit /b 1

echo Starting SentinelFace...
docker compose up %*
exit /b %errorlevel%
