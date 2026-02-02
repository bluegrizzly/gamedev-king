# Game Dev King
## Multi agents to assist game developers on one project.
## Developped by Andy Fire Studio LLC.

This repo contains:
- `web/` — Next.js App Router frontend (TypeScript)
- `api/` — FastAPI backend that streams tokens over SSE

## Prereqs
- Node.js 18+
- Python 3.10+
- uv (Python package manager)

## Setup

### Backend
```bash
cd api
uv venv
.\.venv\Scripts\activate
uv pip install -r requirements.txt
copy .env.example .env
# add your OpenAI key in api/.env
```

Run:
```bash
uvicorn main:app --reload --port 8000
```

### Frontend
```bash
cd web
npm install
npm run dev
```

Open: http://localhost:3000

## Test chat
1. Start API server (port 8000)
2. Start Web app (port 3000)
3. Send a message and watch the assistant stream back

