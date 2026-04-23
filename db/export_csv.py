import sqlite3
import csv
from pathlib import Path

# Paths are relative to the project root
DB_PATH = Path("data/outcomes.db")
CSV_PATH = Path("data/outcomes_snapshot.csv")

def export():
    if not DB_PATH.exists():
        print(f"Error: {DB_PATH} not found. Ensure the scraper has run first.")
        return

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    try:
        # This query pulls the data and maps it to the headers you need
        query = """
        SELECT 
            'UOW' as university,
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
            print("No data found in the database to export.")
            return

        # Write to CSV
        with open(CSV_PATH, 'w', newline='', encoding='utf-8') as f:
            writer = csv.writer(f)
            writer.writerow([
                "university", "code", "name", "year", 
                "sequence", "outcome", "category", "bloom_level"
            ])
            
            for row in rows:
                writer.writerow([
                    row['university'], row['code'], row['name'], row['year'],
                    row['sequence'], row['outcome'], row['category'], row['bloom_level']
                ])

        print(f"Successfully exported {len(rows)} rows to {CSV_PATH}")

    except Exception as e:
        print(f"Export failed: {e}")
    finally:
        conn.close()

if __name__ == "__main__":
    export()