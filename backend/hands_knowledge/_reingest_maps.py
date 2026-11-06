"""Replace the maps doc in the live knowledge store with the updated 22.3KB version."""
import json, urllib.request

BASE = 'https://dl-companion-production.up.railway.app'
H = {'Authorization': 'Bearer sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4'}

r = urllib.request.Request(BASE + '/v1/knowledge/5', headers=H, method='DELETE')
print('DELETE old id5:', urllib.request.urlopen(r, timeout=60).status)

t = open('maps-and-computer-resources.md', encoding='utf-8').read()
body = json.dumps({'name': 'maps-and-computer-resources.md', 'text': t}).encode('utf-8')
r = urllib.request.Request(BASE + '/v1/knowledge', data=body,
                           headers=dict(H, {'Content-Type': 'application/json'}), method='POST')
d = json.load(urllib.request.urlopen(r, timeout=600))
print('POST new:', d.get('id'), d.get('name'), 'chunks=', d.get('chunks'), 'bytes=', len(t.encode('utf-8')))

r = urllib.request.Request(BASE + '/v1/knowledge', headers=H)
s = json.load(urllib.request.urlopen(r, timeout=60))
print('FINAL STORE:', sorted(x['name'] for x in s['sources']))
