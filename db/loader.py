"""
db/loader.py

Creates the SQLite database from schema.sql and provides a function
to load a scraped subject dict into it.

Usage:
    from db.loader import load_subject, init_db
    init_db()                  # create tables (idempotent)
    load_subject(subject_dict) # upsert one subject
"""

import sqlite3
import json
from pathlib import Path
from datetime import datetime
from typing import Optional

DB_PATH     = Path("data/outcomes.db")
SCHEMA_PATH = Path(__file__).parent / "schema.sql"

UNIVERSITY_ID = "UOW"
YEAR          = 2026


# ── Init ──────────────────────────────────────────────────────────────────────

def get_conn() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db():
    """Create tables from schema.sql (idempotent — safe to call repeatedly)."""
    schema = SCHEMA_PATH.read_text()
    conn = get_conn()
    conn.executescript(schema)
    conn.commit()
    conn.close()
    print(f"Database initialised at {DB_PATH.resolve()}")


# ── Upsert a subject ──────────────────────────────────────────────────────────

def load_subject(subject: dict, university_id: str = UNIVERSITY_ID):
    """
    Insert or replace one subject (and its learning outcomes + assessments)
    into the database. Safe to call multiple times — uses upsert semantics.
    """
    code  = subject["code"]
    year  = subject.get("year", YEAR)
    sid   = f"{university_id}-{code}-{year}"

    conn  = get_conn()

    try:
        # ── Subject row ──
        conn.execute(
            """
            INSERT INTO subjects
                (id, university_id, code, name, year, faculty, credit_points,
                 description, prerequisites, url, scraped_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name          = excluded.name,
                faculty       = excluded.faculty,
                credit_points = excluded.credit_points,
                description   = excluded.description,
                prerequisites = excluded.prerequisites,
                url           = excluded.url,
                scraped_at    = excluded.scraped_at
            """,
            (
                sid,
                university_id,
                code,
                subject.get("name", ""),
                year,
                subject.get("faculty", ""),
                subject.get("credit_points"),
                subject.get("description", ""),
                subject.get("prerequisites", ""),
                subject.get("url", ""),
                datetime.utcnow().isoformat(),
            ),
        )

        # ── Learning outcomes (replace all for this subject) ──
        conn.execute(
            "DELETE FROM learning_outcomes WHERE subject_id = ?", (sid,)
        )
        for lo in subject.get("learning_outcomes", []):
            conn.execute(
                """
                INSERT INTO learning_outcomes (subject_id, sequence, outcome)
                VALUES (?, ?, ?)
                """,
                (sid, lo["sequence"], lo["outcome"]),
            )

        # ── Assessments (replace all for this subject) ──
        conn.execute(
            "DELETE FROM assessments WHERE subject_id = ?", (sid,)
        )
        for a in subject.get("assessments", []):
            weight = a.get("weight")
            if isinstance(weight, str):
                weight = "".join(c for c in weight if c.isdigit()) or None
                weight = int(weight) if weight else None
            conn.execute(
                """
                INSERT INTO assessments (subject_id, type, name, weight, description)
                VALUES (?, ?, ?, ?, ?)
                """,
                (sid, a.get("type", ""), a.get("name", ""), weight, a.get("description", "")),
            )

        conn.commit()

    except Exception as e:
        conn.rollback()
        raise e
    finally:
        conn.close()


# ── Bulk load from raw JSON files ─────────────────────────────────────────────

def load_all_raw(raw_dir: str = "data/raw"):
    """
    Load every *.json file in raw_dir into the database.
    Useful for reprocessing after schema changes without re-scraping.
    """
    import glob
    files = sorted(glob.glob(f"{raw_dir}/*.json"))
    print(f"Loading {len(files)} raw files into database…")
    for i, path in enumerate(files, 1):
        try:
            subject = json.loads(Path(path).read_text())
            load_subject(subject)
            if i % 100 == 0:
                print(f"  {i}/{len(files)}")
        except Exception as e:
            print(f"  ERROR loading {path}: {e}")
    print("Done.")


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == "reload":
        init_db()
        load_all_raw()
    else:
        init_db()
        print("Use 'python -m db.loader reload' to load all raw JSON files.")
