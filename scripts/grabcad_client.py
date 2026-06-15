"""
GrabCAD client — cookie-based auth (GRABCAD_SESSION + GRABCAD_XSRF secrets).
Uses /community/api/v1/models endpoint (confirmed working with session cookies).
"""
import os, re, requests

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

class GrabCADClient:
    BASE    = "https://grabcad.com"
    API     = "https://grabcad.com/community/api/v1"

    def __init__(self, email=None, password=None):
        self.s = requests.Session()
        self.s.headers.update({
            "User-Agent":   AGENT,
            "Accept":       "application/json, text/plain, */*",
            "Referer":      "https://grabcad.com/library",
            "Origin":       "https://grabcad.com",
        })
        self.logged_in = self._init_from_cookies()

    def _init_from_cookies(self):
        session_val = os.environ.get("GRABCAD_SESSION", "")
        xsrf_val    = os.environ.get("GRABCAD_XSRF", "")

        if not session_val or not xsrf_val:
            print("GrabCAD: GRABCAD_SESSION / GRABCAD_XSRF not set")
            return False

        print(f"GrabCAD: session={len(session_val)} chars, xsrf={len(xsrf_val)} chars")

        self.s.cookies.set("_grabcad_session", session_val, domain="grabcad.com")
        self.s.cookies.set("XSRF-TOKEN",       xsrf_val,    domain="grabcad.com")
        self.s.headers["X-XSRF-TOKEN"] = requests.utils.unquote(xsrf_val)

        # Verify via community API (the endpoint confirmed working with cookies)
        try:
            r = self.s.get(f"{self.API}/models",
                params={"search": "F-16", "per_page": 1}, timeout=15)
            print(f"GrabCAD: session test HTTP {r.status_code}")
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("models", data.get("results", []))
                print(f"GrabCAD: session valid — test returned {len(items)} result(s)")
                if items and isinstance(items[0], dict):
                    print(f"  Sample: {items[0].get('name','?')!r}")
                return True
            elif r.status_code in (401, 403):
                print("GrabCAD: session expired — please update GRABCAD_SESSION + GRABCAD_XSRF")
            else:
                print(f"GrabCAD: unexpected {r.status_code}: {r.text[:200]}")
            return False
        except Exception as e:
            print(f"GrabCAD: session check error: {e}")
            return False

    def search(self, query, per_page=8):
        if not self.logged_in:
            return []
        try:
            r = self.s.get(f"{self.API}/models",
                params={"search": query, "per_page": per_page, "sort": "relevance"},
                timeout=15)
            if r.status_code == 200:
                data = r.json()
                items = data if isinstance(data, list) else data.get("models", data.get("results", []))
                results = []
                for m in items[:per_page]:
                    if not isinstance(m, dict):
                        continue
                    slug = (m.get("slug") or m.get("url_identifier") or
                            re.sub(r'[^a-z0-9]+', '-', m.get("name","").lower()).strip('-'))
                    results.append({
                        "id":   m.get("id"),
                        "slug": slug,
                        "name": m.get("name", ""),
                        "url":  f"{self.BASE}/library/{slug}",
                        "dl_url": f"{self.BASE}/library/{slug}/download",
                    })
                return results
            if r.status_code == 429:
                print("GrabCAD: rate limited (429)")
            else:
                print(f"GrabCAD search HTTP {r.status_code}: {r.text[:100]}")
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
