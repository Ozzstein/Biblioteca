# Biblioteca Web UI

FastAPI + React dashboard for the Battery Research OS.

## Quick Start

### Development Mode

```bash
# From the Biblioteca root directory
cd scripts/
./start-web.sh
```

This will:
1. Install Python dependencies (`fastapi`, `uvicorn`, etc.)
2. Install npm dependencies
3. Start the FastAPI backend on `http://127.0.0.1:8000`
4. Start the React dev server on `http://localhost:5173`

Open your browser to **http://localhost:5173**

### Production Mode

```bash
# Build the frontend
cd web
npm install
npm run build

# Start the backend (serves built frontend)
cd ..
uv run uvicorn web.api.main:app --host 0.0.0.0 --port 8000
```

Open your browser to **http://localhost:8000**

### Docker

```bash
# Build and run
docker-compose up -d

# View logs
docker-compose logs -f
```

## Features

### Dashboard Pages

| Page | Description |
|------|-------------|
| **Status** | System health, supervisor status, pending files |
| **Corpus** | Document statistics, recent documents, processing queue |
| **Wiki** | Browse knowledge base, search pages, category view |
| **Graph** | Entity/relation statistics, entity browser |
| **Query** | Ask questions with citations, multiple retrieval modes |

### API Endpoints

#### Health & Status
- `GET /api/health` — Health check
- `GET /api/status` — System status (supervisor, health, metrics)

#### Corpus
- `GET /api/corpus/stats` — Corpus statistics
- `GET /api/corpus/documents` — List documents
- `GET /api/corpus/documents/{doc_id}` — Get document details

#### Wiki
- `GET /api/wiki/stats` — Wiki statistics
- `GET /api/wiki/pages` — List wiki pages
- `GET /api/wiki/pages/{path}` — Get wiki page content

#### Graph
- `GET /api/graph/stats` — Graph statistics
- `GET /api/graph/entities` — List entities
- `GET /api/graph/entities/{entity_id}` — Get entity with neighbors

#### Query
- `POST /api/query` — Query the knowledge base
  ```json
  {
    "query": "What causes LFP capacity fade?",
    "mode": "hybrid",
    "quality": false
  }
  ```

## Architecture

```
web/
├── api/
│   └── main.py           # FastAPI backend
├── src/
│   ├── App.tsx           # React app with routing
│   ├── pages/
│   │   ├── Status.tsx    # System status page
│   │   ├── Corpus.tsx    # Document browser
│   │   ├── Wiki.tsx      # Wiki browser
│   │   ├── Graph.tsx     # Graph explorer
│   │   └── Query.tsx     # Query interface
│   └── lib/
│       └── utils.ts      # Utility functions
├── package.json
├── vite.config.ts
├── tailwind.config.js
└── requirements.txt
```

## Tech Stack

**Backend:**
- FastAPI
- Uvicorn
- Pydantic

**Frontend:**
- React 18
- TypeScript
- Vite
- Tailwind CSS
- React Router
- Lucide React (icons)

## Configuration

The web UI reads the same configuration as the CLI:

- `BIBLIOTECA_HOME` — Path to Biblioteca data directory (default: `~/.biblioteca`)
- `ANTHROPIC_API_KEY` — Required for query functionality
- `FIRECRAWL_API_KEY` — Optional, for URL ingestion

## Troubleshooting

### Backend won't start
```bash
# Check if port 8000 is in use
lsof -i :8000

# Kill existing process
kill -9 <PID>
```

### Frontend shows 404 on API calls
- Make sure the backend is running on `http://127.0.0.1:8000`
- Check CORS settings in `web/api/main.py`

### Query fails
- Ensure `ANTHROPIC_API_KEY` is set in `.env`
- Check that the corpus has been ingested (`llm-rag ingest`)
