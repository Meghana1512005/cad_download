import os
from grabcad_client import GrabCADClient

EMAIL = os.environ.get("GRABCAD_EMAIL", "smeghanareddy05@gmail.com")
PASS  = os.environ.get("GRABCAD_PASS",  "")

print(f"Testing GrabCAD with email: {EMAIL[:4]}***")
gc = GrabCADClient(EMAIL, PASS)

if gc.logged_in:
    print("\n✓ Login SUCCESS! Testing search...")
    for query in ["F-16 fighter", "T-72 tank", "AH-64 Apache helicopter"]:
        results = gc.search(query, per_page=3)
        print(f"  '{query}': {len(results)} results")
        for r in results[:2]:
            print(f"    [{r['slug']}] {r['name']}")
else:
    print("\n✗ Login FAILED")
    print("Cookies set:", list(gc.s.cookies.keys()))
