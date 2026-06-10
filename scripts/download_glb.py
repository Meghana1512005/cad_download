import json, os, time, shutil, requests

TOKEN   = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 20))

os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA) as f:
    models = json.load(f)

queue = [m for m in models
         if m.get("sketchfab_id")
         and m.get("download_status") not in ("Downloaded", "Download Failed", "Downloaded (shared model)")]
batch = queue[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Downloading {len(batch)} models (queue index {BATCH_START}–{BATCH_START+len(batch)-1})")

seen = {}
downloaded = 0

for m in batch:
    uid_label = m["uid"]
    sf_id     = m["sketchfab_id"]
    safe_name = m["model_name"].replace(" ","_").replace("/","_")[:50]

    if sf_id in seen and seen[sf_id]:
        fname = f"{uid_label}_{safe_name}.glb"
        dst = os.path.join(OUT_DIR, fname)
        shutil.copy(seen[sf_id], dst)
        m["download_status"] = "Downloaded (shared model)"
        m["local_file"] = fname
        print(f"  ✓ [{uid_label}] Reused from previous download")
        downloaded += 1
        continue

    print(f"  [{uid_label}] Fetching URL for {sf_id}...")
    r = requests.get(f"{BASE}/models/{sf_id}/download", headers=HEADERS, timeout=15)
    if r.status_code != 200:
        m["download_status"] = f"Download Failed ({r.status_code})"
        seen[sf_id] = None
        print(f"    ✗ HTTP {r.status_code}")
        continue

    data = r.json()
    glb  = (data.get("glb")    or {}).get("url")
    gltf = (data.get("gltf")   or {}).get("url")
    src  = (data.get("source") or {}).get("url")
    url  = glb or gltf or src
    ext  = ".glb" if glb else ".zip"

    if not url:
        m["download_status"] = "Download Failed (no URL)"
        seen[sf_id] = None
        continue

    sz = ((data.get("glb") or data.get("gltf") or data.get("source") or {}).get("size", 0)) // 1024
    print(f"    Downloading {sz} KB...")
    dl = requests.get(url, stream=True, timeout=120)
    dl.raise_for_status()

    fname = f"{uid_label}_{safe_name}{ext}"
    out   = os.path.join(OUT_DIR, fname)
    with open(out, "wb") as f:
        for chunk in dl.iter_content(65536):
            f.write(chunk)

    actual_kb = os.path.getsize(out) // 1024
    print(f"    ✓ {fname} ({actual_kb} KB)")
    m["download_status"] = "Downloaded"
    m["local_file"] = fname
    seen[sf_id] = out
    downloaded += 1
    time.sleep(0.5)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone — {downloaded}/{len(batch)} downloaded.")
