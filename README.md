# Learning Outcomes Explorer

Extracts learning outcomes, stores them in SQLite, and serves a searchable web dashboard.

```
uow-learning-outcomes/
├── scraper/
│   └── uow_scraper.py      # Playwright scraper
├── db/
│   ├── schema.sql           # SQLite schema (subjects, outcomes, assessments)
│   ├── loader.py            # Upserts scraped data into the DB
│   └── tagger.py            # Claude API: classifies outcomes by Bloom's taxonomy
├── dashboard/
│   ├── server.py            # Flask API + static server
│   └── index.html           # Browser search UI
├── query.py                 # CLI tool (search, stats, export, raw SQL)
├── requirements.txt
└── .github/workflows/
    └── scrape.yml           # Weekly automated scrape via GitHub Actions
```

---

## Local Setup

### 1. Clone the repo

```bash
git clone https://github.com/YOUR_USERNAME/uow-learning-outcomes.git
cd uow-learning-outcomes
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Initialise the database

```bash
python -m db.loader
# Creates data/outcomes.db with the schema
```

### 4. Run a test scrape (20 subjects)

```bash
python scraper/uow_scraper.py --limit 20
```

This will:
- Open a headless Chromium browser
- Discover subject codes from the UOW handbook search page
- Scrape each subject page for metadata and learning outcomes
- Save raw JSON to `data/raw/` and load into `data/outcomes.db`

A full scrape (~2,000 subjects) takes about 2 hours. Run overnight:

```bash
python scraper/uow_scraper.py
```

The scraper is **resumable** — it skips subjects already in `data/raw/`, so you can safely interrupt and restart.

### 5. (Optional) Tag outcomes with Bloom's taxonomy

Requires an Anthropic API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
python -m db.tagger
```

This sends outcomes to Claude in batches and classifies each one by:
- **Category**: knowledge / skill / application / value
- **Bloom's level**: remember / understand / apply / analyse / evaluate / create

### 6. Launch the dashboard

```bash
python dashboard/server.py
# Open http://localhost:5000
```

### 7. Use the CLI

```bash
# Full-text search
python query.py search "critical thinking"
python query.py search "design" --limit 50

# View a subject
python query.py subject CRWR101

# Database statistics
python query.py stats

# Export to CSV
python query.py export --format csv --out outcomes.csv

# Raw SQL
python query.py sql "SELECT faculty, COUNT(*) n FROM subjects GROUP BY faculty ORDER BY n DESC"
```

---

## GitHub Actions (automated weekly scrape)

The workflow in `.github/workflows/scrape.yml` runs every Sunday at 2am AEST and:

1. Scrapes any new/changed subjects
2. Tags outcomes with Bloom's taxonomy
3. Exports a CSV/JSONL snapshot
4. Commits the snapshot back to the repo
5. Uploads the database as a build artifact (kept 90 days)

### Setup steps

**1. Push this repo to GitHub:**
```bash
git init
git add .
git commit -m "initial commit"
git remote add origin https://github.com/YOUR_USERNAME/uow-learning-outcomes.git
git push -u origin main
```

**2. Add your Anthropic API key as a GitHub secret:**

Go to **Settings → Secrets and variables → Actions → New repository secret**

- Name: `ANTHROPIC_API_KEY`
- Value: `sk-ant-...`

**3. Enable Actions:**

Go to **Actions** tab → click "I understand my workflows, go ahead and enable them."

**4. Run manually to test:**

Actions tab → "Scrape UOW Learning Outcomes" → "Run workflow" → set limit to `20`

---

## Database Schema

```sql
subjects (id, university_id, code, name, year, faculty, credit_points,
          description, prerequisites, url, scraped_at)

learning_outcomes (id, subject_id, sequence, outcome, category, bloom_level)

assessments (id, subject_id, type, name, weight, description)

universities (id, name, state, base_url)
```

Full-text search is via SQLite FTS5 on the `outcome` column.

---

## Expanding to other universities

UOW uses **CourseLoop** — so do ACU, CQU, and several others. The scraper's
`_parse_subject_json` and `_parse_subject_dom` methods handle CourseLoop's API
response format. To add another uni:

1. Add a row to the `universities` table
2. Create `scraper/acU_scraper.py` (copy `uow_scraper.py`, change `BASE_URL`)
3. Pass `university_id="ACU"` to `load_subject()`

Unis on different platforms (Sydney uses custom HTML, Melbourne uses a different CMS)
need their own DOM selectors — same Playwright approach, just different CSS paths.

---

## Useful SQL queries

```sql
-- Subjects covering "sustainability"
SELECT s.code, s.name, lo.outcome
FROM learning_outcomes lo JOIN subjects s ON s.id = lo.subject_id
WHERE lo.outcome LIKE '%sustainability%';

-- Bloom's distribution by faculty
SELECT s.faculty, lo.bloom_level, COUNT(*) n
FROM learning_outcomes lo JOIN subjects s ON s.id = lo.subject_id
WHERE lo.bloom_level IS NOT NULL
GROUP BY s.faculty, lo.bloom_level
ORDER BY s.faculty, n DESC;

-- Subjects with the most "create"-level outcomes
SELECT s.code, s.name, COUNT(*) n
FROM learning_outcomes lo JOIN subjects s ON s.id = lo.subject_id
WHERE lo.bloom_level = 'create'
GROUP BY lo.subject_id ORDER BY n DESC LIMIT 20;

-- Average outcomes per subject by faculty
SELECT faculty, ROUND(AVG(c),1) avg_outcomes
FROM (
  SELECT s.faculty, COUNT(*) c
  FROM learning_outcomes lo JOIN subjects s ON s.id = lo.subject_id
  GROUP BY lo.subject_id
)
GROUP BY faculty ORDER BY avg_outcomes DESC;
```
