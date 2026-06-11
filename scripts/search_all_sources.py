"""
Multi-source CAD model search:
1. Sketchfab (API - free downloadable GLB)
2. GrabCAD  (API - free STEP/IGES/OBJ)
3. Thingiverse (API - free STL)
4. CGTrader free filter
5. Printables / MakerWorld
6. NASA 3D Resources
"""
import json, os, time, re, requests
from urllib.parse import quote

TOKEN   = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
SF_HDR  = {"Authorization": f"Token {TOKEN}"}
SF_BASE = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

# ── Verify Sketchfab auth ─────────────────────────────────────────────────────
me = requests.get(f"{SF_BASE}/me", headers=SF_HDR, timeout=10)
if me.status_code != 200:
    print(f"Sketchfab auth failed ({me.status_code})"); exit(1)
print(f"Authenticated as: {me.json().get('username')}")

# ── Quality filter ─────────────────────────────────────────────────────────────
JUNK = re.compile(
    r'residên|residencia|projeto estrutural|unifamiliar|funerária|urna funer|'
    r'simplified 3d mesh|weapon pack of|modular wall|building \d+ piece|nyc door|'
    r'maytoni|sword from vimose|opait|blend compress|green wall|'
    r'2015 11 25|lustr[aа]|люстра|rc247|day \d+:|1scanaday|'
    r'campground|gas station|lego minifig|necklace|fiat 500|mega phoenix|'
    r'minecraft|fortnite|project house|m2 apartment|m2 residencia', re.I)

def is_good(model_name, result_name):
    if JUNK.search(result_name): return False
    orig = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', model_name.lower()))
    res  = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', result_name.lower()))
    generic = {'the','and','for','with','free','low','poly','high','detail',
               'game','ready','rigged','animated','pbr','military','vehicle',
               'model','type','class','mark','series'}
    overlap = (orig & res) - generic
    return len(overlap) > 0

def fuzzy_queries(name, domain, mfr):
    queries = [name]
    base = re.sub(r'\s+(Mk|Block|Phase|Series)\s*\w+$', '', name, flags=re.I).strip()
    if base != name: queries.append(base)
    m = re.match(r'^([A-Za-z][A-Za-z0-9\-\.]*?[0-9]+)', name)
    if m and m.group(1) != name: queries.append(m.group(1))
    domain_map = {'AIR':'aircraft','HEL':'helicopter','UAV':'drone',
                  'MSL':'missile','NAV':'warship','AFV':'tank armored vehicle',
                  'ART':'artillery','ADS':'air defense missile','ALM':'missile weapon'}
    if domain in domain_map:
        queries.append(f"{name} {domain_map[domain]}")
        if base != name: queries.append(f"{base} {domain_map[domain]}")
    return queries

# ── Source 1: Sketchfab ───────────────────────────────────────────────────────
def search_sketchfab(query):
    try:
        r = requests.get(f"{SF_BASE}/search", headers=SF_HDR, timeout=15,
            params={"q": query, "type": "models", "downloadable": "true", "count": 8})
        if r.status_code != 200: return []
        return [{"uid": m["uid"], "name": m["name"], "source": "sketchfab.com",
                 "url": f"https://sketchfab.com/3d-models/{m['uid']}",
                 "is_free": m.get("price") is None,
                 "downloadable": m.get("isDownloadable", False),
                 "format": "GLB"}
                for m in r.json().get("results", [])]
    except: return []

# ── Source 2: GrabCAD ─────────────────────────────────────────────────────────
def search_grabcad(query):
    try:
        # GrabCAD community library search endpoint
        r = requests.get("https://grabcad.com/community/questions/search",
            params={"query": query, "format": "json"}, timeout=15,
            headers={"Accept": "application/json",
                     "User-Agent": "Mozilla/5.0 CAD-Research-Tool"})
        # Also try the library endpoint
        r2 = requests.get("https://grabcad.com/library.json",
            params={"search": query, "per_page": 8, "page": 1}, timeout=15,
            headers={"Accept": "application/json",
                     "User-Agent": "Mozilla/5.0 CAD-Research-Tool"})
        results = []
        if r2.status_code == 200:
            data = r2.json()
            for m in (data.get("models") or data if isinstance(data, list) else [])[:5]:
                if isinstance(m, dict):
                    results.append({
                        "uid": str(m.get("id", "")),
                        "name": m.get("name", ""),
                        "source": "grabcad.com",
                        "url": f"https://grabcad.com/library/{m.get('slug','')}",
                        "is_free": True,
                        "downloadable": True,
                        "format": "STEP/IGES/OBJ"
                    })
        return results
    except: return []

# ── Source 3: Thingiverse ─────────────────────────────────────────────────────
def search_thingiverse(query):
    try:
        r = requests.get("https://api.thingiverse.com/search/" + quote(query),
            params={"type": "things", "per_page": 5, "page": 1},
            headers={"Authorization": "Bearer " + os.environ.get("THINGIVERSE_TOKEN","")},
            timeout=15)
        if r.status_code != 200: return []
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "thingiverse.com",
                 "url": f"https://www.thingiverse.com/thing:{m.get('id','')}",
                 "is_free": True, "downloadable": True, "format": "STL"}
                for m in r.json().get("hits", r.json() if isinstance(r.json(), list) else [])[:5]]
    except: return []

# ── Source 4: Printables ──────────────────────────────────────────────────────
def search_printables(query):
    try:
        payload = {"operationName": "PrintsListQuery",
                   "variables": {"query": query, "limit": 5, "page": 0,
                                  "filter": {"license": ["CC", "CC-BY", "CC-BY-SA",
                                                          "CC0", "Public Domain"]}},
                   "query": "query PrintsListQuery($query:String,$limit:Int,$page:Int){"
                            "printsListQuery(query:$query,limit:$limit,page:$page)"
                            "{hits{id name}}}" }
        r = requests.post("https://api.printables.com/graphql/",
            json=payload, timeout=15,
            headers={"Content-Type": "application/json"})
        if r.status_code != 200: return []
        hits = r.json().get("data", {}).get("printsListQuery", {}).get("hits", [])
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "printables.com",
                 "url": f"https://www.printables.com/model/{m.get('id','')}",
                 "is_free": True, "downloadable": True, "format": "STL/3MF"}
                for m in hits[:5]]
    except: return []

# ── Source 5: Free3D ──────────────────────────────────────────────────────────
def search_free3d(query):
    try:
        r = requests.get("https://free3d.com/api/search",
            params={"q": query, "limit": 5, "price_type": "free"},
            timeout=15, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                     "source": "free3d.com",
                     "url": f"https://free3d.com/3d-model/{m.get('slug',m.get('id',''))}",
                     "is_free": True, "downloadable": True, "format": "OBJ/FBX"}
                    for m in (data.get("models") or data if isinstance(data, list) else [])[:5]]
    except: return []

def best_match(model_name, results):
    for r in results:
        if r.get("is_free") and r.get("downloadable") and is_good(model_name, r["name"]):
            return r
    return None

# ── Main search loop ──────────────────────────────────────────────────────────
with open(DATA) as f:
    models = json.load(f)

batch = models[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Searching batch {BATCH_START}–{BATCH_START+len(batch)-1} of {len(models)}")

found_total = 0
source_counts = {"sketchfab.com": 0, "grabcad.com": 0,
                 "thingiverse.com": 0, "printables.com": 0, "free3d.com": 0}

for m in batch:
    if m.get("sketchfab_id") or m.get("download_status") not in ("Pending", None, ""):
        continue

    name   = m["model_name"]
    domain = m.get("domain", "")
    mfr    = m.get("manufacturer", "")
    match  = None

    for query in fuzzy_queries(name, domain, mfr):
        # Try each source
        for search_fn in [search_sketchfab, search_grabcad, search_thingiverse,
                          search_printables, search_free3d]:
            results = search_fn(query)
            match   = best_match(name, results)
            if match: break
        if match: break

    if match:
        m["sketchfab_id"]    = match["uid"]
        m["sketchfab_name"]  = match["name"]
        m["source_site"]     = match["source"]
        m["source_url"]      = match["url"]
        m["file_format"]     = match.get("format","")
        m["download_status"] = "Found"
        src = match["source"]
        source_counts[src] = source_counts.get(src, 0) + 1
        print(f"  ✓ [{m['uid']}] {name[:38]} → {match['name'][:40]} [{src}]")
        found_total += 1
    else:
        m["download_status"] = "Not Found"
        print(f"  ✗ [{m['uid']}] {name}")
    time.sleep(0.4)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)

print(f"\nBatch done: {found_total} found")
print("By source:", {k: v for k, v in source_counts.items() if v > 0})
