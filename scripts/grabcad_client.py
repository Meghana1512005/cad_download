"""
GrabCAD cookie-based client.
Since GrabCAD API is deprecated, we use full web session (login → search → download).
"""
import os, re, requests, json, time
from urllib.parse import urljoin

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

class GrabCADClient:
    BASE = "https://grabcad.com"

    def __init__(self, username, password):
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": AGENT})
        self.logged_in = self._login(username, password)

    def _login(self, username, password):
        # Step 1: get CSRF token from login page
        r = self.s.get(f"{self.BASE}/login", timeout=15)
        if r.status_code != 200:
            print(f"GrabCAD: login page failed ({r.status_code})")
            return False

        # Extract authenticity_token
        m = re.search(r'name="authenticity_token"\s+value="([^"]+)"', r.text)
        if not m:
            m = re.search(r'"authenticity_token","([^"]+)"', r.text)
        if not m:
            m = re.search(r'csrf-token["\s]+content="([^"]+)"', r.text, re.I)
        if not m:
            # Try meta tag
            m = re.search(r'<meta[^>]+name="csrf-token"[^>]+content="([^"]+)"', r.text)

        csrf = m.group(1) if m else ""
        if not csrf:
            print("GrabCAD: CSRF token not found")
            return False
        print(f"GrabCAD: CSRF token obtained ({len(csrf)} chars)")

        # Step 2: POST login form
        self.s.headers.update({
            "X-CSRF-Token": csrf,
            "Referer": f"{self.BASE}/login",
            "Origin": self.BASE,
        })
        data = {
            "authenticity_token": csrf,
            "user[login]": username,
            "user[password]": password,
            "user[remember_me]": "0",
            "commit": "Sign in"
        }
        r2 = self.s.post(f"{self.BASE}/login", data=data,
                         allow_redirects=True, timeout=15)
        if r2.status_code in (200, 302):
            # Check if logged in by looking for profile or logged-in indicator
            if username.lower() in r2.text.lower() or "log out" in r2.text.lower() \
               or "sign out" in r2.text.lower() or r2.url != f"{self.BASE}/login":
                print(f"GrabCAD: logged in as {username}")
                return True
            # Try JSON login as fallback
            self.s.headers["Content-Type"] = "application/json"
            r3 = self.s.post(f"{self.BASE}/api/v1/users/sign_in",
                json={"user": {"login": username, "password": password,
                               "remember_me": False}}, timeout=15)
            if r3.status_code in (200, 201):
                print(f"GrabCAD: JSON login ok ({r3.status_code})")
                return True
        print(f"GrabCAD: login failed ({r2.status_code}), url={r2.url}")
        return False

    def search(self, query, per_page=8):
        """Search GrabCAD library."""
        if not self.logged_in:
            return []
        try:
            # Try JSON API search
            r = self.s.get(f"{self.BASE}/library.json",
                params={"search": query, "per_page": per_page,
                        "sort": "relevance", "page": 1},
                headers={"Accept": "application/json"}, timeout=15)
            if r.status_code == 200:
                try:
                    data = r.json()
                    models = data if isinstance(data, list) else data.get("models", [])
                    return [{"id": m.get("id"), "slug": m.get("slug",""),
                             "name": m.get("name",""),
                             "url": f"{self.BASE}/library/{m.get('slug','')}",
                             "dl_url": f"{self.BASE}/library/{m.get('slug','')}/download"}
                            for m in models[:per_page] if isinstance(m, dict)]
                except:
                    pass
            # Fallback: HTML search
            r2 = self.s.get(f"{self.BASE}/library",
                params={"query": query, "sort": "relevance"}, timeout=15)
            if r2.status_code == 200:
                # Extract model slugs from HTML
                slugs = re.findall(r'href="/library/([a-z0-9\-]+)"', r2.text)
                names = re.findall(r'class="[^"]*model-name[^"]*"[^>]*>([^<]+)<', r2.text)
                results = []
                for i, slug in enumerate(slugs[:per_page]):
                    results.append({
                        "id": slug, "slug": slug,
                        "name": names[i] if i < len(names) else slug,
                        "url": f"{self.BASE}/library/{slug}",
                        "dl_url": f"{self.BASE}/library/{slug}/download"
                    })
                return results
        except Exception as e:
            print(f"GrabCAD search error: {e}")
        return []

    def download(self, model, save_path):
        """Download GrabCAD model zip."""
        if not self.logged_in:
            return False
        try:
            slug = model.get("slug", model.get("id",""))
            dl_url = f"{self.BASE}/library/{slug}/download"
            r = self.s.get(dl_url, stream=True, timeout=60, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 1000:
                with open(save_path, "wb") as f:
                    for chunk in r.iter_content(65536):
                        f.write(chunk)
                return True
            print(f"  GrabCAD download: {r.status_code}")
            return False
        except Exception as e:
            print(f"  GrabCAD download error: {e}")
            return False
