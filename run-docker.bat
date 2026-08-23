@echo off
setlocal

where docker >nul 2>nul
if errorlevel 1 (
  echo Docker is required but was not found in PATH.
  exit /b 1
)

set "platform="
if /I "%PROCESSOR_ARCHITEW6432%"=="AMD64" set "platform=linux/amd64"
if /I "%PROCESSOR_ARCHITEW6432%"=="ARM64" set "platform=linux/arm64"
if /I "%PROCESSOR_ARCHITECTURE%"=="AMD64" set "platform=linux/amd64"
if /I "%PROCESSOR_ARCHITECTURE%"=="x86_64" set "platform=linux/amd64"
if /I "%PROCESSOR_ARCHITECTURE%"=="ARM64" set "platform=linux/arm64"
if not defined platform (
  echo Unsupported machine architecture: %PROCESSOR_ARCHITECTURE%.
  echo Only amd64 and arm64 are supported.
  exit /b 1
)

if not exist .env (
  copy /Y .env.example .env >nul
  echo Created .env from .env.example.
)

set "DOCKER_DEFAULT_PLATFORM=%platform%"
echo Using Docker platform: %DOCKER_DEFAULT_PLATFORM%
echo Building Docker images...
docker compose build
if errorlevel 1 exit /b 1

echo Starting SentinelFace...
docker compose up %*
exit /b %errorlevel%
