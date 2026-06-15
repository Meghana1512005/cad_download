"""
Debug script: tests CadNav HTML patterns and GrabCAD login.
Run this as a workflow step before the real search.
"""
import os, re, sys, requests
from grabcad_client import GrabCADClient

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# ── CadNav HTML debug ─────────────────────────────────────────────────────────
print("=" * 60)
print("CadNav HTML diagnosis")
print("=" * 60)
s = requests.Session()
s.headers["User-Agent"] = AGENT
r = s.get("https://www.cadnav.com/3d-models/aircraft/", timeout=15)
print(f"Status: {r.status_code}  Len: {len(r.text)}")

# Show 600 chars around first model link
idx = r.text.find("/3d-models/model-")
if idx >= 0:
    print("\nHTML around first model link:")
    print(repr(r.text[max(0,idx-80):idx+300]))
else:
    print("No /3d-models/model- found in page!")
    print("First 800 chars of page:")
    print(repr(r.text[:800]))

# Test all candidate patterns
patterns = {
    "P1-title":    r'href="[^"]*?/3d-models/model-(\d+)\.html"[^>]*title="([^"]+?) 3d model',
    "P2-h2link":   r'href="[^"]*?/3d-models/model-(\d+)\.html">([^<]+)</a>',
    "P3-ids-only": r'/3d-models/model-(\d+)\.html',
    "P4-h2tag":    r'<h2[^>]*>.*?model-(\d+)\.html[^<]*>([^<]+)</a>',
}
for name, pat in patterns.items():
    m = re.findall(pat, r.text, re.IGNORECASE)
    print(f"\n{name}: {len(m)} matches")
    for x in m[:3]:
        print(f"  {x}")

# ── GrabCAD login debug ───────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("GrabCAD login diagnosis")
print("=" * 60)
user = os.environ.get("GRABCAD_USER", "")
pwd  = os.environ.get("GRABCAD_PASS", "")
if not user or not pwd:
    print("GRABCAD_USER/PASS not set in environment")
    sys.exit(0)

print(f"Email: {user[:6]}***")
gc = GrabCADClient(user, pwd)
if gc.logged_in:
    print("Login OK — testing search...")
    results = gc.search("F-16 Fighting Falcon", per_page=3)
    print(f"Search 'F-16': {len(results)} results")
    for r2 in results:
        print(f"  [{r2.get('slug','')}] {r2.get('name','')}")
else:
    print("Login FAILED")
