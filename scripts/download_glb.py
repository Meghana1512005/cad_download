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

seen = {}   # sketchfab_id -> local path (avoids re-downloading same model)
downloaded = 0

for m in batch:
    uid   = m["uid"]           # e.g. BRZ-003
    sf_id = m["sketchfab_id"]

    # Same Sketchfab model used for multiple UIDs (e.g. BRZ-004 & BRZ-005)
    if sf_id in seen:
        src_path = seen[sf_id]
        if src_path:
            ext   = os.path.splitext(src_path)[1]
            fname = f"{uid}{ext}"           # BRZ-005.glb
            dst   = os.path.join(OUT_DIR, fname)
            shutil.copy(src_path, dst)
            m["download_status"] = "Downloaded (shared model)"
            m["local_file"]      = fname
            print(f"  ✓ [{uid}] {fname}  (shared from {os.path.basename(src_path)})")
            downloaded += 1
        else:
            m["download_status"] = "Download Failed (shared model unavailable)"
        continue

    print(f"  [{uid}] Fetching download URL...")
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

    sz_kb = ((data.get("glb") or data.get("gltf") or data.get("source") or {}).get("size", 0)) // 1024
    print(f"    Downloading {sz_kb} KB → {uid}{ext}")

    dl = requests.get(url, stream=True, timeout=120)
    dl.raise_for_status()

    fname    = f"{uid}{ext}"            # BRZ-003.glb
    out_path = os.path.join(OUT_DIR, fname)
    with open(out_path, "wb") as f:
        for chunk in dl.iter_content(65536):
            f.write(chunk)

    actual_kb = os.path.getsize(out_path) // 1024
    print(f"    ✓ {fname}  ({actual_kb} KB)")
    m["download_status"] = "Downloaded"
    m["local_file"]      = fname
    seen[sf_id]          = out_path
    downloaded += 1
    time.sleep(0.5)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone — {downloaded}/{len(batch)} downloaded.")
