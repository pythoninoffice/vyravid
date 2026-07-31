# Vyravid

All-in-one AI-assisted video generator. Create entire videos, no switching between tools, no other video editing software needed 

You provide ideas, AI will automatically generate:
- script
- smart scene/storyboard
- voiceover
- visuals (images and videos)
- green screen, Ken burns effects
- render final video



![Vyravid screenshot](image.png)

## Quick Start

First-time setup:

```bash
cp .env.example .env
```

Edit `.env` and add the provider keys you plan to use. The app runs locally, but
AI generation features need their corresponding API keys.

From the repo root:

```bash
./scripts/start-api.sh
./scripts/start-frontend.sh
```

Then open:

```text
http://localhost:5173
```

Useful backend checks:

```bash
curl http://localhost:8000/health
curl http://localhost:8000/api/local/info
curl -H "Authorization: Bearer local-token" http://localhost:8000/api/video/user/projects
```

## Environment

Assuming the repo is cloned at:

```text
~/vyravid
```

The backend start script reads env files in this order:

1. `.env`
2. `app/.env`, only if `.env` does not exist

The checked-in `.env.example` is the starting template. Copy it to `.env` and
fill in keys as needed:

```bash
cp .env.example .env
```

After loading env values, `scripts/start-api.sh` derives the local runtime paths
from the checkout directory. For a clone at `~/vyravid`, the effective local
paths are:

```bash
VYRAVID_ROOT=~/vyravid
VYRAVID_DATA=~/vyravid/data
VYRAVID_DB=~/vyravid/data/db/openvid.sqlite3
DATABASE_URL=sqlite:////home/<you>/vyravid/data/db/openvid.sqlite3
VYRAVID_PUBLIC_BASE=http://localhost:8000
CLOUD_VIDEO_PROCESSOR_URL=http://localhost:8000/vp
USE_CLOUD_PROCESSING=true
```

The frontend start script sets:

```bash
VITE_API_URL=http://localhost:8000
```

Vite may also read files under `frontend/`, such as `frontend/.env`.

## Data And Storage

Active SQLite DB:

```text
data/db/openvid.sqlite3
```

Inspect it with:

```bash
sqlite3 data/db/openvid.sqlite3
```

Example project query:

```sql
select id, title, status, created_at from video_projects order by created_at desc;
```

Media files live under:

```text
data/storage/
```

and are served at:

```text
http://localhost:8000/media/<relative-path>
```

Files such as `data/openvid.db` and `data/app.db` are not the active app DB.

## Backend Layout

```text
app/main.py                         FastAPI app, media mounts, active router registration
app/auth.py                         Local auth stub
app/config.py                       Local settings
app/local/                          SQLite and local filesystem adapters
app/api/                            Active API routers
app/services/                       Active app services
app/repositories/                   SQLite-backed repository wrappers
app/models/                         Pydantic models used by active routes/services
app/video_processor/                Embedded ffmpeg/video rendering subsystem mounted at /vp
app/requirements.txt                Direct backend runtime dependencies
```

Important local adapters:

- `app/local/db.py` implements a small Supabase-style query API over SQLite.
- `app/db/supabase_client.py` is still actively used, but now wraps the local DB adapter.
- `app/services/gcs_service.py` is a compatibility wrapper over local filesystem storage.

## Frontend Layout

```text
frontend/src/router/index.ts        Routes
frontend/src/views/DashboardView.vue
frontend/src/components/ProjectManager.vue
frontend/src/views/SimpleProjectCreator.vue
frontend/src/api/                   API clients
frontend/src/stores/                Pinia stores
frontend/src/utils/                 Active frontend helpers
```

Main routes:

```text
/app
/app/projects
/app/projects/:id
/app/simple-creator/:id?
```

## Dependencies

Backend dependencies are listed in:

```text
app/requirements.txt
```

Install with:

```bash
python -m pip install -r app/requirements.txt
```

Frontend dependencies are listed in:

```text
frontend/package.json
```

Install with:

```bash
cd frontend
npm install
```

Useful frontend checks:

```bash
cd frontend
npm run type-check
npm run build
```
