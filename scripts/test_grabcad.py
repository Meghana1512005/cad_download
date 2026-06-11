"""Test GrabCAD auth methods — run this in a workflow to see what works."""
import os, requests, json

USER = os.environ.get("GRABCAD_USER", "meghana.reddy-12")
PASS = os.environ.get("GRABCAD_PASS", "")

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Accept": "application/json, text/plain, */*",
    "Content-Type": "application/json",
    "Origin": "https://grabcad.com",
    "Referer": "https://grabcad.com/login"
}

s = requests.Session()
s.headers.update(HEADERS)

# 1. Get CSRF token from login page
print("=== Step 1: Get CSRF token ===")
r = s.get("https://grabcad.com/login", timeout=15)
print(f"Login page: {r.status_code}")
csrf = None
for line in r.text.split('\n'):
    if 'csrf' in line.lower() and 'content' in line.lower():
        import re
        m = re.search(r'content="([^"]+)"', line)
        if m: csrf = m.group(1); break
    if 'authenticity_token' in line.lower():
        import re
        m = re.search(r'value="([^"]+)"', line)
        if m: csrf = m.group(1); break
print(f"CSRF: {csrf[:20] if csrf else 'not found'}...")

# 2. Try API session endpoint
print("\n=== Step 2: API session login ===")
payload = {"user": {"login": USER, "password": PASS}}
if csrf:
    s.headers["X-CSRF-Token"] = csrf
r2 = s.post("https://grabcad.com/api/v1/sessions", json=payload, timeout=15)
print(f"Sessions endpoint: {r2.status_code}")
print(f"Response: {r2.text[:200]}")

# 3. Try community API
print("\n=== Step 3: Community API login ===")
r3 = s.post("https://grabcad.com/community/sessions",
            json={"login": USER, "password": PASS}, timeout=15)
print(f"Community sessions: {r3.status_code}: {r3.text[:200]}")

# 4. Try search with current session
print("\n=== Step 4: Search test ===")
r4 = s.get("https://grabcad.com/library.json",
           params={"search": "F-16 fighter jet", "per_page": 3}, timeout=15)
print(f"Library search: {r4.status_code}")
if r4.status_code == 200:
    try:
        data = r4.json()
        print(f"Results: {json.dumps(data)[:300]}")
    except:
        print(f"Raw: {r4.text[:200]}")

# 5. Try basic auth search
print("\n=== Step 5: Basic auth search ===")
r5 = requests.get("https://grabcad.com/library.json",
    params={"search": "F-16", "per_page": 3},
    auth=(USER, PASS),
    headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"},
    timeout=15)
print(f"Basic auth search: {r5.status_code}: {r5.text[:200]}")

# 6. Try GrabCAD v2 API
print("\n=== Step 6: GrabCAD v2 API ===")
r6 = s.get("https://grabcad.com/api/v2/models",
           params={"search": "F-16", "per_page": 3}, timeout=15)
print(f"v2 API: {r6.status_code}: {r6.text[:200]}")
