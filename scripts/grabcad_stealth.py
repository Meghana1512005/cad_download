"""
GrabCAD using real browser session cookies — no login needed, no bot detection.
"""
import os, json, re, time, requests

GC_SESSION = os.environ.get("GRABCAD_SESSION", "")
GC_XSRF    = os.environ.get("GRABCAD_XSRF",    "")

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

def build_session():
    s = requests.Session()
    s.headers.update({
        "User-Agent":    AGENT,
        "Accept":        "application/json, text/plain, */*",
        "Referer":       "https://grabcad.com/library",
        "Origin":        "https://grabcad.com",
        "X-XSRF-TOKEN":  requests.utils.unquote(GC_XSRF),
    })
    s.cookies.set("_grabcad_session", GC_SESSION, domain="grabcad.com")
    s.cookies.set("XSRF-TOKEN",       GC_XSRF,    domain="grabcad.com")
    return s

def verify_session(s):
    """Check if cookies are valid."""
    r = s.get("https://grabcad.com/api/v1/users/current",
              headers={"Accept":"application/json"}, timeout=10)
    print(f"Session check: HTTP {r.status_code}")
    if r.status_code == 200:
        try:
            u = r.json()
            print(f"✓ Logged in as: {u.get('name','?')} ({u.get('login','?')})")
            return True
        except: pass
    print(f"Response: {r.text[:150]}")
    return False

def search_grabcad(s, query, per_page=8):
    """Search GrabCAD library."""
    endpoints = [
        f"https://grabcad.com/library.json?search={requests.utils.quote(query)}&per_page={per_page}&sort=relevance",
        f"https://grabcad.com/community/api/v1/models?search={requests.utils.quote(query)}&per_page={per_page}",
        f"https://grabcad.com/api/v1/models?q={requests.utils.quote(query)}&per_page={per_page}",
    ]
    for url in endpoints:
        r = s.get(url, timeout=15)
        if r.status_code == 200:
            try:
                data = r.json()
                models = data if isinstance(data, list) else data.get("models", [])
                if models:
                    print(f"✓ Search works via: {url.split('grabcad.com')[1][:50]}")
                    return [{"slug": m.get("slug",""), "name": m.get("name",""),
                             "url": f"https://grabcad.com/library/{m.get('slug','')}",
                             "dl_url": f"https://grabcad.com/library/{m.get('slug','')}/download"}
                            for m in models[:per_page] if isinstance(m, dict)]
            except Exception as e:
                print(f"  Parse error: {e}")
        else:
            print(f"  {url.split('grabcad.com')[1][:50]} → {r.status_code}")
    return []

def download_model(s, slug, save_path):
    """Download a GrabCAD model."""
    try:
        r = s.get(f"https://grabcad.com/library/{slug}/download",
                  stream=True, timeout=60, allow_redirects=True)
        if r.status_code == 200 and len(r.content) > 1000:
            with open(save_path, "wb") as f:
                for chunk in r.iter_content(65536): f.write(chunk)
            return True
        print(f"Download {slug}: HTTP {r.status_code}")
    except Exception as e:
        print(f"Download error: {e}")
    return False

if __name__ == "__main__":
    if not GC_SESSION:
        print("ERROR: GRABCAD_SESSION secret not set"); exit(1)

    print(f"Session cookie: {GC_SESSION[:20]}...")
    s = build_session()

    print("\n=== Verifying session ===")
    ok = verify_session(s)

    print("\n=== Testing search ===")
    for query in ["F-16 fighter jet", "T-72 tank", "AH-64 Apache helicopter", "Leopard 2 tank"]:
        results = search_grabcad(s, query, per_page=3)
        print(f"  '{query}': {len(results)} results")
        for r in results[:2]:
            print(f"    [{r['slug']}] {r['name']}")
