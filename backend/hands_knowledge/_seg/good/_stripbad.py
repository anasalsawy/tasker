"""Strip degenerated tail lines from good segments (deterministic surgery)."""
import pathlib, re

G = pathlib.Path(r'C:\Users\anasa\tasker-github\backend\hands_knowledge\_seg\good')

BAD_PATTERNS = [
    r'\bdelivered delivered\b', r'\bapplied abort\b', r'\brev dialy\b',
    r'\blouction\b', r'\bmulti windows remain\b', r'\bIL-matched rank cents\b',
    r'\bbuttons highlight delivering', r'\bkeyboard keyboard\?\?',
    r'\bmapmulti\b', r'\bpolicy cents\b',
]

for p in sorted(G.glob('maps_g*.md')):
    lines = p.read_text(encoding='utf-8').split('\n')
    out = []
    for l in lines:
        if any(re.search(b, l) for b in BAD_PATTERNS):
            continue
        if re.search(r'[\u3400-\u9fff\u0400-\u04ff\u3040-\u30ff]', l):
            continue
        out.append(l)
    t = '\n'.join(out).rstrip() + '\n'
    p.write_text(t, encoding='utf-8', newline='\n')
    print('%s -> %d bytes' % (p.name, len(t.encode('utf-8'))))
