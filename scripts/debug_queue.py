import json
from collections import Counter
with open('data/models.json') as f:
    models = json.load(f)
s = Counter(m.get('download_status') for m in models)
print('Status summary:')
for status, count in sorted(s.items(), key=lambda x: -x[1]):
    print('  ' + str(count) + '  ' + str(status))
found_sf  = [m for m in models if m.get('download_status') in ('Found', 'Found on Sketchfab')]
found_gc  = [m for m in models if m.get('download_status') == 'Found on GrabCAD']
found_cn  = [m for m in models if m.get('download_status') == 'Found on CadNav']
not_found = [m for m in models if m.get('download_status') == 'Not Found']
print('Sketchfab queue : ' + str(len(found_sf)))
print('GrabCAD queue   : ' + str(len(found_gc)))
print('CadNav queue    : ' + str(len(found_cn)))
print('Not Found       : ' + str(len(not_found)))
