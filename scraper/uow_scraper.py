import asyncio
import random
import sys
import os
from playwright.async_api import async_playwright, Page
from datetime import datetime

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
BASE_URL = "https://courses.uow.edu.au/search"
YEAR = "2026"

async def scrape_subject(page: Page, code: str):
    print(f"--- Processing {code} ---")
    try:
        # 1. Navigate and wait for the page to be 'settled'
        await page.goto(BASE_URL, wait_until="networkidle", timeout=60000)
        
        # 2. Try multiple ways to find the search box
        # Sometimes the cloud renders the page slightly differently
        search_box = None
        selectors = [
            "input[placeholder*='Search']",
            "input[type='text']",
            "get_by_placeholder('Search subjects, courses...')"
        ]
        
        try:
            # Try the primary placeholder first
            await page.get_by_placeholder("Search subjects, courses...").wait_for(state="visible", timeout=10000)
            search_box = page.get_by_placeholder("Search subjects, courses...")
        except:
            # Fallback to a generic input if placeholder fails
            search_box = page.locator("input").first
            
        await search_box.click()
        await search_box.fill(code)
        await page.keyboard.press("Enter")
        
        # 3. Wait for results
        result_link = page.locator(f"a:has-text('{code}')").first
        await result_link.wait_for(state="visible", timeout=20000)
        await result_link.click()
        
        # 4. Wait for subject page
        await page.wait_for_load_state("networkidle")
        
        # 5. Extract
        subject_name = await page.locator("h1").inner_text()
        subject_name = subject_name.replace(code, "").strip("- ").strip()
        
        outcomes = []
        lo_items = page.locator("section:has-text('Learning Outcomes') li, h3:has-text('Learning Outcomes') + div li")
        
        count = await lo_items.count()
        for i in range(count):
            text = await lo_items.nth(i).inner_text()
            if text.strip():
                outcomes.append({"sequence": i + 1, "outcome": text.strip()})
        
        print(f"Found: {subject_name} ({len(outcomes)} outcomes)")
        return {"university_id": "UOW", "code": code, "name": subject_name, "year": YEAR, "learning_outcomes": outcomes}

    except Exception as e:
        # CRITICAL: Take a screenshot on failure so we can see why it timed out
        if not os.path.exists("data/errors"): os.makedirs("data/errors")
        await page.screenshot(path=f"data/errors/{code}_error.png")
        print(f"Error scraping {code}: {str(e)[:100]}...")
        return None

async def run_scraper(limit=20):
    codes = ["ACCY111", "ACCY112", "ACCY200", "ACCY201", "ACCY202", "ACCY301", "ARTV101"] 
    codes = codes[:limit]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        # Use a very common User Agent to avoid 'Bot' detection
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        for code in codes:
            result = await scrape_subject(page, code)
            if result: results.append(result)
            await asyncio.sleep(random.uniform(3, 6))
            
        await browser.close()
        print(f"Scrape complete. Total subjects processed: {len(results)}")
        return results

if __name__ == "__main__":
    limit_val = 20
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv): limit_val = int(sys.argv[idx + 1])
    asyncio.run(run_scraper(limit=limit_val))