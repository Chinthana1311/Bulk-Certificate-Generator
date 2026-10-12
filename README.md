# CertiBatch — Bulk Certificate Generator

A beginner-friendly Flask REST API that accepts a list of recipients in one request and generates personalized PDF certificates using a single predefined landscape design.

Built for a college placement assignment: Python, Flask, SQLite, ReportLab, and pytest.

## Features

- Submit a bulk generation job with many recipients in one `POST` request
- Validate each recipient independently (name, email format, duplicates)
- Generate professional landscape PDF certificates with ReportLab
- Store job and recipient status in SQLite
- Download generated certificates by certificate ID
- Continue processing when individual recipients fail
- Automated pytest coverage for the required behaviours

## Prerequisites

- Python 3.10 or newer
- pip
- Windows, macOS, or Linux (commands below focus on Windows)

## Setup (Windows)

```bat
cd "D:\Bulk Certificate Generator"
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

## Run the application

```bat
python app.py
```

The API listens on `http://127.0.0.1:5000`.

Quick health check: open `http://127.0.0.1:5000/api/health` in a browser.

## Run tests

```bat
pytest -v
```

Tests use a temporary SQLite database and temporary certificate directory so they do not modify `instance/certificates.db` or real files under `certificates/`.

## Configuration

| Setting | Default | Notes |
| ------- | ------- | ----- |
| Max batch size | 500 recipients | Rejected with HTTP 400 if exceeded |
| Organization name | `CertiBatch Organization` | Override with env `CERTIBATCH_ORG` |
| Database | `instance/certificates.db` | Created automatically on startup |
| PDFs | `certificates/` | Safe unique filenames only |

## API endpoints

| Method | Endpoint | Purpose |
| ------ | -------- | ------- |
| `GET` | `/api/health` | Confirm the API is running |
| `POST` | `/api/jobs` | Submit one bulk generation request |
| `GET` | `/api/jobs/<job_id>` | Job progress, counts, and results |
| `GET` | `/api/jobs/<job_id>/recipients` | Per-recipient success/failure details |
| `GET` | `/api/certificates/<certificate_id>` | Download a generated PDF |

### Example request

`POST /api/jobs` with `Content-Type: application/json`:

```json
{
  "event_name": "Python Workshop 2026",
  "issue_date": "2026-10-12",
  "recipients": [
    {
      "name": "Chinthana A",
      "email": "chinthana@example.com"
    },
    {
      "name": "Priya S",
      "email": "priya@example.com"
    },
    {
      "name": "Arun K",
      "email": "invalid-email"
    }
  ]
}
```

### Example partial-failure response

```json
{
  "job_id": 1,
  "status": "completed_with_errors",
  "total": 3,
  "successful": 2,
  "failed": 1,
  "results": [
    {
      "name": "Chinthana A",
      "email": "chinthana@example.com",
      "status": "success",
      "certificate_id": 101
    },
    {
      "name": "Priya S",
      "email": "priya@example.com",
      "status": "success",
      "certificate_id": 102
    },
    {
      "name": "Arun K",
      "email": "invalid-email",
      "status": "failed",
      "error": "Invalid email address."
    }
  ]
}
```

Job-level statuses:

- `processing` — job created, recipients being handled
- `completed` — all recipients succeeded
- `completed_with_errors` — at least one success and one failure
- `failed` — every recipient failed

### Check job status

```
GET /api/jobs/1
```

### List recipients for a job

```
GET /api/jobs/1/recipients
```

### Download a certificate

```
GET /api/certificates/101
```

Returns the PDF as an attachment. Unknown IDs return HTTP 404. Clients cannot supply filesystem paths; only stored certificate IDs are accepted.

## Database schema

### `jobs`

| Column | Type | Description |
| ------ | ---- | ----------- |
| id | INTEGER PK | Job ID |
| event_name | TEXT | Event / course name |
| issue_date | TEXT | Issue date string |
| status | TEXT | Job status |
| total_recipients | INTEGER | Batch size |
| successful_count | INTEGER | Successes |
| failed_count | INTEGER | Failures |
| created_at | TEXT | UTC creation timestamp |

### `recipients`

| Column | Type | Description |
| ------ | ---- | ----------- |
| id | INTEGER PK | Row ID |
| job_id | INTEGER FK | Parent job |
| name | TEXT | Recipient name |
| email | TEXT | Recipient email |
| status | TEXT | `success` or `failed` |
| certificate_id | INTEGER UNIQUE | Public download ID (if success) |
| certificate_path | TEXT | Server-side PDF path (if success) |
| error_message | TEXT | Validation / generation error (if failed) |

Foreign keys are enabled with `PRAGMA foreign_keys = ON`. Queries use parameterized SQL.

## Design decisions

### Why synchronous processing?

Recipients are processed one-by-one inside the same `POST /api/jobs` request. That keeps the project simple to run and explain: no Redis, Celery, or background workers.

**Trade-off:** Very large batches or slow machines may hit HTTP timeouts. For production-scale workloads, a queue/worker could process jobs asynchronously while the API returns `processing` immediately.

### How individual failures are handled

Validation and PDF generation errors for one recipient are caught, stored on that recipient row, and processing continues with the next recipient. One bad email never blocks the rest of the batch.

### Certificate design

PDFs use one fixed landscape A4 layout inspired by a professional appreciation certificate: gold titles, grey decorative waves, diamond accents, date/signature lines, and a gold seal. The HTML file under `templates/certificate.html` documents the same layout; ReportLab in `certificate.py` produces the actual PDFs.

### Security notes for this assignment

- Filenames are generated with certificate ID + random suffix (never raw user input)
- Certificate download only serves files under the configured `certificates/` directory
- No authentication is included (out of scope for this assignment)

## Project structure

```
CertiBatch/
├── app.py                 # Flask endpoints and job processing
├── database.py            # SQLite schema and helpers
├── certificate.py         # ReportLab PDF generation
├── requirements.txt
├── README.md
├── templates/
│   └── certificate.html   # Visual reference for the fixed template
├── tests/
│   └── test_app.py
├── certificates/          # Generated PDFs
└── instance/
    └── certificates.db    # Created on first run
```

## Current limitations and future improvements

- Synchronous processing only (no background workers)
- Single fixed certificate template (no template editor)
- No authentication or rate limiting
- Basic email format check (not full RFC validation)
- Organization name is a simple default / environment variable

Possible improvements: async job queue, email delivery of PDFs, ZIP download of a whole job, richer date validation, and optional authentication.

## Interview talking points

| Question | Short answer |
| -------- | ------------ |
| Why Flask? | Lightweight; easy REST APIs and interview explanation |
| Why SQLite? | Relational storage with no separate DB server |
| How are certificates generated? | ReportLab draws a fixed landscape PDF per recipient |
| How are invalid recipients handled? | Record failure, continue with the others |
| How is progress tracked? | Job and recipient rows in SQLite |
| Why synchronous? | Simpler for an academic demo; workers can come later |
| How do you test PDF failure? | Mock `generate_certificate` so one call raises; assert others succeed |
