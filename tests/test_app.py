"""Automated tests for CertiBatch API."""

import os
import sys

import pytest

# Ensure project root is on the path when running pytest from any cwd
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

import app as app_module
import certificate
import database


@pytest.fixture
def client(tmp_path):
    """Flask test client with temporary DB and certificate directory."""
    db_file = tmp_path / "test_certificates.db"
    cert_dir = tmp_path / "certs"
    cert_dir.mkdir()

    # Reset module state for isolation between tests
    database.set_db_path(str(db_file))
    certificate.set_certificate_dir(str(cert_dir))
    database.init_db(str(db_file))

    app_module.app.config["TESTING"] = True
    with app_module.app.test_client() as test_client:
        yield test_client


def _valid_payload(extra_recipients=None):
    recipients = [
        {"name": "Chinthana A", "email": "chinthana@example.com"},
        {"name": "Priya S", "email": "priya@example.com"},
    ]
    if extra_recipients:
        recipients.extend(extra_recipients)
    return {
        "event_name": "Python Workshop 2026",
        "issue_date": "2026-10-12",
        "recipients": recipients,
    }


def test_health(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.get_json()
    assert data["status"] == "ok"


def test_create_job_with_multiple_recipients(client):
    response = client.post("/api/jobs", json=_valid_payload())
    assert response.status_code == 201
    data = response.get_json()
    assert data["total"] == 2
    assert data["successful"] == 2
    assert data["failed"] == 0
    assert data["status"] == "completed"
    assert "job_id" in data
    assert len(data["results"]) == 2
    for result in data["results"]:
        assert result["status"] == "success"
        assert "certificate_id" in result


def test_reject_malformed_and_missing_fields(client):
    # Not JSON object
    response = client.post("/api/jobs", data="not-json", content_type="application/json")
    assert response.status_code == 400

    # Missing event_name
    response = client.post(
        "/api/jobs",
        json={"issue_date": "2026-10-12", "recipients": [{"name": "A", "email": "a@b.com"}]},
    )
    assert response.status_code == 400
    assert "event_name" in response.get_json()["error"]

    # Missing recipients
    response = client.post(
        "/api/jobs",
        json={"event_name": "Event", "issue_date": "2026-10-12"},
    )
    assert response.status_code == 400

    # Empty recipients
    response = client.post(
        "/api/jobs",
        json={"event_name": "Event", "issue_date": "2026-10-12", "recipients": []},
    )
    assert response.status_code == 400


def test_invalid_recipient_data(client):
    payload = _valid_payload(
        extra_recipients=[{"name": "Arun K", "email": "invalid-email"}]
    )
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["total"] == 3
    assert data["successful"] == 2
    assert data["failed"] == 1
    assert data["status"] == "completed_with_errors"

    failed = [r for r in data["results"] if r["status"] == "failed"]
    assert len(failed) == 1
    assert "Invalid email" in failed[0]["error"]


def test_blank_name_and_duplicate_email(client):
    payload = {
        "event_name": "Workshop",
        "issue_date": "2026-10-12",
        "recipients": [
            {"name": "  ", "email": "one@example.com"},
            {"name": "Valid", "email": "valid@example.com"},
            {"name": "Dup", "email": "valid@example.com"},
        ],
    }
    response = client.post("/api/jobs", json=payload)
    assert response.status_code == 201
    data = response.get_json()
    assert data["successful"] == 1
    assert data["failed"] == 2
    errors = [r["error"] for r in data["results"] if r["status"] == "failed"]
    assert any("Name" in e for e in errors)
    assert any("Duplicate" in e for e in errors)


def test_pdf_generated_successfully(client):
    response = client.post("/api/jobs", json=_valid_payload())
    data = response.get_json()
    cert_id = data["results"][0]["certificate_id"]
    row = database.get_certificate_by_id(cert_id)
    assert row is not None
    assert os.path.isfile(row["certificate_path"])
    assert row["certificate_path"].lower().endswith(".pdf")
    # PDF magic bytes
    with open(row["certificate_path"], "rb") as f:
        assert f.read(4) == b"%PDF"


def test_get_job_status_and_counts(client):
    create = client.post(
        "/api/jobs",
        json=_valid_payload(extra_recipients=[{"name": "Bad", "email": "bad"}]),
    )
    job_id = create.get_json()["job_id"]

    response = client.get(f"/api/jobs/{job_id}")
    assert response.status_code == 200
    data = response.get_json()
    assert data["job_id"] == job_id
    assert data["total"] == 3
    assert data["successful"] == 2
    assert data["failed"] == 1
    assert len(data["results"]) == 3

    recipients_resp = client.get(f"/api/jobs/{job_id}/recipients")
    assert recipients_resp.status_code == 200
    assert len(recipients_resp.get_json()["recipients"]) == 3


def test_continue_when_generation_fails(client, monkeypatch):
    """Mock generation so one recipient fails; others must still succeed."""
    call_count = {"n": 0}
    real_generate = certificate.generate_certificate

    def flaky_generate(**kwargs):
        call_count["n"] += 1
        if call_count["n"] == 1:
            raise RuntimeError("simulated PDF failure")
        return real_generate(**kwargs)

    monkeypatch.setattr(certificate, "generate_certificate", flaky_generate)
    # Also patch the name used inside app.process_job (imported module attribute)
    monkeypatch.setattr(app_module.certificate, "generate_certificate", flaky_generate)

    response = client.post("/api/jobs", json=_valid_payload())
    assert response.status_code == 201
    data = response.get_json()
    assert data["successful"] == 1
    assert data["failed"] == 1
    assert data["status"] == "completed_with_errors"

    statuses = {r["name"]: r["status"] for r in data["results"]}
    assert "failed" in statuses.values()
    assert "success" in statuses.values()


def test_download_certificate(client):
    create = client.post("/api/jobs", json=_valid_payload())
    cert_id = create.get_json()["results"][0]["certificate_id"]

    response = client.get(f"/api/certificates/{cert_id}")
    assert response.status_code == 200
    assert response.mimetype == "application/pdf"
    assert response.data[:4] == b"%PDF"


def test_404_for_missing_job_and_certificate(client):
    assert client.get("/api/jobs/99999").status_code == 404
    assert client.get("/api/jobs/99999/recipients").status_code == 404
    assert client.get("/api/certificates/99999").status_code == 404


def test_batch_size_limit(client):
    recipients = [
        {"name": f"User {i}", "email": f"user{i}@example.com"}
        for i in range(app_module.MAX_BATCH_SIZE + 1)
    ]
    response = client.post(
        "/api/jobs",
        json={
            "event_name": "Huge Event",
            "issue_date": "2026-10-12",
            "recipients": recipients,
        },
    )
    assert response.status_code == 400
    assert "maximum" in response.get_json()["error"].lower()
