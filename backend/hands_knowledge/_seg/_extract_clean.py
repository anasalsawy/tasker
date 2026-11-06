"""Extract truly-clean section blocks from _maps_snap15.md into _seg/good/*.
Drops the duplicate section-4 blob, keeps first 7 sections, renumbers.
"""
import re, pathlib

D = pathlib.Path(r'C:\Users\anasa\tasker-github\backend\hands_knowledge')
src = (D / '_maps_snap15.md').read_text(encoding='utf-8', errors='replace')
GOOD = D / '_seg' / 'good'
GOOD.mkdir(parents=True, exist_ok=True)

head, *blocks = re.split(r'(?=^## )', src, flags=re.M)
(D / '_seg/good/h00.md').write_text(head.rstrip() + '\n\n', encoding='utf-8', newline='\n')

# blocks in order: 1, 4(AppUserModelID-v1), 5, 4-dup(WScript-v2), 5, 6, 7
seen, chosen = set(), []
for b in blocks:
    m = re.match(r'## (\d+)\. (.*)\n', b)
    n = int(m.group(1))
    if n in seen:      # duplicate section number: keep the richer (longer) one later
        continue
    seen.add(n)
    chosen.append(b)

# clean-line audit helper
BAD = re.compile(r'[\u0400-\u04ff\u3040-\u30ff\u3400-\u9fff\u0e00-\u0e7f\u0590-\u05ff\ufffd【】…]')
def clean_lines(b):
    out = []
    for l in b.split('\n'):
        words = re.findall(r"[A-Za-z']{3,}", l.lower())
        if len(words) - len(set(words)) >= 3:      # fat degeneration in that line
            continue
        if BAD.search(l):
            continue
        out.append(l)
    return '\n'.join(out)

renum = {'1': '1', '2': '2', '4': '3', '5': '4', '6': '5', '7': '6', '8': '7', '9': '8'}
for b in chosen:
    oldn = re.match(r'## (\d+)\.', b).group(1)
    nb = re.sub(r'^## \d+\.', '## %s.' % renum[oldn], b, count=1)
    nb = clean_lines(nb)
    if not nb.endswith('\n'):
        nb += '\n'
    quality = len(nb)
    (GOOD / ('maps_g%s.md' % renum[oldn])).write_text(nb + '\n', encoding='utf-8', newline='\n')
    print('saved g%s from section %s  %d bytes' % (renum[oldn], oldn, len(nb.encode('utf-8'))))
