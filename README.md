# Bulk Certificate Generator API

A backend API that accepts a list of recipients in a single request, validates them,
generates a PDF certificate for each valid recipient from one predefined template,
tracks progress, and lets the client retrieve the results.

**Stack:** Python 3.12, FastAPI, SQLAlchemy, SQLite, ReportLab, pytest

## Setup

```bash
git clone <your-repo-url>
cd bulk-certificate-api
python -m venv venv
venv\Scripts\activate          # Windows
source venv/bin/activate       # Mac/Linux
pip install -r requirements.txt
```

## Run the application

```bash
uvicorn app.main:app --reload
```

- API: http://127.0.0.1:8000
- Interactive docs (Swagger UI): http://127.0.0.1:8000/docs

The SQLite database (`certificates.db`) and the `output/` folder are created automatically.

## Run tests

```bash
pytest -v
```

Tests use a temporary database and output folder, so they never touch real data.

## Submit a certificate generation request

```bash
curl -X POST http://127.0.0.1:8000/jobs \
  -H "Content-Type: application/json" \
  -d '{
    "event_name": "Python Workshop 2026",
    "issued_by": "Reva University",
    "recipients": [
      {"name": "Asha Rao", "email": "asha@example.com"},
      {"name": "Ravi Kumar", "email": "ravi@example.com", "achievement": "First Place"}
    ]
  }'
```

Response (`202 Accepted`):

```json
{"job_id": "…", "status": "pending", "total": 2, "accepted": 2, "rejected": 0}
```

`achievement` is optional and defaults to `"Participation"`.

## Check progress

```bash
curl http://127.0.0.1:8000/jobs/{job_id}
```

Returns the job status (`pending`, `processing`, `completed`, `completed_with_errors`,
`failed`), counts of generated / failed / invalid / pending certificates, and a
per-recipient list with error reasons.

## Retrieve generated certificates

| Endpoint | Purpose |
|---|---|
| `GET /jobs/{job_id}/certificates?status=generated` | List certificates (optional status filter) |
| `GET /certificates/{certificate_id}/download` | Download one PDF |
| `GET /jobs/{job_id}/download` | Download all generated PDFs as a ZIP |

## Endpoints summary

| Method | Path | Description |
|---|---|---|
| POST | `/jobs` | Create a bulk generation job |
| GET | `/jobs/{job_id}` | Job status and per-recipient results |
| GET | `/jobs/{job_id}/certificates` | List certificates |
| GET | `/certificates/{id}/download` | Download one certificate |
| GET | `/jobs/{job_id}/download` | Download all as ZIP |
| GET | `/health` | Health check |

## Design decisions

**Background processing instead of synchronous generation.**
`POST /jobs` saves the job, returns `202 Accepted` with a `job_id`, and generates
the PDFs in a background task. Generating hundreds of PDFs inside the request would
block the client and risk HTTP timeouts. The trade-off is that the client must poll
`GET /jobs/{id}`. I used FastAPI `BackgroundTasks` because it needs no extra
infrastructure. Its limits: tasks run in the same process and are lost if the server
restarts. For production I would move `service.process_job` to a queue (Celery/RQ with
Redis); the service layer would not change.

**Two levels of validation.**
A malformed request (no recipients, missing event name, more than 1000 recipients)
is rejected with `422` and nothing is saved. Individual recipients are validated one
by one: an invalid recipient is stored with status `invalid` and the reasons, and the
valid ones are still generated. One bad row never blocks the rest.

**Failure isolation.**
Each certificate is generated inside its own `try/except` and committed
individually. A failure is recorded as `failed` with the error message and the job
continues. The final job status is `completed_with_errors` if any certificate is
`failed` or `invalid`.

**Data model.**
`Job` (one bulk request) has many `Certificate` rows (one per recipient). Counts are
computed from the rows with a `GROUP BY` query rather than stored, so they can't get
out of sync. IDs are UUIDs so they can't be guessed by counting.

**Layered structure.**
Routes in `main.py` handle only HTTP concerns. Business logic is in `service.py`.
PDF drawing is isolated in `pdf.py`, so the template can change without touching
anything else.

**Background task uses its own database session.**
The request's session is closed once the response is sent, so `process_job` opens
its own.

**SQLite.**
It is a relational database that needs no setup. To use PostgreSQL, change
`DATABASE_URL` in `app/database.py` and install `psycopg2-binary`.

**Safe file handling.**
PDFs are stored under `output/<job_id>/<certificate_id>.pdf`, so user-supplied names
never become file paths. Names inside the ZIP are sanitised.

## Known limitations

- Jobs in progress are lost if the server restarts (they stay in `processing`).
- ZIP files are built in memory, which is fine for hundreds of certificates but not
  for very large jobs.
- No authentication or per-user job ownership.
- Tables are created with `create_all`; a real project would use migrations (Alembic).

## Project structure

```
app/
  main.py       HTTP endpoints
  service.py    job creation, background processing, status summary
  pdf.py        certificate template and PDF rendering
  models.py     SQLAlchemy tables
  schemas.py    Pydantic request/response models
  database.py   engine and session setup
tests/          pytest suite
```