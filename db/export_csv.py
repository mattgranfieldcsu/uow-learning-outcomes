import sqlite3
import csv
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "outcomes.db"
CSV_PATH = BASE_DIR / "data" / "outcomes_snapshot.csv"

def export():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # Changed to LEFT JOIN so subjects appear even if outcomes are 0
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
        LEFT JOIN learning_outcomes lo ON s.id = lo.subject_id
        ORDER BY s.code, lo.sequence
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["university", "code", "name", "year", "sequence", "outcome", "category", "bloom_level"])
            for row in rows:
                writer.writerow(list(row))

        print(f"SUCCESS: Exported {len(rows)} rows. Check {CSV_PATH}")

    except Exception as e:
        print(f"Export failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export()