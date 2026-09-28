import os
import time
from playwright.sync_api import sync_playwright

def capture():
    with sync_playwright() as p:
        browser = p.chromium.launch(
            executable_path="C:\\Program Files\\Google\\Chrome\\Application\\chrome.exe",
            headless=True,
        )
        page = browser.new_page(viewport={"width": 1280, "height": 850})
        page.goto("http://localhost:8501")
        page.wait_for_timeout(3000)

        # 1. Main Workspace Screenshot
        page.screenshot(path="slide_screenshot_main.png")
        print("Captured: slide_screenshot_main.png")

        # 2. Upload sample document
        sample_path = os.path.abspath("data/sample_meeting_minutes.docx")
        file_input = page.locator('input[type="file"]')
        if file_input.count() > 0:
            file_input.set_input_files(sample_path)
            print("File uploaded, waiting 4s for indexing...")
            page.wait_for_timeout(4000)
            page.screenshot(path="slide_screenshot_indexed.png")
            print("Captured: slide_screenshot_indexed.png")

        # 3. Click Extract Tasks button
        extract_button = page.get_by_role("button", name="Extract Tasks")
        if extract_button.count() > 0:
            print("Clicking Extract Tasks...")
            extract_button.click()
            # Wait for Ollama/Gemini to finish extraction
            page.wait_for_timeout(25000)
            page.screenshot(path="slide_screenshot_results.png")
            print("Captured: slide_screenshot_results.png")

        browser.close()

if __name__ == "__main__":
    capture()
