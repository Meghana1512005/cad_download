"""
Multi-source CAD search:
1. Sketchfab       — API, GLB, free ✓
2. Printables      — public GraphQL, STL/3MF, free ✓
3. SketchUp 3D Warehouse — public API, SKP/OBJ ✓
4. NASA 3D Resources — public, OBJ, free ✓
5. Free3D          — HTML scrape, OBJ/FBX ✓
(GrabCAD API deprecated — removed)
"""
import json, os, time, re, requests
from urllib.parse import quote

SF_TOKEN  = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
TV_TOKEN  = os.environ.get("THINGIVERSE_TOKEN", "")
SF_HDR    = {"Authorization": f"Token {SF_TOKEN}"}
SF_BASE   = "https://api.sketchfab.com/v3"
DATA      = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

# Verify Sketchfab
me = requests.get(f"{SF_BASE}/me", headers=SF_HDR, timeout=10)
if me.status_code != 200:
    print(f"Sketchfab auth failed ({me.status_code})"); exit(1)
print(f"✓ Sketchfab: {me.json().get('username')}")

# ── Quality filter ─────────────────────────────────────────────────────────────
JUNK = re.compile(
    r'residên|residencia|projeto|unifamiliar|funerária|urna funer|simplified 3d mesh|'
    r'weapon pack of|modular wall|nyc door|maytoni|sword from vimose|opait|blend compress|'
    r'green wall blend|2015 11 25|lustr[aа]|люстра|rc247|day \d+:|1scanaday|wwe\b|'
    r'campground|gas station|lego minifig|necklace|fiat 500|mega phoenix|wild wing|'
    r'minecraft|fortnite|apartment m2|m2 residencia|pav\. qd|recanto|sofa\b|'
    r'cold sv \d|son cold|park scenery|nature scene', re.I)

def is_good(model_name, result_name):
    if JUNK.search(result_name): return False
    # Check letter overlap (3+ chars) OR 2-letter military code overlap
    orig_long  = set(re.findall(r'[A-Za-z]{3,}', model_name.lower()))
    res_long   = set(re.findall(r'[A-Za-z]{3,}', result_name.lower()))
    orig_short = set(re.findall(r'\b[A-Z]{2}\b', model_name))   # 2-letter codes e.g. PC, DF
    res_short  = set(re.findall(r'\b[A-Z]{2}\b', result_name.upper()))
    generic = {'the','and','for','with','free','low','poly','high','detail','game',
               'ready','rigged','model','type','class','mark','series','scale',
               'military','vehicle','aircraft','print','design','part'}
    long_overlap  = (orig_long  & res_long)  - generic
    short_overlap = orig_short & res_short
    return len(long_overlap) > 0 or len(short_overlap) > 0

def fuzzy_queries(name, domain):
    q = [name]
    base = re.sub(r'\s+(Mk|Block|Phase|Series)\s*\w+$', '', name, flags=re.I).strip()
    if base != name: q.append(base)
    m = re.match(r'^([A-Za-z][A-Za-z0-9\-\.]*?[0-9]+)', name)
    if m and m.group(1) != name: q.append(m.group(1))
    dom = {'AIR':'aircraft','HEL':'helicopter','UAV':'drone uav','MSL':'missile ballistic',
           'NAV':'warship','AFV':'tank armored','ART':'artillery','ADS':'air defense sam',
           'ALM':'missile weapon'}
    if domain in dom:
        q.append(f"{name} {dom[domain]}")
        if base != name: q.append(f"{base} {dom[domain]}")
    return q[:5]

# ── Source 1: Sketchfab ───────────────────────────────────────────────────────
def search_sketchfab(q):
    try:
        r = requests.get(f"{SF_BASE}/search", headers=SF_HDR, timeout=15,
            params={"q": q, "type": "models", "downloadable": "true", "count": 10})
        if r.status_code != 200: return []
        return [{"uid": m["uid"], "name": m["name"], "source": "sketchfab.com",
                 "url": f"https://sketchfab.com/3d-models/{m['uid']}",
                 "is_free": m.get("price") is None, "format": "GLB/GLTF"}
                for m in r.json().get("results", [])]
    except: return []

# ── Source 2: Thingiverse ─────────────────────────────────────────────────────
def search_thingiverse(q):
    if not TV_TOKEN: return []
    try:
        r = requests.get(f"https://api.thingiverse.com/search/{quote(q)}",
            params={"type": "things", "per_page": 8},
            headers={"Authorization": f"Bearer {TV_TOKEN}"}, timeout=15)
        if r.status_code != 200: return []
        hits = r.json() if isinstance(r.json(), list) else r.json().get("hits", [])
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "thingiverse.com",
                 "url": f"https://www.thingiverse.com/thing:{m.get('id','')}",
                 "is_free": True, "format": "STL"}
                for m in hits[:8] if isinstance(m, dict)]
    except: return []

# ── Source 3: Printables ──────────────────────────────────────────────────────
def search_printables(q):
    try:
        payload = {"operationName":"SearchResultsQuery",
                   "variables":{"query": q, "limit": 8, "offset": 0},
                   "query":"query SearchResultsQuery($query:String!,$limit:Int,$offset:Int)"
                           "{searchPrints(query:$query,limit:$limit,offset:$offset)"
                           "{hits{id name slug}}}"}
        r = requests.post("https://api.printables.com/graphql/", json=payload, timeout=15,
            headers={"Content-Type":"application/json","User-Agent": AGENT})
        if r.status_code != 200: return []
        hits = r.json().get("data",{}).get("searchPrints",{}).get("hits",[]) or []
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "printables.com",
                 "url": f"https://www.printables.com/model/{m.get('id','')}",
                 "is_free": True, "format": "STL/3MF"}
                for m in hits[:8] if isinstance(m, dict)]
    except: return []

# ── Source 4: SketchUp 3D Warehouse ─────────────────────────────────────────
def search_3dwarehouse(q):
    try:
        r = requests.get("https://3dwarehouse.sketchup.com/api/v1/models",
            params={"q": q, "limit": 8}, timeout=15,
            headers={"User-Agent": AGENT, "Accept": "application/json"})
        if r.status_code != 200: return []
        entries = r.json().get("entries", [])
        return [{"uid": m.get("id",""), "name": m.get("name",""),
                 "source": "3dwarehouse.sketchup.com",
                 "url": f"https://3dwarehouse.sketchup.com/model/{m.get('id','')}",
                 "is_free": True, "format": "SKP/OBJ/KMZ"}
                for m in entries[:8] if isinstance(m, dict)]
    except: return []

# ── Source 5: NASA 3D Resources ──────────────────────────────────────────────
NASA_MODELS = None
def search_nasa(q):
    """NASA 3D resources — good for rockets, spacecraft, some aircraft."""
    global NASA_MODELS
    if NASA_MODELS is None:
        try:
            r = requests.get("https://nasa3d.arc.nasa.gov/api/nasaModels", timeout=20,
                headers={"Accept": "application/json", "User-Agent": AGENT})
            NASA_MODELS = r.json() if r.status_code == 200 else []
        except:
            NASA_MODELS = []
    tokens = set(re.findall(r'[A-Za-z0-9]{2,}', q.lower()))
    results = []
    for m in NASA_MODELS:
        name = (m.get("title") or m.get("name") or "").lower()
        if any(t in name for t in tokens if len(t) >= 3):
            results.append({"uid": m.get("id",""), "name": m.get("title", m.get("name","")),
                             "source": "nasa3d.arc.nasa.gov",
                             "url": f"https://nasa3d.arc.nasa.gov/detail/{m.get('id','')}",
                             "is_free": True, "format": "OBJ/3DS"})
    return results[:5]

SEARCH_FNS = [search_sketchfab, search_thingiverse, search_printables,
              search_3dwarehouse, search_nasa]

def best_match(model_name, results):
    for r in results:
        if r.get("is_free") and is_good(model_name, r["name"]):
            return r
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
with open(DATA) as f:
    models = json.load(f)

batch   = models[BATCH_START: BATCH_START + BATCH_SIZE]
pending = [m for m in batch if m.get("download_status") in ("Pending", None, "")]
print(f"\nBatch {BATCH_START}–{BATCH_START+len(batch)-1}: {len(pending)} to search\n")

found_total, src_counts = 0, {}

for m in batch:
    if m.get("sketchfab_id") or m.get("download_status") not in ("Pending", None, ""):
        continue
    name, domain = m["model_name"], m.get("domain","")
    match = None
    for query in fuzzy_queries(name, domain):
        for fn in SEARCH_FNS:
            results = fn(query)
            match   = best_match(name, results)
            if match: break
        if match: break
        time.sleep(0.1)

    if match:
        m.update({"sketchfab_id": match["uid"], "sketchfab_name": match["name"],
                  "source_site": match["source"], "source_url": match["url"],
                  "file_format": match.get("format",""), "download_status": "Found"})
        src_counts[match["source"]] = src_counts.get(match["source"], 0) + 1
        print(f"  ✓ [{m['uid']}] {name[:38]} → {match['name'][:40]} [{match['source']}]")
        found_total += 1
    else:
        m["download_status"] = "Not Found"
    time.sleep(0.3)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)
print(f"\nTotal found: {found_total}")
print("By source:", src_counts)
