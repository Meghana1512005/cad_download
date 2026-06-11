"""GrabCAD login + search + download via Playwright headless Chrome."""
import os, json, time, re, requests

EMAIL = os.environ.get("GRABCAD_EMAIL", "smeghanareddy05@gmail.com")
PASS  = os.environ.get("GRABCAD_PASS",  "")

def get_grabcad_session():
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True, args=["--no-sandbox"])
        ctx = browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36")
        page = ctx.new_page()

        print("Navigating to GrabCAD login...")
        page.goto("https://grabcad.com/login", wait_until="networkidle", timeout=30000)
        time.sleep(2)

        # Fill email/login field
        for sel in ['input[name="user[login]"]', 'input[type="email"]',
                    '#user_login', 'input[placeholder*="mail" i]',
                    'input[placeholder*="username" i]']:
            try:
                page.fill(sel, EMAIL, timeout=3000)
                print(f"  Filled login with selector: {sel}")
                break
            except: pass

        # Fill password
        for sel in ['input[name="user[password]"]', 'input[type="password"]',
                    '#user_password']:
            try:
                page.fill(sel, PASS, timeout=3000)
                print(f"  Filled password with selector: {sel}")
                break
            except: pass

        # Click submit
        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'button:has-text("Sign in")', 'input[value="Sign in"]']:
            try:
                page.click(sel, timeout=3000)
                print(f"  Clicked submit: {sel}")
                break
            except: pass

        # Wait for navigation
        time.sleep(4)
        page.wait_for_load_state("networkidle", timeout=15000)
        url_after = page.url
        print(f"URL after login: {url_after}")

        logged_in = "login" not in url_after.lower()
        print(f"Logged in: {logged_in}")

        # Get cookies
        cookies = ctx.cookies()
        browser.close()

        # Build requests session
        s = requests.Session()
        s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        for c in cookies:
            s.cookies.set(c["name"], c["value"],
                          domain=c.get("domain","").lstrip("."))

        return s, logged_in

def search_grabcad(session, query, per_page=8):
    try:
        r = session.get("https://grabcad.com/library.json",
            params={"search": query, "per_page": per_page, "sort": "relevance"},
            headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            models = data if isinstance(data, list) else data.get("models", [])
            return [{"slug": m.get("slug",""), "name": m.get("name",""),
                     "url": f"https://grabcad.com/library/{m.get('slug','')}"}
                    for m in models[:per_page] if isinstance(m, dict)]
        print(f"Search HTTP {r.status_code}")
    except Exception as e:
        print(f"Search error: {e}")
    return []

if __name__ == "__main__":
    session, ok = get_grabcad_session()
    if ok:
        print("\n✓ GrabCAD login SUCCESS!\n")
        for q in ["F-16 fighter", "T-72 tank", "AH-64 Apache"]:
            results = search_grabcad(session, q)
            print(f"'{q}': {len(results)} results")
            for r in results[:2]:
                print(f"  [{r['slug']}] {r['name']}")
    else:
        print("\n✗ Login failed — GrabCAD may require manual login")
        print("Cookies obtained:", list(session.cookies.keys()))
        # Still try search with whatever cookies we have
        print("\nTrying search anyway...")
        r = search_grabcad(session, "F-16 fighter")
        print(f"Results: {len(r)}")
        for x in r[:3]: print(f"  {x['name']}")
