"""
Multi-source CAD search — Sketchfab + GrabCAD (cookie session) + Printables + 3D Warehouse + NASA
"""
import json, os, time, re, requests
from urllib.parse import quote

# Credentials
SF_TOKEN   = os.environ.get("SKETCHFAB_TOKEN",  "7ca059dbec904c6da9985c82faa2ca44")
GC_SESSION = os.environ.get("GRABCAD_SESSION",  "")
GC_XSRF    = os.environ.get("GRABCAD_XSRF",     "")
TV_TOKEN   = os.environ.get("THINGIVERSE_TOKEN","")

SF_HDR  = {"Authorization": f"Token {SF_TOKEN}"}
SF_BASE = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))
AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

# Verify Sketchfab
me = requests.get(f"{SF_BASE}/me", headers=SF_HDR, timeout=10)
if me.status_code != 200:
    print(f"Sketchfab auth failed ({me.status_code})"); exit(1)
print(f"✓ Sketchfab: {me.json().get('username')}")

# Build GrabCAD session from browser cookies
gc_session = None
if GC_SESSION and GC_XSRF:
    gc_session = requests.Session()
    gc_session.headers.update({
        "User-Agent":   AGENT,
        "Accept":       "application/json",
        "Referer":      "https://grabcad.com/library",
        "X-XSRF-TOKEN": requests.utils.unquote(GC_XSRF),
    })
    gc_session.cookies.set("_grabcad_session", GC_SESSION, domain="grabcad.com")
    gc_session.cookies.set("XSRF-TOKEN",       GC_XSRF,    domain="grabcad.com")
    # Quick test
    r = gc_session.get("https://grabcad.com/community/api/v1/models",
        params={"search":"F-16","per_page":1}, timeout=10)
    if r.status_code == 200:
        print(f"✓ GrabCAD: session valid")
    else:
        print(f"✗ GrabCAD: session invalid ({r.status_code}), skipping")
        gc_session = None
else:
    print("✗ GrabCAD: no session cookies provided")

# ── Quality filter ─────────────────────────────────────────────────────────────
JUNK = re.compile(
    r'residên|residencia|projeto|unifamiliar|funerária|simplified 3d mesh|'
    r'weapon pack of|modular wall building|nyc door|maytoni|sword from vimose|'
    r'opait|blend compress|2015 11 25|lustr[aа]|люстра|rc247|day \d+:|1scanaday|'
    r'wwe\b|campground|gas station|lego minifig|necklace|fiat 500|mega phoenix|'
    r'wild wing|longboard|hinge rail|minecraft|fortnite|m2 residencia|pav\. qd|'
    r'cold sv \d|son cold|park scenery|sofa\b|chair\b|table\b|door\b|bed\b', re.I)

def is_good(model_name, result_name):
    if not result_name or JUNK.search(result_name): return False
    orig_long  = set(re.findall(r'[A-Za-z]{3,}', model_name.lower()))
    res_long   = set(re.findall(r'[A-Za-z]{3,}', result_name.lower()))
    orig_short = set(re.findall(r'\b[A-Z]{2,3}\b', model_name))
    res_short  = set(re.findall(r'\b[A-Z]{2,3}\b', result_name.upper()))
    generic = {'the','and','for','with','free','low','poly','high','detail','game',
               'ready','rigged','model','type','class','mark','series','scale',
               'military','vehicle','aircraft','print','design','part','new'}
    long_ok  = len((orig_long  & res_long)  - generic) > 0
    short_ok = len(orig_short & res_short) > 0
    return long_ok or short_ok

def fuzzy_queries(name, domain):
    q = [name]
    base = re.sub(r'\s+(Mk|Block|Phase|Series)\s*\w+$', '', name, flags=re.I).strip()
    if base != name: q.append(base)
    m = re.match(r'^([A-Za-z][A-Za-z0-9\-\.]*?[0-9]+)', name)
    if m and m.group(1) != name: q.append(m.group(1))
    dom = {'AIR':'aircraft military','HEL':'helicopter military','UAV':'drone uav',
           'MSL':'missile ballistic','NAV':'warship naval','AFV':'tank armored vehicle',
           'ART':'artillery howitzer','ADS':'air defense missile system','ALM':'missile weapon'}
    if domain in dom:
        q.append(f"{name} {dom[domain]}")
        if base != name: q.append(f"{base} {dom[domain]}")
    return q[:5]

# ── Source 1: Sketchfab ───────────────────────────────────────────────────────
def search_sketchfab(q):
    try:
        r = requests.get(f"{SF_BASE}/search", headers=SF_HDR, timeout=15,
            params={"q":q,"type":"models","downloadable":"true","count":10})
        if r.status_code != 200: return []
        return [{"uid":m["uid"],"name":m["name"],"source":"sketchfab.com",
                 "url":f"https://sketchfab.com/3d-models/{m['uid']}",
                 "is_free":m.get("price") is None,"format":"GLB/GLTF"}
                for m in r.json().get("results",[])]
    except: return []

# ── Source 2: GrabCAD (cookie session) ───────────────────────────────────────
def search_grabcad(q):
    if not gc_session: return []
    try:
        r = gc_session.get("https://grabcad.com/community/api/v1/models",
            params={"search":q,"per_page":8,"sort":"relevance"}, timeout=15)
        if r.status_code != 200: return []
        data = r.json()
        items = data if isinstance(data,list) else data.get("models",data.get("results",[]))
        results = []
        for m in items[:8]:
            if not isinstance(m,dict): continue
            # Try multiple field name patterns
            slug = (m.get("slug") or m.get("url_identifier") or
                    m.get("url","").split("/library/")[-1].split("/")[0] or
                    str(m.get("id","")))
            name = (m.get("name") or m.get("title") or m.get("model_name") or
                    m.get("label",""))
            if slug and name:
                results.append({"uid":slug,"name":name,"source":"grabcad.com",
                                 "url":f"https://grabcad.com/library/{slug}",
                                 "is_free":True,"format":"STEP/IGES/OBJ"})
        return results
    except Exception as e:
        return []

# ── Source 3: Thingiverse ─────────────────────────────────────────────────────
def search_thingiverse(q):
    if not TV_TOKEN: return []
    try:
        r = requests.get(f"https://api.thingiverse.com/search/{quote(q)}",
            params={"type":"things","per_page":8},
            headers={"Authorization":f"Bearer {TV_TOKEN}"}, timeout=15)
        if r.status_code != 200: return []
        hits = r.json() if isinstance(r.json(),list) else r.json().get("hits",[])
        return [{"uid":str(m.get("id","")),"name":m.get("name",""),
                 "source":"thingiverse.com",
                 "url":f"https://www.thingiverse.com/thing:{m.get('id','')}",
                 "is_free":True,"format":"STL"}
                for m in hits[:8] if isinstance(m,dict)]
    except: return []

# ── Source 4: Printables ──────────────────────────────────────────────────────
def search_printables(q):
    try:
        payload = {"operationName":"SearchResultsQuery",
                   "variables":{"query":q,"limit":8,"offset":0},
                   "query":"query SearchResultsQuery($query:String!,$limit:Int,$offset:Int)"
                           "{searchPrints(query:$query,limit:$limit,offset:$offset)"
                           "{hits{id name slug}}}"}
        r = requests.post("https://api.printables.com/graphql/",
            json=payload,timeout=15,
            headers={"Content-Type":"application/json","User-Agent":AGENT})
        if r.status_code != 200: return []
        hits = r.json().get("data",{}).get("searchPrints",{}).get("hits",[]) or []
        return [{"uid":str(m.get("id","")),"name":m.get("name",""),
                 "source":"printables.com",
                 "url":f"https://www.printables.com/model/{m.get('id','')}",
                 "is_free":True,"format":"STL/3MF"}
                for m in hits[:8] if isinstance(m,dict)]
    except: return []

# ── Source 5: SketchUp 3D Warehouse ─────────────────────────────────────────
def search_3dwarehouse(q):
    try:
        r = requests.get("https://3dwarehouse.sketchup.com/api/v1/models",
            params={"q":q,"limit":8},timeout=15,
            headers={"User-Agent":AGENT,"Accept":"application/json"})
        if r.status_code != 200: return []
        entries = r.json().get("entries",[])
        return [{"uid":m.get("id",""),"name":m.get("name",""),
                 "source":"3dwarehouse.sketchup.com",
                 "url":f"https://3dwarehouse.sketchup.com/model/{m.get('id','')}",
                 "is_free":True,"format":"SKP/OBJ"}
                for m in entries[:8] if isinstance(m,dict)]
    except: return []

# ── Source 6: NASA 3D Resources ──────────────────────────────────────────────
NASA_CACHE = None
def search_nasa(q):
    global NASA_CACHE
    if NASA_CACHE is None:
        try:
            r = requests.get("https://nasa3d.arc.nasa.gov/api/nasaModels",
                timeout=20,headers={"Accept":"application/json","User-Agent":AGENT})
            NASA_CACHE = r.json() if r.status_code==200 else []
        except: NASA_CACHE = []
    tokens = set(re.findall(r'[A-Za-z0-9]{2,}',q.lower()))
    results = []
    for m in NASA_CACHE:
        nm = (m.get("title") or m.get("name") or "").lower()
        if any(t in nm for t in tokens if len(t)>=3):
            results.append({"uid":m.get("id",""),"name":m.get("title",m.get("name","")),
                             "source":"nasa3d.arc.nasa.gov",
                             "url":f"https://nasa3d.arc.nasa.gov/detail/{m.get('id','')}",
                             "is_free":True,"format":"OBJ/3DS"})
    return results[:5]


# ── Source 7: CadNav ──────────────────────────────────────────────────────────
def search_cadnav(q):
    import re as _re
    try:
        r = requests.get('https://www.cadnav.com/3d-models/',
            params={'q': q, 'category': '0'},
            headers={'User-Agent': AGENT, 'Accept': 'text/html'},
            timeout=15)
        if r.status_code != 200: return []
        # Extract model links and names from HTML
        models = _re.findall(
            r'href="(https://www\.cadnav\.com/3d-models/model-(\d+)\.html)"[^>]*>\s*<img[^>]*title="([^"]+)"',
            r.text)
        if not models:
            # Alternative pattern
            models_alt = _re.findall(
                r'href="(/3d-models/model-(\d+)\.html)"[^>]*title="([^"]+)"',
                r.text)
            models = [(f'https://www.cadnav.com{m[0]}', m[1], m[2]) for m in models_alt]
        results = []
        seen = set()
        for url, mid, name in models[:8]:
            if mid not in seen and name.strip():
                seen.add(mid)
                results.append({
                    'uid': f'cadnav_{mid}',
                    'name': name.strip(),
                    'source': 'cadnav.com',
                    'url': url if url.startswith('http') else f'https://www.cadnav.com{url}',
                    'is_free': True,
                    'format': 'OBJ/3DS/FBX/MAX'
                })
        return results
    except Exception as e:
        return []

SEARCH_FNS = [search_sketchfab, search_grabcad, search_cadnav, search_thingiverse,
              search_printables, search_3dwarehouse, search_nasa]

def best_match(model_name, results):
    for r in results:
        if r.get("is_free") and is_good(model_name, r["name"]):
            return r
    return None

# ── Main ──────────────────────────────────────────────────────────────────────
with open(DATA) as f:
    models = json.load(f)

batch   = models[BATCH_START: BATCH_START+BATCH_SIZE]
pending = [m for m in batch if m.get("download_status") in ("Pending",None,"")]
print(f"\nBatch {BATCH_START}-{BATCH_START+len(batch)-1}: {len(pending)} to search\n")

found_total, src_counts = 0, {}

for m in batch:
    if m.get("sketchfab_id") or m.get("download_status") not in ("Pending",None,""):
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
        m.update({"sketchfab_id":match["uid"],"sketchfab_name":match["name"],
                  "source_site":match["source"],"source_url":match["url"],
                  "file_format":match.get("format",""),"download_status":"Found"})
        src_counts[match["source"]] = src_counts.get(match["source"],0)+1
        print(f"  ✓ [{m['uid']}] {name[:38]} → {match['name'][:42]} [{match['source']}]")
        found_total += 1
    else:
        m["download_status"] = "Not Found"
    time.sleep(0.3)

with open(DATA,"w") as f:
    json.dump(models, f, indent=2)
print(f"\nFound: {found_total} | By source: {src_counts}")
