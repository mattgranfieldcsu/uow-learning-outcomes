"""
UOW Learning Outcomes Scraper
Fetches all subjects from the UOW CourseLoop handbook and extracts
learning outcomes, assessments, and subject metadata.

Run from the project root:
    python scraper/uow_scraper.py
"""

import json
import time
import random
import logging
import argparse
import subprocess
from pathlib import Path
from datetime import datetime
from typing import Optional

from playwright.sync_api import sync_playwright, Page, Response

# ── Logging ──────────────────────────────────────────────────────────────────

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler("scraper.log"),
        logging.StreamHandler(),
    ],
)
log = logging.getLogger(__name__)

# ── Config ───────────────────────────────────────────────────────────────────

BASE_URL   = "https://courses.uow.edu.au"
YEAR       = 2026
DELAY_MIN  = 2.0   # Be polite to UOW servers
DELAY_MAX  = 4.5
TIMEOUT    = 30_000

RAW_DIR    = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)

# ── Step 1: Discover all subject codes ───────────────────────────────────────

def get_all_subject_codes(page: Page) -> list[dict]:
    """Intercept CourseLoop API or fallback to DOM scrape."""
    subject_list = []
    api_responses = {}

    def handle_response(response: Response):
        url = response.url
        if "courseapi" in url and ("search" in url or "subject" in url):
            try:
                data = response.json()
                api_responses[url] = data
            except Exception:
                pass

    page.on("response", handle_response)

    log.info("Loading UOW subject search page...")
    page.goto(
        f"{BASE_URL}/search?ct=subject&year={YEAR}",
        wait_until="networkidle",
        timeout=TIMEOUT,
    )
    time.sleep(3)

    for url, data in api_responses.items():
        subjects = _parse_search_response(data)
        if subjects:
            subject_list.extend(subjects)

    if not subject_list:
        log.info("No API capture — extracting from DOM...")
        subject_list = _extract_subjects_from_dom(page)

    return subject_list

def _parse_search_response(data: dict | list) -> list[dict]:
    subjects = []
    items = []
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        items = data.get("items") or data.get("results") or data.get("data") or []

    for item in items:
        code = item.get("code") or item.get("subjectCode")
        name = item.get("name") or item.get("title")
        if code and name:
            subjects.append({"code": code.strip(), "name": name.strip()})
    return subjects

def _extract_subjects_from_dom(page: Page) -> list[dict]:
    subjects = []
    for _ in range(5):
        page.keyboard.press("End")
        time.sleep(0.5)

    anchors = page.query_selector_all('a[href*="/subject/"]')
    for a in anchors:
        href = a.get_attribute("href") or ""
        parts = href.rstrip("/").split("/")
        if len(parts) >= 2:
            code = parts[-1]
            name = (a.inner_text() or "").strip()
            if code and name:
                subjects.append({"code": code, "name": name})
    return subjects

# ── Step 2: Scrape individual subject pages ───────────────────────────────────

def scrape_subject(page: Page, code: str, year: int = YEAR) -> Optional[dict]:
    url  = f"{BASE_URL}/subject/{year}/{code}?year={year}"
    captured = {}

    def handle_response(response: Response):
        if "courseapi" in response.url and code.lower() in response.url.lower():
            try:
                captured["json"] = response.json()
            except Exception:
                pass

    page.on("response", handle_response)

    try:
        page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
        time.sleep(1.5)
        return _parse_subject_json(captured["json"], code, url) if captured.get("json") else _parse_subject_dom(page, code, url)
    except Exception as e:
        log.warning(f"Failed to scrape {code}: {e}")
        return None
    finally:
        page.remove_listener("response", handle_response)

def _parse_subject_json(raw: dict, code: str, url: str) -> dict:
    subject = raw.get("subject") or raw.get("data") or raw
    lo_source = subject.get("learningOutcomes") or subject.get("outcomes") or []
    
    learning_outcomes = []
    for i, lo in enumerate(lo_source, start=1):
        text = lo if isinstance(lo, str) else lo.get("description", "")
        if text:
            learning_outcomes.append({"sequence": i, "outcome": text.strip()})

    return {
        "code": code,
        "name": subject.get("name") or subject.get("title") or "",
        "year": YEAR,
        "description": (subject.get("description") or "").strip(),
        "url": url,
        "learning_outcomes": learning_outcomes,
        "raw": raw
    }

def _parse_subject_dom(page: Page, code: str, url: str) -> dict:
    # Basic fallback if API intercept fails
    return {
        "code": code,
        "name": (page.query_selector("h1").inner_text() if page.query_selector("h1") else ""),
        "year": YEAR,
        "url": url,
        "learning_outcomes": [],
        "note": "DOM Fallback used"
    }

# ── Main ──────────────────────────────────────────────────────────────────────

def run(limit: Optional[int] = None):
    # Auto-pull to stay in sync with GitHub Actions
    try:
        log.info("Syncing with remote repository...")
        subprocess.run(["git", "pull", "--rebase"], check=False)
    except Exception as e:
        log.warning(f"Sync failed: {e}")

    from tqdm import tqdm
    from db.loader import load_subject 

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(user_agent="Mozilla/5.0", viewport={"width": 1440, "height": 900})
        page = context.new_page()

        subjects_meta = get_all_subject_codes(page)

        # Fallback to seed list if discovery fails
        if not subjects_meta:
            seed_path = Path("data/seed_codes.txt")
            if seed_path.exists():
                log.info("Using seed_codes.txt fallback")
                subjects_meta = [{"code": c.strip()} for c in seed_path.read_text().splitlines() if c.strip()]

        if limit:
            subjects_meta = subjects_meta[:limit]

        for meta in tqdm(subjects_meta, unit="subject"):
            code = meta["code"]
            raw_path = RAW_DIR / f"{code}.json"
            
            if raw_path.exists():
                load_subject(json.loads(raw_path.read_text()))
                continue

            subject = scrape_subject(page, code)
            if subject:
                raw_path.write_text(json.dumps(subject, indent=2))
                load_subject(subject)
            
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        browser.close()

if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--limit", type=int)
    args = parser.parse_args()
    run(limit=args.limit)