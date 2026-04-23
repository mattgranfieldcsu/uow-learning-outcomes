import sqlite3
import csv
from pathlib import Path

DB_PATH = Path("data/outcomes.db")
CSV_PATH = Path("data/outcomes_snapshot.csv")

def export():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
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
        """
        cursor.execute(query)
        rows = cursor.fetchall()
        
        if not rows:
            # This is the "Diagnostic" part
            cursor.execute("SELECT COUNT(*) FROM subjects")
            s_count = cursor.fetchone()[0]
            cursor.execute("SELECT COUNT(*) FROM learning_outcomes")
            l_count = cursor.fetchone()[0]
            print(f"DIAGNOSTIC: Found {s_count} subjects and {l_count} outcomes in DB, but the JOIN failed.")
            print("Check if the subject_id in learning_outcomes matches the id in subjects.")
            return

        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow(["university", "code", "name", "year", "sequence", "outcome", "category", "bloom_level"])
            for row in rows:
                writer.writerow([
                    row['university'], row['code'], row['name'], row['year'],
                    row['sequence'], row['outcome'], row['category'], row['bloom_level']
                ])

        print(f"SUCCESS: Exported {len(rows)} rows to CSV.")

    except Exception as e:
        print(f"Export failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export()