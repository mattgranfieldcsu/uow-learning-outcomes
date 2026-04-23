import asyncio
import random
import sys
from playwright.async_api import async_playwright, Page
from datetime import datetime

# ─── CONFIGURATION ──────────────────────────────────────────────────────────
BASE_URL = "https://courses.uow.edu.au/search"
YEAR = "2026"

async def scrape_subject(page: Page, code: str):
    """
    Mimics a human user: Goes to search page, types the code, 
    clicks the result, and extracts outcomes.
    """
    print(f"--- Processing {code} ---")
    
    try:
        # 1. Start at the search page to establish a valid session
        await page.goto(BASE_URL, wait_until="load", timeout=60000)
        
        # 2. Find search box and type the code
        search_box = page.get_by_placeholder("Search subjects, courses...")
        await search_box.click()
        await search_box.fill(code)
        await asyncio.sleep(random.uniform(0.5, 1.2)) 
        await page.keyboard.press("Enter")
        
        # 3. Wait for the specific result and click it
        result_link = page.locator(f"a:has-text('{code}')").first
        await result_link.wait_for(state="visible", timeout=15000)
        await result_link.click()
        
        # 4. Wait for the subject detail page to load
        await page.wait_for_load_state("networkidle")
        
        # 5. Extraction Logic
        subject_name = await page.locator("h1").inner_text()
        subject_name = subject_name.replace(code, "").strip("- ").strip()
        
        outcomes = []
        lo_section = page.locator("section", has_text="Learning Outcomes")
        lo_items = lo_section.locator("li")
        
        count = await lo_items.count()
        if count == 0:
            lo_items = page.locator("h3:has-text('Learning Outcomes') + div li")
            count = await lo_items.count()

        for i in range(count):
            text = await lo_items.nth(i).inner_text()
            if text.strip():
                outcomes.append({
                    "sequence": i + 1,
                    "outcome": text.strip()
                })
        
        print(f"Found: {subject_name} ({len(outcomes)} outcomes)")
        
        return {
            "university_id": "UOW",
            "code": code,
            "name": subject_name,
            "year": YEAR,
            "learning_outcomes": outcomes
        }

    except Exception as e:
        print(f"Error scraping {code}: {str(e)[:100]}...")
        return None

async def run_scraper(limit=20):
    # For the pilot, we'll use a hardcoded list or you can point this to a file
    codes = ["ACCY111", "ACCY112", "ACCY200", "ACCY201", "ACCY202", "ACCY301", "ARTV101"] 
    codes = codes[:limit]

    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()
        
        results = []
        for code in codes:
            result = await scrape_subject(page, code)
            if result:
                results.append(result)
            await asyncio.sleep(random.uniform(2, 4))
            
        await browser.close()
        # In a real setup, here you would call your db_loader to save results
        print(f"Scrape complete. Total subjects processed: {len(results)}")
        return results

if __name__ == "__main__":
    # Handle the --limit argument from GitHub Actions
    limit_val = 20
    if "--limit" in sys.argv:
        idx = sys.argv.index("--limit")
        if idx + 1 < len(sys.argv):
            limit_val = int(sys.argv[idx + 1])
    
    asyncio.run(run_scraper(limit=limit_val))