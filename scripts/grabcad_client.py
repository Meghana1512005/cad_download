"""
GrabCAD client — Playwright headless Chrome with anti-detection settings.
"""
import os, re, time, requests

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class GrabCADClient:
    BASE = "https://grabcad.com"

    def __init__(self, email, password):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": AGENT})
        self.logged_in = self._login_playwright(email, password)

    def _login_playwright(self, email, password):
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            print("GrabCAD: playwright not installed")
            return False

        print("GrabCAD: launching headless browser (stealth mode)...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=[
                        "--no-sandbox",
                        "--disable-dev-shm-usage",
                        "--disable-blink-features=AutomationControlled",
                        "--disable-web-security",
                        "--disable-features=IsolateOrigins,site-per-process",
                    ]
                )
                ctx = browser.new_context(
                    user_agent=AGENT,
                    viewport={"width": 1280, "height": 800},
                    locale="en-US",
                    timezone_id="America/New_York",
                    java_script_enabled=True,
                )
                page = ctx.new_page()

                # Remove webdriver fingerprint
                page.add_init_script("""
                    Object.defineProperty(navigator, 'webdriver', {get: () => undefined});
                    Object.defineProperty(navigator, 'plugins', {get: () => [1,2,3,4,5]});
                    Object.defineProperty(navigator, 'languages', {get: () => ['en-US','en']});
                    window.chrome = {runtime: {}};
                """)

                print("  Navigating to login page...")
                page.goto(f"{self.BASE}/login", wait_until="networkidle", timeout=30000)
                time.sleep(2)

                print(f"  Page title: {page.title()}")

                # Fill email
                email_sel = None
                for sel in ['input[type="email"]', 'input[name="user[login]"]',
                            '#user_login', 'input[placeholder*="mail" i]']:
                    try:
                        page.wait_for_selector(sel, timeout=3000)
                        page.fill(sel, email)
                        email_sel = sel
                        print(f"  Email filled ({sel})")
                        break
                    except: pass

                if not email_sel:
                    print("  ERROR: could not find email field")
                    print("  Page HTML snippet:", page.content()[:500])

                time.sleep(0.5)

                # Fill password
                for sel in ['input[type="password"]', 'input[name="user[password]"]',
                            '#user_password']:
                    try:
                        page.wait_for_selector(sel, timeout=3000)
                        page.fill(sel, password)
                        print(f"  Password filled ({sel})")
                        break
                    except: pass

                time.sleep(0.5)

                # Try submitting via keyboard Enter (more natural than click)
                print("  Pressing Enter to submit...")
                page.keyboard.press("Enter")

                # Wait for navigation or error
                try:
                    page.wait_for_url(
                        lambda url: "login" not in url.lower(),
                        timeout=15000
                    )
                except:
                    pass

                time.sleep(3)
                final_url = page.url
                print(f"  Final URL: {final_url}")

                # Print any visible error messages
                for err_sel in [".alert", ".flash", ".error", "[class*='error']",
                                "[class*='alert']", "[class*='flash']"]:
                    try:
                        msgs = page.locator(err_sel).all_text_contents()
                        if msgs:
                            print(f"  Page messages ({err_sel}): {msgs}")
                    except: pass

                logged_in = "login" not in final_url.lower()

                # Transfer cookies to requests session
                for c in ctx.cookies():
                    self.s.cookies.set(
                        c["name"], c["value"],
                        domain=c.get("domain", ".grabcad.com").lstrip(".")
                    )
                xsrf = self.s.cookies.get("XSRF-TOKEN", "")
                if xsrf:
                    self.s.headers["X-XSRF-TOKEN"] = requests.utils.unquote(xsrf)

                browser.close()
                print(f"GrabCAD: {'LOGIN OK' if logged_in else 'LOGIN FAILED'}")
                return logged_in

        except Exception as e:
            print(f"GrabCAD: Playwright error: {e}")
            return False

    def search(self, query, per_page=8):
        if not self.logged_in:
            return []
        try:
            r = self.s.get(f"{self.BASE}/library.json",
                params={"search": query, "per_page": per_page, "sort": "relevance"},
                headers={"Accept": "application/json"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                models = data if isinstance(data, list) else data.get("models", [])
                return [{"id": m.get("id"), "slug": m.get("slug", ""),
                         "name": m.get("name", ""),
                         "url": f"{self.BASE}/library/{m.get('slug', '')}",
                         "dl_url": f"{self.BASE}/library/{m.get('slug', '')}/download"}
                        for m in models[:per_page] if isinstance(m, dict)]
            print(f"GrabCAD search HTTP {r.status_code}")
        except Exception as e:
            print(f"GrabCAD search error: {e}")
        return []

    def download(self, slug, save_path):
        if not self.logged_in:
            return False
        try:
            r = self.s.get(f"{self.BASE}/library/{slug}/download",
                stream=True, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                return True
            print(f"GrabCAD download {slug}: HTTP {r.status_code}")
        except Exception as e:
            print(f"GrabCAD download error: {e}")
        return False
