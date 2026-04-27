#!/bin/bash
# Start Biblioteca Web UI (Development Mode)
# Run this from the Biblioteca root directory

set -e

echo "🚀 Starting Biblioteca Web UI..."
echo ""

# Check if .env exists
if [ ! -f .env ]; then
    echo "⚠️  Warning: .env file not found. Copy .env.example to .env and configure API keys."
    echo "   cp .env.example .env"
    echo ""
fi

# Start backend in background
echo "📡 Starting FastAPI backend on http://127.0.0.1:8000"
cd web
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python -m venv .venv
fi

source .venv/bin/activate
pip install -q -r requirements.txt

# Install main package
cd ..
pip install -q -e ".[web]"

# Start uvicorn
cd web
uvicorn api.main:app --reload --host 127.0.0.1 --port 8000 &
BACKEND_PID=$!
echo "✅ Backend started (PID: $BACKEND_PID)"
echo ""

# Wait for backend to be ready
echo "⏳ Waiting for backend to be ready..."
sleep 3

# Start frontend
echo "🎨 Starting React dev server on http://localhost:5173"
if [ ! -d "node_modules" ]; then
    echo "📦 Installing npm dependencies..."
    npm install
fi

npm run dev

# Cleanup on exit
trap "kill $BACKEND_PID 2>/dev/null || true" EXIT
