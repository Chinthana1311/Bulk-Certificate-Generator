"""CertiBatch — Bulk Certificate Generator Flask REST API."""

import os
import re
from flask import Flask, jsonify, request, send_file

import certificate
import database

MAX_BATCH_SIZE = 500
EMAIL_PATTERN = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

app = Flask(__name__)


def create_app(db_path=None, cert_dir=None, org_name=None):
    """
    Application factory used by tests and by the main entry point.

    Ensures the database and certificate directory exist.
    """
    if db_path is not None:
        database.set_db_path(db_path)
    if cert_dir is not None:
        certificate.set_certificate_dir(cert_dir)
    if org_name is not None:
        certificate.set_org_name(org_name)

    database.init_db()
    os.makedirs(certificate.get_certificate_dir(), exist_ok=True)
    return app


def _error(message, status=400):
    return jsonify({"error": message}), status


def _validate_job_payload(data):
    """
    Validate top-level job fields.
    Returns (ok, error_message, normalised_data).
    """
    if not isinstance(data, dict):
        return False, "Request body must be a JSON object.", None

    event_name = data.get("event_name")
    issue_date = data.get("issue_date")
    recipients = data.get("recipients")

    if event_name is None or (isinstance(event_name, str) and not event_name.strip()):
        return False, "Missing or empty required field: event_name.", None
    if not isinstance(event_name, str):
        return False, "event_name must be a string.", None

    if issue_date is None or (isinstance(issue_date, str) and not issue_date.strip()):
        return False, "Missing or empty required field: issue_date.", None
    if not isinstance(issue_date, str):
        return False, "issue_date must be a string.", None

    if recipients is None:
        return False, "Missing required field: recipients.", None
    if not isinstance(recipients, list):
        return False, "recipients must be a list.", None
    if len(recipients) == 0:
        return False, "recipients list must not be empty.", None
    if len(recipients) > MAX_BATCH_SIZE:
        return (
            False,
            f"Batch size exceeds maximum of {MAX_BATCH_SIZE} recipients.",
            None,
        )

    return (
        True,
        None,
        {
            "event_name": event_name.strip(),
            "issue_date": issue_date.strip(),
            "recipients": recipients,
        },
    )


def _validate_recipient(recipient, seen_emails):
    """
    Validate one recipient independently.
    Returns (ok, name, email, error_message).
    """
    if not isinstance(recipient, dict):
        return False, "", "", "Recipient must be an object with name and email."

    name = recipient.get("name")
    email = recipient.get("email")

    if name is None or not isinstance(name, str) or not name.strip():
        display_name = name if isinstance(name, str) else ""
        return False, display_name, str(email or ""), "Name is required and must not be blank."

    if email is None or not isinstance(email, str) or not email.strip():
        return False, name.strip(), "", "Email is required and must not be blank."

    name = name.strip()
    email = email.strip()
    email_key = email.lower()

    if not EMAIL_PATTERN.match(email):
        return False, name, email, "Invalid email address."

    if email_key in seen_emails:
        return False, name, email, "Duplicate email address in this request."

    seen_emails.add(email_key)
    return True, name, email, None


def _recipient_result(row):
    """Shape a recipient DB row for JSON responses."""
    result = {
        "name": row["name"],
        "email": row["email"],
        "status": row["status"],
    }
    if row["status"] == "success":
        result["certificate_id"] = row["certificate_id"]
    else:
        result["error"] = row["error_message"] or "Unknown error"
    return result


def process_job(job_id, event_name, issue_date, recipients):
    """
    Synchronously validate and generate certificates for each recipient.
    Individual failures are recorded; processing continues for the rest.
    """
    successful = 0
    failed = 0
    seen_emails = set()
    results = []

    for recipient in recipients:
        ok, name, email, error = _validate_recipient(recipient, seen_emails)

        if not ok:
            database.add_recipient(
                job_id=job_id,
                name=name or (recipient.get("name") if isinstance(recipient, dict) else "") or "unknown",
                email=email or (str(recipient.get("email")) if isinstance(recipient, dict) else "") or "",
                status="failed",
                error_message=error,
            )
            failed += 1
            results.append(
                {
                    "name": name or "unknown",
                    "email": email or "",
                    "status": "failed",
                    "error": error,
                }
            )
            continue

        try:
            cert_id = database.next_certificate_id()
            path = certificate.generate_certificate(
                recipient_name=name,
                event_name=event_name,
                issue_date=issue_date,
                certificate_id=cert_id,
            )
            database.add_recipient(
                job_id=job_id,
                name=name,
                email=email,
                status="success",
                certificate_id=cert_id,
                certificate_path=path,
            )
            successful += 1
            results.append(
                {
                    "name": name,
                    "email": email,
                    "status": "success",
                    "certificate_id": cert_id,
                }
            )
        except Exception as exc:  # noqa: BLE001 — isolate per-recipient failures
            database.add_recipient(
                job_id=job_id,
                name=name,
                email=email,
                status="failed",
                error_message=f"Certificate generation failed: {exc}",
            )
            failed += 1
            results.append(
                {
                    "name": name,
                    "email": email,
                    "status": "failed",
                    "error": f"Certificate generation failed: {exc}",
                }
            )

    if successful == 0 and failed > 0:
        status = "failed"
    elif failed > 0:
        status = "completed_with_errors"
    else:
        status = "completed"

    database.update_job(job_id, status, successful, failed)
    return status, successful, failed, results


@app.get("/")
def home():
    """Interactive UI to create bulk certificate jobs in the browser."""
    return (
        """
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>CertiBatch — Bulk Certificate Generator</title>
  <style>
    :root {
      --gold: #c9a227;
      --gold-dark: #a8841a;
      --grey: #555;
      --line: #ddd;
      --bg: #f7f5f0;
      --card: #fff;
    }
    * { box-sizing: border-box; }
    body {
      margin: 0;
      font-family: "Segoe UI", Helvetica, Arial, sans-serif;
      color: var(--grey);
      background:
        radial-gradient(circle at top left, #fff8e7 0%, transparent 45%),
        linear-gradient(180deg, #faf7f0, #f0ece4);
      min-height: 100vh;
      padding: 32px 16px 48px;
    }
    .wrap { max-width: 760px; margin: 0 auto; }
    h1 {
      font-family: Georgia, "Times New Roman", serif;
      color: var(--gold);
      letter-spacing: 0.12em;
      margin: 0 0 6px;
      font-size: 2rem;
    }
    .sub { margin: 0 0 28px; color: #777; }
    .panel {
      background: var(--card);
      border: 1px solid var(--line);
      border-radius: 10px;
      padding: 22px;
      margin-bottom: 18px;
      box-shadow: 0 8px 24px rgba(0,0,0,0.04);
    }
    label { display: block; font-size: 0.85rem; margin-bottom: 6px; font-weight: 600; }
    input {
      width: 100%;
      padding: 10px 12px;
      border: 1px solid #ccc;
      border-radius: 6px;
      font-size: 1rem;
      margin-bottom: 14px;
    }
    .row { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
    .recipient {
      display: grid;
      grid-template-columns: 1fr 1fr auto;
      gap: 10px;
      align-items: end;
      margin-bottom: 10px;
    }
    .recipient label { margin: 0 0 4px; }
    .recipient input { margin: 0; }
    button, .btn {
      border: 0;
      border-radius: 6px;
      padding: 10px 16px;
      cursor: pointer;
      font-size: 0.95rem;
      text-decoration: none;
      display: inline-block;
    }
    .primary { background: var(--gold); color: #fff; font-weight: 600; }
    .primary:hover { background: var(--gold-dark); }
    .secondary { background: #eee; color: #444; }
    .danger { background: #f3e8e8; color: #8a3030; }
    .actions { display: flex; gap: 10px; flex-wrap: wrap; margin-top: 8px; }
    #status {
      display: none;
      padding: 12px 14px;
      border-radius: 6px;
      margin-bottom: 14px;
      background: #f3f0e6;
      border: 1px solid #e4d7b0;
    }
    table { width: 100%; border-collapse: collapse; font-size: 0.95rem; }
    th, td { text-align: left; padding: 10px 8px; border-bottom: 1px solid var(--line); }
    th { font-size: 0.8rem; text-transform: uppercase; letter-spacing: 0.04em; color: #888; }
    .ok { color: #1f7a3f; font-weight: 600; }
    .fail { color: #a33; font-weight: 600; }
    @media (max-width: 640px) {
      .row, .recipient { grid-template-columns: 1fr; }
    }
  </style>
</head>
<body>
  <div class="wrap">
    <h1>CERTIBATCH</h1>
    <p class="sub">Generate personalized PDF certificates for many recipients at once.</p>

    <div class="panel">
      <form id="job-form">
        <div class="row">
          <div>
            <label for="event_name">Event / Course name</label>
            <input id="event_name" name="event_name" required
                   value="Python Workshop 2026" placeholder="Python Workshop 2026" />
          </div>
          <div>
            <label for="issue_date">Issue date</label>
            <input id="issue_date" name="issue_date" type="date" required />
          </div>
        </div>

        <label>Recipients</label>
        <div id="recipients"></div>

        <div class="actions">
          <button type="button" class="secondary" id="add-row">+ Add recipient</button>
          <button type="submit" class="primary">Generate certificates</button>
        </div>
      </form>
    </div>

    <div id="status"></div>

    <div class="panel" id="results-panel" style="display:none;">
      <h2 style="margin-top:0;font-family:Georgia,serif;color:var(--gold-dark);">Results</h2>
      <div id="summary"></div>
      <table>
        <thead>
          <tr>
            <th>Name</th>
            <th>Email</th>
            <th>Status</th>
            <th>Action</th>
          </tr>
        </thead>
        <tbody id="results-body"></tbody>
      </table>
    </div>
  </div>

  <script>
    const recipientsEl = document.getElementById("recipients");
    const dateInput = document.getElementById("issue_date");
    dateInput.value = new Date().toISOString().slice(0, 10);

    function addRow(name = "", email = "") {
      const div = document.createElement("div");
      div.className = "recipient";
      div.innerHTML = `
        <div>
          <label>Name</label>
          <input class="name" required placeholder="Full name" value="${name}" />
        </div>
        <div>
          <label>Email</label>
          <input class="email" type="text" required placeholder="name@example.com" value="${email}" />
        </div>
        <button type="button" class="danger remove">Remove</button>
      `;
      div.querySelector(".remove").onclick = () => {
        if (recipientsEl.children.length > 1) div.remove();
      };
      recipientsEl.appendChild(div);
    }

    addRow("Chinthana A", "chinthana@example.com");
    addRow("Priya S", "priya@example.com");
    addRow("Arun K", "invalid-email");

    document.getElementById("add-row").onclick = () => addRow();

    document.getElementById("job-form").onsubmit = async (e) => {
      e.preventDefault();
      const status = document.getElementById("status");
      status.style.display = "block";
      status.textContent = "Generating certificates...";

      const recipients = [...recipientsEl.querySelectorAll(".recipient")].map((row) => ({
        name: row.querySelector(".name").value.trim(),
        email: row.querySelector(".email").value.trim(),
      }));

      const payload = {
        event_name: document.getElementById("event_name").value.trim(),
        issue_date: document.getElementById("issue_date").value,
        recipients,
      };

      try {
        const res = await fetch("/api/jobs", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        const data = await res.json();
        if (!res.ok) {
          status.textContent = data.error || "Request failed.";
          return;
        }

        status.textContent =
          `Job #${data.job_id} — ${data.status}: ${data.successful} success, ${data.failed} failed (total ${data.total}).`;

        document.getElementById("results-panel").style.display = "block";
        document.getElementById("summary").innerHTML =
          `<p><strong>Job ID:</strong> ${data.job_id} &nbsp;|&nbsp; <strong>Status:</strong> ${data.status}</p>`;

        const tbody = document.getElementById("results-body");
        tbody.innerHTML = "";
        data.results.forEach((r) => {
          const tr = document.createElement("tr");
          const action =
            r.status === "success"
              ? `<a class="btn primary" href="/api/certificates/${r.certificate_id}">Download PDF</a>`
              : `<span class="fail">${r.error || "Failed"}</span>`;
          tr.innerHTML = `
            <td>${r.name}</td>
            <td>${r.email || ""}</td>
            <td class="${r.status === "success" ? "ok" : "fail"}">${r.status}</td>
            <td>${action}</td>
          `;
          tbody.appendChild(tr);
        });
      } catch (err) {
        status.textContent = "Could not reach the server. Is Flask running?";
      }
    };
  </script>
</body>
</html>
        """,
        200,
        {"Content-Type": "text/html; charset=utf-8"},
    )


@app.get("/api/health")
def health():
    return jsonify({"status": "ok", "message": "CertiBatch API is running."})


@app.post("/api/jobs")
def create_job():
    data = request.get_json(silent=True)
    ok, err, payload = _validate_job_payload(data)
    if not ok:
        return _error(err, 400)

    job_id = database.create_job(
        event_name=payload["event_name"],
        issue_date=payload["issue_date"],
        total_recipients=len(payload["recipients"]),
    )

    status, successful, failed, results = process_job(
        job_id=job_id,
        event_name=payload["event_name"],
        issue_date=payload["issue_date"],
        recipients=payload["recipients"],
    )

    return (
        jsonify(
            {
                "job_id": job_id,
                "status": status,
                "total": len(payload["recipients"]),
                "successful": successful,
                "failed": failed,
                "results": results,
            }
        ),
        201,
    )


@app.get("/api/jobs/<int:job_id>")
def get_job(job_id):
    job = database.get_job(job_id)
    if job is None:
        return _error("Job not found.", 404)

    recipients = database.get_recipients_for_job(job_id)
    return jsonify(
        {
            "job_id": job["id"],
            "event_name": job["event_name"],
            "issue_date": job["issue_date"],
            "status": job["status"],
            "total": job["total_recipients"],
            "successful": job["successful_count"],
            "failed": job["failed_count"],
            "created_at": job["created_at"],
            "results": [_recipient_result(r) for r in recipients],
        }
    )


@app.get("/api/jobs/<int:job_id>/recipients")
def get_job_recipients(job_id):
    job = database.get_job(job_id)
    if job is None:
        return _error("Job not found.", 404)

    recipients = database.get_recipients_for_job(job_id)
    return jsonify(
        {
            "job_id": job_id,
            "recipients": [_recipient_result(r) for r in recipients],
        }
    )


@app.get("/api/certificates/<int:certificate_id>")
def download_certificate(certificate_id):
    row = database.get_certificate_by_id(certificate_id)
    if row is None:
        return _error("Certificate not found.", 404)

    path = row["certificate_path"]
    if not path or not os.path.isfile(path):
        return _error("Certificate file is missing.", 404)

    # Only serve files under the configured certificates directory
    cert_dir = os.path.abspath(certificate.get_certificate_dir())
    real_path = os.path.abspath(path)
    if not real_path.startswith(cert_dir + os.sep) and real_path != cert_dir:
        return _error("Certificate file is missing.", 404)

    return send_file(
        real_path,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=os.path.basename(real_path),
    )


# Initialise defaults when imported / run directly
create_app()


if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
