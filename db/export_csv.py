import sqlite3
import csv
import os
from pathlib import Path

# ── Path Resolution ──────────────────────────────────────────────────────────
# This ensures we find the 'data' folder at the project root, 
# regardless of whether we run this from /db or from the root.
BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "outcomes.db"
CSV_PATH = BASE_DIR / "data" / "outcomes_snapshot.csv"

def export():
    print(f"Targeting database at: {DB_PATH}")
    
    if not DB_PATH.exists():
        print(f"FAIL: Database file does not exist at {DB_PATH}")
        # List files in data/ for debugging purposes in the GitHub log
        data_dir = BASE_DIR / "data"
        if data_dir.exists():
            print(f"Contents of {data_dir}: {os.listdir(data_dir)}")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # This query joins the subjects and outcomes using the composite ID
        # defined in your loader.py (university-code-year)
        query = """
        SELECT 
            s.university_id as university,
            s.code, 
            s.name, 
            s.year, 
            lo.sequence, 
            lo.outcome, 
            lo.category, 
            lo.bloom_level
        FROM subjects s
        JOIN learning_outcomes lo ON s.id = lo.subject_id
        ORDER BY s.code, lo.sequence
        """
        
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            # Diagnostic check: Are there subjects but no outcomes?
            cursor.execute("SELECT COUNT(*) FROM subjects")
            s_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM learning_outcomes")
            l_count = cursor.fetchone()[0]
            print(f"DIAGNOSTIC: Found {s_count} subjects and {l_count} outcomes in DB.")
            print("The JOIN returned 0 rows. Check if subject_id matches accurately.")
            return

        # Write the CSV file
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            # Standardizing headers for your credit recognition team
            writer.writerow([
                "university", "code", "name", "year", 
                "sequence", "outcome", "category", "bloom_level"
            ])
            
            for row in rows:
                writer.writerow([
                    row['university'], row['code'], row['name'], row['year'],
                    row['sequence'], row['outcome'], row['category'], row['bloom_level']
                ])

        print(f"SUCCESS: Exported {len(rows)} rows to {CSV_PATH}")

    except Exception as e:
        print(f"ERROR during export process: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export()