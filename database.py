"""SQLite database setup and operations for CertiBatch."""

import os
import sqlite3
from datetime import datetime, timezone

# Default paths (overridable in tests via init_db / set_db_path)
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_DB_PATH = os.path.join(BASE_DIR, "instance", "certificates.db")

_db_path = DEFAULT_DB_PATH


def set_db_path(path):
    """Override the database file path (used by tests)."""
    global _db_path
    _db_path = path


def get_db_path():
    return _db_path


def get_connection():
    """Open a SQLite connection with foreign keys enabled."""
    conn = sqlite3.connect(_db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def init_db(db_path=None):
    """Create the database file and tables if they do not exist."""
    if db_path is not None:
        set_db_path(db_path)

    os.makedirs(os.path.dirname(_db_path) or ".", exist_ok=True)

    conn = get_connection()
    try:
        conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_name TEXT NOT NULL,
                issue_date TEXT NOT NULL,
                status TEXT NOT NULL,
                total_recipients INTEGER NOT NULL DEFAULT 0,
                successful_count INTEGER NOT NULL DEFAULT 0,
                failed_count INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS recipients (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                job_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                status TEXT NOT NULL,
                certificate_id INTEGER UNIQUE,
                certificate_path TEXT,
                error_message TEXT,
                FOREIGN KEY (job_id) REFERENCES jobs(id) ON DELETE CASCADE
            );
            """
        )
        conn.commit()
    finally:
        conn.close()


def create_job(event_name, issue_date, total_recipients):
    """Insert a new job with status 'processing' and return its id."""
    created_at = datetime.now(timezone.utc).isoformat()
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO jobs (
                event_name, issue_date, status,
                total_recipients, successful_count, failed_count, created_at
            ) VALUES (?, ?, ?, ?, 0, 0, ?)
            """,
            (event_name, issue_date, "processing", total_recipients, created_at),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def update_job(job_id, status, successful_count, failed_count):
    """Update job status and counts after processing."""
    conn = get_connection()
    try:
        conn.execute(
            """
            UPDATE jobs
            SET status = ?, successful_count = ?, failed_count = ?
            WHERE id = ?
            """,
            (status, successful_count, failed_count, job_id),
        )
        conn.commit()
    finally:
        conn.close()


def add_recipient(
    job_id,
    name,
    email,
    status,
    certificate_id=None,
    certificate_path=None,
    error_message=None,
):
    """Insert a recipient result row and return its primary key."""
    conn = get_connection()
    try:
        cursor = conn.execute(
            """
            INSERT INTO recipients (
                job_id, name, email, status,
                certificate_id, certificate_path, error_message
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                name,
                email,
                status,
                certificate_id,
                certificate_path,
                error_message,
            ),
        )
        conn.commit()
        return cursor.lastrowid
    finally:
        conn.close()


def get_job(job_id):
    """Return a job row as a dict, or None if not found."""
    conn = get_connection()
    try:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_recipients_for_job(job_id):
    """Return all recipient rows for a job as a list of dicts."""
    conn = get_connection()
    try:
        rows = conn.execute(
            """
            SELECT * FROM recipients
            WHERE job_id = ?
            ORDER BY id ASC
            """,
            (job_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def get_certificate_by_id(certificate_id):
    """Return a successful recipient row by certificate_id, or None."""
    conn = get_connection()
    try:
        row = conn.execute(
            """
            SELECT * FROM recipients
            WHERE certificate_id = ? AND status = 'success'
            """,
            (certificate_id,),
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def next_certificate_id():
    """Allocate the next unique certificate ID across all recipients."""
    conn = get_connection()
    try:
        row = conn.execute(
            "SELECT COALESCE(MAX(certificate_id), 100) + 1 AS next_id FROM recipients"
        ).fetchone()
        return int(row["next_id"])
    finally:
        conn.close()
