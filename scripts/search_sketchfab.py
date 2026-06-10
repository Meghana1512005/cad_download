import json, os, time, re, requests

TOKEN   = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

me = requests.get(f"{BASE}/me", headers=HEADERS, timeout=10)
if me.status_code != 200:
    print(f"ERROR: Auth failed ({me.status_code})")
    exit(1)
print(f"Authenticated as: {me.json().get('username')}")

def search(query, military=True):
    q = query + (" military" if military else "")
    r = requests.get(f"{BASE}/search", headers=HEADERS, timeout=15,
        params={"q": q, "type": "models", "downloadable": "true", "count": 8})
    if r.status_code != 200:
        return []
    return [{"uid": m["uid"], "name": m["name"],
             "is_free": m.get("price") is None,
             "downloadable": m.get("isDownloadable", False)}
            for m in r.json().get("results", [])]

def is_good_match(model_name, sketchfab_name):
    """Check if Sketchfab result is actually related to the model."""
    # Extract meaningful tokens from original model name
    orig_tokens = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', model_name.lower()))
    sf_tokens   = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', sketchfab_name.lower()))
    # At least one meaningful token must overlap
    overlap = orig_tokens & sf_tokens
    # Exclude common generic words that cause false matches
    generic = {'the','and','for','with','day','scan','model','free','low','poly',
               'high','detail','game','ready','rigged','animated','pbr','military'}
    meaningful = overlap - generic
    return len(meaningful) > 0

def best_match(model_name, results):
    for r in results:
        if r["is_free"] and r["downloadable"]:
            if is_good_match(model_name, r["name"]):
                return r
    return None

with open(DATA) as f:
    models = json.load(f)

batch = models[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Searching batch {BATCH_START}–{BATCH_START+len(batch)-1} of {len(models)}")
found = skipped = 0

for m in batch:
    if m.get("sketchfab_id") or m.get("download_status") not in ("Pending", None, ""):
        skipped += 1
        continue

    name = m["model_name"]
    # Exact name
    match = best_match(name, search(name, military=False))
    # Fuzzy: base token + military
    if not match:
        base = re.split(r'[-/ ]', name)[0]
        if base and base != name and len(base) > 2:
            match = best_match(name, search(base, military=True))

    if match:
        m["sketchfab_id"]    = match["uid"]
        m["sketchfab_name"]  = match["name"]
        m["download_status"] = "Found on Sketchfab"
        print(f"  ✓ [{m['uid']}] {name[:35]} → {match['name'][:40]}")
        found += 1
    else:
        m["download_status"] = "Not Found"
        print(f"  ✗ [{m['uid']}] {name}")
    time.sleep(0.3)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone — found:{found} skipped:{skipped} not_found:{BATCH_SIZE-found-skipped}")
