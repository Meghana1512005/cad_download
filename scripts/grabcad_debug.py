import os, time
EMAIL = os.environ.get("GRABCAD_EMAIL", "smeghanareddy05@gmail.com")
PASS  = os.environ.get("GRABCAD_PASS", "")

from playwright.sync_api import sync_playwright
with sync_playwright() as p:
    browser = p.chromium.launch(headless=True, args=[
        "--no-sandbox", "--disable-blink-features=AutomationControlled",
        "--disable-infobars", "--disable-dev-shm-usage"])
    ctx = browser.new_context(
        user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120.0.0.0 Safari/537.36",
        viewport={"width":1280,"height":720},
        java_script_enabled=True)
    page = ctx.new_page()
    page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")

    page.goto("https://grabcad.com/login", wait_until="networkidle", timeout=30000)
    time.sleep(3)

    # Screenshot to see what the page looks like
    page.screenshot(path="/tmp/grabcad_login.png", full_page=True)
    print("Screenshot saved")

    # Print visible text to understand what's on page
    content = page.content()
    # Check for CAPTCHA
    has_recaptcha = "recaptcha" in content.lower() or "captcha" in content.lower()
    has_hcaptcha  = "hcaptcha" in content.lower()
    print(f"reCAPTCHA detected: {has_recaptcha}")
    print(f"hCaptcha detected: {has_hcaptcha}")

    # Show input fields found
    inputs = page.query_selector_all("input")
    print(f"Input fields found: {len(inputs)}")
    for inp in inputs:
        t = inp.get_attribute("type") or ""
        n = inp.get_attribute("name") or ""
        p_text = inp.get_attribute("placeholder") or ""
        print(f"  input type={t} name={n} placeholder={p_text}")

    browser.close()
