"""
dashboard/server.py

Lightweight Flask API that exposes the SQLite database to the web dashboard.
Serves the dashboard HTML and handles all data queries.

Usage:
    pip install flask
    python dashboard/server.py
    Open http://localhost:5000
"""

import sqlite3
import json
from pathlib import Path
from flask import Flask, jsonify, request, send_from_directory

DB_PATH       = Path("data/outcomes.db")
DASHBOARD_DIR = Path(__file__).parent

app = Flask(__name__, static_folder=str(DASHBOARD_DIR))


def get_conn():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def rows_to_list(rows):
    return [dict(r) for r in rows]


# ── Routes ────────────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return send_from_directory(DASHBOARD_DIR, "index.html")


@app.route("/api/stats")
def api_stats():
    conn = get_conn()
    stats = {
        "subjects":  conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0],
        "outcomes":  conn.execute("SELECT COUNT(*) FROM learning_outcomes").fetchone()[0],
        "faculties": conn.execute(
            "SELECT COUNT(DISTINCT faculty) FROM subjects WHERE faculty != ''"
        ).fetchone()[0],
        "by_faculty": rows_to_list(conn.execute(
            "SELECT faculty, COUNT(*) AS n FROM subjects "
            "WHERE faculty != '' GROUP BY faculty ORDER BY n DESC"
        ).fetchall()),
        "by_bloom": rows_to_list(conn.execute(
            "SELECT bloom_level, COUNT(*) AS n FROM learning_outcomes "
            "WHERE bloom_level IS NOT NULL GROUP BY bloom_level"
        ).fetchall()),
        "by_category": rows_to_list(conn.execute(
            "SELECT category, COUNT(*) AS n FROM learning_outcomes "
            "WHERE category IS NOT NULL GROUP BY category ORDER BY n DESC"
        ).fetchall()),
        "avg_outcomes": conn.execute(
            "SELECT ROUND(AVG(c),1) FROM (SELECT COUNT(*) c FROM learning_outcomes GROUP BY subject_id)"
        ).fetchone()[0],
    }
    conn.close()
    return jsonify(stats)


@app.route("/api/search")
def api_search():
    q      = request.args.get("q", "").strip()
    limit  = min(int(request.args.get("limit", 50)), 200)
    faculty = request.args.get("faculty", "")
    bloom  = request.args.get("bloom", "")

    conn = get_conn()

    # Build query
    where_clauses = []
    params = []

    if q:
        # Try FTS
        fts_rows = []
        try:
            fts_rows = conn.execute(
                "SELECT rowid FROM lo_fts WHERE lo_fts MATCH ? LIMIT ?",
                (q, limit * 2),
            ).fetchall()
        except Exception:
            pass

        if fts_rows:
            id_list = ",".join(str(r[0]) for r in fts_rows)
            where_clauses.append(f"lo.id IN ({id_list})")
        else:
            where_clauses.append("lo.outcome LIKE ?")
            params.append(f"%{q}%")

    if faculty:
        where_clauses.append("s.faculty = ?")
        params.append(faculty)

    if bloom:
        where_clauses.append("lo.bloom_level = ?")
        params.append(bloom)

    where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

    sql = f"""
        SELECT
            s.code, s.name AS subject_name, s.faculty, s.credit_points, s.url,
            lo.sequence, lo.outcome, lo.category, lo.bloom_level
        FROM learning_outcomes lo
        JOIN subjects s ON s.id = lo.subject_id
        {where}
        ORDER BY s.code, lo.sequence
        LIMIT ?
    """
    params.append(limit)
    rows = conn.execute(sql, params).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


@app.route("/api/subject/<code>")
def api_subject(code):
    conn = get_conn()
    subject = conn.execute(
        "SELECT * FROM subjects WHERE code = ? ORDER BY year DESC LIMIT 1",
        (code.upper(),),
    ).fetchone()
    if not subject:
        conn.close()
        return jsonify({"error": "Not found"}), 404

    outcomes = rows_to_list(conn.execute(
        "SELECT * FROM learning_outcomes WHERE subject_id = ? ORDER BY sequence",
        (subject["id"],),
    ).fetchall())

    assessments = rows_to_list(conn.execute(
        "SELECT * FROM assessments WHERE subject_id = ? ORDER BY id",
        (subject["id"],),
    ).fetchall())

    conn.close()
    return jsonify({
        **dict(subject),
        "learning_outcomes": outcomes,
        "assessments": assessments,
    })


@app.route("/api/faculties")
def api_faculties():
    conn = get_conn()
    rows = conn.execute(
        "SELECT DISTINCT faculty FROM subjects WHERE faculty != '' ORDER BY faculty"
    ).fetchall()
    conn.close()
    return jsonify([r[0] for r in rows])


@app.route("/api/subjects")
def api_subjects():
    faculty = request.args.get("faculty", "")
    conn = get_conn()
    if faculty:
        rows = conn.execute(
            "SELECT code, name, faculty, credit_points FROM subjects WHERE faculty = ? ORDER BY code",
            (faculty,),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT code, name, faculty, credit_points FROM subjects ORDER BY code LIMIT 500"
        ).fetchall()
    conn.close()
    return jsonify(rows_to_list(rows))


if __name__ == "__main__":
    if not DB_PATH.exists():
        print(f"ERROR: Database not found at {DB_PATH}")
        print("Run the scraper first: python scraper/uow_scraper.py --limit 20")
        exit(1)
    print(f"Starting server at http://localhost:5000")
    app.run(debug=True, port=5000)
