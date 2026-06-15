"""Debug: test CadNav + probe GrabCAD search API parameters."""
import os, re, requests
from bs4 import BeautifulSoup

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# ── CadNav quick check ────────────────────────────────────────────────────────
print("=" * 60)
print("CadNav quick check")
print("=" * 60)
s = requests.Session()
s.headers["User-Agent"] = AGENT
r = s.get("https://www.cadnav.com/3d-models/aircraft/", timeout=15)
soup = BeautifulSoup(r.text, "html.parser")
seen = set()
for a in soup.find_all("a", href=re.compile(r"/3d-models/model-\d+\.html")):
    mid = re.search(r"model-(\d+)", a.get("href",""))
    if mid and mid.group(1) not in seen:
        seen.add(mid.group(1))
print(f"CadNav aircraft page: {len(seen)} unique models OK")

# ── GrabCAD API probe ─────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("GrabCAD API parameter probe")
print("=" * 60)

session_val = os.environ.get("GRABCAD_SESSION", "")
xsrf_val    = os.environ.get("GRABCAD_XSRF", "")

gc = requests.Session()
gc.headers.update({
    "User-Agent":   AGENT,
    "Accept":       "application/json",
    "Referer":      "https://grabcad.com/library",
    "X-XSRF-TOKEN": requests.utils.unquote(xsrf_val),
})
gc.cookies.set("_grabcad_session", session_val, domain="grabcad.com")
gc.cookies.set("XSRF-TOKEN",       xsrf_val,    domain="grabcad.com")

QUERY = "F-16 Fighting Falcon"

# Try every plausible endpoint + parameter combination
endpoints = [
    ("community/api/v1/models", "q"),
    ("community/api/v1/models", "query"),
    ("community/api/v1/models", "search"),
    ("community/api/v1/models", "keywords"),
    ("community/api/v1/search", "q"),
    ("community/api/v1/search", "query"),
    ("library.json",            "query"),
    ("library.json",            "q"),
    ("library.json",            "search"),
]

for path, param in endpoints:
    try:
        url = f"https://grabcad.com/{path}"
        r = gc.get(url, params={param: QUERY, "per_page": 3, "sort": "relevance"}, timeout=10)
        if r.status_code != 200:
            print(f"  {path}?{param}=...  → HTTP {r.status_code}")
            continue
        data = r.json()
        items = data if isinstance(data, list) else data.get("models", data.get("results", data.get("hits", [])))
        if not isinstance(items, list):
            print(f"  {path}?{param}=...  → unexpected structure: {str(data)[:80]}")
            continue
        names = [m.get("name","?") for m in items[:3] if isinstance(m, dict)]
        # Check if results look relevant (contain F, 16, fighter, etc.)
        relevant = any(any(w in n.lower() for w in ["f-16","f16","falcon","fighter"]) for n in names)
        marker = "✓ RELEVANT" if relevant else "  random"
        print(f"  {path}?{param}=...  → {len(items)} results {marker}: {names}")
    except Exception as e:
        print(f"  {path}?{param}=...  → ERROR: {e}")
