"""
GrabCAD download via Playwright (headless Chrome).
Handles JavaScript-rendered login and search.
"""
import os, json, time, re
from pathlib import Path

USER = os.environ.get("GRABCAD_USER", "meghana.reddy-12")
PASS = os.environ.get("GRABCAD_PASS", "")
# GrabCAD may use email — try both
EMAIL = os.environ.get("GRABCAD_EMAIL", USER)  # fallback to username

def get_grabcad_client():
    """Returns a requests session with valid GrabCAD cookies via Playwright."""
    try:
        from playwright.sync_api import sync_playwright
        import requests

        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            ctx = browser.new_context(
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            )
            page = ctx.new_page()

            print("GrabCAD (Playwright): navigating to login...")
            page.goto("https://grabcad.com/login", timeout=30000)
            page.wait_for_load_state("networkidle", timeout=15000)

            # Try username first, fallback to email
            login_val = EMAIL
            try:
                page.fill('input[name="user[login]"]', login_val, timeout=5000)
                page.fill('input[name="user[password]"]', PASS, timeout=5000)
            except:
                # Try alternative selectors
                page.fill('input[placeholder*="mail" i], input[type="email"]', login_val, timeout=5000)
                page.fill('input[type="password"]', PASS, timeout=5000)

            page.click('input[type="submit"], button[type="submit"]', timeout=5000)
            time.sleep(3)
            page.wait_for_load_state("networkidle", timeout=15000)

            current_url = page.url
            print(f"GrabCAD: after login → {current_url}")

            if "login" in current_url:
                print("GrabCAD: login may have failed, trying email login...")
                # Try email if username didn't work
                page.goto("https://grabcad.com/login", timeout=15000)
                page.wait_for_load_state("networkidle", timeout=10000)
                for sel in ['input[name="user[login]"]', 'input[type="email"]', '#user_login']:
                    try:
                        page.fill(sel, EMAIL, timeout=2000)
                        break
                    except: continue
                for sel in ['input[name="user[password]"]', 'input[type="password"]', '#user_password']:
                    try:
                        page.fill(sel, PASS, timeout=2000)
                        break
                    except: continue
                page.click('input[type="submit"], button[type="submit"]', timeout=5000)
                time.sleep(3)
                page.wait_for_load_state("networkidle", timeout=15000)
                current_url = page.url

            logged_in = "login" not in current_url
            print(f"GrabCAD: logged_in={logged_in}, url={current_url}")

            # Extract cookies and transfer to requests session
            cookies = ctx.cookies()
            browser.close()

            s = requests.Session()
            s.headers.update({"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            for c in cookies:
                s.cookies.set(c["name"], c["value"], domain=c.get("domain",""))

            return s, logged_in

    except ImportError:
        print("Playwright not installed")
        return None, False
    except Exception as e:
        print(f"Playwright error: {e}")
        return None, False

def search_grabcad_pw(session, query, per_page=8):
    """Search GrabCAD with authenticated session."""
    try:
        r = session.get("https://grabcad.com/library.json",
            params={"search": query, "per_page": per_page, "sort": "relevance"},
            headers={"Accept": "application/json"}, timeout=15)
        if r.status_code == 200:
            data = r.json()
            models = data if isinstance(data, list) else data.get("models", [])
            return [{"id": m.get("id"), "slug": m.get("slug",""),
                     "name": m.get("name",""),
                     "url": f"https://grabcad.com/library/{m.get('slug','')}",
                     "dl_url": f"https://grabcad.com/library/{m.get('slug','')}/download"}
                    for m in models[:per_page] if isinstance(m, dict)]
        print(f"GrabCAD search: {r.status_code}")
    except Exception as e:
        print(f"GrabCAD search error: {e}")
    return []

def download_grabcad_pw(session, slug, save_path):
    """Download a GrabCAD model ZIP."""
    try:
        r = session.get(f"https://grabcad.com/library/{slug}/download",
            stream=True, timeout=60, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(65536): f.write(chunk)
            return True
        print(f"GrabCAD download {slug}: {r.status_code}")
    except Exception as e:
        print(f"GrabCAD download error: {e}")
    return False

# ── Test when run directly ────────────────────────────────────────────────────
if __name__ == "__main__":
    session, ok = get_grabcad_client()
    if ok:
        print("\nSearching for 'F-16 fighter jet'...")
        results = search_grabcad_pw(session, "F-16 fighter jet")
        print(f"Found {len(results)} results:")
        for r in results[:5]:
            print(f"  [{r['slug']}] {r['name']} — {r['url']}")
    else:
        print("Login failed.")
