"""
UOW Learning Outcomes Scraper
Fetches all subjects from the UOW CourseLoop handbook and extracts
learning outcomes, assessments, and subject metadata.

Run from the project root:
    python scraper/uow_scraper.py

Requirements: playwright, tqdm
    pip install playwright tqdm
    playwright install chromium
"""

import json
import time
import random
import logging
import argparse
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
DELAY_MIN  = 2.0   # seconds between requests (be polite)
DELAY_MAX  = 4.5
TIMEOUT    = 30_000  # ms

RAW_DIR    = Path("data/raw")
RAW_DIR.mkdir(parents=True, exist_ok=True)


# ── Step 1: Discover all subject codes ───────────────────────────────────────

def get_all_subject_codes(page: Page) -> list[dict]:
    """
    Navigate to the UOW subject search and extract every subject code + name.
    CourseLoop loads results as React state; we intercept the underlying API.
    """
    subject_list = []
    api_responses = {}

    def handle_response(response: Response):
        url = response.url
        # CourseLoop uses a search endpoint that returns paginated JSON
        if "courseapi" in url and ("search" in url or "subject" in url):
            try:
                data = response.json()
                api_responses[url] = data
            except Exception:
                pass

    page.on("response", handle_response)

    log.info("Loading subject search page…")
    page.goto(
        f"{BASE_URL}/search?ct=subject&year={YEAR}",
        wait_until="networkidle",
        timeout=TIMEOUT,
    )
    time.sleep(3)

    # Try to extract from intercepted API responses first
    for url, data in api_responses.items():
        log.info(f"API response captured: {url}")
        subjects = _parse_search_response(data)
        if subjects:
            subject_list.extend(subjects)

    # Fallback: extract subject links directly from the rendered DOM
    if not subject_list:
        log.info("No API capture — extracting from DOM…")
        subject_list = _extract_subjects_from_dom(page)

    log.info(f"Discovered {len(subject_list)} subjects")
    return subject_list


def _parse_search_response(data: dict | list) -> list[dict]:
    """Parse the CourseLoop search API JSON into a flat list."""
    subjects = []

    if isinstance(data, list):
        items = data
    elif isinstance(data, dict):
        # Common CourseLoop shapes
        items = (
            data.get("items")
            or data.get("results")
            or data.get("data")
            or data.get("subjects")
            or []
        )

    for item in items:
        code = item.get("code") or item.get("subjectCode") or item.get("id")
        name = item.get("name") or item.get("title") or item.get("subjectName")
        if code and name:
            subjects.append({"code": code.strip(), "name": name.strip()})

    return subjects


def _extract_subjects_from_dom(page: Page) -> list[dict]:
    """
    Last-resort DOM scrape.
    Loads all results by scrolling, then pulls anchor tags.
    """
    subjects = []

    # Scroll to trigger lazy loading
    for _ in range(10):
        page.keyboard.press("End")
        time.sleep(0.5)

    anchors = page.query_selector_all('a[href*="/subject/"]')
    for a in anchors:
        href = a.get_attribute("href") or ""
        # URL shape: /subject/2026/CRWR101
        parts = href.rstrip("/").split("/")
        if len(parts) >= 2:
            code = parts[-1]
            name = (a.inner_text() or "").strip()
            if code and name:
                subjects.append({"code": code, "name": name})

    return subjects


# ── Step 2: Scrape individual subject pages ───────────────────────────────────

def scrape_subject(page: Page, code: str, year: int = YEAR) -> Optional[dict]:
    """
    Navigate to a single subject page and return structured data including
    all learning outcomes, assessments, and metadata.
    """
    url  = f"{BASE_URL}/subject/{year}/{code}?year={year}"
    data = None

    captured = {}

    def handle_response(response: Response):
        r_url = response.url
        if "courseapi" in r_url and code.lower() in r_url.lower():
            try:
                captured["json"] = response.json()
            except Exception:
                pass

    page.on("response", handle_response)

    try:
        page.goto(url, wait_until="networkidle", timeout=TIMEOUT)
        time.sleep(1.5)

        # Prefer intercepted JSON (most reliable)
        if captured.get("json"):
            data = _parse_subject_json(captured["json"], code, url)
        else:
            # Fallback: parse the rendered HTML
            data = _parse_subject_dom(page, code, url)

    except Exception as e:
        log.warning(f"Failed to scrape {code}: {e}")

    finally:
        page.remove_listener("response", handle_response)

    return data


def _parse_subject_json(raw: dict, code: str, url: str) -> dict:
    """Parse CourseLoop's internal subject JSON into our schema."""

    # CourseLoop nests data differently across uni deployments
    subject = raw.get("subject") or raw.get("data") or raw

    learning_outcomes = []
    for i, lo in enumerate(
        subject.get("learningOutcomes")
        or subject.get("subjectLearningOutcomes")
        or subject.get("outcomes")
        or [],
        start=1,
    ):
        text = ""
        if isinstance(lo, str):
            text = lo.strip()
        elif isinstance(lo, dict):
            text = (
                lo.get("description")
                or lo.get("text")
                or lo.get("outcome")
                or ""
            ).strip()
        if text:
            learning_outcomes.append({"sequence": i, "outcome": text})

    assessments = []
    for a in (
        subject.get("assessments")
        or subject.get("assessment")
        or []
    ):
        if isinstance(a, dict):
            assessments.append(
                {
                    "type":        a.get("type") or a.get("assessmentType") or "",
                    "name":        a.get("name") or a.get("title") or "",
                    "weight":      a.get("weight") or a.get("percentage") or None,
                    "description": a.get("description") or "",
                }
            )

    return {
        "code":              code,
        "name":              subject.get("name") or subject.get("title") or "",
        "year":              subject.get("year") or YEAR,
        "faculty":           subject.get("faculty") or subject.get("school") or "",
        "credit_points":     subject.get("creditPoints") or subject.get("cp") or 6,
        "description":       (subject.get("description") or subject.get("overview") or "").strip(),
        "prerequisites":     subject.get("prerequisites") or subject.get("preRequisites") or "",
        "url":               url,
        "learning_outcomes": learning_outcomes,
        "assessments":       assessments,
        "raw":               raw,
    }


def _parse_subject_dom(page: Page, code: str, url: str) -> dict:
    """
    Fallback DOM parser when we can't intercept the API.
    Targets CourseLoop's standard HTML structure.
    """
    def text(selector: str) -> str:
        el = page.query_selector(selector)
        return (el.inner_text() or "").strip() if el else ""

    def texts(selector: str) -> list[str]:
        return [
            (el.inner_text() or "").strip()
            for el in page.query_selector_all(selector)
            if (el.inner_text() or "").strip()
        ]

    # Learning outcomes: CourseLoop renders them in a section with a heading
    # then a list. We find the heading and grab the subsequent <li> items.
    lo_texts = texts('[data-testid="learning-outcomes"] li')
    if not lo_texts:
        lo_texts = texts('.learning-outcomes li')
    if not lo_texts:
        # Generic fallback: find heading then adjacent list
        lo_texts = page.evaluate("""() => {
            const headings = [...document.querySelectorAll('h2, h3, h4')];
            const loHeading = headings.find(h =>
                h.textContent.toLowerCase().includes('learning outcome')
            );
            if (!loHeading) return [];
            let el = loHeading.nextElementSibling;
            while (el && el.tagName !== 'UL' && el.tagName !== 'OL') {
                el = el.nextElementSibling;
            }
            if (!el) return [];
            return [...el.querySelectorAll('li')].map(li => li.textContent.trim());
        }""")

    learning_outcomes = [
        {"sequence": i + 1, "outcome": lo}
        for i, lo in enumerate(lo_texts)
        if lo
    ]

    # Assessments
    assessment_rows = page.query_selector_all(
        'table[data-testid="assessment"] tr, .assessment-table tr'
    )
    assessments = []
    for row in assessment_rows[1:]:  # skip header
        cells = [td.inner_text().strip() for td in row.query_selector_all("td")]
        if len(cells) >= 2:
            assessments.append(
                {
                    "type":        cells[0] if len(cells) > 0 else "",
                    "name":        cells[1] if len(cells) > 1 else "",
                    "weight":      cells[2] if len(cells) > 2 else None,
                    "description": cells[3] if len(cells) > 3 else "",
                }
            )

    return {
        "code":              code,
        "name":              text("h1"),
        "year":              YEAR,
        "faculty":           text('[data-testid="faculty"], .faculty-name'),
        "credit_points":     6,  # default; parse if found
        "description":       text('[data-testid="description"], .subject-description'),
        "prerequisites":     text('[data-testid="prerequisites"], .prerequisites'),
        "url":               url,
        "learning_outcomes": learning_outcomes,
        "assessments":       assessments,
        "raw":               {},
    }


# ── Step 3: Persist raw JSON ──────────────────────────────────────────────────

def save_raw(subject: dict):
    """Save raw JSON so we can re-process without re-scraping."""
    path = RAW_DIR / f"{subject['code']}.json"
    path.write_text(json.dumps(subject, indent=2, ensure_ascii=False))


# ── Main orchestration ────────────────────────────────────────────────────────

def run(codes_file: Optional[str] = None, limit: Optional[int] = None):
    """
    Full scrape pipeline.

    Args:
        codes_file: Path to a text file of subject codes (one per line).
                    If omitted, codes are discovered from the search page.
        limit:      Stop after N subjects (useful for testing).
    """
    import sys
    import os
    sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    from tqdm import tqdm
    from db.loader import load_subject  # imported here to avoid circular imports

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-setuid-sandbox"],
        )
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/122.0.0.0 Safari/537.36"
            ),
            viewport={"width": 1440, "height": 900},
            locale="en-AU",
        )
        page = context.new_page()

        # ── Discover subjects ──
        if codes_file:
            raw_codes = Path(codes_file).read_text().splitlines()
            subjects_meta = [
                {"code": c.strip(), "name": ""} for c in raw_codes if c.strip()
            ]
        else:
            subjects_meta = get_all_subject_codes(page)

        # If dynamic discovery found nothing, fall back to seed list
        if not subjects_meta:
            seed_path = Path(__file__).parent.parent / "data" / "seed_codes.txt"
            if seed_path.exists():
                log.info(f"Dynamic discovery found 0 subjects — falling back to seed list")
                raw_codes = seed_path.read_text().splitlines()
                subjects_meta = [
                    {"code": c.strip(), "name": ""} for c in raw_codes if c.strip()
                ]
                log.info(f"Loaded {len(subjects_meta)} codes from seed list")

        if limit:
            subjects_meta = subjects_meta[:limit]

        log.info(f"Scraping {len(subjects_meta)} subjects…")

        ok, failed = 0, []

        for meta in tqdm(subjects_meta, unit="subject"):
            code = meta["code"]

            # Skip if already scraped
            raw_path = RAW_DIR / f"{code}.json"
            if raw_path.exists():
                log.debug(f"Skipping {code} (already have raw data)")
                existing = json.loads(raw_path.read_text())
                load_subject(existing)
                ok += 1
                continue

            subject = scrape_subject(page, code)
            if subject:
                save_raw(subject)
                load_subject(subject)
                ok += 1
            else:
                failed.append(code)

            # Polite delay
            time.sleep(random.uniform(DELAY_MIN, DELAY_MAX))

        browser.close()

    log.info(f"Done. {ok} succeeded, {len(failed)} failed.")
    if failed:
        log.warning(f"Failed codes: {', '.join(failed)}")
        Path("failed_codes.txt").write_text("\n".join(failed))


# ── CLI ───────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="UOW subject scraper")
    parser.add_argument(
        "--codes", help="Path to text file of subject codes (one per line)"
    )
    parser.add_argument(
        "--limit", type=int, help="Only scrape this many subjects (for testing)"
    )
    args = parser.parse_args()
    run(codes_file=args.codes, limit=args.limit)
