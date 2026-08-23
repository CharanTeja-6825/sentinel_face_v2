#!/usr/bin/env sh
set -eu

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker is required but was not found in PATH." >&2
  exit 1
fi

case "$(uname -m)" in
  x86_64|amd64)
    platform="linux/amd64"
    ;;
  arm64|aarch64)
    platform="linux/arm64"
    ;;
  *)
    echo "Unsupported machine architecture: $(uname -m). Only amd64 and arm64 are supported." >&2
    exit 1
    ;;
esac

if [ ! -f .env ]; then
  cp .env.example .env
  echo "Created .env from .env.example."
fi

export DOCKER_DEFAULT_PLATFORM="$platform"
echo "Using Docker platform: $DOCKER_DEFAULT_PLATFORM"
echo "Building Docker images..."
docker compose build

echo "Starting SentinelFace..."
exec docker compose up "$@"
