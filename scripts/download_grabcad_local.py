"""
Run this LOCALLY (not on GitHub Actions) to download GrabCAD models.
GrabCAD blocks cloud/datacenter IPs - your local IP works fine.

Setup:
  pip install requests trimesh

Usage:
  set GRABCAD_SESSION=<your _grabcad_session cookie value>
  set GRABCAD_XSRF=<your XSRF-TOKEN cookie value>
  python download_grabcad_local.py

Or hardcode them below (lines marked EDIT).
"""
import json, os, re, time, zipfile, shutil, requests, sys

# ── EDIT THESE if you don't want to use env vars ──────────────────────────────
GRABCAD_SESSION = os.environ.get("GRABCAD_SESSION", "")  # _grabcad_session cookie
GRABCAD_XSRF    = os.environ.get("GRABCAD_XSRF",    "")  # XSRF-TOKEN cookie
# ─────────────────────────────────────────────────────────────────────────────

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DATA       = os.path.join(SCRIPT_DIR, "..", "data", "models.json")
OUT_DIR    = os.path.join(SCRIPT_DIR, "..", "downloaded_models")
AGENT      = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
FORMAT_PREF = ['.obj', '.stl', '.dae', '.ply', '.fbx', '.3ds', '.step', '.stp', '.iges']
CONVERT_EXTS = {'.obj', '.stl', '.dae', '.ply', '.glb', '.gltf'}

os.makedirs(OUT_DIR, exist_ok=True)

if not GRABCAD_SESSION or not GRABCAD_XSRF:
    print("ERROR: set GRABCAD_SESSION and GRABCAD_XSRF environment variables")
    print("  Get them from Chrome DevTools → Application → Cookies → grabcad.com")
    sys.exit(1)

# ── Session setup ─────────────────────────────────────────────────────────────
s = requests.Session()
s.headers.update({
    "User-Agent": AGENT,
    "Accept": "*/*",
    "Referer": "https://grabcad.com/library",
    "Origin":  "https://grabcad.com",
})
s.cookies.set("_grabcad_session", GRABCAD_SESSION, domain="grabcad.com")
s.cookies.set("XSRF-TOKEN",       GRABCAD_XSRF,    domain="grabcad.com")
s.headers["X-XSRF-TOKEN"] = requests.utils.unquote(GRABCAD_XSRF)

# Verify session
r = s.get("https://grabcad.com/community/api/v1/models",
          params={"query": "F-16", "per_page": 1}, timeout=15)
if r.status_code != 200:
    print(f"ERROR: GrabCAD session check failed (HTTP {r.status_code})")
    print("  Update your GRABCAD_SESSION and GRABCAD_XSRF cookies")
    sys.exit(1)
print(f"GrabCAD session OK\n")

# ── Helpers ───────────────────────────────────────────────────────────────────
def best_file_in_zip(zf):
    names = zf.namelist()
    for ext in FORMAT_PREF:
        for n in names:
            if n.lower().endswith(ext) and not os.path.basename(n).startswith('__'):
                return n
    return None

def try_convert_to_glb(src, dst):
    ext = os.path.splitext(src)[1].lower()
    if ext not in CONVERT_EXTS:
        return False
    if ext in ('.glb', '.gltf'):
        shutil.copy2(src, dst); return True
    try:
        import trimesh
        mesh = trimesh.load(src, force='mesh')
        if hasattr(mesh, 'export'):
            mesh.export(dst)
            return os.path.exists(dst) and os.path.getsize(dst) > 500
    except Exception as e:
        print(f"    trimesh: {e}")
    return False

def get_model_id(slug):
    """Search for model by slug to get its numeric ID."""
    query = slug.replace("-", " ")[:50]
    try:
        r = s.get("https://grabcad.com/community/api/v1/models",
                  params={"query": query, "per_page": 10}, timeout=15)
        if r.status_code != 200:
            return None
        data = r.json()
        items = data if isinstance(data, list) else data.get("models", data.get("results", []))
        for m in items:
            m_slug = m.get("slug") or m.get("url_identifier") or ""
            if m_slug == slug:
                return m.get("id")
        if items:
            return items[0].get("id")
    except Exception as e:
        print(f"    model ID lookup error: {e}")
    return None

def get_download_url(model_id, slug):
    """Get direct download URL for a GrabCAD model via API."""
    try:
        r = s.get(f"https://grabcad.com/community/api/v1/models/{model_id}", timeout=15)
        if r.status_code == 200:
            detail = r.json()
            # Look for files array
            for key in ("files", "cad_files", "documents"):
                files = detail.get(key, [])
                if isinstance(files, list) and files:
                    for f in files:
                        url = f.get("download_url") or f.get("url") or f.get("public_url")
                        if url:
                            return url
            # Some versions embed a direct download URL at top level
            url = detail.get("download_url") or detail.get("file_url")
            if url:
                return url
    except Exception as e:
        print(f"    detail API error: {e}")
    # Fallback: try the files/download endpoint with model_id
    return f"https://grabcad.com/community/api/v1/models/{model_id}/files/download"

def download_model(slug, uid):
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)
    zip_path = os.path.join(model_dir, f"{uid}_grabcad.zip")

    # Pre-visit model page to warm up session
    s.get(f"https://grabcad.com/library/{slug}", timeout=15)

    # Step 1: try direct download (no redirect follow - capture redirect location)
    r_check = s.get(f"https://grabcad.com/library/{slug}/download",
                    allow_redirects=False, timeout=30)

    download_url = None
    if r_check.status_code in (200, 206):
        # Direct file response
        download_url = f"https://grabcad.com/library/{slug}/download"
    elif r_check.status_code in (301, 302, 303, 307, 308):
        loc = r_check.headers.get("Location", "")
        if loc and ("s3.amazonaws.com" in loc or "grabcad" not in loc or "files/download" in loc):
            download_url = loc
            print(f"    redirect → {loc[:80]}")
        else:
            # Redirect to a page, not a file — use API instead
            print(f"    redirect to page, trying API")

    # Step 2: if no direct URL, look up via search API
    if not download_url:
        model_id = get_model_id(slug)
        if model_id:
            download_url = get_download_url(model_id, slug)
            print(f"    API: model_id={model_id} url={str(download_url)[:60]}")
        else:
            return None, "could not find model ID"

    # Step 3: download from resolved URL
    r = s.get(download_url, stream=True, timeout=120, allow_redirects=True)

    if r.status_code != 200:
        return None, f"HTTP {r.status_code} at {r.url[:80]}"

    size = 0
    with open(zip_path, "wb") as f:
        for chunk in r.iter_content(65536):
            f.write(chunk); size += len(chunk)

    if size < 500:
        os.remove(zip_path)
        return None, f"Response too small ({size} bytes)"

    # Extract ZIP
    try:
        with zipfile.ZipFile(zip_path, 'r') as zf:
            best = best_file_in_zip(zf)
            if not best:
                return None, f"No usable 3D file in ZIP ({zf.namelist()[:3]})"
            ext = os.path.splitext(best)[1].lower()
            native = os.path.join(model_dir, f"{uid}{ext}")
            with zf.open(best) as src_f, open(native, 'wb') as dst_f:
                shutil.copyfileobj(src_f, dst_f)
        os.remove(zip_path)
    except zipfile.BadZipFile:
        # Maybe not a ZIP — save as-is
        ext = '.bin'
        native = os.path.join(model_dir, f"{uid}{ext}")
        os.rename(zip_path, native)
    except Exception as e:
        return None, f"ZIP error: {e}"

    # Try GLB conversion
    glb = os.path.join(model_dir, f"{uid}.glb")
    if try_convert_to_glb(native, glb):
        return glb, "glb"
    return native, ext.lstrip('.')

# ── Main ──────────────────────────────────────────────────────────────────────
models = json.load(open(DATA))
queue  = [m for m in models if m.get("download_status") == "Found on GrabCAD"]
print(f"Found {len(queue)} GrabCAD models to download\n")

downloaded = failed = 0
for i, m in enumerate(queue):
    uid  = m["uid"]
    slug = m.get("grabcad_slug", "")
    name = m.get("model_name", "")
    print(f"[{i+1}/{len(queue)}] {uid}: {name!r}  slug={slug}")

    path, fmt = download_model(slug, uid)
    time.sleep(2)

    if path and os.path.exists(path) and os.path.getsize(path) > 500:
        m["download_status"] = "Downloaded"
        m["local_file"]      = path
        m["file_format"]     = fmt
        downloaded += 1
        print(f"  ✓ {fmt.upper()}  {os.path.getsize(path)//1024} KB")
    else:
        m["download_status"] = "Download Failed"
        m["local_file"]      = ""
        failed += 1
        print(f"  ✗ {fmt}")

    # Save progress every 10 models
    if (i + 1) % 10 == 0:
        json.dump(models, open(DATA, 'w'), indent=2)
        print(f"  --- Progress saved ({downloaded} ok, {failed} failed) ---")

json.dump(models, open(DATA, 'w'), indent=2)
print(f"\nDone. Downloaded: {downloaded} | Failed: {failed}")
print(f"Files saved to: {os.path.abspath(OUT_DIR)}")
