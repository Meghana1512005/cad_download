"""
GrabCAD client — cookie-based auth (GRABCAD_SESSION + GRABCAD_XSRF secrets).
User logs in manually in Chrome, copies cookies, stores as GitHub Secrets.
"""
import os, re, requests

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class GrabCADClient:
    BASE = "https://grabcad.com"

    def __init__(self, email=None, password=None):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent": AGENT,
            "Accept":     "application/json, text/plain, */*",
            "Referer":    "https://grabcad.com/library",
            "Origin":     "https://grabcad.com",
        })
        self.logged_in = self._init_from_cookies()

    def _init_from_cookies(self):
        session_val = os.environ.get("GRABCAD_SESSION", "")
        xsrf_val    = os.environ.get("GRABCAD_XSRF", "")

        if not session_val or not xsrf_val:
            print("GrabCAD: GRABCAD_SESSION / GRABCAD_XSRF not set")
            return False

        # Set cookies
        self.s.cookies.set("_grabcad_session", session_val, domain="grabcad.com")
        self.s.cookies.set("XSRF-TOKEN",       xsrf_val,    domain="grabcad.com")
        self.s.headers["X-XSRF-TOKEN"] = requests.utils.unquote(xsrf_val)

        # Verify session is still valid
        try:
            r = self.s.get(f"{self.BASE}/community/api/v1/users/me",
                           headers={"Accept": "application/json"}, timeout=10)
            if r.status_code == 200:
                user = r.json()
                name = user.get("name") or user.get("login") or "unknown"
                print(f"GrabCAD: session valid — logged in as {name!r}")
                return True
            # Try alternate endpoint
            r2 = self.s.get(f"{self.BASE}/api/v1/users/current",
                            headers={"Accept": "application/json"}, timeout=10)
            if r2.status_code == 200:
                user = r2.json()
                name = user.get("name") or user.get("login") or "unknown"
                print(f"GrabCAD: session valid — logged in as {name!r}")
                return True
            print(f"GrabCAD: session check failed (HTTP {r.status_code}) — cookies may be expired")
            print(f"  Response: {r.text[:120]}")
            return False
        except Exception as e:
            print(f"GrabCAD: session check error: {e}")
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
