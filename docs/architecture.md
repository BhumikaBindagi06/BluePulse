# BluePulse Integration Architecture

## Boundaries

- `modules/`: Owned by individual team members. Integration code must not modify files inside `modules/`.
- `contracts/`: Installable `bluepulse_contracts` package defining shared Pydantic schemas across modules and backend services.
- `backend/`: FastAPI integration layer (`app/api/v1/`), configuration (`app/core/`), sync SQLAlchemy session (`app/db/`), and orchestration services (`app/services/`).
- `data/sample/`: Sample payloads for local development and integration smoke tests.

## Database Configuration

By default, `DATABASE_URL` uses SQLite (`sqlite:///./bluepulse.db`). For PostgreSQL, set `DATABASE_URL` in `.env`, for example:

```env
DATABASE_URL=postgresql+psycopg://user:password@localhost:5432/bluepulse
```

