"""Deterministic assembler for maps-and-computer-resources.md.
Usage:
  py _maps_build.py            -> rebuild maps from _seg/maps_p*.md in order
Safety checks per pass: heading count, '^## ' map, markdown fence parity,
gibberish heuristic (non-CJK/non-ASCII junk runs), file size, clean EOF."""
import re, sys, pathlib

D = pathlib.Path(r'C:\Users\anasa\tasker-github\backend\hands_knowledge')
SEG = D / '_seg' / 'good'
OUT = D / 'maps-and-computer-resources.md'

def seg_files():
    files = []
    for p in SEG.glob('maps_g*.md'):
        m = re.fullmatch(r'maps_g(\d+)', p.stem)
        if not m:
            print('SKIP noncanonical segment:', p.name)
            continue
        files.append((int(m.group(1)), p))
    ordered = [p for _, p in sorted(files)]
    h00 = SEG / 'h00.md'
    if h00.exists():
        ordered.insert(0, h00)
    return ordered

def build():
    parts = []
    for p in seg_files():
        t = p.read_text(encoding='utf-8')
        parts.append(t.rstrip() + '\n\n')
    text = ''.join(parts).rstrip() + '\n'
    # normalize: single blank line between paragraphs collapses fine as-is; ensure LF
    text = text.replace('\r\n', '\n').replace('\r', '\n')
    return text

def checks(text):
    problems = []
    heads = re.findall(r'^## (\d+)\. (.*)$', text, re.M)
    nums = [int(n) for n, _ in heads]
    if nums != list(range(1, len(nums) + 1)):
        problems.append('heading numbers not 1..N: %s' % nums)
    if text.count('```') % 2:
        problems.append('unbalanced code fences')
    # structural duplicates of same section number
    dup = {n for n in nums if nums.count(n) > 1}
    if dup:
        problems.append('duplicate section numbers: %s' % sorted(dup))
    tail = text[-80:]
    if not re.search(r'[.!?`\)]\s*$', text):
        problems.append('dirty tail: %r' % tail)
    # corruption sentinels: unexpected non-latin scripts (exclude legit arrows/curly quotes/BOM)
    bad = re.findall(r'[\u3400-\u4dbf\u4e00-\u9fff\u3040-\u30ff\uac00-\ud7af\u0e00-\u0e7f\u0590-\u05ff\u0400-\u04ff\ufffd]+', text)
    if bad:
        problems.append('non-latin script runs: %s' % [b[:8] for b in bad][:6])
    # repeated-word collapse pattern (writer degeneration signature): 3+ CONSECUTIVE repeats
    rep = re.findall(r'\b(\w{3,})\b(?:\s+\1\b){2,}', text, re.I)
    if rep:
        problems.append('word-repeat degeneration: %s' % rep[:5])
    # truly identical adjacent sentences
    sents = [s.strip() for s in re.split(r'(?<=[.!?])\s+', text) if len(s.strip()) > 40]
    dup_sent = {a for a, b in zip(sents, sents[1:]) if a == b}
    if dup_sent:
        problems.append('duplicated sentence: %r' % list(dup_sent)[:2])
    # CJK punctuation in latin doc
    if re.search(r'[⺀-￯]', text):
        problems.append('CJK punctuation present')
    # per-section word counts, decision-range is 300-600
    secs = re.split(r'^## \d+\.', text, flags=re.M)[1:]
    for i, s in enumerate(secs, 1):
        wc = len(re.findall(r'\S+', s))
        if wc < 250:
            problems.append('section %d thin: %d words' % (i, wc))
        if wc > 750:
            problems.append('section %d bloated: %d words' % (i, wc))
    return heads, problems

def main():
    text = build()
    heads, problems = checks(text)
    OUT.write_text(text, encoding='utf-8', newline='\n')
    print('WROTE %s  %d bytes  %d sections' % (OUT.name, len(text.encode('utf-8')), len(heads)))
    for n, t in heads:
        print('  %2s. %s' % (n, t))
    if problems:
        print('PROBLEMS:')
        for p in problems:
            print('  - ' + p)
        sys.exit(1)
    print('CHECKS OK')

if __name__ == '__main__':
    main()
