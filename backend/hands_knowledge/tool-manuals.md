# Tool Manuals — decision-then-idiom

Reference for a computer-use agent: WHEN to reach for each tool, THEN the exact idiom. Check exit codes after anything non-trivial (`$LASTEXITCODE` PowerShell, `$?` bash). Prefer real parsers (jq, sqlite3, pdfplumber) over regex. Read the failure output before retrying; never treat a silenced error as success.

## 1. ripgrep (rg) recipes

Use `rg` for every "find text in files" job — recursive, `.gitignore`-aware, fast. `grep -r` only where rg is absent. Put patterns starting with `-` after `--`.

```
rg -n --smart-case "TODO" .                 # line numbers; case-ignores unless caps present
rg -l -g "!**/node_modules/**" "refresh_token"   # filenames only, skip a subtree
rg -c "ERROR" app.log                       # per-file match counts
rg -U -o "BEGIN [.#\s\S]*? END" dump        # -U required for multiline; \n never matches without it
rg -F "^#money[usd]" notes.md               # -F literal: regex chars stay inert
rg --pcre2 "(?<!\d)\d{16}(?!\d)" cards      # lookaround needs PCRE2 (or -P grep); default engine refuses
rg -tjs -tts --sort=path "^import " .       # several types, deterministic order
rg --files-without-match "</footer>" views  # inverse discovery
rg -o --no-filename "[0-9a-f]{7,40}" | sort -u | wc -l
```

Steer size first: `rg -l`, then `rg -c`, then `rg -n -A3 -B3` on the two or three files that matter — never dump raw content into the transcript. `--max-columns 240 --max-columns-preview` keeps minified bundles from flooding out. `--json` gives one object per event for `jq`. `-uuu` reveals hidden and ignored files and also matches binary; pair binary work with `--binary`/`--text` so output stays printable. `.rgignore` layers ignore rules under `.gitignore`; `--no-ignore-vcs` keeps your own. `--pre pdftotext --pre-arg='-layout'` indexes formats rg cannot read. PowerShell does NOT glob: quote `--glob "*.ts"` and let rg expand it.

## 2. jq recipes

Any JSON payload goes through `jq`; regex breaks on the first escaped quote. Flags: `-r` raw strings, `-s` slurp to array, `-n` no input, `--arg k v` / `--argjson k 3` (kills quoting and injection pain), `--slurpfile k f`, `-c` compact, `-e` exit status reflects emptiness (script guard).

```
jq -r '.data.items[] | "\(.id)\t\(.name)"'                  # TSV out
jq -r '.[] | [.id,.state,.created_at] | @tsv'               # @tsv/@csv handle quoting
jq -s 'add | unique_by(.id)'                               # merge JSONL + dedupe
jq 'group_by(.status) | map({status:.[0].status, n:length})'  # histogram
jq 'paths(numbers) as $p | {path:$p, value:getpath($p)}'     # flatten numbers
jq -n --arg t "$TOK" '{auth:{scheme:"bearer", token:$t}}'
jq 'del(.. | objects | .__typename?)'                       # scrub GraphQL noise
jq -r '.errors[]?.message // empty'                         # no "null" lines
jq -s 'map(select(.role=="assistant")) | length'
```

`//` is the ALTERNATIVE operator — it fires on `null` AND `false`; it is not a comment. `?` suppresses a type error only for the immediately preceding expression. `*` recursively merges objects (`.[0] * .[1]` as a patch), `+` concatenates arrays. Top-N: `sort_by(-.score) | .[:20]`. Presence-first discovery beats guessing keys: `jq 'keys'`, `.. | objects | select(has("email"))`, then read that path. Date math: `fromdateiso8601`/`todate` want a `Z`ed or offset-stamped string; `strptime` + `mktime` for custom formats. Big JSONL: skip `-s` (memory), stream one object at a time with `select`.

## 3. curl and Invoke-RestMethod

Decision: `curl.exe` (ships with Windows 10+) when byte-level control matters — streaming, proxies, TLS, multipart, timing. `Invoke-RestMethod` when you want the body parsed into objects for one-shot GET/POST. `Invoke-WebRequest` only when you need `.StatusCode`/`.Headers`; under PS 5.1 its HTML parser is slow and it **throws on 4xx**. Use `-sS` on curl, never bare `-s` — bare `-s` hides the failure reason too.

```
curl -sS -o out.json -w "%{http_code} %{time_total} %{size_download}\n" URL
curl -sS -H "Authorization: Bearer $TOK" -H "Accept: application/json" URL
curl -sS -X POST -H 'Content-Type: application/json' --data-binary @body.json URL
curl -s --retry 3 --retry-delay 2 --retry-connrefused --max-time 25 URL
curl -sS -D - -o /dev/null URL                          # headers to stdout, body discarded
curl -s --fail-with-body -o b URL || tail -c 400 b      # -f hides error body; keep it
curl -x http://127.0.0.1:8888 --cacert ca.pem https://internal/api
curl -sN -H 'Accept: text/event-stream' URL             # -N/--no-buffer for streams
```

PowerShell: **`-TimeoutSec` is mandatory** (PS 5.1 default ≈100 s). Auth headers go in a hashtable.

```powershell
$h = @{ Authorization = "Bearer $env:TOK" }
Invoke-RestMethod -Uri $u -Headers $h -TimeoutSec 20
Invoke-RestMethod -Uri $u -Method Patch -Headers $h -ContentType 'application/json' `
  -Body ([Text.Encoding]::UTF8.GetBytes((ConvertTo-Json $o -Depth 8 -Compress))) -TimeoutSec 20
```

Two traps. (a) **UTF-8 body**: `-Body 'text é'` under PS 5.1 is encoded with the ANSI codepage and corrupts non-ASCII silently — always pass a UTF-8 byte array; pwsh 7 defaults to UTF-8, send bytes anyway for parity. (b) **Error shape**: `-SkipHttpErrorCheck` and `-ResponseHeadersRead` are pwsh 7+ only; in 5.1 use `try{…}catch{ $_.ErrorDetails.Message; [int]$_.Exception.Response.StatusCode }` — the body survives only in `ErrorDetails`. Multipart upload: `-Form` is 7+, so on 5.1 shell out to `curl.exe -F "file=@a.png" -F k=v URL`. Token-bearing headers containing `&` must be quoted when routed through `cmd /c`.

**SSE gotcha:** `Invoke-RestMethod`, buffered `Invoke-WebRequest`, and `GetStringAsync` read the *entire* response — a `text/event-stream` endpoint looks like a hang until timeout and yields nothing partial. Consume streams with `curl.exe -sN` in a line loop, or `HttpClient` with `HttpCompletionOption.ResponseHeadersRead` + `StreamReader`. Frame facts: events are `event:`/`data:`/`id:`/`retry:` lines terminated by a blank line; consecutive `data:` lines of one event must be joined with `\n`; one leading space after the colon is stripped per spec; `:ping` comment lines are heartbeats — ignore them; a wrong `Accept` makes the server reply with plain JSON and the stream "ends instantly". `curl: (18) transfer closed with outstanding read data remaining` on a long-lived stream is the server hanging up, not a tool failure.

## 4. PowerShell ↔ cmd ↔ bash equivalents

| task | PowerShell | cmd.exe | bash |
| --- | --- | --- | --- |
| B iff A ok | `A; if ($?) {B}` (7: `A && B`) | `A && B` | `A && B` |
| always run B | `A; B` | `A & B` | `A; B` |
| env for one call | `$env:X='v'; A` | `set "X=v" && A` | `X=v A` |
| capture output | `$o = & exe args` → string[] | `for /f "delims=" %i in ('exe') do @echo %i` | `o=$(exe args)` |
| list incl. hidden | `gci -Force` | `dir /a` | `ls -la` |
| find in PATH | `(Get-Command node).Source` | `where node` | `command -v node` |
| background | `Start-Process -PassThru -WindowStyle Hidden` | `start /b cmd /c A` | `A & echo $!` |
| null sink | `A \| Out-Null` ; `A 2>$null` | `A >nul 2>&1` | `A >/dev/null 2>&1` |
| exit code | `$LASTEXITCODE` (native exes only) | `%ERRORLEVEL%` (use `!` in loops) | `$?` |
| multiline string | `@"…"@` (interps), `@'…'@` (literal) | `^` line join | `…` or heredoc |
| recurse+filter+act | `gci -R -File -Filter *.log \| ? {$_.LastWriteTime -gt $d} \| rm` | `for /r %f in (*.log) do @…` | `find . -name '*.log' -mtime -1 -print0 \| xargs -0 rm` |
| path parts | `Split-Path -Leaf $f`; `[IO.Path]::GetFileNameWithoutExtension` | `%~nxf` | `basename`, `dirname`, `${f%.*}` |
| replace in file | `(gc f) -replace 'a','b' \| sc f` (BOM risk! use `[IO.File]::WriteAllLines`) | no in-place | `sed -i 's/a/b/g' f` |
| measure runtime | `Measure-Command { A }` | none native | `time A` |
| URL encode | `[uri]::EscapeDataString($s)` | — | `q=$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote_plus(sys.argv[1]))' "$s")` |
| pass args literally | `& exe --% /Flag:%VAR%` (stops PS parsing) | `%%` inside .bat | quote normally |

Three interop landmines. (1) PowerShell parses switches itself: `/foo` can bind as a PS parameter — use `--%` or wrap in `cmd /c`. (2) In 5.1, native stderr merged via `2>&1` arrives as ErrorRecord objects; ordering and line-wrapping break. Safest is `cmd /c "A 2>&1"` or `$ErrorActionPreference='Continue'`. (3) `&&`/`||` are syntax errors in 5.1. Cross-shell payloads containing `$`, `(`, `&`, or quotes: write a `.ps1`/`.sh` file and invoke with `-File` / `bash -c`, never rebuild inside double-quoted strings.

## 5. python one-liners for data munging

`python -c` / `py -c` (Windows launcher) wins when a step needs a dict, a float compare, a timezone, or CSV quoting — the point where awk/sed turn brittle. Windows quoting: outer `"…"`, inner `'…'`, no nested double quotes; past ~200 chars stop and run a real script file. If plain `python` on Windows opens the Microsoft Store stub, use `py`.

```bash
py -c "import json,collections;print(collections.Counter(j['status'] for j in json.load(open('r.json'))))"
python3 -c "print(sum(1 for l in open('a.log',encoding='utf-8',errors='replace') if 'ERROR' in l))"
python3 -c "from pathlib import Path;print([p for p in Path('.').rglob('*.env')])"
python3 -c "import re,sys;print(sorted({m.group() for m in re.finditer(r'\d+\.\d+\.\d+', sys.stdin.read())}))"
python3 -c "import statistics as s; d=[float(x) for x in sys.argv[1:]]; print(s.mean(d), s.median(d))" 1.2 3.4 2.9
```

To know the shape of an unknown JSON file without guessing path names, print keys: `py -c "import json;d=json.load(open('f'));print(type(d), list(d)[:8])"`. Heredocs work in bash (`python3 - <<'EOF'`) and PowerShell (`@'…'@ | python -`), not in cmd; quoted `'EOF'` prevents shell expansion of `$var`. Read files as `open(p, encoding='utf-8', errors='replace')` — a tool-written latin-1 CSV otherwise kills the scan on one stray byte. For CSV, `open(fn, newline='', encoding='utf-8-sig')` + `csv.DictReader`; missing `newline=''` on Windows shifts rows when fields embed newlines. Never `float(value)` scraped columns blindly — `1,000`, `N/A`, and `—` throw; use a `try/except ValueError` or mask non-numeric rows first. Sort with a `key=` (`max(objs, key=lambda o: o['ts'])`) rather than sorting parallel lists by hand. For timezone conversion: `datetime.fromisoformat(s).astimezone(timezone.utc)`. When the "one-liner" runs over one screen, it deserves to be `tool.py` — a reviewable file beats a cursed pipeline.

## 6. git failure recoveries

**Detached HEAD.** Symptom: `git status` shows `HEAD detached at abc1234` — from `git checkout <sha|tag>`, or a CI clone. Commits made while detached have no branch but are not lost (reachable until GC). Pin immediately: `git branch keep-1601` (or note `git rev-parse HEAD`). Reattach: `git switch -c fix-1234` keeps the current commit as a named branch with zero merging. Fold into an existing branch: `git switch main; git merge keep-1601` (or rebase the temp branch onto main). Never "convert" with `git checkout main -- .` — that copies trees into the worktree, drops the history, and silently overwrites your unstaged edits. Uncommitted + untracked work: `git stash -u` before switching. Always verify with `git status` then `git log --oneline --graph -5`; `git reflog` is the last-resort map of where HEAD has been.

**Stuck merge.** Triage commands: `git status` (which state: merging vs rebasing), `git diff --name-only --diff-filter=U` (unmerged files), `git ls-files -u` (stages 1=base, 2=ours, 3=theirs per file), `git log --oneline -1 MERGE_HEAD` (what's being pulled in). During a rebase the labels **invert**: `--ours` = the branch you're rebasing onto (upstream), `--theirs` = your commits being replayed. Test the inversion on one file before mass-resolving; picking the wrong side deletes good work without a warning. Per-file take one side: `git checkout --ours <f>` / `git checkout --theirs <f>`, then `git add <f>`. Whole-operation bias: `git merge -X theirs`, `git rebase -X ours` (same inversion rule). If a file is unresolvable from the markers, `git checkout --conflict=merge <f>` restores them. Finish: merge → `git add .; git commit --no-edit`; rebase → `git add .; git rebase --continue`. Absolution paths: `git merge --abort` / `git rebase --abort` / `git cherry-pick --abort`, then `git reflog` to confirm HEAD where you expect. If you already `reset --hard`'d the wrong thing, `git reset --hard ORIG_HEAD` or the exact reflog SHA.

**Interactive auth that hangs an agent.** Set `GIT_TERMINAL_PROMPT=0` so credential prompts fail fast with a real error instead of blocking a captured pipe forever: bash `GIT_TERMINAL_PROMPT=0 git fetch`, PowerShell `$env:GIT_TERMINAL_PROMPT='0'` (or per-call `git -c core.askPass=`). `GIT_ASKPASS` overrides everything: point it at a script that echoes two lines (username then token), or `GIT_ASKPASS=echo` to make auth *fail on purpose* — the classic way to probe "does this remote even need creds?" without popping a GUI dialog. SSH remotes have no askpass; use `GIT_SSH_COMMAND='ssh -oBatchMode=yes -oStrictHostKeyChecking=accept-new'`. Which credential wins: `echo "protocol=https` + `host=github.com" | git credential fill` on bash/PS with care — prints the user + secret the helper will actually submit. Confirm helper wiring with `git config --show-origin --get-all credential.helper`. Prefer a per-invocation fix over editing global config: `git -c http.extraHeader="AUTHORIZATION: bearer $TOK" clone URL`. Conservative read-only probes first: `git ls-remote URL` after any auth change.

**Cache/corner cases.** Line-ending churn presented as conflicts: `git diff --ignore-space-at-eol`; pin truth with `.gitattributes` (`* text=auto eol=lf`, `*.ps1 text eol=crlf`) rather than everyone using a different `core.autocrlf`. Shallow-clone failure (`... missing delta`): `git fetch --unshallow` or `--deepen N`. Bad objects: `git fsck --full`. If the worktree keeps showing deleted files as modified, check `git config core.fileMode false` on Windows/WSL handoffs.

## 7. sqlite3 CLI

Decision: `sqlite3` for anything stored in a `.sqlite`/`.db` file an app uses (browser history, task queues, app caches). Never edit a live app DB while the app is running — copy it first or open read-only.

```
sqlite3 app.db ".tables"                       # structure before anything else
sqlite3 app.db ".schema events"
sqlite3 "file:app.db?mode=ro&immutable=1" ...  # refuse writes, refuse to create
sqlite3 app.db -cmd ".mode column" -cmd ".headers on" "select id,ts from events order by ts desc limit 20;"
sqlite3 app.db ".mode json" "select status, count(*) as n from jobs group by status;"   # array of objects
sqlite3 app.db ".mode insert jobs" "select * from jobs limit 50;"   # portable SQL out
sqlite3 app.db "PRAGMA integrity_check;" "PRAGMA journal_mode;"
sqlite3 -bail app.db ".read seed.sql"          # stop at first error
```

Dump and move: `sqlite3 old.db ".dump" > full.sql` (schema+data, text), or `.dump --schema` alone, `.dump --table config`. Rebuild: `sqlite3 new.db ".read full.sql"`. CSV in/out: `.import --csv -skipping 1 data.csv tbl` (table must exist; `.mode csv` + `.headers on` + `.once out.csv` writes it back). One-liners from a shell prefer heredoc so quoting stays sane:

```
sqlite3 app.db <<'SQL'
.mode json
select id, name from users where created_at > '2026-01-01' order by created_at desc limit 10;
SQL
```

SQLite dialect traps vs Postgres: no `now()` (use `datetime('now')`, `strftime('%s','now')`), no `ILIKE` (`LIKE` is already case-insensitive for ASCII; `instr()` for exactness), `SERIAL` → `INTEGER PRIMARY KEY AUTOINCREMENT`, `::` casts → `CAST(x AS TEXT)`, sizes are `COUNT(*)`. Booleans are 0/1; dates are TEXT or INTEGER — check the real storage with `typeof(col)` before filtering, and for millisecond epochs do `datetime(ts/1000,'unixepoch')` then add the local offset only if you must. `json_extract(meta,'$.path')` works when `json_valid(meta)` — half of "app metadata" columns are double-encoded JSON strings needing two calls. Query only what you print, then `| jq` for shape. Hanging on write = `SQLITE_BUSY`; add `-cmd ".timeout 5000"`. If the shell is missing, `python3 -c "import sqlite3;print(sqlite3.connect('app.db').execute('select…').fetchall())"` — parameterize with `?`, never f-string user text into SQL.

## 8. ffmpeg quick recipes

Decision: `ffmpeg` for re-encode/trim/frame grab, `ffprobe` first to learn what you actually have. `-y` always (else it hangs on overwrite prompts); inputs go **before** the seek when you want speed, **after** when you want accuracy.

```
ffprobe -v error -show_entries format=duration,size:stream=index,codec_type,codec_name,width,height,r_frame_rate -of json in.mp4
ffmpeg -y -ss 8 -t 12 -i in.mp4 -c copy cut.mp4                     # fast trim, copy, GOP edges
ffmpeg -y -i in.mp4 -ss 8 -to 20 -c:v libx264 -preset veryfast -crf 23 -c:a aac cut.mp4   # exact trim
ffmpeg -y -ss 00:01:23.500 -i in.mp4 -frames:v 1 -update 1 still.png   # one exact frame
ffmpeg -y -i in.mp4 -vf "fps=1/5,scale=640:-2" -q:v 3 g%04d.jpg        # contact sheet for scanning
ffmpeg -y -i in.mkv -map 0:v:0 -map 0:a:0 -c copy out.mp4              # remux, drop extra tracks
ffmpeg -y -i in.mp4 -f lavfi -i anullsrc=r=44100:cl=stereo -shortest -c:v copy -c:a aac withaudio.mp4
```

Silent-audio recipe exists because players and upload APIs reject video with no audio stream; `anullsrc` + `-shortest` + `-c:v copy` is lossless and fast. `-c copy` trims on keyframes, so the cut can start grey/black or a half-second early — re-encode when the cut must be frame-accurate. Scale to `-2` (mod-2) or x264 errors out. Film-strip scrubbing beats reading a 10-minute video: 1 frame / 5 s at 640 px is ~120 small images per hour, and you OCR the width. Log hygiene: `-loglevel error -stats`; drive long jobs with `-progress pipe:1` and poll. Filters separated by commas and arguments need escaping: `-vf "select=eq(n\,87)"`; quotes: in PowerShell wrap the filter in single quotes so PS does not eat `$`/`:`. Looping/plateau: `-stream_loop -1`, `-t` cap. Faststart for web playback: `-movflags +faststart`.

## 9. pdfplumber / pypdf vs pdftotext -layout

Decision tree. Want quick readable text with column alignment preserved and no structure → `pdftotext -layout` (poppler; not installed by default on Windows). Want tables, cell values, or word coordinates → `pdfplumber` (python, slower, most faithful). Want split/merge/rotate/metadata/decrypt with no analysis → `pypdf` (pure python, cheap, crude text order). Text is missing everywhere → the page is an image: rasterize and OCR, stop trying text extractors.

```bash
pdftotext -layout -f 1 -l 5 report.pdf out.txt    # pages 1-5, keeps aligned columns
pdftotext -raw report.pdf -                       # stream order, single-column docs
pdftotext -nodiag report.pdf -                    # drop marginalia/diagonal noise
pdftoppm -png -r 200 -f 1 -l 3 report.pdf page    # rasterize for vision/OCR
```

```python
import pdfplumber
with pdfplumber.open("report.pdf") as pdf:
    print(len(pdf.pages), pdf.metadata)
    p = pdf.pages[0]
    print(p.extract_text())                 # reading-order guess
    print(p.extract_tables())               # trusted only when the PDF has rules
    ws = p.extract_words(x_tolerance=1.5)   # bbox rows/build your own columns
    print(p.lines and len(p.lines), len(p.rects))   # ruled? then use tables
```

```bash
python3 -c "from pypdf import PdfReader as R;print('\n'.join((p.extract_text() or '') for p in R('a.pdf').pages))"
```

Read-practice: write with `encoding='utf-8'`; normalize with `unicodedata.normalize('NFKC', text)` before regexing (ligatures `ﬁ`, soft hyphens, curly quotes otherwise poison matching). Empty output from every tool plus `pdftotext` printing only form feeds → the PDF is scanned images → rasterize (`pdftoppm -r 200..300`) then tesseract; never OCR a layout column guess. On unruled tables, do NOT trust `extract_tables()`; cluster `extract_words()` by `top` (tolerance ~3 pt) then split columns by x-bucket. Budget: pdfplumber ~0.5–2 s/page, so on 300-page docs restrict to page ranges (`-f/-l`, `pdf.pages[i:j]`) or grep the dump of `pdftotext` first and open only the hit pages.

## 10. tesseract flags

OCR only when no text layer exists. PSM decides quality, not the language pack. Default `--psm 3` assumes a full printed page and mis-segments cropped UI.

```
tesseract shot.png out --psm 6 -l eng          # terminal/dialog/code: uniform block — workhorse
tesseract caption.png stdout --psm 7           # one line: button label, status cell
tesseract badge.png out --psm 13               # raw pre-cropped line
tesseract watermarked.png out --psm 11         # sparse text over graphics
tesseract amount.png out --psm 7 -c tessedit_char_whitelist=0123456789.:-
tesseract shot.png stdout tsv                  # words + bbox + confidence, TS output extension switches their exit-code roles reused
```

Run `tesseract --list-langs` first; language failure = missing `.traineddata` or bad `TESSDATA_PREFIX`. Upscaling 2× with grayscale (`magick x.png -colorspace gray -resize 200% png:- | tesseract - stdout --psm 6`) beats any flag on 1× small-font screenshots.

## 11. regex mini-atlas

Pick engine first, then pattern — lookbehind support differs: PCRE2 (`rg --pcre2`, `grep -P`, python `re`) wants fixed-width lookbehind. .NET / PowerShell `[regex]` allows variable-width. JS: modern V8 accepts lookbehind, old engines don't. Go RE2 / rg default: outright rejects lookaround AND backreferences. When a pattern won't compile, don't fight the engine — match broad, then filter the exclusion in downstream code (`rg -o 'pat' | rg -v 'ban'`, or a comprehension). One rule: never try to fully validate IPv6 or semver with one regex; match candidates, validate in code.

Library-ready patterns (email/semver/ip/date):

```
email        ([\w.+-]+@[\w-]+(?:\.[\w-]+)+)
semver loose v?(\d+)\.(\d+)\.(\d+)(?:-([\w.+-]+))?
semver full  ^(?P<major>0|[1-9]\d*)\.(?P<minor>0|[1-9]\d*)\.(?P<patch>0|[1-9]\d*)(?:-(?P<pre>[0-9A-Za-z.-]+))?(?:\+(?P<build>[0-9A-Za-z.-]+))?$   # named groups: (?P<name>…) python/rg; (?<name>…) .NET & modern JS
ipv4+port    \b(?:(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)\.){3}(?:25[0-5]|2[0-4]\d|1\d\d|[1-9]?\d)(?::(\d{2,5}))?\b   # match-then-cast, ints≥256 already impossible
iso8601      \d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?(?:Z|[+-]\d{2}:?\d{2})?)?
human date   \d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*,?\s+\d{4} | (?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}
uuid         \b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b
url          https?://[^\s<>"']+ with .rstrip('.,;:!?)') after, parens/quotes overlap links
```

Verify before believing: test any pattern against 3 positive + 3 negative samples (`py -c "import re;print(re.findall(r'…', sample))"`). Catastrophic backtracking (`(a+)+b` on nonmatches): RE2-immune, PCRE/python freeze — bound with timeouts or atomic groups.

## 12. encoding hell

Files on disk are bytes; display encoding is a separate lie layered on top. Ground rules: pwsh 7 defaults to UTF-8 everywhere; PowerShell 5.1 reads the *console* at the OEM codepage (`chcp` 437/850/936…) and scripts by BOM — a UTF-8 `.ps1` saved **without** BOM by pwsh 7 gets parsed as ANSI by 5.1 and its é/—/中文 become mojibake in the *source*, not just the output. Save shared scripts with BOM (`[Text.UTF8Encoding]::new($true)`) or keep .ps1 pure-ASCII. Read reliably: `Get-Content -Raw -Encoding utf8` (5.1 semantics!) or `[IO.File]::ReadAllText($p,[Text.Encoding]::UTF8)`. Write BOMless UTF-8: `[IO.File]::WriteAllText($p,$s,[Text.UTF8Encoding]::new($false))` — note PS 5.1 `Set-Content -Encoding UTF8` *adds* a BOM and `Out-File` defaults to UTF-16LE, while pwsh 7 `Set-Content/Out-File` default to BOMless UTF-8 (`-Encoding utf8BOM` if you need the old shape). JSON parsers that choke on `ï»¿`/`锘縝` got the BOM; strip in python with `utf-8-sig` or `lstrip('\ufeff')`.

Console + children: `chcp 65001` alone is not enough — pair with `[Console]::OutputEncoding=[Text.Encoding]::UTF8`, and set `PYTHONUTF8=1` or `PYTHONIOENCODING=utf-8` so python subprocesses stop crashing on cp1252 stdout. Java tools need `-Dfile.encoding=UTF-8`; git needs `core.quotepath false` to stop escaping non-ASCII filenames into `\303\251` octals.

Mojibake rescue = reverse the wrong decode, on a copy of the bytes. Signatures: `Ã©` for `é` → UTF-8 read as cp1252: `s.encode('cp1252').decode('utf-8')`; `â€™` curly quote same cause; `é→ï¿½` chains after latin1 bets are dead as `□`/U+FFFD — bytes already destroyed, don't "fix", re-fetch. `锟斤拷` = UTF-8→GBK→UTF-8 double mangling, partially recoverable via `s.encode('gbk','ignore').decode('utf-8','replace')`. Diagnose honestly: `file -bi` / python `chardet`/`charset_normalizer` guess, `head -c 16 f | xxd` shows the BOM. Tool choice: `iconv -f latin1 -t utf-8//TRANSLIT in > out` (`//IGNORE` drops, `//TRANSLIT` approximates); on Windows, git-bash bundles iconv. PowerShell Ultimate Encoding (module) automates guessing when `Get-Content`'s defaults betray you.

## 13. Networking probes — order of cheapness

Go cheapest → loudest; stop as soon as the question is answered. (1) Name: `Resolve-DnsName host -Type A` (PS), `getent hosts`/`dig +short` (Linux), `nslookup` fallback. (2) TCP reach: `Test-NetConnection host -Port 443` reports `TcpTestSucceeded` but is slow (it does DNS + ICMP first) — on failure read which stage died. Linux equivalents in cost order: `timeout 3 bash -c '</dev/tcp/10.0.0.5/8080' && echo OPEN` (no external binary, shell builtin), `ss -ltnp | rg :8080` for *local* listeners before probing remote, `ss -tn state established '( dport = :443 )'` who's connected where. (3) Local binding sanity: `ss -ltn` vs `netstat -ano` (Windows) → map PID `Get-Process -Id (netstat -ano | findstr :5432).Split()[-1]`, then `Get-Process -Id $pid | Select Path`. Loopback confusion: server bound `127.0.0.1` vs `0.0.0.0` is the #1 "works inside, refused outside" cause — `ss -ltn` shows the bind address; Windows firewall is #2 (check `Get-NetFirewallRule -DisplayGroup "File and Printer Sharing" | fl` or netsh, not just antivirus). (4) Route/MTU weirdness: `ping`/tracert only prove ICMP if ICMP is allowed (many hosts drop it → false timeout while TCP works — prefer TCP probes); `ip route get 8.8.8.8` shows egress interface + source IP; `Test-Connection` in PS 7 vs CIM `Win32_PingStatus` in 5.1. (5) TLS: `openssl s_client -connect host:443 -servername host` (print subject/issuer/expiry: pipe to `openssl x509 -noout -subject -enddate`); Windows: `curl -vI https://host` reveals cert chain verdict cheaply. (6) HTTP breadcrumbs: `curl -sS -o /dev/null -w '%{http_code} %{remote_ip} %{time_total}\n'` distinguishes DNS-TLS-connect-time vs server-slow. Proxy reality check: `$env:HTTP_PROXY` / `netsh winhttp show proxy` / `Get-ItemProperty 'HKCU:\…\Internet Settings' | select ProxyEnable,ProxyServer` all differ in who honors them — browsers, curl, git, WinHTTP each read a different store.

## 14. Windows triage trio — process, service, scheduled task

Answering "what is actually running / will it run again on boot".

```powershell
Get-Process node | Select-Object Id,StartTime,Path   # Path is $null without elevation for other users' procs
(Get-CimInstance Win32_Process -Filter "ProcessId=$pid").CommandLine   # full args incl. secrets — mask when reporting
Get-Service | Where Status -eq 'Running'
Get-CimInstance Win32_StartupCommand | select Name,Command,Location     # HKCU/HKLM Run keys,StartUp folders
sc.exe queryex Showing-Service    # PID + service state; sc start/stop needs elevation; Restart-Service is friendlier
```

Cross-checks: image file name vs `Get-Process` list vs Task Scheduler `Get-ScheduledTask | ? State -eq 'Running'` — startup entries hide in three stores at once, fix "app won't stay open" that way. Port-to-owner without admin: `Get-NetTCPConnection -LocalPort 8080 | Select OwningProcess` then map the PID. When a service dies right after start, read its own exit reason, not speculation: `Get-WinEvent -FilterHashtable @{LogName='System'; ProviderName='Service Control Manager'} -MaxEvents 20 | Format-List TimeCreated,Message` — SCM logs event 7031 (crashed) / 7034 (terminated unexpectedly) / 7000 (start failed, often a path/permission problem) with the service name. If `Path` is `$null` you're hitting the elevation wall: relaunch the probe elevated (`Start-Process powershell -Verb RunAs`) rather than guessing the binary location.
