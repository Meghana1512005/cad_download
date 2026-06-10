"""Step 2 — Download GLB files for all models with a sketchfab_id."""
import json, os, time, requests

TOKEN   = os.environ["SKETCHFAB_TOKEN"]
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 50))

os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA) as f:
    models = json.load(f)

# Only process models that have a Sketchfab ID and aren't downloaded yet
queue = [m for m in models
         if m.get("sketchfab_id")
         and m.get("download_status") not in ("Downloaded", "Download Failed")]
batch = queue[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Downloading batch of {len(batch)} models")

# Track seen Sketchfab IDs to avoid duplicate downloads
seen = {}
downloaded = 0

for m in batch:
    uid_label = m["uid"]
    sf_id     = m["sketchfab_id"]

    # If same Sketchfab model already downloaded (e.g. BRZ-004 & BRZ-005)
    if sf_id in seen:
        src = seen[sf_id]
        fname = f"{uid_label}_{m['model_name'].replace(' ','_').replace('/','_')}.glb"
        dst = os.path.join(OUT_DIR, fname)
        import shutil
        shutil.copy(src, dst)
        m["download_status"] = "Downloaded (shared model)"
        m["local_file"]      = fname
        print(f"  ✓ [{uid_label}] Reused from {os.path.basename(src)}")
        downloaded += 1
        continue

    print(f"  [{uid_label}] Fetching URL for {sf_id}...")
    r = requests.get(f"{BASE}/models/{sf_id}/download", headers=HEADERS, timeout=15)
    if r.status_code != 200:
        m["download_status"] = f"Download Failed ({r.status_code})"
        print(f"    ✗ HTTP {r.status_code}: {r.text[:100]}")
        continue

    data = r.json()
    url  = (data.get("glb")    or {}).get("url") or \
           (data.get("gltf")   or {}).get("url") or \
           (data.get("source") or {}).get("url")
    ext  = ".glb" if data.get("glb") else ".zip"

    if not url:
        m["download_status"] = "Download Failed (no URL)"
        continue

    safe_name = m["model_name"].replace(" ","_").replace("/","_")[:50]
    fname = f"{uid_label}_{safe_name}{ext}"
    out   = os.path.join(OUT_DIR, fname)

    print(f"    Downloading {ext} ({(data.get('glb') or data.get('gltf') or data.get('source',{})).get('size',0)//1024} KB)...")
    dl = requests.get(url, stream=True, timeout=120)
    dl.raise_for_status()
    with open(out, "wb") as f:
        for chunk in dl.iter_content(65536):
            f.write(chunk)

    size_kb = os.path.getsize(out) // 1024
    print(f"    ✓ Saved: {fname} ({size_kb} KB)")
    m["download_status"] = "Downloaded"
    m["local_file"]      = fname
    seen[sf_id]          = out
    downloaded += 1
    time.sleep(0.5)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone. Downloaded {downloaded}/{len(batch)} models.")
