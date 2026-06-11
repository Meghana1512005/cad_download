import os
from grabcad_client import GrabCADClient

USER = os.environ.get("GRABCAD_USER", "meghana.reddy-12")
PASS = os.environ.get("GRABCAD_PASS", "")

print(f"Testing GrabCAD login for user: {USER}")
gc = GrabCADClient(USER, PASS)

if gc.logged_in:
    print("\nSearching for 'F-16 fighter jet'...")
    results = gc.search("F-16 fighter jet")
    print(f"Found {len(results)} results:")
    for r in results[:5]:
        print(f"  {r['name']} — {r['url']}")
else:
    print("Login failed — checking cookies:")
    for k, v in gc.s.cookies.items():
        print(f"  {k}: {v[:30]}...")
