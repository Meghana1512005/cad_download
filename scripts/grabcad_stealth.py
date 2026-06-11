"""
GrabCAD login using playwright-stealth to bypass bot detection.
Falls back to manual cookie injection if stealth login fails.
"""
import os, time, json, requests

EMAIL = os.environ.get("GRABCAD_EMAIL", "smeghanareddy05@gmail.com")
PASS  = os.environ.get("GRABCAD_PASS",  "")
# Optional: manually provided session cookie from real browser
GC_SESSION = os.environ.get("GRABCAD_SESSION", "")
GC_XSRF    = os.environ.get("GRABCAD_XSRF",    "")

def login_with_stealth():
    """Try stealth Playwright login."""
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import stealth_sync
        stealth_available = True
        print("playwright-stealth: available")
    except ImportError:
        stealth_available = False
        print("playwright-stealth: not installed, trying without")

    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=True,
            args=["--no-sandbox","--disable-setuid-sandbox",
                  "--disable-blink-features=AutomationControlled",
                  "--disable-infobars","--disable-dev-shm-usage",
                  "--window-size=1280,720"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) "
                       "Chrome/120.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":720},
            locale="en-US", timezone_id="America/New_York",
            java_script_enabled=True,
            permissions=["geolocation"])
        page = ctx.new_page()

        # Patch webdriver detection
        page.add_init_script("""
            Object.defineProperty(navigator,'webdriver',{get:()=>undefined});
            Object.defineProperty(navigator,'plugins',{get:()=>[1,2,3,4,5]});
            Object.defineProperty(navigator,'languages',{get:()=>['en-US','en']});
            window.chrome={runtime:{}};
        """)

        if stealth_available:
            stealth_sync(page)
            print("Stealth patches applied")

        print("Loading GrabCAD login page...")
        page.goto("https://grabcad.com/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)

        # Check for CAPTCHA
        content = page.content()
        if "recaptcha" in content.lower():
            print("⚠ reCAPTCHA detected on page!")
        if "hcaptcha" in content.lower():
            print("⚠ hCaptcha detected on page!")

        # Screenshot to see what we're dealing with
        page.screenshot(path="/tmp/grabcad_before_login.png")
        print("Screenshot: /tmp/grabcad_before_login.png")

        # Try to fill and submit
        try:
            page.wait_for_selector('input[type="email"], input[name="user[login]"]', timeout=8000)
            page.fill('input[type="email"], input[name="user[login]"]', EMAIL)
            time.sleep(0.5)
            page.fill('input[type="password"]', PASS)
            time.sleep(0.5)
            page.screenshot(path="/tmp/grabcad_filled.png")
            page.click('button[type="submit"], input[type="submit"]')
            time.sleep(5)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Form fill error: {e}")

        page.screenshot(path="/tmp/grabcad_after_login.png")
        url = page.url
        print(f"URL after submit: {url}")
        logged_in = "login" not in url

        cookies = ctx.cookies()
        browser.close()
        return cookies, logged_in

def build_session(cookies):
    """Build requests session from Playwright cookies."""
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain","").lstrip("."))
    return s

def build_session_from_manual(session_cookie, xsrf_token):
    """Build requests session from manually provided cookies."""
    s = requests.Session()
    s.headers.update({
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
        "X-XSRF-TOKEN": requests.utils.unquote(xsrf_token)
    })
    s.cookies.set("_grabcad_session", session_cookie, domain="grabcad.com")
    s.cookies.set("XSRF-TOKEN", xsrf_token, domain="grabcad.com")
    return s

def test_session(session):
    """Test if session can search GrabCAD."""
    r = session.get("https://grabcad.com/library.json",
        params={"search":"F-16 fighter","per_page":3},
        headers={"Accept":"application/json"}, timeout=15)
    print(f"Search test: HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            data = r.json()
            models = data if isinstance(data, list) else data.get("models", [])
            print(f"✓ Search works! Found {len(models)} models")
            for m in models[:3]:
                print(f"  [{m.get('slug','')}] {m.get('name','')}")
            return True
        except Exception as e:
            print(f"Parse error: {e}: {r.text[:100]}")
    else:
        print(f"Response: {r.text[:100]}")
    return False

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Option A: Try stealth Playwright login
    print("="*50)
    print("Option A: Stealth Playwright login")
    print("="*50)
    cookies, logged_in = login_with_stealth()
    if logged_in:
        print("✓ Stealth login worked!")
        s = build_session(cookies)
        test_session(s)
    else:
        print("✗ Stealth login failed")

        # Option B: Use manually-provided session cookies
        if GC_SESSION and GC_XSRF:
            print("\n" + "="*50)
            print("Option B: Manual session cookies")
            print("="*50)
            s = build_session_from_manual(GC_SESSION, GC_XSRF)
            if test_session(s):
                print("✓ Manual cookies work!")
                # Save working cookies to file for use in search script
                cookie_data = {"_grabcad_session": GC_SESSION, "XSRF-TOKEN": GC_XSRF}
                with open("/tmp/grabcad_cookies.json", "w") as f:
                    json.dump(cookie_data, f)
            else:
                print("✗ Manual cookies also failed")
        else:
            print("\nTo use manual cookies, add GitHub Secrets:")
            print("  GRABCAD_SESSION = value of _grabcad_session cookie from your browser")
            print("  GRABCAD_XSRF    = value of XSRF-TOKEN cookie from your browser")
            print()
            print("How to get these:")
            print("1. Log into grabcad.com in Chrome")
            print("2. Open DevTools (F12) → Application → Cookies → https://grabcad.com")
            print("3. Copy _grabcad_session and XSRF-TOKEN values")
