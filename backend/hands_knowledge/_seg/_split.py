"""Split the known-good snapshot into per-section segments (idempotent)."""
import re, pathlib

D = pathlib.Path(r'C:\Users\anasa\tasker-github\backend\hands_knowledge')
src = (D / '_maps_snap15.md').read_text(encoding='utf-8')
out = D / '_seg' / 'filtered'
out.mkdir(parents=True, exist_ok=True)

# leading header before first '## '
head, *rest = re.split(r'(?=^## )', src, flags=re.M)
(D / '_seg' / 'filtered' / 'maps_h00.md').write_text(head.rstrip() + '\n\n', encoding='utf-8')
print('header block %d bytes' % len(head))
for blk in rest:
    m = re.match(r'## (\d+)\. (.*)', blk)
    print('section', m.group(1), m.group(2)[:50], len(blk))
# dedupe: keep first occurrence of each section number
seen = {}
for blk in rest:
    n = int(re.match(r'## (\d+)\.', blk).group(1))
    if n not in seen:
        seen[n] = blk
for n, blk in sorted(seen.items()):
    p = out / ('maps_s%02d.md' % n)
    p.write_text(blk.rstrip() + '\n\n', encoding='utf-8', newline='\n')
    print('WROTE', p.name, len(blk.encode('utf-8')), 'B')
