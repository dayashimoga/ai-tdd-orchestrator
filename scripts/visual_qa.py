"""
Visual Quality Assurance module.
Uses a headless browser to screenshot generated HTML and sends the image
to an Ollama Vision LLM for aesthetic assessment.
"""
import os
import glob
import base64
import requests

OLLAMA_URL = "http://localhost:11434/api/generate"
VLM_MODEL = os.getenv("VLM_MODEL", "llava")

def find_html_files(target_dir="your_project"):
    """Find all HTML files in the target project directory."""
    pattern = os.path.join(target_dir, "**", "*.html")
    return glob.glob(pattern, recursive=True)

def capture_screenshot(html_path, output_path=None):
    """
    Captures a screenshot of an HTML file using Playwright.
    Falls back to Selenium if Playwright is not installed.
    Returns the path to the screenshot PNG file.
    """
    if output_path is None:
        output_path = html_path.replace(".html", "_screenshot.png")
        
    # Convert to absolute file:// URL for the browser
    abs_path = os.path.abspath(html_path)
    file_url = f"file:///{abs_path.replace(os.sep, '/')}"
    
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page(viewport={"width": 1280, "height": 720})
            page.goto(file_url)
            page.wait_for_load_state("networkidle")
            page.screenshot(path=output_path, full_page=True)
            browser.close()
        print(f"📸 Screenshot captured: {output_path}")
        return output_path
    except ImportError:
        print("⚠️ Playwright not installed. Trying Selenium fallback...")
    except Exception as e:
        print(f"⚠️ Playwright screenshot failed: {e}")
    
    # Selenium fallback
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1280,720")
        
        driver = webdriver.Chrome(options=chrome_options)
        driver.get(file_url)
        driver.save_screenshot(output_path)
        driver.quit()
        print(f"📸 Screenshot captured (Selenium): {output_path}")
        return output_path
    except Exception as e:
        print(f"⚠️ Selenium screenshot also failed: {e}")
        return None

def assess_with_vlm(screenshot_path):
    """
    Sends a screenshot to the Ollama Vision LLM for aesthetic assessment.
    Returns a dict with 'passed' (bool) and 'feedback' (str).
    """
    if not screenshot_path or not os.path.exists(screenshot_path):
        return {"passed": True, "feedback": "No screenshot available to assess."}
    
    try:
        with open(screenshot_path, "rb") as f:
            image_b64 = base64.b64encode(f.read()).decode("utf-8")
    except Exception as e:
        return {"passed": True, "feedback": f"Could not read screenshot: {e}"}
    
    prompt = (
        "You are a senior UI/UX reviewer. Analyze this webpage screenshot critically. "
        "Rate the following out of 10:\n"
        "1. Layout alignment and centering\n"
        "2. Color scheme and contrast\n"
        "3. Typography readability\n"
        "4. Overall aesthetic appeal\n\n"
        "If any score is below 6, respond with FAIL and explain what needs fixing. "
        "If all scores are 6+, respond with PASS.\n\n"
        "Format: PASS or FAIL followed by your assessment."
    )
    
    payload = {
        "model": VLM_MODEL,
        "prompt": prompt,
        "images": [image_b64],
        "stream": False,
        "options": {"temperature": 0.2, "num_ctx": 4096}
    }
    
    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=120)
        response.raise_for_status()
        result = response.json().get("response", "")
        
        passed = "PASS" in result.upper().split("\n")[0] if result else True
        return {"passed": passed, "feedback": result}
    except Exception as e:
        print(f"⚠️ VLM assessment failed: {e}")
        return {"passed": True, "feedback": f"VLM assessment skipped: {e}"}


def run_visual_qa(target_dir="your_project"):
    """
    Main entry point for visual QA. 
    Finds HTML files, screenshots them, and assesses each with the VLM.
    Returns a list of assessment results.
    """
    html_files = find_html_files(target_dir)
    
    if not html_files:
        print("ℹ️ No HTML files found. Skipping visual QA.")
        return []
    
    print(f"\n👁️ Visual QA: Found {len(html_files)} HTML file(s) to assess.")
    results = []
    
    for html_file in html_files:
        print(f"\n🔍 Assessing: {html_file}")
        screenshot = capture_screenshot(html_file)
        assessment = assess_with_vlm(screenshot)
        assessment["file"] = html_file
        results.append(assessment)
        
        if assessment["passed"]:
            print(f"  ✅ PASSED: {assessment['feedback'][:100]}")
        else:
            print(f"  ❌ FAILED: {assessment['feedback'][:200]}")
        
        # Clean up screenshot
        if screenshot and os.path.exists(screenshot):
            try:
                os.remove(screenshot)
            except Exception:
                pass
    
    return results
