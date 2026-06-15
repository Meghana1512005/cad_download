"""
Download models found on GrabCAD and CadNav.
- GrabCAD: login -> download ZIP -> extract best 3D file -> convert to GLB if possible
- CadNav:  2-step download (get uhash -> download file) -> convert to GLB if possible

Files saved to: downloaded_models/{UID}/{UID}.{ext}
GLB conversion attempted via trimesh (OBJ/STL/DAE/PLY -> GLB).
"""
import json, os, re, time, zipfile, shutil, requests, tempfile
from grabcad_client import GrabCADClient

DATA         = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
OUT_DIR      = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START  = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE   = int(os.environ.get("BATCH_SIZE", 50))
GRABCAD_USER = os.environ.get("GRABCAD_USER", "")
GRABCAD_PASS = os.environ.get("GRABCAD_PASS", "")
AGENT        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# GLB conversion priority (trimesh-supported formats)
CONVERT_EXTS = {'.obj', '.stl', '.dae', '.ply', '.glb', '.gltf'}
# Download preference order for GrabCAD ZIP contents
FORMAT_PREF  = ['.obj', '.stl', '.dae', '.ply', '.fbx', '.3ds', '.step', '.stp', '.iges']

os.makedirs(OUT_DIR, exist_ok=True)

# ── trimesh conversion ────────────────────────────────────────────────────────
def try_convert_to_glb(src_path, out_glb_path):
    """Try to convert src_path to GLB. Returns True on success."""
    ext = os.path.splitext(src_path)[1].lower()
    if ext not in CONVERT_EXTS:
        return False
    if ext in ('.glb', '.gltf'):
        shutil.copy2(src_path, out_glb_path)
        return True
    try:
        import trimesh
        mesh = trimesh.load(src_path, force='mesh')
        if hasattr(mesh, 'export'):
            mesh.export(out_glb_path)
            if os.path.exists(out_glb_path) and os.path.getsize(out_glb_path) > 500:
                return True
    except Exception as e:
        print(f"    trimesh convert failed ({ext}): {e}")
    return False

def best_file_in_zip(zf):
    """Pick the best 3D file from a ZIP archive based on FORMAT_PREF."""
    names = zf.namelist()
    for ext in FORMAT_PREF:
        for n in names:
            if n.lower().endswith(ext) and not os.path.basename(n).startswith('__'):
                return n
    return None

# ── GrabCAD ───────────────────────────────────────────────────────────────────
gc = None
if GRABCAD_USER and GRABCAD_PASS:
    print(f"Logging into GrabCAD ({GRABCAD_USER[:6]}***)...")
    gc = GrabCADClient(GRABCAD_USER, GRABCAD_PASS)
    if not gc.logged_in:
        print("GrabCAD login failed")
        gc = None
    else:
        print("GrabCAD ready")

def download_from_grabcad(slug, uid):
    if not gc:
        return None, "No GrabCAD session"
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)
    zip_path = os.path.join(model_dir, f"{uid}_grabcad.zip")

    ok = gc.download(slug, zip_path)
    if not ok or not os.path.exists(zip_path) or os.path.getsize(zip_path) < 500:
        return None, "GrabCAD download failed or empty"

    # Extract ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            best = best_file_in_zip(zf)
            if not best:
                return None, "No usable 3D file in ZIP"
            ext = os.path.splitext(best)[1].lower()
            native_path = os.path.join(model_dir, f"{uid}{ext}")
            with zf.open(best) as src, open(native_path, 'wb') as dst:
                shutil.copyfileobj(src, dst)
        os.remove(zip_path)
    except Exception as e:
        return None, f"ZIP extract error: {e}"

    # Try GLB conversion
    glb_path = os.path.join(model_dir, f"{uid}.glb")
    if try_convert_to_glb(native_path, glb_path):
        return glb_path, "glb"
    # Return native format
    return native_path, ext.lstrip('.')

# ── CadNav ────────────────────────────────────────────────────────────────────
cn = requests.Session()
cn.headers["User-Agent"] = AGENT

def download_from_cadnav(cadnav_id, uid):
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)

    # Step 1: get intermediate page with uhash
    step1_url = f"https://www.cadnav.com/plus/download.php?open=0&aid={cadnav_id}&cid=3"
    try:
        r1 = cn.get(step1_url, timeout=15)
        if r1.status_code != 200:
            return None, f"CadNav step1 HTTP {r1.status_code}"
        uhash_match = re.search(
            r'href="/plus/download\.php\?open=2&(?:amp;)?id=\d+&(?:amp;)?uhash=([a-f0-9]+)"',
            r1.text)
        if not uhash_match:
            # Try alternate format
            uhash_match = re.search(r'uhash=([a-f0-9]+)', r1.text)
        if not uhash_match:
            return None, "CadNav: uhash not found in step1 page"
        uhash = uhash_match.group(1)
    except Exception as e:
        return None, f"CadNav step1 error: {e}"

    # Step 2: follow download link
    step2_url = f"https://www.cadnav.com/plus/download.php?open=2&id={cadnav_id}&uhash={uhash}"
    try:
        r2 = cn.get(step2_url, timeout=60, stream=True, allow_redirects=True)
        if r2.status_code != 200:
            return None, f"CadNav step2 HTTP {r2.status_code}"

        # Detect extension from Content-Disposition or URL
        cd = r2.headers.get("Content-Disposition", "")
        fname_match = re.search(r'filename[^;=\n]*=[\s"\']*([^\n;"\']+)', cd)
        if fname_match:
            ext = os.path.splitext(fname_match.group(1).strip())[1].lower()
        else:
            ext = os.path.splitext(r2.url.split('?')[0])[1].lower() or '.bin'

        native_path = os.path.join(model_dir, f"{uid}{ext}")
        with open(native_path, 'wb') as f:
            for chunk in r2.iter_content(65536):
                f.write(chunk)

        if os.path.getsize(native_path) < 500:
            os.remove(native_path)
            return None, "CadNav: downloaded file too small"

    except Exception as e:
        return None, f"CadNav step2 error: {e}"

    # Try GLB conversion
    glb_path = os.path.join(model_dir, f"{uid}.glb")
    if try_convert_to_glb(native_path, glb_path):
        return glb_path, "glb"
    return native_path, ext.lstrip('.')

# ── Main ──────────────────────────────────────────────────────────────────────
models = json.load(open(DATA))
queue  = [m for m in models
          if m.get("download_status") in ("Found on GrabCAD", "Found on CadNav")
          and "Downloaded" not in str(m.get("download_status", ""))]
batch  = queue[BATCH_START: BATCH_START + BATCH_SIZE]

print(f"Queue: {len(queue)} | Batch: [{BATCH_START}:{BATCH_START+len(batch)}] ({len(batch)} models)\n")

downloaded = failed = 0

for m in batch:
    uid    = m["uid"]
    status = m.get("download_status", "")

    if status == "Found on GrabCAD":
        slug = m.get("grabcad_slug", "")
        if not slug:
            print(f"  [SKIP] {uid}: no grabcad_slug")
            continue
        print(f"  [GrabCAD] {uid}: {m.get('model_name','')!r}  slug={slug}")
        path, fmt = download_from_grabcad(slug, uid)
        time.sleep(3)

    elif status == "Found on CadNav":
        cadnav_id = m.get("cadnav_id", "")
        if not cadnav_id:
            print(f"  [SKIP] {uid}: no cadnav_id")
            continue
        print(f"  [CadNav]  {uid}: {m.get('model_name','')!r}  id={cadnav_id}")
        path, fmt = download_from_cadnav(cadnav_id, uid)
        time.sleep(2)

    else:
        continue

    if path and os.path.exists(path) and os.path.getsize(path) > 500:
        m["download_status"] = "Downloaded"
        m["local_file"]      = path
        m["file_format"]     = fmt
        downloaded += 1
        size_kb = os.path.getsize(path) // 1024
        print(f"    OK  {fmt.upper()}  {size_kb} KB")
    else:
        m["download_status"] = "Download Failed"
        m["local_file"]      = ""
        failed += 1
        print(f"    FAILED: {fmt}")

json.dump(models, open(DATA, "w"), indent=2)
print(f"\nDone. Downloaded: {downloaded} | Failed: {failed}")

# Write debug summary
with open(os.path.join(os.path.dirname(DATA), "download_debug_gc_cn.txt"), "w") as f:
    f.write(f"queue={len(queue)} batch={len(batch)} downloaded={downloaded} failed={failed}\n")
