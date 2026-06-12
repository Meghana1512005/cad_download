import json
from collections import Counter

with open('data/models.json') as f:
    models = json.load(f)

s = Counter(m.get('download_status') for m in models)
print('Status summary:')
for status, count in sorted(s.items(), key=lambda x: -x[1]):
    print('  ' + str(count) + '  ' + str(status))

found = [m for m in models if m.get('download_status', '') in ('Found', 'Found on Sketchfab')]
print('Queue (Found): ' + str(len(found)))
if found:
    first = found[0]
    print('First: ' + first['uid'] + ' | ' + str(first.get('sketchfab_id')))
