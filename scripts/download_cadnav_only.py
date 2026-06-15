"""
CadNav-only downloader for scheduled runs.
Reads batch position from data/cadnav_pos.txt, downloads BATCH_SIZE models,
advances position, writes back.
"""
import json, os, re, time, shutil, requests, sys

DATA     = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
POS_FILE = os.path.join(os.path.dirname(__file__), "..", "data", "cadnav_pos.txt")
OUT_DIR  = os.path.join(os.path.dirname(__file__), "..", "downloaded_models")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 3))
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

CONVERT_EXTS = {'.obj', '.stl', '.dae', '.ply', '.glb', '.gltf'}
os.makedirs(OUT_DIR, exist_ok=True)

cn = requests.Session()
cn.headers.update({
    "User-Agent": AGENT,
    "Accept": "text/html,application/xhtml+xml,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.5",
})

CADNAV_CIDS = [3, 1, 2, 4, 5, 6]

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

def cadnav_get_uhash(cadnav_id, model_page, stored_cid=None):
    cids = CADNAV_CIDS[:]
    if stored_cid and stored_cid in cids:
        cids.remove(stored_cid); cids.insert(0, stored_cid)
    for cid in cids:
        url = f"https://www.cadnav.com/plus/download.php?open=0&aid={cadnav_id}&cid={cid}"
        cn.headers["Referer"] = model_page
        try:
            r = cn.get(url, timeout=20, allow_redirects=True)
            if r.status_code != 200:
                continue
            m = re.search(r'href="[^"]*download\.php\?open=2&(?:amp;)?id=\d+&(?:amp;)?uhash=([a-f0-9A-F0-9]+)"', r.text)
            if not m:
                m = re.search(r'uhash=([a-f0-9A-F0-9]{8,})', r.text)
            if m:
                print(f"    uhash found (cid={cid})")
                return m.group(1), cid
            time.sleep(0.5)
        except Exception as e:
            print(f"    step1 cid={cid} error: {e}")
    return None, None

def download_cadnav(cadnav_id, uid, stored_cid=None):
    model_dir = os.path.join(OUT_DIR, uid)
    os.makedirs(model_dir, exist_ok=True)
    model_page = f"https://www.cadnav.com/3d-models/model-{cadnav_id}.html"

    try:
        rp = cn.get(model_page, timeout=15)
        print(f"    model page HTTP {rp.status_code}")
    except Exception as e:
        print(f"    model page error: {e}")

    uhash, used_cid = cadnav_get_uhash(cadnav_id, model_page, stored_cid)
    if not uhash:
        return None, "uhash not found"

    step2 = f"https://www.cadnav.com/plus/download.php?open=2&id={cadnav_id}&uhash={uhash}"
    cn.headers["Referer"] = f"https://www.cadnav.com/plus/download.php?open=0&aid={cadnav_id}&cid={used_cid}"
    try:
        r2 = cn.get(step2, timeout=60, stream=True, allow_redirects=True)
        if r2.status_code != 200:
            return None, f"step2 HTTP {r2.status_code}"

        cd = r2.headers.get("Content-Disposition", "")
        fm = re.search(r'filename[^;=\n]*=[\s"\']*([^\n;"\']+)', cd)
        ext = os.path.splitext(fm.group(1).strip())[1].lower() if fm else \
              os.path.splitext(r2.url.split('?')[0])[1].lower() or '.bin'

        native = os.path.join(model_dir, f"{uid}{ext}")
        size = 0
        with open(native, 'wb') as f:
            for chunk in r2.iter_content(65536):
                f.write(chunk); size += len(chunk)

        if size < 500:
            body = open(native,'rb').read().decode('utf-8','replace')
            os.remove(native)
            return None, f"small ({size}b): {body[:80]!r}"

        print(f"    downloaded {size} bytes, ext={ext}")
        glb = os.path.join(model_dir, f"{uid}.glb")
        if try_convert_to_glb(native, glb):
            return glb, "glb"
        return native, ext.lstrip('.')
    except Exception as e:
        return None, f"step2 error: {e}"

# ── Main ──────────────────────────────────────────────────────────────────────
models = json.load(open(DATA))
queue  = [m for m in models if m.get("download_status") == "Found on CadNav"]
batch  = queue[BATCH_START: BATCH_START + BATCH_SIZE]

print(f"CadNav queue: {len(queue)} | Batch [{BATCH_START}:{BATCH_START+len(batch)}]")

downloaded = failed = 0
for m in batch:
    uid = m["uid"]
    cid = m.get("cadnav_id", "")
    print(f"\n  [{uid}] {m.get('model_name','')} id={cid}")
    path, fmt = download_cadnav(cid, uid, m.get("cadnav_cid"))
    time.sleep(2)

    if path and os.path.exists(path) and os.path.getsize(path) > 500:
        m["download_status"] = "Downloaded"
        m["local_file"] = path
        m["file_format"] = fmt
        downloaded += 1
        print(f"    OK {fmt.upper()} {os.path.getsize(path)//1024} KB")
    else:
        m["download_status"] = "Download Failed"
        m["local_file"] = ""
        failed += 1
        print(f"    FAILED: {fmt}")

# Advance position (skip failed ones too — they'll be retried separately)
new_pos = BATCH_START + len(batch)
if new_pos >= len(queue):
    new_pos = 0  # wrap around
open(POS_FILE, 'w').write(str(new_pos))

json.dump(models, open(DATA, 'w'), indent=2)
print(f"\nDone: downloaded={downloaded} failed={failed} next_pos={new_pos}")
