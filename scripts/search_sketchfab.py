import json, os, time, re, requests

TOKEN   = os.environ.get("SKETCHFAB_TOKEN", "7ca059dbec904c6da9985c82faa2ca44")
HEADERS = {"Authorization": f"Token {TOKEN}"}
BASE    = "https://api.sketchfab.com/v3"
DATA    = os.path.join(os.path.dirname(__file__), "..", "data", "models.json")
BATCH_START = int(os.environ.get("BATCH_START", 0))
BATCH_SIZE  = int(os.environ.get("BATCH_SIZE", 100))

me = requests.get(f"{BASE}/me", headers=HEADERS, timeout=10)
if me.status_code != 200:
    print(f"Auth failed ({me.status_code})"); exit(1)
print(f"Authenticated as: {me.json().get('username')}")

def search_sketchfab(query, count=8):
    """Search Sketchfab for free downloadable models."""
    r = requests.get(f"{BASE}/search", headers=HEADERS, timeout=15,
        params={"q": query, "type": "models", "downloadable": "true", "count": count})
    if r.status_code != 200: return []
    return [{"uid": m["uid"], "name": m["name"], "source": "sketchfab.com",
             "is_free": m.get("price") is None,
             "downloadable": m.get("isDownloadable", False)}
            for m in r.json().get("results", [])]

def is_good_match(model_name, result_name):
    """Check if search result is genuinely related to the model."""
    generic = {'the','and','for','with','day','scan','model','free','low','poly',
               'high','detail','game','ready','rigged','animated','pbr','military',
               'stone','necklace','campground','gas','station','street','park',
               'downtown','shop','house','building','car','truck','bike','photo'}
    orig = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', model_name.lower()))
    sf   = set(re.findall(r'[A-Za-z]{3,}|\d{2,}', result_name.lower()))
    overlap = (orig & sf) - generic
    # Extra check: result name must not be clearly unrelated
    junk = re.search(r'\bday \d+\b|\b1scanaday\b|\bwwe\b|\bfiat 500\b|\blego\b|'
                     r'\bnecklace\b|\bstone\b|\bcampground\b|\bgas station\b', result_name, re.I)
    return len(overlap) > 0 and not junk

def best_free(results, model_name):
    return next((r for r in results
                 if r["is_free"] and r["downloadable"]
                 and is_good_match(model_name, r["name"])), None)

def fuzzy_queries(model_name, domain, manufacturer):
    """Generate search queries from specific to fuzzy."""
    queries = [model_name]
    # Strip common suffixes for fuzzy
    base = re.sub(r'\s+(Mk|Block|Phase)\s*\w+$', '', model_name, flags=re.I).strip()
    if base != model_name: queries.append(base)
    # Base designator only
    m = re.match(r'^([A-Za-z][A-Za-z0-9\-\.]*?[0-9]+)', model_name)
    if m and m.group(1) != model_name: queries.append(m.group(1))
    # Add domain context
    domain_words = {
        'AIR':'aircraft','HEL':'helicopter','UAV':'drone uav','MSL':'missile',
        'NAV':'warship','AFV':'armored vehicle tank','ART':'artillery',
        'ADS':'air defense missile system','ALM':'missile'
    }
    if domain in domain_words:
        queries.append(f"{model_name} {domain_words[domain]}")
        if base != model_name:
            queries.append(f"{base} {domain_words[domain]}")
    return queries

with open(DATA) as f:
    models = json.load(f)

batch = models[BATCH_START: BATCH_START + BATCH_SIZE]
print(f"Searching batch {BATCH_START}–{BATCH_START+len(batch)-1} of {len(models)}")
found = skipped = 0

for m in batch:
    if (m.get('sketchfab_id')
            or m.get('download_status') not in ('Pending', None, '')):
        skipped += 1
        continue

    name   = m['model_name']
    domain = m.get('domain', '')
    mfr    = m.get('manufacturer', '')

    match = None
    for query in fuzzy_queries(name, domain, mfr):
        results = search_sketchfab(query)
        match = best_free(results, name)
        if match: break

    if match:
        m['sketchfab_id']    = match['uid']
        m['sketchfab_name']  = match['name']
        m['source_site']     = match['source']
        m['download_status'] = 'Found on Sketchfab'
        print(f"  ✓ [{m['uid']}] {name[:40]} → {match['name'][:45]}")
        found += 1
    else:
        m['download_status'] = 'Not Found'
        print(f"  ✗ [{m['uid']}] {name}")
    time.sleep(0.4)

with open(DATA, 'w') as f:
    json.dump(models, f, indent=2)
print(f"\nBatch done — found:{found}  skipped:{skipped}  not_found:{BATCH_SIZE-found-skipped}")
