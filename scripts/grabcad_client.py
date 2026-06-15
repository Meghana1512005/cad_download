"""
GrabCAD client — uses Playwright headless Chrome for login (handles JS-based auth),
then uses extracted cookies for all HTTP requests.
"""
import os, re, time, requests

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

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
            print("GrabCAD: playwright not installed, falling back to requests login")
            return self._login_requests(email, password)

        print("GrabCAD: launching headless browser...")
        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(
                    headless=True,
                    args=["--no-sandbox", "--disable-dev-shm-usage"]
                )
                ctx = browser.new_context(user_agent=AGENT)
                page = ctx.new_page()

                page.goto(f"{self.BASE}/login", wait_until="networkidle", timeout=30000)
                time.sleep(1)

                # Fill email
                for sel in ['input[name="user[login]"]', 'input[type="email"]',
                            '#user_login', 'input[placeholder*="mail" i]',
                            'input[placeholder*="sername" i]']:
                    try:
                        page.fill(sel, email, timeout=3000)
                        print(f"  Email filled ({sel})")
                        break
                    except: pass

                # Fill password
                for sel in ['input[name="user[password]"]', 'input[type="password"]',
                            '#user_password']:
                    try:
                        page.fill(sel, password, timeout=3000)
                        print(f"  Password filled ({sel})")
                        break
                    except: pass

                # Submit
                for sel in ['input[type="submit"]', 'button[type="submit"]',
                            'button:has-text("Sign in")', 'input[value="Sign in"]']:
                    try:
                        page.click(sel, timeout=3000)
                        print(f"  Clicked submit ({sel})")
                        break
                    except: pass

                # Wait for redirect away from /login
                try:
                    page.wait_for_url(
                        lambda url: "login" not in url.lower(),
                        timeout=20000
                    )
                except:
                    pass

                time.sleep(2)
                final_url = page.url
                print(f"  Final URL: {final_url}")
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
                if logged_in:
                    print("GrabCAD: Playwright login SUCCESS")
                else:
                    print("GrabCAD: Playwright login FAILED (still on login page)")
                return logged_in

        except Exception as e:
            print(f"GrabCAD: Playwright login error: {e}")
            return False

    def _login_requests(self, email, password):
        """Fallback: plain HTTP POST (may not work on JS-heavy sites)."""
        r = self.s.get(f"{self.BASE}/login", timeout=15)
        if r.status_code != 200:
            return False
        csrf = None
        for pattern in [
            r'name="authenticity_token"\s+value="([^"]+)"',
            r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"',
        ]:
            m = re.search(pattern, r.text, re.I)
            if m:
                csrf = m.group(1)
                break
        if not csrf:
            print("GrabCAD requests: CSRF not found")
            return False
        self.s.headers.update({
            "X-CSRF-Token": csrf, "Referer": f"{self.BASE}/login",
            "Origin": self.BASE,
        })
        r2 = self.s.post(f"{self.BASE}/login", data={
            "authenticity_token": csrf,
            "user[login]": email,
            "user[password]": password,
            "commit": "Sign in",
        }, allow_redirects=True, timeout=15)
        print(f"GrabCAD requests login: {r2.status_code}, url={r2.url}")
        return "login" not in r2.url

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
