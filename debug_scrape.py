import asyncio
from playwright.async_api import async_playwright

async def test():
    subject_code = "ACCY111"
    # We start at the HANDBOOK home instead of the subject page
    home_url = "https://courses.uow.edu.au/search"
    
    print(f"--- HUMAN FLOW DIAGNOSTIC START ---")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=False)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36"
        )
        page = await context.new_page()

        print(f"1. Loading search page: {home_url}")
        await page.goto(home_url, wait_until="load")
        
        print(f"2. Searching for {subject_code}...")
        # Type the subject into the search box
        await page.get_by_placeholder("Search subjects, courses...").fill(subject_code)
        await page.keyboard.press("Enter")
        
        print("3. Waiting for results...")
        await page.wait_for_timeout(3000) # Give it 3 seconds to think

        # Try to find the link for the subject and click it
        try:
            link_selector = f"text={subject_code}"
            print(f"4. Attempting to click result for {subject_code}...")
            await page.click(link_selector)
            
            print("5. Waiting for subject page to load...")
            await page.wait_for_load_state("networkidle")
            
            print(f"\nFinal URL after click: {page.url}")
            print(f"Page Title: '{await page.title()}'")
            
            content = await page.content()
            if "Learning Outcomes" in content:
                print("✅ SUCCESS: The 'Learning Outcomes' are visible!")
            else:
                print("❌ FAIL: Still no outcomes. Check the browser window.")

        except Exception as e:
            print(f"\nCould not find or click the result: {e}")

        print(f"\n--- DIAGNOSTIC COMPLETE ---")
        input("Check the browser. Did it load the subject properly?\nPress ENTER to close...")
        await browser.close()

if __name__ == "__main__":
    asyncio.run(test())