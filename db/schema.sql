-- UOW Learning Outcomes Database Schema
-- Compatible with SQLite 3.35+

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

-- ── Universities ─────────────────────────────────────────────────────────────
-- Pre-populated; add more rows as you expand beyond UOW.

CREATE TABLE IF NOT EXISTS universities (
    id          TEXT PRIMARY KEY,   -- e.g. "UOW", "USyd", "ANU"
    name        TEXT NOT NULL,
    state       TEXT,
    base_url    TEXT,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

INSERT OR IGNORE INTO universities (id, name, state, base_url) VALUES
    ('UOW', 'University of Wollongong', 'NSW', 'https://courses.uow.edu.au');


-- ── Subjects ──────────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS subjects (
    id              TEXT PRIMARY KEY,           -- "{uni}-{code}-{year}" e.g. "UOW-CRWR101-2026"
    university_id   TEXT NOT NULL REFERENCES universities(id),
    code            TEXT NOT NULL,              -- "CRWR101"
    name            TEXT NOT NULL,
    year            INTEGER NOT NULL,
    faculty         TEXT,
    school          TEXT,
    credit_points   INTEGER,
    description     TEXT,
    prerequisites   TEXT,
    url             TEXT,
    scraped_at      DATETIME DEFAULT CURRENT_TIMESTAMP,
    UNIQUE(university_id, code, year)
);

CREATE INDEX IF NOT EXISTS idx_subjects_code       ON subjects(code);
CREATE INDEX IF NOT EXISTS idx_subjects_faculty     ON subjects(faculty);
CREATE INDEX IF NOT EXISTS idx_subjects_university  ON subjects(university_id);
CREATE INDEX IF NOT EXISTS idx_subjects_year        ON subjects(year);


-- ── Learning Outcomes ─────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS learning_outcomes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    sequence    INTEGER NOT NULL,       -- order within the subject (1-based)
    outcome     TEXT NOT NULL,
    -- Auto-categorisation (populated by tagger.py)
    category    TEXT,                   -- "knowledge" | "skill" | "application" | "value" | "other"
    bloom_level TEXT                    -- "remember" | "understand" | "apply" | "analyse" | "evaluate" | "create"
);

CREATE INDEX IF NOT EXISTS idx_lo_subject  ON learning_outcomes(subject_id);
CREATE INDEX IF NOT EXISTS idx_lo_category ON learning_outcomes(category);

-- Full-text search on outcome text
CREATE VIRTUAL TABLE IF NOT EXISTS lo_fts USING fts5(
    outcome,
    subject_id UNINDEXED,
    content='learning_outcomes',
    content_rowid='id'
);

-- Keep FTS index in sync
CREATE TRIGGER IF NOT EXISTS lo_ai AFTER INSERT ON learning_outcomes BEGIN
    INSERT INTO lo_fts(rowid, outcome, subject_id)
    VALUES (new.id, new.outcome, new.subject_id);
END;

CREATE TRIGGER IF NOT EXISTS lo_ad AFTER DELETE ON learning_outcomes BEGIN
    INSERT INTO lo_fts(lo_fts, rowid, outcome, subject_id)
    VALUES ('delete', old.id, old.outcome, old.subject_id);
END;

CREATE TRIGGER IF NOT EXISTS lo_au AFTER UPDATE ON learning_outcomes BEGIN
    INSERT INTO lo_fts(lo_fts, rowid, outcome, subject_id)
    VALUES ('delete', old.id, old.outcome, old.subject_id);
    INSERT INTO lo_fts(rowid, outcome, subject_id)
    VALUES (new.id, new.outcome, new.subject_id);
END;


-- ── Assessments ───────────────────────────────────────────────────────────────

CREATE TABLE IF NOT EXISTS assessments (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    subject_id  TEXT NOT NULL REFERENCES subjects(id) ON DELETE CASCADE,
    type        TEXT,                   -- "essay" | "exam" | "presentation" | "project" | ...
    name        TEXT,
    weight      INTEGER,                -- percentage (0-100)
    description TEXT
);

CREATE INDEX IF NOT EXISTS idx_assessments_subject ON assessments(subject_id);
CREATE INDEX IF NOT EXISTS idx_assessments_type    ON assessments(type);


-- ── Scrape log ────────────────────────────────────────────────────────────────
-- Tracks every scrape run so you know what's fresh.

CREATE TABLE IF NOT EXISTS scrape_log (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    university_id   TEXT,
    year            INTEGER,
    started_at      DATETIME,
    finished_at     DATETIME,
    subjects_ok     INTEGER DEFAULT 0,
    subjects_failed INTEGER DEFAULT 0,
    notes           TEXT
);
