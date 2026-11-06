"""QA the maps doc line by line: flags repeated-token degeneration and non-Latin script."""
import sys, re, pathlib

path = pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else
                    r'C:\Users\anasa\tasker-github\backend\hands_knowledge\maps-and-computer-resources.md')
t = path.read_text(encoding='utf-8', errors='replace')
flagged = 0
for i, l in enumerate(t.split('\n'), 1):
    w = re.findall(r"[A-Za-z']{3,}", l.lower())
    dups = len(w) - len(set(w))
    cjk = re.search(r'[\u3400-\u9fff\u0400-\u04ff\u0e00-\u0e7f\u3040-\u30ff\u0590-\u05ff]', l)
    junk = re.search(r'\b(brb|whim【|klik|pung|konsp|hund مو|antiebrowsenúde)', l)
    if dups >= 3 or cjk:
        flagged += 1
        print('%5d  %s' % (i, l[:180]))
print('--- flagged lines: %d of %d  (%s) ---' % (flagged, t.count('\n') + 1, path.name))
