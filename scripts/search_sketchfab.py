"""Step 1 — Search Sketchfab for each model, find free downloadable ones."""
import json, os, time, re, requests

TOKEN   = os.environ["SKETCHFAB_TOKEN"]
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

def search(query):
    r = requests.get(f"{BASE}/search", headers=HEADERS, timeout=15,
        params={"q": query, "type": "models", "downloadable": "true", "count": 5})
    if r.status_code != 200:
        return []
    return [{"uid": m["uid"], "name": m["name"],
             "is_free": m.get("price") is None,
             "downloadable": m.get("isDownloadable", False)}
            for m in r.json().get("results", [])]

def best_free(results):
    return next((r for r in results if r["is_free"] and r["downloadable"]), None)

with open(DATA) as f:
    models = json.load(f)

batch = models[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Batch {BATCH_START}–{BATCH_START+len(batch)-1} / {len(models)}")
found = 0

for m in batch:
    if m.get("sketchfab_id") or m.get("download_status") not in ("Pending", None, ""):
        continue
    name = m["model_name"]
    match = best_free(search(name))
    if not match:
        base = re.split(r'[-/ ]', name)[0]
        if base != name:
            match = best_free(search(f"{base} military"))
    if match:
        m["sketchfab_id"]   = match["uid"]
        m["sketchfab_name"] = match["name"]
        m["download_status"] = "Found on Sketchfab"
        print(f"  ✓ [{m['uid']}] {name} → {match['name']}")
        found += 1
    else:
        m["download_status"] = "Not Found"
        print(f"  ✗ [{m['uid']}] {name}")
    time.sleep(0.3)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone. Found {found} new matches.")
