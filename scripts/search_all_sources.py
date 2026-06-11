"""
Multi-source CAD model search:
1. Sketchfab  (API, GLB, free)
2. GrabCAD    (session auth, STEP/IGES/OBJ, free)
3. Thingiverse (token auth, STL, free)
4. Printables  (public GraphQL, STL, free)
5. SketchUp 3D Warehouse (public, SKP/OBJ, free)
"""
import json, os, time, re, requests
from urllib.parse import quote

# ── Credentials ───────────────────────────────────────────────────────────────
SF_TOKEN  = os.environ.get("SKETCHFAB_TOKEN",  "7ca059dbec904c6da9985c82faa2ca44")
GC_USER   = os.environ.get("GRABCAD_USER",     "meghana.reddy-12")
GC_PASS   = os.environ.get("GRABCAD_PASS",     "")
TV_TOKEN  = os.environ.get("THINGIVERSE_TOKEN","")

SF_HDR    = {"Authorization": f"Token {SF_TOKEN}"}
SF_BASE   = "https://api.sketchfab.com/v3"
DATA      = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

# ── Sketchfab auth ─────────────────────────────────────────────────────────────
me = requests.get(f"{SF_BASE}/me", headers=SF_HDR, timeout=10)
if me.status_code != 200:
    print(f"Sketchfab auth failed ({me.status_code})"); exit(1)
print(f"Sketchfab: authenticated as {me.json().get('username')}")

# ── GrabCAD session ────────────────────────────────────────────────────────────
gc_session = requests.Session()
gc_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
              "Accept": "application/json", "Content-Type": "application/json"}
gc_auth_ok = False
if GC_PASS:
    try:
        r = gc_session.post("https://grabcad.com/api/v1/sessions",
            json={"user": {"login": GC_USER, "password": GC_PASS}},
            headers=gc_headers, timeout=15)
        if r.status_code in (200, 201):
            gc_auth_ok = True
            print(f"GrabCAD: authenticated as {GC_USER}")
        else:
            # Try email login fallback
            r2 = gc_session.post("https://grabcad.com/login",
                data={"user[login]": GC_USER, "user[password]": GC_PASS},
                headers={"User-Agent": gc_headers["User-Agent"]}, timeout=15)
            gc_auth_ok = r2.status_code in (200, 302)
            print(f"GrabCAD: login attempt {'ok' if gc_auth_ok else 'failed'} ({r2.status_code})")
    except Exception as e:
        print(f"GrabCAD: auth error: {e}")
else:
    print("GrabCAD: no password provided, search only (no download)")

# ── Quality filter ─────────────────────────────────────────────────────────────
JUNK = re.compile(
    r'residên|residencia|projeto|unifamiliar|funerária|urna funer|'
    r'simplified 3d mesh|weapon pack of|modular wall building|nyc door|'
    r'maytoni|sword from vimose|opait|blend compress|green wall blend|'
    r'2015 11 25|lustr[aа]|люстра|rc247|day \d+:|1scanaday|'
    r'campground|gas station|lego minifig|necklace|fiat 500|mega phoenix|'
    r'minecraft|fortnite|project house|m2 apartment|m2 residencia|'
    r'sofa|chair|table|lamp|door|window|roof|floor|wall|desk|bed', re.I)

def is_good(model_name, result_name):
    if JUNK.search(result_name): return False
    orig = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', model_name.lower()))
    res  = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', result_name.lower()))
    generic = {'the','and','for','with','free','low','poly','high','detail',
               'game','ready','rigged','animated','pbr','military','vehicle',
               'model','type','class','mark','series','scale','print','design'}
    overlap = (orig & res) - generic
    return len(overlap) > 0

def fuzzy_queries(name, domain):
    queries = [name]
    base = re.sub(r'\s+(Mk|Block|Phase|Series)\s*\w+$', '', name, flags=re.I).strip()
    if base != name: queries.append(base)
    m = re.match(r'^([A-Za-z][A-Za-z0-9\-\.]*?[0-9]+)', name)
    if m and m.group(1) != name: queries.append(m.group(1))
    domain_map = {'AIR':'aircraft military','HEL':'helicopter military',
                  'UAV':'drone uav military','MSL':'missile ballistic',
                  'NAV':'warship naval','AFV':'tank armored vehicle',
                  'ART':'artillery self propelled','ADS':'air defense sam system',
                  'ALM':'air launched missile weapon'}
    if domain in domain_map:
        queries.append(f"{name} {domain_map[domain]}")
        if base != name: queries.append(f"{base} {domain_map[domain]}")
    return queries[:5]  # cap at 5 queries

# ── Search functions ───────────────────────────────────────────────────────────
def search_sketchfab(query):
    try:
        r = requests.get(f"{SF_BASE}/search", headers=SF_HDR, timeout=15,
            params={"q": query, "type": "models", "downloadable": "true", "count": 8})
        if r.status_code != 200: return []
        return [{"uid": m["uid"], "name": m["name"], "source": "sketchfab.com",
                 "url": f"https://sketchfab.com/3d-models/{m['uid']}",
                 "is_free": m.get("price") is None,
                 "downloadable": True, "format": "GLB/GLTF"}
                for m in r.json().get("results", [])]
    except: return []

def search_grabcad(query):
    try:
        r = gc_session.get("https://grabcad.com/library.json",
            params={"search": query, "per_page": 8, "page": 1,
                    "sort": "relevance", "categories": ""},
            headers=gc_headers, timeout=15)
        if r.status_code != 200: return []
        data = r.json()
        models_list = data if isinstance(data, list) else data.get("models", [])
        results = []
        for m in models_list[:8]:
            if not isinstance(m, dict): continue
            results.append({
                "uid": str(m.get("id", m.get("slug",""))),
                "name": m.get("name", ""),
                "source": "grabcad.com",
                "url": f"https://grabcad.com/library/{m.get('slug', m.get('id',''))}",
                "is_free": True, "downloadable": gc_auth_ok,
                "format": "STEP/IGES/OBJ/SolidWorks"
            })
        return results
    except Exception as e:
        return []

def search_thingiverse(query):
    if not TV_TOKEN: return []
    try:
        r = requests.get(f"https://api.thingiverse.com/search/{quote(query)}",
            params={"type": "things", "per_page": 8, "page": 1},
            headers={"Authorization": f"Bearer {TV_TOKEN}"}, timeout=15)
        if r.status_code != 200: return []
        data = r.json()
        hits = data if isinstance(data, list) else data.get("hits", [])
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "thingiverse.com",
                 "url": f"https://www.thingiverse.com/thing:{m.get('id','')}",
                 "is_free": True, "downloadable": True, "format": "STL"}
                for m in hits[:8] if isinstance(m, dict)]
    except: return []

def search_printables(query):
    try:
        payload = {
            "operationName": "SearchResultsQuery",
            "variables": {"query": query, "limit": 8, "offset": 0},
            "query": """query SearchResultsQuery($query:String!,$limit:Int,$offset:Int){
              searchPrints(query:$query,limit:$limit,offset:$offset){
                hits{id name url}}}"""
        }
        r = requests.post("https://api.printables.com/graphql/",
            json=payload, timeout=15,
            headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"})
        if r.status_code != 200: return []
        hits = r.json().get("data",{}).get("searchPrints",{}).get("hits",[]) or []
        return [{"uid": str(m.get("id","")), "name": m.get("name",""),
                 "source": "printables.com",
                 "url": m.get("url", f"https://www.printables.com/model/{m.get('id','')}"),
                 "is_free": True, "downloadable": True, "format": "STL/3MF"}
                for m in hits[:8] if isinstance(m, dict)]
    except: return []

def search_3dwarehouse(query):
    try:
        r = requests.get("https://3dwarehouse.sketchup.com/api/v1/models",
            params={"q": query, "limit": 8, "offset": 0, "orderBy": "RELEVANCE"},
            headers={"User-Agent": "Mozilla/5.0",
                     "Accept": "application/json"}, timeout=15)
        if r.status_code != 200: return []
        data = r.json()
        entries = data.get("entries", data if isinstance(data, list) else [])
        return [{"uid": m.get("id",""), "name": m.get("name",""),
                 "source": "3dwarehouse.sketchup.com",
                 "url": f"https://3dwarehouse.sketchup.com/model/{m.get('id','')}",
                 "is_free": True, "downloadable": True, "format": "SKP/OBJ/KMZ"}
                for m in entries[:8] if isinstance(m, dict)]
    except: return []

SEARCH_FNS = [search_sketchfab, search_grabcad, search_thingiverse,
              search_printables, search_3dwarehouse]

def best_match(model_name, results):
    for r in results:
        if r.get("is_free") and is_good(model_name, r["name"]):
            return r
    return None

# ── Main ───────────────────────────────────────────────────────────────────────
with open(DATA) as f:
    models = json.load(f)

batch = models[BATCH_START: BATCH_START + BATCH_SIZE]
pending = [m for m in batch if m.get("download_status") in ("Pending", None, "")]
print(f"Batch {BATCH_START}–{BATCH_START+len(batch)-1}: {len(pending)} to search")

found_total = 0
src_counts = {}

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
        m["sketchfab_id"]    = match["uid"]
        m["sketchfab_name"]  = match["name"]
        m["source_site"]     = match["source"]
        m["source_url"]      = match["url"]
        m["file_format"]     = match.get("format","")
        m["download_status"] = "Found"
        src = match["source"]
        src_counts[src] = src_counts.get(src,0) + 1
        print(f"  ✓ [{m['uid']}] {name[:38]} → {match['name'][:40]} [{src}]")
        found_total += 1
    else:
        m["download_status"] = "Not Found"
    time.sleep(0.3)

with open(DATA, "w") as f:
    json.dump(models, f, indent=2)

print(f"\nFound: {found_total} | Sources: {src_counts}")
