"""
Debug: tests CadNav HTML patterns and GrabCAD Playwright login.
"""
import os, re, sys, requests
from bs4 import BeautifulSoup

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# ── CadNav HTML debug ──────────────────────────────────────────────────────────
print("=" * 60)
print("CadNav HTML diagnosis")
print("=" * 60)
s = requests.Session()
s.headers["User-Agent"] = AGENT
r = s.get("https://www.cadnav.com/3d-models/aircraft/", timeout=15)
print(f"Status: {r.status_code}  Len: {len(r.text)}")

soup = BeautifulSoup(r.text, "html.parser")
links = soup.find_all("a", href=re.compile(r"/3d-models/model-\d+\.html"))
print(f"BeautifulSoup model links: {len(links)}")
for a in links[:5]:
    href = a.get("href", "")
    mid  = re.search(r"model-(\d+)", href)
    name = (a.get("title", "") or a.get_text(strip=True))
    name = re.sub(r'\s*3d model.*$', '', name, flags=re.I).strip()
    print(f"  [{mid.group(1) if mid else '?'}] {name!r}")

# ── GrabCAD Playwright login debug ────────────────────────────────────────────
print("\n" + "=" * 60)
print("GrabCAD Playwright login diagnosis")
print("=" * 60)
user = os.environ.get("GRABCAD_USER", "")
pwd  = os.environ.get("GRABCAD_PASS", "")
if not user or not pwd:
    print("GRABCAD_USER/PASS not set")
    sys.exit(0)

print(f"Email: {user[:6]}***")
from grabcad_client import GrabCADClient
gc = GrabCADClient(user, pwd)
if gc.logged_in:
    print("\nLogin OK - testing search...")
    for q in ["F-16 Fighting Falcon", "T-72 tank", "AH-64 Apache"]:
        results = gc.search(q, per_page=3)
        print(f"  '{q}': {len(results)} results")
        for r2 in results[:2]:
            print(f"    [{r2.get('slug','')}] {r2.get('name','')}")
else:
    print("Login FAILED")
