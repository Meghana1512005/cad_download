"""
GrabCAD cookie-based client using email + CSRF token login.
"""
import os, re, requests

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

class GrabCADClient:
    BASE = "https://grabcad.com"

    def __init__(self, email, password):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": AGENT})
        self.logged_in = self._login(email, password)

    def _login(self, email, password):
        # Step 1: get login page + CSRF token
        r = self.s.get(f"{self.BASE}/login", timeout=15)
        if r.status_code != 200:
            print(f"GrabCAD: login page failed ({r.status_code})")
            return False

        # Extract authenticity_token
        csrf = None
        for pattern in [
            r'name="authenticity_token"\s+value="([^"]+)"',
            r'"authenticity_token","([^"]+)"',
            r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"',
            r'csrf-token["\s]+content="([^"]+)"',
        ]:
            m = re.search(pattern, r.text, re.I)
            if m: csrf = m.group(1); break

        if not csrf:
            print("GrabCAD: CSRF token not found")
            return False
        print(f"GrabCAD: CSRF token obtained ({len(csrf)} chars)")

        # Step 2: POST login with EMAIL (not username)
        self.s.headers.update({
            "X-CSRF-Token": csrf,
            "Referer": f"{self.BASE}/login",
            "Origin": self.BASE,
            "Content-Type": "application/x-www-form-urlencoded",
        })
        data = {
            "authenticity_token": csrf,
            "user[login]": email,        # use email here
            "user[password]": password,
            "user[remember_me]": "0",
            "commit": "Sign in",
        }
        r2 = self.s.post(f"{self.BASE}/login", data=data,
                         allow_redirects=True, timeout=15)
        print(f"GrabCAD: login response {r2.status_code}, url={r2.url}")

        if "login" not in r2.url or r2.status_code in (200,) and "sign_out" in r2.text.lower():
            print("GrabCAD: login successful!")
            return True

        # Fallback: try JSON API login with email
        self.s.headers["Content-Type"] = "application/json"
        r3 = self.s.post(f"{self.BASE}/api/v1/users/sign_in",
            json={"user": {"email": email, "password": password}}, timeout=15)
        print(f"GrabCAD: JSON login {r3.status_code}: {r3.text[:100]}")
        if r3.status_code in (200, 201):
            return True

        print("GrabCAD: all login attempts failed")
        return False

    def search(self, query, per_page=8):
        if not self.logged_in: return []
        try:
            r = self.s.get(f"{self.BASE}/library.json",
                params={"search": query, "per_page": per_page, "sort": "relevance"},
                headers={"Accept": "application/json",
                         "Content-Type": "application/json"}, timeout=15)
            if r.status_code == 200:
                data = r.json()
                models = data if isinstance(data, list) else data.get("models", [])
                return [{"id": m.get("id"), "slug": m.get("slug",""),
                         "name": m.get("name",""),
                         "url": f"{self.BASE}/library/{m.get('slug','')}",
                         "dl_url": f"{self.BASE}/library/{m.get('slug','')}/download"}
                        for m in models[:per_page] if isinstance(m, dict)]
            print(f"GrabCAD search: HTTP {r.status_code}")
        except Exception as e:
            print(f"GrabCAD search error: {e}")
        return []

    def download(self, slug, save_path):
        if not self.logged_in: return False
        try:
            r = self.s.get(f"{self.BASE}/library/{slug}/download",
                stream=True, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(65536): f.write(chunk)
                return True
            print(f"GrabCAD download {slug}: HTTP {r.status_code}")
        except Exception as e:
            print(f"GrabCAD download error: {e}")
        return False
