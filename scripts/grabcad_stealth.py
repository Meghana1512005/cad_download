"""
GrabCAD via playwright-stealth: login + intercept API + search + download.
"""
import os, time, json, re, requests

EMAIL      = os.environ.get("GRABCAD_EMAIL",   "smeghanareddy05@gmail.com")
PASS       = os.environ.get("GRABCAD_PASS",    "")
GC_SESSION = os.environ.get("GRABCAD_SESSION", "")
GC_XSRF    = os.environ.get("GRABCAD_XSRF",   "")

def get_session_and_api():
    """Login via Playwright, intercept network calls to find search API endpoint."""
    from playwright.sync_api import sync_playwright
    try:
        from playwright_stealth import stealth_sync
        HAS_STEALTH = True
    except ImportError:
        HAS_STEALTH = False
        print("Note: install playwright-stealth for better bot bypass")

    captured_requests = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=[
            "--no-sandbox","--disable-setuid-sandbox",
            "--disable-blink-features=AutomationControlled"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width":1280,"height":720})
        page = ctx.new_page()
        page.add_init_script("Object.defineProperty(navigator,'webdriver',{get:()=>undefined})")
        if HAS_STEALTH: stealth_sync(page)

        # Intercept all API requests during search
        def on_request(req):
            url = req.url
            if "grabcad.com" in url and any(x in url for x in
                    ["/api/","/library","/search","/models","/community"]):
                captured_requests.append({"url": url, "method": req.method,
                                          "headers": dict(req.headers)})

        page.on("request", on_request)

        # ── Step 1: Login ─────────────────────────────────────────────────────
        print("Logging in...")
        page.goto("https://grabcad.com/login", wait_until="domcontentloaded", timeout=30000)
        time.sleep(2)
        try:
            page.fill('input[type="email"], input[name="user[login]"]', EMAIL, timeout=5000)
            page.fill('input[type="password"]', PASS, timeout=5000)
            page.click('button[type="submit"], input[type="submit"]', timeout=5000)
            time.sleep(4)
            page.wait_for_load_state("networkidle", timeout=15000)
        except Exception as e:
            print(f"Login form error: {e}")

        url = page.url
        logged_in = "login" not in url and "dashboard" in url or "grabcad.com/" == url[-len("grabcad.com/"):]
        print(f"URL: {url} | Logged in: {logged_in}")

        # ── Step 2: Navigate to library search & capture API calls ───────────
        if logged_in or "login" not in url:
            print("\nNavigating to search page...")
            captured_requests.clear()
            page.goto("https://grabcad.com/library?query=F-16+fighter&sort=relevance",
                      wait_until="networkidle", timeout=30000)
            time.sleep(3)

            print(f"\nCaptured {len(captured_requests)} API calls:")
            for req in captured_requests[:20]:
                print(f"  {req['method']} {req['url'][:100]}")

            # Try to get search results from page
            try:
                # Look for JSON data in page scripts
                content = page.content()
                json_blocks = re.findall(r'"models"\s*:\s*(\[.*?\])', content[:50000], re.S)
                if json_blocks:
                    print(f"\nFound models JSON in page ({len(json_blocks)} blocks)")
                    models = json.loads(json_blocks[0])[:5]
                    for m in models:
                        if isinstance(m, dict):
                            print(f"  [{m.get('slug','')}] {m.get('name','')}")
            except Exception as e:
                print(f"Page parse error: {e}")

        # ── Step 3: Get cookies ───────────────────────────────────────────────
        cookies = ctx.cookies()
        browser.close()

    # Build session
    s = requests.Session()
    s.headers.update({"User-Agent":"Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120"})
    for c in cookies:
        s.cookies.set(c["name"], c["value"], domain=c.get("domain","").lstrip("."))

    # Extract XSRF token from cookies for header
    xsrf = next((c["value"] for c in cookies if c["name"] == "XSRF-TOKEN"), "")
    if xsrf:
        s.headers["X-XSRF-TOKEN"] = requests.utils.unquote(xsrf)

    return s, logged_in, captured_requests

def find_search_endpoint(session, captured):
    """Try all captured API endpoints to find one that returns model data."""
    # First try captured endpoints
    for req in captured:
        url = req["url"]
        if "search" in url or "library" in url or "model" in url:
            try:
                r = session.get(url, timeout=10,
                                headers={"Accept":"application/json"})
                if r.status_code == 200:
                    data = r.json()
                    if data and (isinstance(data, list) or "model" in str(data).lower()):
                        print(f"✓ Working endpoint: {url[:80]}")
                        return url
            except: pass

    # Try known endpoint patterns
    endpoints = [
        "https://grabcad.com/community/api/v1/models?query=F-16&sort=relevance&per_page=5",
        "https://grabcad.com/community/api/v2/search?query=F-16&type=models&per_page=5",
        "https://grabcad.com/api/v1/search?q=F-16&per_page=5",
        "https://grabcad.com/api/v2/models?search=F-16&per_page=5",
        "https://grabcad.com/library.json?search=F-16&per_page=5",
        "https://grabcad.com/api/v1/models?q=F-16&per_page=5",
        "https://grabcad.com/api/v3/models?search=F-16&per_page=5",
    ]
    for url in endpoints:
        try:
            r = session.get(url, timeout=10, headers={"Accept":"application/json"})
            print(f"  {url.split('grabcad.com')[1][:50]:50} → {r.status_code}: {r.text[:60]}")
            if r.status_code == 200:
                try:
                    data = r.json()
                    if data:
                        print(f"  ✓ WORKS: {url}")
                        return url
                except: pass
        except Exception as e:
            print(f"  Error: {e}")
    return None

if __name__ == "__main__":
    session, logged_in, captured = get_session_and_api()
    print(f"\nLogged in: {logged_in}")
    print("\n=== Finding working search endpoint ===")
    endpoint = find_search_endpoint(session, captured)
    if endpoint:
        print(f"\n✓ Use this endpoint: {endpoint}")
    else:
        print("\n✗ No working JSON search endpoint found")
        print("Will need to scrape HTML search results instead")
