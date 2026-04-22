#!/usr/bin/env python3
"""
query.py — CLI search tool for the learning outcomes database.

Examples:
    python query.py search "critical thinking"
    python query.py subject CRWR101
    python query.py stats
    python query.py export --format csv --out outcomes.csv
    python query.py bloom-chart
"""

import sqlite3
import json
import csv
import sys
import argparse
from pathlib import Path

DB_PATH = Path("data/outcomes.db")

BLOOM_ORDER = ["remember", "understand", "apply", "analyse", "evaluate", "create"]
BAR_CHARS   = "▏▎▍▌▋▊▉█"


def get_conn() -> sqlite3.Connection:
    if not DB_PATH.exists():
        print(f"Database not found at {DB_PATH}. Run the scraper first.")
        sys.exit(1)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


# ── Commands ──────────────────────────────────────────────────────────────────

def cmd_search(args):
    """Full-text search across all learning outcomes."""
    conn = get_conn()
    query = args.query

    # Try FTS first, fall back to LIKE
    try:
        rows = conn.execute(
            """
            SELECT s.code, s.name, s.faculty, lo.sequence, lo.outcome, lo.category, lo.bloom_level
            FROM lo_fts
            JOIN learning_outcomes lo ON lo.id = lo_fts.rowid
            JOIN subjects s           ON s.id  = lo.subject_id
            WHERE lo_fts MATCH ?
            ORDER BY rank
            LIMIT ?
            """,
            (query, args.limit),
        ).fetchall()
    except Exception:
        rows = conn.execute(
            """
            SELECT s.code, s.name, s.faculty, lo.sequence, lo.outcome, lo.category, lo.bloom_level
            FROM learning_outcomes lo
            JOIN subjects s ON s.id = lo.subject_id
            WHERE lo.outcome LIKE ?
            ORDER BY s.code, lo.sequence
            LIMIT ?
            """,
            (f"%{query}%", args.limit),
        ).fetchall()

    conn.close()

    if not rows:
        print(f"No outcomes matched '{query}'")
        return

    print(f"\n{'─'*80}")
    print(f"  {len(rows)} outcome(s) matching '{query}'")
    print(f"{'─'*80}\n")

    for r in rows:
        tag = f"[{r['bloom_level']}]" if r['bloom_level'] else ""
        cat = f"({r['category']})"    if r['category']    else ""
        print(f"  {r['code']}  {r['name']}")
        print(f"  Faculty: {r['faculty'] or '—'}  {cat} {tag}")
        print(f"  {r['outcome']}")
        print()


def cmd_subject(args):
    """Show all details for a single subject."""
    conn = get_conn()
    code = args.code.upper()

    subject = conn.execute(
        "SELECT * FROM subjects WHERE code = ? ORDER BY year DESC LIMIT 1", (code,)
    ).fetchone()

    if not subject:
        print(f"Subject '{code}' not found.")
        conn.close()
        return

    outcomes = conn.execute(
        "SELECT * FROM learning_outcomes WHERE subject_id = ? ORDER BY sequence",
        (subject["id"],),
    ).fetchall()

    assessments = conn.execute(
        "SELECT * FROM assessments WHERE subject_id = ? ORDER BY id",
        (subject["id"],),
    ).fetchall()

    conn.close()

    # Pretty print
    print(f"\n{'═'*80}")
    print(f"  {subject['code']}  {subject['name']}")
    print(f"  {subject['faculty'] or '—'}  ·  {subject['credit_points']} cp  ·  {subject['year']}")
    print(f"  {subject['url']}")
    print(f"{'═'*80}\n")

    if subject["description"]:
        print("DESCRIPTION")
        print(f"  {subject['description'][:500]}")
        print()

    if subject["prerequisites"]:
        print(f"PREREQUISITES\n  {subject['prerequisites']}\n")

    print(f"LEARNING OUTCOMES ({len(outcomes)})")
    for lo in outcomes:
        tag = f"  [{lo['bloom_level']}]" if lo['bloom_level'] else ""
        print(f"  {lo['sequence']}. {lo['outcome']}{tag}")
    print()

    if assessments:
        print(f"ASSESSMENTS")
        for a in assessments:
            weight = f"  {a['weight']}%" if a['weight'] else ""
            print(f"  · {a['type'] or a['name']}{weight}")
            if a['description']:
                print(f"    {a['description'][:120]}")
    print()


def cmd_stats(args):
    """Print database statistics."""
    conn = get_conn()

    total_subjects  = conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0]
    total_outcomes  = conn.execute("SELECT COUNT(*) FROM learning_outcomes").fetchone()[0]
    total_assess    = conn.execute("SELECT COUNT(*) FROM assessments").fetchone()[0]
    avg_outcomes    = conn.execute(
        "SELECT AVG(c) FROM (SELECT COUNT(*) c FROM learning_outcomes GROUP BY subject_id)"
    ).fetchone()[0]

    print(f"\n{'─'*50}")
    print(f"  DATABASE STATISTICS")
    print(f"{'─'*50}")
    print(f"  Subjects:             {total_subjects:,}")
    print(f"  Learning outcomes:    {total_outcomes:,}")
    print(f"  Assessments:          {total_assess:,}")
    print(f"  Avg outcomes/subject: {avg_outcomes:.1f}" if avg_outcomes else "")
    print()

    # Faculty breakdown
    faculties = conn.execute(
        """SELECT faculty, COUNT(*) n FROM subjects
           WHERE faculty != '' GROUP BY faculty ORDER BY n DESC"""
    ).fetchall()
    if faculties:
        print(f"  BY FACULTY")
        for row in faculties:
            bar_len = int(row['n'] / max(r['n'] for r in faculties) * 30)
            print(f"  {'█' * bar_len:<30}  {row['n']:>4}  {row['faculty']}")
        print()

    # Bloom distribution
    bloom = conn.execute(
        """SELECT bloom_level, COUNT(*) n FROM learning_outcomes
           WHERE bloom_level IS NOT NULL GROUP BY bloom_level"""
    ).fetchall()
    if bloom:
        bloom_dict = {r['bloom_level']: r['n'] for r in bloom}
        max_n = max(bloom_dict.values())
        print(f"  BLOOM'S TAXONOMY DISTRIBUTION")
        for level in BLOOM_ORDER:
            n = bloom_dict.get(level, 0)
            bar_len = int(n / max_n * 30) if max_n else 0
            print(f"  {level:<12} {'█' * bar_len:<30}  {n:>5}")
        print()

    conn.close()


def cmd_export(args):
    """Export outcomes to CSV or JSONL."""
    conn = get_conn()

    rows = conn.execute(
        """
        SELECT
            s.university_id, s.code, s.name, s.year, s.faculty, s.credit_points,
            s.url,
            lo.sequence, lo.outcome, lo.category, lo.bloom_level
        FROM learning_outcomes lo
        JOIN subjects s ON s.id = lo.subject_id
        ORDER BY s.code, lo.sequence
        """
    ).fetchall()
    conn.close()

    out_path = Path(args.out)

    if args.format == "csv":
        with open(out_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(
                f,
                fieldnames=[
                    "university", "code", "name", "year", "faculty",
                    "credit_points", "url", "sequence", "outcome", "category", "bloom_level"
                ],
            )
            writer.writeheader()
            for r in rows:
                writer.writerow({
                    "university":    r["university_id"],
                    "code":          r["code"],
                    "name":          r["name"],
                    "year":          r["year"],
                    "faculty":       r["faculty"],
                    "credit_points": r["credit_points"],
                    "url":           r["url"],
                    "sequence":      r["sequence"],
                    "outcome":       r["outcome"],
                    "category":      r["category"],
                    "bloom_level":   r["bloom_level"],
                })
    elif args.format == "jsonl":
        with open(out_path, "w", encoding="utf-8") as f:
            for r in rows:
                f.write(json.dumps(dict(r)) + "\n")

    print(f"Exported {len(rows)} rows to {out_path}")


def cmd_sql(args):
    """Run a raw SQL query and print results."""
    conn = get_conn()
    try:
        rows = conn.execute(args.sql).fetchall()
        if not rows:
            print("No results.")
            return
        headers = rows[0].keys()
        col_widths = [
            max(len(h), max((len(str(r[h] or "")) for r in rows), default=0))
            for h in headers
        ]
        fmt = "  " + "  ".join(f"{{:<{w}}}" for w in col_widths)
        print(fmt.format(*headers))
        print("  " + "  ".join("─" * w for w in col_widths))
        for row in rows[:200]:
            print(fmt.format(*[str(row[h] or "") for h in headers]))
        if len(rows) > 200:
            print(f"  … {len(rows) - 200} more rows")
    except Exception as e:
        print(f"SQL error: {e}")
    finally:
        conn.close()


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(
        description="Query the UOW learning outcomes database",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python query.py search "critical thinking"
  python query.py search "design" --limit 50
  python query.py subject CRWR101
  python query.py stats
  python query.py export --format csv --out outcomes.csv
  python query.py sql "SELECT faculty, COUNT(*) FROM subjects GROUP BY faculty"
        """,
    )
    sub = parser.add_subparsers(dest="command")

    # search
    p_search = sub.add_parser("search", help="Full-text search learning outcomes")
    p_search.add_argument("query")
    p_search.add_argument("--limit", type=int, default=30)

    # subject
    p_subj = sub.add_parser("subject", help="Show all info for a subject code")
    p_subj.add_argument("code")

    # stats
    sub.add_parser("stats", help="Database statistics and charts")

    # export
    p_exp = sub.add_parser("export", help="Export to CSV or JSONL")
    p_exp.add_argument("--format", choices=["csv", "jsonl"], default="csv")
    p_exp.add_argument("--out", default="outcomes.csv")

    # sql
    p_sql = sub.add_parser("sql", help="Run a raw SQL query")
    p_sql.add_argument("sql")

    args = parser.parse_args()

    dispatch = {
        "search":  cmd_search,
        "subject": cmd_subject,
        "stats":   cmd_stats,
        "export":  cmd_export,
        "sql":     cmd_sql,
    }

    if args.command in dispatch:
        dispatch[args.command](args)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
