#!/bin/bash
set -e

# One-command deploy script for Scrapper-agent
# Usage: ./deploy.sh

REPO_URL="https://github.com/ssubrahmanyama/Scrapper-agent.git"
PROJECT_DIR="Scrapper-agent"

# 1. Clone if not already present
if [ ! -d "backend" ] && [ ! -f "docker-compose.yml" ]; then
  echo "Cloning repository..."
  git clone "$REPO_URL" "$PROJECT_DIR"
  cd "$PROJECT_DIR"
else
  echo "Using existing project directory."
fi

# 2. Copy .env if needed
if [ ! -f backend/.env ]; then
  echo "Copying backend/.env.example to backend/.env..."
  cp backend/.env.example backend/.env
fi

# 3. Build and start Docker services

echo "Building and starting Docker containers..."
docker compose up --build -d

# 4. Wait for backend to be healthy
printf "Waiting for backend service to become healthy..."
for i in {1..30}; do
  STATUS=$(docker compose ps --format json | grep 'backend' | grep -o 'running')
  if [ "$STATUS" = "running" ]; then
    echo " ready!"
    break
  fi
  sleep 2
  printf "."
done

# 5. Run DB migrations

echo "Running database migrations..."
docker compose exec backend /venv/bin/alembic upgrade head || {
  echo "Migration failed. Check logs with: docker compose logs backend";
  exit 1;
}

echo "\n✅ Deployment complete!"
echo "--------------------------------------"
echo "Frontend:        http://localhost:3000"
echo "API docs:        http://localhost:8000/docs"
echo "Celery Flower:   http://localhost:5555"
echo "--------------------------------------"
echo "To view logs:    docker compose logs -f"
echo "To stop:         docker compose down"
