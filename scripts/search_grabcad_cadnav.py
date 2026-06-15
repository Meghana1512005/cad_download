"""
Search GrabCAD (email+password) and CadNav (category crawl with BeautifulSoup)
for all models currently marked 'Not Found'.
"""
import json, os, re, time, requests
from bs4 import BeautifulSoup
from grabcad_client import GrabCADClient

DATA         = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START  = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE   = int(os.environ.get("BATCH_SIZE", 500))

AGENT        = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/120"

JUNK = re.compile(
    r'\b(anime|minecraft|fortnite|lego|cartoon|lowpoly|low.poly|game.asset|'
    r'unity|unreal|roblox|toy|figurine|doll|chibi|pokemon|necklace|jewelry|'
    r'sofa|chair|door|table|lamp|sculpt|fantasy|medieval|viking|knight|sword|'
    r'axe|bow|shield|magic|wizard|elf)\b', re.I)

STOP = {'the','and','for','with','mk','type','class','series','model','version',
        'military','aircraft','helicopter','tank','vehicle','missile','system',
        'new','mod','improved','advanced','main','battle','light','heavy','medium'}

def word_score(a, b):
    wa = set(w.lower() for w in re.findall(r'[a-z0-9]+', a, re.I) if len(w) >= 2) - STOP
    wb = set(w.lower() for w in re.findall(r'[a-z0-9]+', b, re.I) if len(w) >= 2) - STOP
    if not wa:
        return 0
    return len(wa & wb) / len(wa)

def fuzzy_queries(name, domain):
    queries = [name]
    base = re.sub(r'\s+(Mk|Block|Phase|Mod|Variant|Version|Batch)\s*[\w\.]+$',
                  '', name, flags=re.I).strip()
    if base != name:
        queries.append(base)
    m = re.match(r'^([A-Z]{1,3}[-\s]?\d[\w\-\.]*)', name)
    if m and m.group(1) != name:
        queries.append(m.group(1))
    return queries[:3]

# ── CadNav: category crawl using BeautifulSoup ────────────────────────────────
print("Building CadNav index (crawling category pages)...")
cn = requests.Session()
cn.headers["User-Agent"] = AGENT

CADNAV_CATS = [
    ("aircraft",   "https://www.cadnav.com/3d-models/aircraft/"),
    ("weapons",    "https://www.cadnav.com/3d-models/weapons/"),
    ("vehicle",    "https://www.cadnav.com/3d-models/vehicle/"),
    ("watercraft", "https://www.cadnav.com/3d-models/watercraft/"),
]

cadnav_index = []

for cat_name, cat_url in CADNAV_CATS:
    page = 1
    while page <= 50:
        url = cat_url if page == 1 else cat_url.rstrip('/') + f"/index-{page}.html"
        try:
            r = cn.get(url, timeout=15)
            soup = BeautifulSoup(r.text, "html.parser")

            entries = []
            # Strategy 1: all links to model pages
            for a in soup.find_all("a", href=re.compile(r"/3d-models/model-\d+\.html")):
                href = a.get("href", "")
                mid_m = re.search(r"model-(\d+)\.html", href)
                if not mid_m:
                    continue
                mid = mid_m.group(1)
                # Prefer title attr, then link text, then parent h2 text
                name = (a.get("title", "") or a.get_text(strip=True) or
                        (a.find_parent("h2") or a).get_text(strip=True))
                # Strip " 3d model download" suffix
                name = re.sub(r'\s*3d model.*$', '', name, flags=re.I).strip()
                if name and mid:
                    entries.append((mid, name))

            if not entries:
                break  # no more pages

            # Deduplicate within this page
            seen_page = set()
            for mid, mname in entries:
                if mid not in seen_page and mname:
                    seen_page.add(mid)
                    cadnav_index.append((mid, mname, cat_name))

            print(f"  {cat_name} page {page}: {len(seen_page)} models")
            time.sleep(0.4)
            page += 1
        except Exception as e:
            print(f"  {cat_name} page {page} error: {e}")
            break

# Global deduplicate
seen_ids = set()
cadnav_index = [(mid, mn, cat) for mid, mn, cat in cadnav_index
                if mid not in seen_ids and not seen_ids.add(mid)]
print(f"CadNav index: {len(cadnav_index)} unique models\n")

def cadnav_match(model_name):
    best_score, best = 0, None
    for mid, cname, cat in cadnav_index:
        if JUNK.search(cname):
            continue
        s = word_score(model_name, cname)
        if s > best_score:
            best_score, best = s, (mid, cname)
    if best_score >= 0.6:
        return best, best_score
    return None, 0

# ── GrabCAD: cookie-based session ────────────────────────────────────────────
print("Initialising GrabCAD (cookie session)...")
gc_client = GrabCADClient()
gc = gc_client if gc_client.logged_in else None
if gc:
    print("GrabCAD ready\n")
else:
    print("GrabCAD session invalid — skipping GrabCAD search\n")

DOMAIN_HINTS = {
    'AIR': 'aircraft jet fighter', 'HEL': 'helicopter',
    'UAV': 'drone uav',            'NAV': 'warship naval frigate',
    'AFV': 'tank armored vehicle', 'ART': 'artillery howitzer',
    'MSL': 'missile ballistic',    'ADS': 'air defense missile',
    'ALM': 'missile weapon',
}

def grabcad_search(model_name, domain):
    if not gc:
        return None, 0
    queries = fuzzy_queries(model_name, domain)
    hint = DOMAIN_HINTS.get(domain, '')
    if hint:
        queries.append(f"{model_name} {hint}")
    for q in queries[:4]:
        results = gc.search(q, per_page=8)
        for res in results:
            rname = res.get('name', '')
            if not rname or JUNK.search(rname):
                continue
            s = word_score(model_name, rname)
            if s >= 0.5:
                return res, s
        time.sleep(1.2)
    return None, 0

# ── Main ──────────────────────────────────────────────────────────────────────
models    = json.load(open(DATA))
not_found = [m for m in models if m.get("download_status") == "Not Found"]
batch     = not_found[BATCH_START: BATCH_START + BATCH_SIZE]

print(f"Not Found total : {len(not_found)}")
print(f"Batch           : [{BATCH_START}:{BATCH_START+len(batch)}]  ({len(batch)} models)\n")

found_cadnav = found_grabcad = 0

for i, m in enumerate(batch):
    uid  = m["uid"]
    name = m.get("model_name", "").strip()
    if not name:
        continue

    # 1 — CadNav first (no rate limit)
    cn_match, cn_score = cadnav_match(name)
    if cn_match:
        mid, cname = cn_match
        m["download_status"] = "Found on CadNav"
        m["source_site"]     = "CadNav"
        m["source_url"]      = f"https://www.cadnav.com/3d-models/model-{mid}.html"
        m["cadnav_id"]       = mid
        m["cadnav_name"]     = cname
        m["cadnav_cid"]      = CADNAV_CAT_CID.get(cn_cat, 3)
        found_cadnav += 1
        print(f"  [CadNav]  {uid}: {name!r} -> {cname!r} ({cn_score:.2f})")
        continue

    # 2 — GrabCAD (rate-limited)
    gc_res, gc_score = grabcad_search(name, m.get("domain", ""))
    if gc_res:
        m["download_status"] = "Found on GrabCAD"
        m["source_site"]     = "GrabCAD"
        m["source_url"]      = gc_res.get("url", "")
        m["grabcad_slug"]    = gc_res.get("slug", "")
        m["grabcad_id"]      = gc_res.get("id")
        found_grabcad += 1
        print(f"  [GrabCAD] {uid}: {name!r} -> {gc_res['name']!r} ({gc_score:.2f})")

    if (i + 1) % 100 == 0:
        print(f"  --- {i+1}/{len(batch)} | CadNav: {found_cadnav} | GrabCAD: {found_grabcad} ---")
        json.dump(models, open(DATA, "w"), indent=2)

json.dump(models, open(DATA, "w"), indent=2)
print(f"\nDone. CadNav: {found_cadnav} | GrabCAD: {found_grabcad} | Total: {found_cadnav+found_grabcad}")
