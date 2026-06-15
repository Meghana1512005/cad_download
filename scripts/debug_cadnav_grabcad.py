"""Debug: tests CadNav HTML + GrabCAD cookie session."""
import os, re, sys, requests
from bs4 import BeautifulSoup

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# ── CadNav ────────────────────────────────────────────────────────────────────
print("=" * 60)
print("CadNav HTML diagnosis")
print("=" * 60)
s = requests.Session()
s.headers["User-Agent"] = AGENT
r = s.get("https://www.cadnav.com/3d-models/aircraft/", timeout=15)
print(f"Status: {r.status_code}  Len: {len(r.text)}")
soup = BeautifulSoup(r.text, "html.parser")
seen = set()
entries = []
for a in soup.find_all("a", href=re.compile(r"/3d-models/model-\d+\.html")):
    mid = re.search(r"model-(\d+)", a.get("href",""))
    if not mid: continue
    if mid.group(1) in seen: continue
    seen.add(mid.group(1))
    name = re.sub(r'\s*3d model.*$','', a.get("title","") or a.get_text(strip=True), flags=re.I).strip()
    if name:
        entries.append((mid.group(1), name))
print(f"Unique models on page 1: {len(entries)}")
for mid, name in entries[:5]:
    print(f"  [{mid}] {name!r}")

# ── GrabCAD ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("GrabCAD cookie session diagnosis")
print("=" * 60)
sess  = os.environ.get("GRABCAD_SESSION", "")
xsrf  = os.environ.get("GRABCAD_XSRF", "")
user  = os.environ.get("GRABCAD_USER", "")
print(f"GRABCAD_SESSION set: {'YES (' + str(len(sess)) + ' chars)' if sess else 'NO'}")
print(f"GRABCAD_XSRF    set: {'YES (' + str(len(xsrf)) + ' chars)' if xsrf else 'NO'}")
print(f"GRABCAD_USER    set: {'YES' if user else 'NO'}")

from grabcad_client import GrabCADClient
gc = GrabCADClient()
if gc.logged_in:
    print("\nSession valid — testing search...")
    for q in ["F-16 Fighting Falcon", "T-72 tank", "AH-64 Apache"]:
        results = gc.search(q, per_page=3)
        print(f"  '{q}': {len(results)} results")
        for r2 in results[:2]:
            print(f"    [{r2.get('slug','')}] {r2.get('name','')}")
else:
    print("Session INVALID or expired — update GRABCAD_SESSION + GRABCAD_XSRF secrets")
