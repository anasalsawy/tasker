"""Probe the live DL-Companion knowledge store: list sources, check for
duplicates (esp. desktop-windows.md), and report raw JSON fields per source."""
import json
import urllib.request

BASE = "https://dl-companion-production.up.railway.app"
KEY = "Bearer sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4"

req = urllib.request.Request(BASE + "/v1/knowledge", headers={"Authorization": KEY})
with urllib.request.urlopen(req, timeout=120) as resp:
    store = json.load(resp)

sources = store.get("sources", store if isinstance(store, list) else [])
print("SOURCE COUNT:", len(sources))
names = {}
for s in sources:
    name = s.get("name")
    names.setdefault(name, []).append(s)
    print("  id=%s  name=%s  keys=%s" % (s.get("id"), name, sorted(s.keys())))
    # dump any chunk-count-ish field
    for k in ("chunks", "chunk_count", "num_chunks", "size", "created_at", "createdAt", "ingested_at"):
        if k in s:
            print("      %s=%s" % (k, s[k]))

dupes = {n: v for n, v in names.items() if len(v) > 1}
print("\nDUPLICATE NAMES:", json.dumps({n: [x.get("id") for x in v] for n, v in dupes.items()}) if dupes else "none")
print("FULL KEYS OF STORE OBJECT:", sorted(store.keys()) if isinstance(store, dict) else "(list)")
