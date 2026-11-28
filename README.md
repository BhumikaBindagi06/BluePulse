# BluePulse

## Run Locally

### 1. Create a virtual environment and install packages

```bash
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

pip install -e ./contracts
pip install -e "./backend[dev]"
```

### 2. Configure environment variables

Copy `.env.example` to `.env` in `backend/` (or the repo root if running from there):

```bash
cp .env.example backend/.env
```

SQLite (`sqlite:///./bluepulse.db`) is used by default. To use PostgreSQL, set `DATABASE_URL` in `.env` (e.g., `postgresql+psycopg://user:password@localhost:5432/bluepulse`).

### 3. Start the FastAPI server

```bash
cd backend
uvicorn app.main:app --reload
```

Verify the health endpoint at `http://127.0.0.1:8000/api/v1/health`.

### 4. Run tests and linting

```bash
ruff check contracts backend
cd backend && pytest
```
