# Shell and Command Line — the agent's steering wheel

The shell (bash on Linux/macOS, PowerShell/cmd on Windows) is the fastest, most reliable way to operate a computer. Prefer it over clicking whenever a task touches files, processes, text, or the network. Every command returns an exit code (0 = success, non-zero = failure — always check `$?` in bash or `$LASTEXITCODE` in PowerShell after non-trivial commands).

## File operations

- `ls -la` — list everything including hidden files (dotfiles). `-l` shows permissions, owner, size, mtime; `-h` human-readable sizes; `-t` sort by time; `-r` reverse.
- `cp -r src/ dest/` — copy recursively (required for directories). `cp -i` prompts before overwrite; `cp -u` copies only newer files.
- `mv old new` — move or rename. Atomic within one filesystem; cheap. Use `mv -i` to avoid clobbering.
- `rm file` — delete. `rm -r dir/` recursive; `rm -f` force, no prompt. DANGER: `rm -rf` on a wrong path is unrecoverable — always run `pwd` and `ls` first to verify location, prefer exact paths, never wildcard+rf near `/` or `$HOME` unless certain.
- `mkdir -p a/b/c` — create nested dirs, no error if existing.
- `touch file` — create empty file or bump mtime.
- `ln -s target linkname` — symlink. Broken symlink if target moves. `readlink -f` resolves full path.
- `find /path -name "*.log" -mtime -7` — find by name pattern modified under 7 days ago. `-type f` files only, `-type d` dirs, `-size +100M` big files, `-exec cmd {} \;` run command per hit, `-delete` remove matches. `find` walks recursively by default; `-maxdepth 1` restricts.
- `rg pattern` (ripgrep) — the modern grep: recursive by default, respects .gitignore, fast. `rg -l` file names only; `rg -c` counts; `rg -i` case-insensitive; `rg -A 3 -B 3` context lines; `rg --type py` filter by file type; `rg 'fn\s+\w+'` regex. If rg absent: `grep -r "pattern" . --include="*.py"`.
- `du -sh *` — size of each entry in cwd. `df -h` free disk space. `ncdu` interactive disk explorer if installed.
- `file thing` — identify file type by content, not extension.
- `head -n 50 file` / `tail -n 50 file` — first/last lines. `tail -f logfile` follows a growing log (Ctrl+C to stop). `less file` for paginated reading (q quits, / searches).
- `wc -l file` counts lines; `sort | uniq -c | sort -rn` is the classic frequency histogram.

## Text operations

- `cat a b > combined` concatenate; `cat` alone dumps a file to stdout.
- `grep "error" app.log` — lines matching. `-v` invert, `-o` only the matched part, `-E` extended regex, `-P` perl regex (lookarounds).
- `sed 's/foo/bar/g'` — stream replace. In-place: `sed -i 's/old/new/g' file` (macOS: `sed -i '' ...`). `sed -n '10,20p'` prints lines 10-20. `sed '/pattern/d'` deletes matching lines.
- `awk '{print $1}'` — column extraction (whitespace-delimited). `awk -F, '{print $2}'` CSV second column. `awk '$3 > 100'` filter rows. Sum a column: `awk '{s+=$1} END {print s}'`.
- `cut -d: -f1 /etc/passwd` — delimiter field cut. `tr 'a-z' 'A-Z'` transliterate. `tr -d '\r'` strip CR.
- `xargs` — turn stdin into command args. `find . -name "*.tmp" | xargs rm` or safer with null-delimiting: `find . -name "*.tmp" -print0 | xargs -0 rm`. `xargs -I{} cp {} /dest/` placeholder form.
- `diff a b` differences; `comm`/`join` set ops on sorted files; `jq` for JSON (see below); `column -t -s,` pretty-print aligned columns.
- JSON: `jq '.items[].name' data.json`, `jq -r` raw strings (no quotes), `jq '.[] | select(.status=="ok")'` filter. YAML: `yq`. Prefer `jq` over regexing JSON — always.

## Pipes, redirection, exit codes

- `cmd1 | cmd2` — stdout of cmd1 becomes stdin of cmd2. Chain freely: `cat access.log | awk '{print $1}' | sort | uniq -c | sort -rn | head`.
- `> file` overwrite stdout, `>> file` append, `2> file` stderr, `2>&1` merge stderr into stdout, `&> file` both to one file, `< file` stdin from file, `> /dev/null 2>&1` silence everything.
- `cmd1 && cmd2` — run cmd2 only if cmd1 succeeded. `cmd1 || cmd2` — only if failed. `cmd1 ; cmd2` — unconditionally.
- Exit codes: 0 success, 1 general error, 2 misuse (grep: no match = 1, error = 2), 126 not executable, 127 command not found, 130 Ctrl+C. Test in scripts: `if [ $? -eq 0 ]` or just `if cmd; then ...`.
- Command substitution: `$(cmd)` or backticks — `files=$(find . -name "*.txt")`. Process substitution: `diff <(ls a) <(ls b)`.
- Brace expansion: `mkdir {a,b,c}`, `mv file.{txt,bak}`. Glob: `*.txt`, `?` one char, `[0-9]`. Glob does not match dotfiles by default.

## Environment variables

- `export VAR=value` set for session; `VAR=value cmd` set for one command only. `echo $VAR` read, `env` list all, `unset VAR` remove.
- `PATH` — colon-separated dirs searched for executables. `which cmd` / `command -v cmd` shows what will run. Add a dir: `export PATH="$PATH:/opt/bin"` (append to ~/.bashrc or ~/.zshrc to persist).
- Useful vars: `$HOME`, `$USER`, `$PWD`, `$OLDPWD`, `$HOSTNAME`. `$?` last exit code, `$$` shell PID, `$!` last background PID.
- .env pattern: `set -a; source .env; set +a` loads KEY=VALUE lines into env.
- Secrets: never `echo` tokens into logs; prefer reading from env or files with `chmod 600`.

## Processes

- `ps aux | grep name` — find a process. `pgrep -af python` — PID + command line match. `pidof name` exact.
- `kill PID` — SIGTERM (polite). `kill -9 PID` — SIGKILL (force, no cleanup; last resort). `kill -HUP PID` reload config for many daemons.
- `pkill -f "pattern"` — kill by command-line match. `killall name` by exact name. Safer: `pgrep -af pattern` first, verify, then kill.
- `jobs` list background jobs in current shell; `cmd &` start backgrounded; `fg %1` foreground; `bg %1` resume in background; Ctrl+Z suspends.
- `nohup cmd > out.log 2>&1 &` — survives shell logout; `disown` removes from job table. For real persistence use systemd, tmux, or screen instead.
- `top` or `htop` — live process view (`htop` nicer: F6 sort, F9 kill). `ps aux --sort=-%mem | head` top memory hogs. `/proc/<pid>/` has everything: cmdline, cwd, environ.
- `lsof -i :8080` — what holds port 8080. `lsof /path/file` — what has it open. `fuser -k 8080/tcp` kill by port.

## Networking: ssh, curl, wget

- `ssh user@host` — remote shell. `ssh -i key.pem user@host` key auth. `ssh -L 8080:localhost:80 user@host` local port forward. `scp local user@host:/path/` copy over ssh. `rsync -avz src/ user@host:dest/` incremental sync (prefer over scp for trees).
- `curl` — the HTTP workhorse. `curl -s url` silent GET; `curl -O url` save with remote name; `curl -o file url` save as; `curl -I url` headers only; `curl -L url` follow redirects; `curl -X POST -H "Content-Type: application/json" -d '{"k":"v"}' url` JSON POST; `curl -H "Authorization: Bearer TOKEN" url`; `curl -u user:pass url` basic auth; `curl -F "file=@a.png" url` multipart upload; `curl -s url | jq .` inspect JSON APIs. `-w '%{http_code}'` prints status; `-f` fail on HTTP error; `-k` skip TLS verify (debugging only).
- `wget -q url` quiet download; `wget -c` resume; `wget -r -np -k url` mirror a page tree (careful).
- `ping -c 4 host` connectivity; `dig host` / `nslookup host` DNS; `ss -tlnp` listening ports with processes; `ip addr` / `ip route` interfaces and gateway; `traceroute host` path. Test a port: `curl -v telnet://host:port` or `nc -zv host port`.

## sudo and permissions context

- `sudo cmd` run as root; `sudo -i` root shell; `sudo -u user cmd` as another user. Agents: if a command fails with "Permission denied," first check ownership (`ls -la`), try without sudo if it's in your own home, use sudo only when clearly required (system dirs, ports <1024, package installs).
- Never run `curl ... | sudo bash` blindly — inspect the script first.

## Package managers

- Debian/Ubuntu: `apt update && apt install -y pkg`, `apt search term`, `apt remove pkg`, `dpkg -L pkg` files installed, `dpkg -S /path/file` which package owns it.
- RHEL/Fedora: `dnf install pkg`. Arch: `pacman -S pkg`. Alpine: `apk add pkg`.
- macOS: `brew install pkg`, `brew search term`, `brew list`, `brew services start name`.
- Python: `pip install pkg` (prefer `python -m pip install pkg`), `pip install -r requirements.txt`, `pip show pkg`, `pipx install tool` for isolated CLI tools. Use venvs: `python -m venv .venv && source .venv/bin/activate`.
- Node: `npm install pkg` (local), `npm install -g pkg` (global CLI), `npx tool` run without install, `npm run script` package.json scripts.
- Rule: install with the ecosystem's own manager (pip/npm/brew), use apt only for system-level deps.

## Scripting patterns (bash)

- Skeleton: `#!/usr/bin/env bash` then `set -euo pipefail` — exit on error, undefined var, pipe failure. This prevents silent half-runs.
- Args: `$1`, `$2`, `$@` all, `$#` count, `shift` rotate. Validate: `: "${1:?usage: script.sh FILE}"`.
- Conditionals: `if [ -f file ]` exists-file, `-d dir`, `-z "$s"` empty string, `-n` non-empty, `[ "$a" = "$b" ]` string eq, `-eq -ne -lt -gt` numeric, `[[ str == *pat* ]]` glob match. `cmd && echo ok || echo fail`.
- Loops: `for f in *.log; do echo "$f"; done`, `while read -r line; do ...; done < file` read lines safely, `while true; do cmd; sleep 5; done` simple poll loop (prefer `watch cmd`).
- Capture output: `out=$(cmd)`; always quote: `"$out"`. Quote all variable expansions unless you intentionally want word-splitting.
- Temp files: `tmp=$(mktemp)`; cleanup with `trap 'rm -f "$tmp"' EXIT`.
- Logging: `echo "[$(date -Is)] message" >&2` — messages to stderr, data to stdout, so pipelines stay clean.
- Read stdin when piped: `[ -p /dev/stdin ] && cat - || cat "$1"` pattern makes tools work both ways.

## Here-docs and inline content

- Create a file with content: `cat > file.txt <<'EOF'` ... `EOF` — quoted delimiter prevents variable expansion (use unquoted `EOF` to expand vars inside).
- Append: `cat >> file <<'EOF'`. Feed a command: `python3 <<'EOF'` for inline scripts, `ssh host <<'EOF'` to run remote commands.
- Multi-line into sudo: `sudo tee /etc/conf <<'EOF'` (tee because `>` redirection happens as the unprivileged user).
- Here-string: `cmd <<< "one line of stdin"`.

## High-reliability agent patterns

- Verify before destroying: `ls` the target, then act, then `ls` again to confirm.
- Idempotence: `mkdir -p`, `touch`, `grep -q pattern file || echo pattern >> file`.
- Dry-run flags exist: `rsync -n`, `mv -i`, `apt --dry-run`. Use them first.
- Check success explicitly: `cmd && echo OK || echo FAIL`; read actual exit codes; never assume.
- Long outputs: pipe to `head` to sample, redirect full output to a file and read slices with `sed -n '1,100p' file`.
- When a command isn't found: `which cmd`, then check PATH, then install via the right package manager.
