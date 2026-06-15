"""
Download models found on GrabCAD and CadNav.
- GrabCAD: cookie-based session -> download ZIP -> extract best 3D file -> convert to GLB if possible
- CadNav:  2-step download (get uhash -> download file) -> convert to GLB if possible

Files saved to: downloaded_models/{UID}/{UID}.{ext}
GLB conversion attempted via trimesh (OBJ/STL/DAE/PLY -> GLB).
"""
import json, os, re, time, zipfile, shutil, requests, sys

# Add scripts dir to path so grabcad_client import works
sys.path.insert(0, os.path.dirname(__file__))
from grabcad_client import GrabCADClient

DATA         = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
OUT_DIR      = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START  = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE   = int(os.environ.get("BATCH_SIZE", 50))
AGENT        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

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
print("Initializing GrabCAD client (cookie-based)...")
gc = GrabCADClient()  # reads GRABCAD_SESSION + GRABCAD_XSRF from env
if not gc.logged_in:
    print("WARNING: GrabCAD session not available — GrabCAD downloads will be skipped")
    gc = None
else:
    print("GrabCAD ready")

def find_grabcad_direct_url(slug):
    """Try to find a direct file download URL via the GrabCAD API."""
    try:
        # Search for the model to get its ID
        r = gc.s.get(f"{gc.API}/models",
                     params={"query": slug.replace("-", " "), "per_page": 5}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        items = data if isinstance(data, list) else data.get("models", data.get("results", []))
        # Find the matching slug
        mid = None
        for m in items:
            m_slug = (m.get("slug") or m.get("url_identifier") or "")
            if m_slug == slug or slug in m_slug:
                mid = m.get("id")
                break
        if not mid and items:
            mid = items[0].get("id")
        if not mid:
            return None
        # Try model detail endpoint for file list
        r2 = gc.s.get(f"{gc.API}/models/{mid}", timeout=15)
        if r2.status_code == 200:
            detail = r2.json()
            # Look for file download URLs in the response
            for key in ("files", "cad_files", "documents"):
                files = detail.get(key, [])
                if isinstance(files, list):
                    for f in files:
                        url = f.get("url") or f.get("download_url") or f.get("public_url")
                        if url:
                            return url
        # Try direct API download endpoint
        r3 = gc.s.get(f"{gc.BASE}/library/{slug}/download/free",
                      allow_redirects=False, timeout=15)
        if r3.status_code in (301, 302, 303, 307, 308):
            loc = r3.headers.get("Location", "")
            if loc and not "grabcad.com/library" in loc:
                return loc  # External URL (S3 etc)
    except Exception as e:
        print(f"    GrabCAD API probe error: {e}")
    return None

def download_from_grabcad(slug, uid):
    if not gc:
        return None, "No GrabCAD session (check GRABCAD_SESSION + GRABCAD_XSRF secrets)"
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)
    zip_path = os.path.join(model_dir, f"{uid}_grabcad.zip")

    # First try: direct /download endpoint
    ok = gc.download(slug, zip_path)

    # If that fails, try to find a direct URL via API
    if not ok or not os.path.exists(zip_path) or os.path.getsize(zip_path) < 500:
        print(f"    Direct download failed, probing GrabCAD API...")
        direct_url = find_grabcad_direct_url(slug)
        if direct_url:
            print(f"    Found direct URL: {direct_url[:80]}")
            try:
                r = gc.s.get(direct_url, stream=True, timeout=60, allow_redirects=True)
                if r.status_code == 200:
                    with open(zip_path, "wb") as f:
                        for chunk in r.iter_content(65536):
                            f.write(chunk)
                    if os.path.getsize(zip_path) > 500:
                        ok = True
            except Exception as e:
                print(f"    Direct URL download error: {e}")

    if not ok or not os.path.exists(zip_path) or os.path.getsize(zip_path) < 500:
        # Log diagnostic info to file
        diag_info = "GrabCAD diag: unknown"
        try:
            r_diag = gc.s.get(f"https://grabcad.com/library/{slug}/download",
                              allow_redirects=True, timeout=20)
            snippet = r_diag.content[:150].decode('utf-8', errors='replace') if r_diag.content else "(empty)"
            diag_info = f"HTTP {r_diag.status_code} url={r_diag.url[:80]} body={snippet!r}"
            print(f"    Diag: {diag_info}")
        except Exception as e:
            diag_info = f"error: {e}"
            print(f"    Diag error: {e}")
        return None, f"GrabCAD: {diag_info}"

    # Extract ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            best = best_file_in_zip(zf)
            if not best:
                all_names = zf.namelist()
                print(f"    ZIP contents: {all_names[:5]}")
                return None, f"No usable 3D file in ZIP (has {len(all_names)} files)"
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
    return native_path, ext.lstrip('.')

# ── CadNav ────────────────────────────────────────────────────────────────────
cn = requests.Session()
cn.headers.update({
    "User-Agent": AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

CADNAV_CIDS = [3, 1, 2, 4, 5, 6]  # try weapons first, then aircraft, vehicle, watercraft

def cadnav_get_uhash(cadnav_id, model_page, cid_order=None):
    """Try cid=3,1,2,4,5,6 until step1 returns a valid uhash. Returns (uhash, cid) or (None, None)."""
    for cid in (cid_order or CADNAV_CIDS):
        url = f"https://www.cadnav.com/plus/download.php?open=0&aid={cadnav_id}&cid={cid}"
        cn.headers["Referer"] = model_page
        try:
            r = cn.get(url, timeout=20, allow_redirects=True)
            if r.status_code != 200:
                continue
            match = re.search(
                r'href="[^"]*download\.php\?open=2&(?:amp;)?id=\d+&(?:amp;)?uhash=([a-f0-9A-F0-9]+)"',
                r.text)
            if not match:
                match = re.search(r'uhash=([a-f0-9A-F0-9]{8,})', r.text)
            if match:
                print(f"    CadNav uhash found with cid={cid}")
                return match.group(1), cid
            time.sleep(0.5)
        except Exception as e:
            print(f"    CadNav step1 cid={cid} error: {e}")
    return None, None

def download_from_cadnav(cadnav_id, uid, stored_cid=None):
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)

    # Pre-visit the model page to establish session cookie + Referer
    model_page = f"https://www.cadnav.com/3d-models/model-{cadnav_id}.html"
    try:
        rp = cn.get(model_page, timeout=15, allow_redirects=True)
        print(f"    CadNav model page HTTP {rp.status_code} (pre-visit)")
    except Exception as e:
        print(f"    CadNav model page pre-visit failed: {e} — continuing anyway")

    # Step 1: try multiple cids to find uhash
    # Reorder cids: try stored_cid first if available
    cid_order = CADNAV_CIDS[:]
    if stored_cid and stored_cid in cid_order:
        cid_order.remove(stored_cid)
        cid_order.insert(0, stored_cid)
    uhash, used_cid = cadnav_get_uhash(cadnav_id, model_page, cid_order)
    if not uhash:
        return None, f"CadNav: uhash not found after trying cids {CADNAV_CIDS}"

    # Step 2: follow download link
    step2_url = f"https://www.cadnav.com/plus/download.php?open=2&id={cadnav_id}&uhash={uhash}"
    cn.headers["Referer"] = f"https://www.cadnav.com/plus/download.php?open=0&aid={cadnav_id}&cid={used_cid}"
    try:
        r2 = cn.get(step2_url, timeout=60, stream=True, allow_redirects=True)
        if r2.status_code != 200:
            return None, f"CadNav step2 HTTP {r2.status_code} (url={r2.url})"

        # Detect extension from Content-Disposition or URL
        cd = r2.headers.get("Content-Disposition", "")
        fname_match = re.search(r'filename[^;=\n]*=[\s"\']*([^\n;"\']+)', cd)
        if fname_match:
            ext = os.path.splitext(fname_match.group(1).strip())[1].lower()
        else:
            ext = os.path.splitext(r2.url.split('?')[0])[1].lower() or '.bin'

        native_path = os.path.join(model_dir, f"{uid}{ext}")
        size = 0
        with open(native_path, 'wb') as f:
            for chunk in r2.iter_content(65536):
                f.write(chunk)
                size += len(chunk)

        print(f"    CadNav downloaded {size} bytes, ext={ext}, CD={cd[:80]!r}")

        if size < 500:
            body_str = ""
            try:
                with open(native_path, 'rb') as ff:
                    body_str = ff.read().decode('utf-8', errors='replace')
                print(f"    CadNav small response body: {body_str!r}")
            except:
                pass
            os.remove(native_path)
            return None, f"CadNav({size}b): {body_str[:80]!r}"

    except Exception as e:
        return None, f"CadNav step2 error: {e}"

    # Try GLB conversion
    glb_path = os.path.join(model_dir, f"{uid}.glb")
    if try_convert_to_glb(native_path, glb_path):
        return glb_path, "glb"
    return native_path, ext.lstrip('.')

# ── Main ──────────────────────────────────────────────────────────────────────
models = json.load(open(DATA))
# Include both "Found on X" and "Download Failed" (retry failed ones)
queue  = [m for m in models
          if m.get("download_status") in ("Found on GrabCAD", "Found on CadNav", "Download Failed")]
batch  = queue[BATCH_START: BATCH_START + BATCH_SIZE]

print(f"\nQueue: {len(queue)} | Batch: [{BATCH_START}:{BATCH_START+len(batch)}] ({len(batch)} models)\n")

downloaded = failed = skipped = 0
errors = []

for m in batch:
    uid    = m["uid"]
    status = m.get("download_status", "")

    # Determine source: prefer source fields over status string
    is_grabcad = bool(m.get("grabcad_slug")) and status in ("Found on GrabCAD", "Download Failed")
    is_cadnav  = bool(m.get("cadnav_id"))   and status in ("Found on CadNav",  "Download Failed")
    # If Download Failed, pick whichever source field exists
    if status == "Download Failed":
        is_grabcad = bool(m.get("grabcad_slug")) and not bool(m.get("cadnav_id"))
        is_cadnav  = bool(m.get("cadnav_id"))

    if is_grabcad:
        slug = m.get("grabcad_slug", "")
        print(f"  [GrabCAD] {uid}: {m.get('model_name','')!r}  slug={slug}")
        path, fmt = download_from_grabcad(slug, uid)
        time.sleep(3)

    elif is_cadnav:
        cadnav_id = m.get("cadnav_id", "")
        print(f"  [CadNav]  {uid}: {m.get('model_name','')!r}  id={cadnav_id}")
        stored_cid = m.get("cadnav_cid")
        path, fmt = download_from_cadnav(cadnav_id, uid, stored_cid=stored_cid)
        time.sleep(2)

    else:
        print(f"  [SKIP] {uid}: status={status!r} no valid source fields")
        skipped += 1
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
        errors.append(f"{uid}: {fmt}")
        print(f"    FAILED: {fmt}")

json.dump(models, open(DATA, "w"), indent=2)
print(f"\nDone. Downloaded={downloaded} | Failed={failed} | Skipped={skipped}")
if errors:
    print("\nFailed models:")
    for e in errors:
        print(f"  {e}")

# Write debug summary
debug_path = os.path.join(os.path.dirname(DATA), "download_debug_gc_cn.txt")
with open(debug_path, "w") as f:
    f.write(f"queue={len(queue)} batch={len(batch)} downloaded={downloaded} failed={failed} skipped={skipped}\n")
    if errors:
        f.write("\nErrors:\n")
        for e in errors:
            f.write(f"  {e}\n")
    f.write("\nNote: full body/diagnostic output is in GitHub Actions run log\n")
