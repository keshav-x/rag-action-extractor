import os
import time
from playwright.sync_api import sync_playwright

def dismiss_prompts(page):
    try:
        page.evaluate("""() => {
            document.querySelectorAll('[data-testid="stToast"], [data-testid="stNotification"], [data-testid="stFloatingContainer"], [data-testid="stToolbar"]').forEach(el => el.remove());
            const banners = Array.from(document.querySelectorAll('div')).filter(d => d.innerText && d.innerText.includes('Help agents write better apps'));
            banners.forEach(b => b.remove());
        }""")
    except Exception:
        pass

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 850})
        page.goto("http://localhost:8501")
        print("Waiting for page load...")
        page.wait_for_selector('h1', timeout=20000)
        page.wait_for_timeout(2000)
        dismiss_prompts(page)
        page.wait_for_timeout(500)

        # 1. Main Workspace Screenshot
        dismiss_prompts(page)
        page.screenshot(path="slide_screenshot_main.png")
        print("Captured: slide_screenshot_main.png")

        # 2. Upload sample document if not already loaded
        sample_path = os.path.abspath("data/sample.pdf")
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            file_input.set_input_files(sample_path)
            print("File uploaded, waiting 4s for indexing...")
            page.wait_for_timeout(4000)
            dismiss_prompts(page)
            page.screenshot(path="slide_screenshot_indexed.png")
            print("Captured: slide_screenshot_indexed.png")

        # 3. Click Extract Tasks button
        extract_button = page.get_by_role("button", name="Extract Tasks")
        if extract_button.count() > 0:
            print("Clicking Extract Tasks...")
            extract_button.click()
            # Wait for Ollama extraction (around 8-10 seconds)
            print("Waiting for extraction results...")
            page.wait_for_selector('.task-card', timeout=30000)
            page.wait_for_timeout(1000)
            dismiss_prompts(page)
            page.screenshot(path="slide_screenshot_results.png")
            print("Captured: slide_screenshot_results.png")

        browser.close()

if __name__ == "__main__":
    capture()
