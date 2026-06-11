"""
Multi-source downloader:
- Sketchfab: direct GLB via API
- GrabCAD: direct download link
- Thingiverse: zip download via API
- Printables/Free3D: direct file URL
"""
import json, os, time, shutil, requests

TOKEN   = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
SF_HDR  = {"Authorization": f"Token {TOKEN}"}
SF_BASE = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 20))

os.makedirs(OUT_DIR, exist_ok=True)

with open(DATA) as f:
    models = json.load(f)

# Queue: models Found but not yet Downloaded
queue = [m for m in models
         if m.get("sketchfab_id")
         and m.get("download_status") in ("Found", "Found on Sketchfab")
         and "Downloaded" not in str(m.get("download_status", ""))]
batch = queue[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Downloading {len(batch)} models (queue {BATCH_START}–{BATCH_START+len(batch)-1})")

seen = {}
downloaded = 0

def download_from_sketchfab(uid, model_uid):
    """Download GLB from Sketchfab API."""
    r = requests.get(f"{SF_BASE}/models/{uid}/download", headers=SF_HDR, timeout=15)
    if r.status_code == 429:
        print(f"    ⚠ Rate limited, waiting 30s...")
        import time as t2; t2.sleep(30)
        r = requests.get(f"{SF_BASE}/models/{sf_id}/download", headers=SF_HDR, timeout=15)
    if r.status_code != 200:
        return None, f"SF HTTP {r.status_code}"
    data = r.json()
    url  = (data.get("glb") or {}).get("url") or \
           (data.get("gltf") or {}).get("url") or \
           (data.get("source") or {}).get("url")
    ext  = ".glb" if data.get("glb") else ".zip"
    if not url: return None, "No URL"
    sz   = ((data.get("glb") or data.get("gltf") or data.get("source") or {}).get("size", 0)) // 1024
    print(f"    Sketchfab GLB {sz} KB...")
    dl = requests.get(url, stream=True, timeout=120)
    dl.raise_for_status()
    model_dir = os.path.join(OUT_DIR, model_uid)
    os.makedirs(model_dir, exist_ok=True)
    out = os.path.join(model_dir, f"{model_uid}{ext}")
    with open(out, "wb") as f:
        for chunk in dl.iter_content(65536): f.write(chunk)
    return out, "OK"

def download_from_grabcad(url, model_uid):
    """Download from GrabCAD direct link."""
    # GrabCAD files are zip archives
    try:
        r = requests.get(url, timeout=30, allow_redirects=True,
                         headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200 and len(r.content) > 1000:
            model_dir = os.path.join(OUT_DIR, model_uid)
            os.makedirs(model_dir, exist_ok=True)
            out = os.path.join(model_dir, f"{model_uid}.zip")
            with open(out, "wb") as f: f.write(r.content)
            return out, "OK"
    except: pass
    return None, "GrabCAD download failed"

for m in batch:
    uid      = m["uid"]
    sf_id    = m.get("sketchfab_id")
    source   = m.get("source_site", "sketchfab.com")
    src_url  = m.get("source_url", "")
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)

    # Handle shared Sketchfab IDs (same model for multiple UIDs)
    if sf_id in seen:
        src_path = seen[sf_id]
        if src_path:
            ext = os.path.splitext(src_path)[1]
            dst = os.path.join(model_dir, f"{uid}{ext}")
            shutil.copy(src_path, dst)
            m["download_status"] = "Downloaded (shared)"
            m["local_file"] = os.path.join(uid, f"{uid}{ext}")
            print(f"  ✓ [{uid}] {uid}{ext} (shared)")
            downloaded += 1
        continue

    print(f"  [{uid}] {m['model_name'][:40]} [{source}]")

    out_path, status = None, "No method"

    if "sketchfab" in source:
        out_path, status = download_from_sketchfab(sf_id, uid)
    elif "grabcad" in source:
        out_path, status = download_from_grabcad(src_url, uid)
    else:
        # Try direct URL download
        try:
            r = requests.get(src_url, timeout=30, allow_redirects=True,
                             headers={"User-Agent": "Mozilla/5.0"})
            if r.status_code == 200 and len(r.content) > 1000:
                ext = ".glb" if b"glTF" in r.content[:4] else ".zip"
                out_path = os.path.join(model_dir, f"{uid}{ext}")
                with open(out_path, "wb") as f: f.write(r.content)
                status = "OK"
        except Exception as e:
            status = str(e)[:50]

    if out_path and os.path.getsize(out_path) > 500:
        kb = os.path.getsize(out_path) // 1024
        print(f"    ✓ {uid}/{os.path.basename(out_path)} ({kb} KB)")
        m["download_status"] = "Downloaded"
        m["local_file"] = os.path.join(uid, os.path.basename(out_path))
        seen[sf_id] = out_path
        downloaded += 1
    else:
        print(f"    ✗ {status}")
        m["download_status"] = f"Download Failed ({status})"
        seen[sf_id] = None

    time.sleep(2)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nDone — {downloaded}/{len(batch)} downloaded.")
