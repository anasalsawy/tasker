# Linux Systems — the machine underneath

A working mental model of Linux for an agent that must observe, change, and repair a live system. Everything here is operational: what to run, what it returns, and what the result means.

## 1. The process model

Linux runs everything as a process. A process has a PID, a parent PPID, a user (UID/GID), a state, an environment block, open file descriptors, and a memory map. There is no separate "application" concept — an app is a process tree.

- `ps -ef` / `ps aux` — snapshot of all processes. `aux` = BSD format (USER, PID, %CPU, %MEM, VSZ, RSS, TTY, STAT, START, TIME, COMMAND); `-ef` = full listing with PPID in column 3.
- `ps -eo pid,ppid,user,stat,rss,etime,args --sort=-rss | head -20` — precise and machine-parseable: top memory consumers. `--sort=-cpu` for CPU. `etime` = elapsed wall time. `args` = full command line, which reveals flags, config paths, and which of several look-alike services is the one you care about.
- `pgrep -a pattern` — PIDs plus command lines. `-u user` for scoping; `-f` matches the full command line, not just the 15-char `comm` name. `pkill` takes the same selectors. ALWAYS run the `pgrep` first, confirm the list, then kill.
- Process states in `STAT`: `R` running; `S` interruptible sleep (normal — waiting on something); `D` **uninterruptible sleep** (stuck inside a kernel call — usually disk, NFS, or a driver; `kill -9` will NOT free it); `T` stopped (SIGSTOP / job control); `Z` **zombie** (exited but the parent never reaped it; consumes only a PID slot — fix by signalling or restarting the *parent*, not the zombie). Trailing flags: `s` session leader, `l` multithreaded, `+` in the foreground process group, `<` high priority, `N` nice'd down.
- A `D`-state process will not die, and knowing that saves minutes of flailing. Find what it is blocked on: `sudo cat /proc/<pid>/stack`, `ls -l /proc/<pid>/cwd` (is it on a dead NFS mount?), `sudo dmesg -T | tail -50` for I/O errors.

Every process exposes its truth under `/proc`:
- `/proc/<pid>/cmdline` — argv, NUL-separated: `tr '\0' ' ' < /proc/$PID/cmdline`.
- `/proc/<pid>/exe` — symlink to the real binary. If it reads `-> /usr/bin/foo (deleted)` the binary was replaced while the process kept running: the classic "I upgraded the package but the old code is still serving" tell. Restart it.
- `/proc/<pid>/cwd` — its working directory. Critical: `.env`, `config.yaml`, and every relative path resolve here, not next to the binary. Explains "my edit had no effect" far more often than caching does.
- `/proc/<pid>/environ` — the exact environment the process started with: `sudo cat /proc/$PID/environ | tr '\0' '\n' | sort`. Use this to confirm a service actually got the variable you believe you exported. Shell exports never reach an already-running service.
- `/proc/<pid>/fd/` — open descriptors as symlinks: `ls -l /proc/$PID/fd`. 0/1/2 are stdin/stdout/stderr; in a daemon they usually point at a journald socket or `/dev/null`.
- `/proc/<pid>/status` — State, Threads, VmRSS, Uids. System-wide: `/proc/meminfo`, `/proc/cpuinfo`, `/proc/uptime`, `/proc/loadavg` (compare the 1-minute number with `nproc`; sustained load above core count means queueing).
- `sudo dmesg -T` / `journalctl -k -b` — kernel ring buffer: OOM kills, disk errors, segfaults, USB attach. If a process vanished silently, search for `Out of memory: Killed process <pid> (name)`.
- Threads: `ps -T -p <pid>`; live per-thread CPU with `top -H -p <pid>`. A runaway thread inside an otherwise healthy-looking service only shows up here.

Network namespaces: `lsns`, and `sudo nsenter -t <pid> -n -- ss -tlnp` to inspect from inside a container's view. A container and the host can each report port availability the other cannot see, which is why "that port is free" and "address already in use" can both be true at once.

Signals: `1 HUP` (many daemons reload config; systemd services usually ignore it — restart instead), `2 INT` (Ctrl+C), `9 KILL` (uncatchable, no cleanup — temp files and locks stay behind), `15 TERM` (default; catchable and graceful), `18 CONT`, `19 STOP` (catchable — prefer SIGSTOP when you want to pause a process you still intend to examine). SIGPIPE (`13`) kills a writer on a closed pipe, so `cmd | head -1` may report a harmless non-zero exit for the left-hand command.

Exit codes that recur: `0` success; `1` generic failure (also `grep` "no match" — a trap under `set -e`); `2` misuse or grep error; `126` found but not executable; `127` command not found; `128+N` killed by signal N, so `137` = SIGKILL (normally the OOM killer or an explicit `kill -9`) and `143` = SIGTERM (a clean shutdown request); `255` from `ssh` when the remote command failed or the connection dropped.

## 2. Filesystem hierarchy

One tree rooted at `/`. Other disks mount *into* it; there are no drive letters.

FHS — where things live and why:
- `/bin`, `/sbin` — essential binaries, now usually symlinks into `/usr/bin`, `/usr/sbin` ("merged /usr"). `/usr/bin` = distro packages; `/usr/local/bin` = machine-local installs, earlier in the default PATH, and the correct home for your own scripts and symlinks.
- `/etc` — machine-local configuration; text only, no binaries. Upgrades never silently overwrite a file you edited (dpkg prompts instead). Prefer drop-in directories so vendor files stay untouched: `/etc/systemd/system/`, `/etc/cron.d/`, `/etc/nginx/conf.d/`, `/etc/profile.d/`, `/etc/sudoers.d/`, `/etc/apt/apt.conf.d/`, `/etc/logrotate.d/`.
- `/var` — variable data. `/var/log` (syslog, journald, app logs, `/var/log/journal/`), `/var/lib` (persistent app state: `/var/lib/docker`, `/var/lib/postgresql`, `/var/lib/mysql`, `/var/lib/apt`), `/var/cache` (regenerable by design), `/var/spool` (cron/mail/cups queues), `/var/tmp` (survives reboot), `/var/run` → `/run` (tmpfs holding pid files and unix sockets, wiped at boot — a stale `/run/x.pid` or leftover socket after a crash is a common cause of "won't restart").
- `/tmp` — often tmpfs and aggressively purged (systemd-tmpfiles, frequently on reboot). Never keep long-lived state there; assume it can vanish mid-run. `/dev/shm` is RAM-backed shared memory used for IPC and caches; a container's small `/dev/shm` default sometimes breaks apps that memory-map large files.
- `/opt` — self-contained third-party software (`/opt/<vendor>/bin`, `lib`); add to PATH manually. `/srv` = site-supplied service data.
- `/home/<user>` — dotfiles and XDG dirs: `~/.bashrc`, `~/.profile`, `~/.config/<app>/`, `~/.local/bin`, `~/.local/share`, `~/.cache`, `~/.ssh` (700; `authorized_keys` 600; `id_ed25519` 600). XDG vars: `$XDG_CONFIG_HOME` (~/.config), `$XDG_DATA_HOME` (~/.local/share), `$XDG_STATE_HOME` (~/.local/state), `$XDG_CACHE_HOME` (~/.cache). A well-behaved agent writes config under `~/.config` and never assumes root.
- `/proc`, `/sys`, `/dev`, `/run` — virtual filesystems, not storage. sysfs exposes hardware and drivers: `/sys/class/dmi/id/product_name` (machine model), `/sys/class/net/eth0/operstate` (link state), `/sys/block/sda/queue/rotational`, `/sys/block/sda/device/timeout`, `/sys/kernel/mm/transparent_hugepage/enabled`.
- `/root` is root's home, mode 700 — unprivileged agents cannot read it without sudo. `/mnt` for manual mounts, `/media` for desktop automounts.

Device files: block devices appear as `/dev/sda`, `/dev/sda1`, `/dev/nvme0n1p1`, `/dev/mmcblk0p2`. `/dev/disk/by-id/` and `/dev/disk/by-uuid/` give stable names across reboots — use UUIDs in `/etc/fstab`, because `sdb` becomes `sdc` the moment someone unplugs a USB stick. `lsblk -f` shows the tree with filesystems, UUIDs and mount points; `blkid` lists UUIDs; `findmnt` shows real mounts with their options and is the best single command for "is this actually NFS or just a local directory?"

## 3. Permissions, ownership, and "Access denied"

Three classes (owner `u`, group `g`, other `o`) × three bits (r=4, w=2, x=1). `ls -l` prints 10 characters: type then triplets, e.g. `-rwxr-xr--` = 0754. Type char: `-` file, `d` dir, `l` symlink, `c`/`b` device, `s` socket, `p` fifo.

- **Directories need `x` to be traversed at all.** A directory at mode 444 hides its contents even though the files inside are readable — the most common "the directory looks empty though `stat` says it has files" bug. Writing into a directory additionally requires `w` on the *directory*, not the file: that is why "the file is 777 but I still cannot delete it" happens (deletion needs dir `w` + sticky-bit rules).
- Sane defaults: dirs 755, files 644, private keys 600, `~/.ssh` 700. World-writable files break SSH login under sshd `StrictModes`, and are a security hazard.
- `chmod 644 f`; `chmod -R u+rwX dir` (capital `X` sets the exec bit only on directories and already-executable files — the safe recursive form); `chmod u+x,go-w f`; `chown user:group f`; `chown -R`; `chgrp group f`. Inspect with `stat -c '%A %a %U:%G %n' f`. Symlinks: `chmod`/`chown` follow the link; use `-h` to act on the link itself.
- `umask` sets create-time defaults: `022` → files 644 / dirs 755; `002` for shared group work; `077` private. Files are created as `666 & ~umask`, which is why they never gain +x by default. Check with `umask`; persist in `~/.bashrc`, or per-service with `UMask=` in a unit.
- Special bits: setuid on a binary (`/usr/bin/passwd` runs as the file's owner) shows as `s` in the owner slot; setgid on a file (runs as the file's group) and setgid on a **directory** (children inherit the directory's group *and* the setgid bit) — how team-shared folders work: `sudo chgrp team dir && sudo chmod 2775 dir`. The sticky bit (shown as `t`) means only an entry's owner (or root) may delete or rename it, which is exactly why `/tmp` is `1777` rather than `777`.
- ACLs grant beyond the three classes: `getfacl f`; `setfacl -m u:bob:rw f`; `setfacl -m g:deploy:rx f`; `setfacl -d -m u:bob:rw f` sets a *default* ACL inherited by new children; `-R`, `-b` remove all, `-x u:bob` delete one entry. A `+` at the end of `ls -l` output means "an ACL exists, look with getfacl". "It's group-writable but the other user still can't write" is usually a missing default ACL, a parent directory without `x`, or the user not actually in the group in the current session (`id` — group membership needs a fresh login).
- Immutable flags surprise: `lsattr` may show `i` → even root cannot modify or unlink until `sudo chattr -i f`. `getcap /usr/bin/ping` explains a binary that needs no setuid.
- SELinux (RHEL/Fedora/Alma/Rocky; enforcing by default) denies access that `ls -l` cannot explain: nginx 403 on a world-readable file, ssh refusing a key, a container blind to a bind-mounted volume. Diagnose: `getenforce`, `ls -Z f`, `ps -Z`, and the smoking gun `sudo ausearch -m avc -ts recent`. Fix properly: `sudo semanage fcontext -a -t httpd_sys_content_t '/data/site(/.*)?' && sudo restorecon -Rv /data/site`; non-standard ports need `sudo semanage port -a -t http_port_t -p tcp 8443`; behaviour switches are booleans — `getsebool -a | grep httpd`, `sudo setsebool -P httpd_can_network_connect 1`. For container bind mounts use the `:Z` / `:z` mount option. `sudo setenforce 0` masks the problem and reverts on reboot — last resort only. Quick test of "is it SELinux?": `sudo setenforce 0`, retry the action, set it back. AppArmor (Ubuntu/SUSE) is friendlier: `sudo aa-status`, denials in `/var/log/syslog` or `sudo dmesg | grep -i apparmor`, profiles in `/etc/apparmor.d/`, `sudo tallylog`-style learning mode with `aa-complain /etc/apparmor.d/usr.sbin.nginx`.
- systemd hardening directives also produce "permission denied" that no chmod can fix: `PrivateTmp=yes`, `ProtectSystem=strict`, `ProtectHome=yes`, `ReadOnlyPaths`/`ReadWritePaths`, `DynamicUser=yes` (the service runs as an ephemeral uid that owns nothing on disk). Inspect with `systemctl show foo -p ProtectSystem,PrivateTmp,DynamicUser,ReadWritePaths` or `systemctl cat foo`. The fix is a `ReadWritePaths=` drop-in, not `chmod 777`.
- Processes do not re-check permissions on FDs already open: after fixing perms, restart the service.

sudo mechanics: `sudo cmd`; `sudo -i` root login shell; `sudo -u svc cmd` as another user; `sudo -l` (check what you are actually allowed to run before promising a fix); `sudo -n cmd` non-interactive — fails instead of prompting, which is what automation wants; `sudo !!` re-runs the previous command as root. If sudo demands a tty where none exists, use `sudo -S` with the password on stdin (it leaks into shell history and process listings — avoid) or fix the policy. Never pipe a remote script into `sudo bash` without reading it: `curl -fsSL <url> | less` first, then run the reviewed file.

## 4. systemd: services, units, timers, and logs

`systemctl` is the service manager and init (PID 1) on most modern distros. Inside a container with no systemd, run processes directly or use a supervisor instead.

Unit search paths, in increasing precedence: `/usr/lib/systemd/system/` (package-installed; also `/lib/systemd/system/` on Debian/Ubuntu), `/run/systemd/system/` (runtime, non-persistent), `/etc/systemd/system/` (admin — where YOUR units belong). `systemctl cat foo.service` prints the effective file *and every drop-in*, each preceded by `# /path/to/file` — the fastest way to see what really runs. If a unit is not where you expect: `find /etc /usr/lib /run -name 'foo.service'`.

Everyday verbs: `systemctl start|stop|restart foo`; `systemctl reload foo` (sends SIGHUP — only works if the daemon supports it; check with `systemctl can-reload foo`); `systemctl status foo` (state, main PID, cgroup, last log lines); `systemctl daemon-reload` (required after ANY edit to a unit file or drop-in — forgetting this is the single biggest cause of "I changed the file and nothing happened"); `systemctl reset-failed foo` (clears failed state and the start-limit counter); `systemctl enable --now foo` (start now and at boot); `systemctl disable --now foo`. Scriptable checks: `systemctl is-active --quiet foo || echo down`, `systemctl is-enabled foo`, `systemctl list-units --type=service --state=running --no-pager`, `systemctl list-unit-files --state=enabled`. Remember `enabled`/`disabled`/`static`/`masked` describe *boot* behaviour while `active`/`inactive`/`failed`/`activating` describe *now* — so a unit can be active-but-disabled (fine until reboot) or enabled-but-failed.

A **masked** unit cannot start at all (its file is a symlink to `/dev/null`, created by `systemctl mask`): `systemctl unmask foo` first, then start. This is a frequent deliberate state in packaging (e.g. masking `getty` in containers), so check for it before concluding a service is broken. A **static** unit has no `[Install]` section and is meant to be pulled in by another unit (`.socket`, `.path`, `.target`) — if you want it always on, write your own unit in `/etc/systemd/system/` rather than fighting the vendor's.

Template units have `@` in the name: `serial-getty@ttyS0.service`, `myapp@worker1.service`. The instance string after `@` substitutes `%i` (plain) and `%I` (unescaped) inside the unit; `%n` is the full unit name, `%N` the name without suffix, `%p` the prefix, `%H` the hostname. Note `-` inside the instance is a field separator in some contexts, so avoid hyphens in instance names if you rely on `%i` splitting. Manage instances with `systemctl list-units 'myapp@*'`.

A well-formed unit for an agent-deployed app:

```ini
# /etc/systemd/system/myapp.service
[Unit]
Description=MyApp worker
Documentation=https://example.com/docs
After=network-online.target postgresql.service
Wants=network-online.target

[Service]
Type=simple
User=app
Group=app
WorkingDirectory=/opt/myapp
Environment=PORT=8080
EnvironmentFile=-/etc/myapp/env
ExecStart=/opt/myapp/venv/bin/python -m myapp serve
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=3
StartLimitIntervalSec=60
StartLimitBurst=5
StandardOutput=journal
StandardError=journal
NoNewPrivileges=true
PrivateTmp=true

[Install]
WantedBy=multi-user.target
```

Rules that matter:
- `ExecStart` does **not** run through a shell. No pipes, no `&&`, no globs, no `~`, no variable expansion beyond systemd's own `%`/`$` forms. If you need a pipeline, write a script or use `ExecStart=/bin/bash -c '...'` (and then quote carefully). Each argument is split on whitespace: `systemd` does not honour the shell's quoting rules the way people expect — the recommended pattern is a wrapper script with `#!/usr/bin/env bash`.
- Values starting with a special char are modifiers: `-foo` ignores its failure, `+` runs as root, `@` strips argv[0], `!` runs with full privileges. Put the modifier first.
- `Environment=` uses `NAME=value` with no spaces around `=`; values with spaces need double quotes inside the assignment. `EnvironmentFile=` reads a plain `KEY=value` file; a leading `-` means "missing file is OK". Variables from the file expand in `ExecStart` as `${VAR}` — and they must be exported, not just defined, to reach child processes. `$ VARIABLE` in a unit expands from the manager's environment, not the service's, so prefer `${VAR}` for service-level vars.
- systemd drops the user's shell PATH for services: `Environment=PATH=/usr/local/bin:/usr/bin:/bin` if a command "is not found" in the service but works in your shell. Never put relative paths in `ExecStart`.
- `WorkingDirectory=` must exist and be readable, or the service fails with status=203/EXEC or 204/OUTOF… usually `200/CHDIR`. `chdir` failures look mysterious in `systemctl status`.
- `status=203/EXEC` = the binary cannot be executed: wrong path, missing shebang, not executable, arch mismatch (an x86 binary on ARM: `file /opt/app/bin/tool` and `uname -m`). `status=127/EXEC`-ish codes from `ExecStartPre` are the same idea for hook scripts. `status=217/USER` = the `User=` does not exist (common after `useradd` in the wrong place or in containers). `status=218/`GREP = group missing.
- Timeout: `TimeoutStartSec` (default 90s) kills a service that never signals readiness; `TimeoutStopSec` then escalates SIGTERM → SIGKILL. A "service takes forever then dies" log is usually this. For DB-backed apps that need retries to connect, either fix ordering or raise the timeout.
- Start-limit: repeated crashes produce `Start request repeated too quickly.` Clear it with `systemctl reset-failed foo` after fixing the cause, otherwise systemd keeps refusing.
- Ordering vs. requirement: `After=` only sequences *startup*, it does not require the unit; add `Requires=` (failure propagates) or `Wants=` (soft). Neither means "the database is accepting connections" — that needs an app-level retry loop, `Type=notify`, or a socket with `Deferr…`.
- Sandbox/hardening options that break apps: `PrivateTmp=yes` (the service gets its own `/tmp`, so a file you wrote in `/tmp` from your shell is invisible to it — a top cause of confusing "No such file or directory"); `ProtectSystem=strict` (read-only everything except `ReadWritePaths=`); `ProtectHome=yes`; `DynamicUser=yes` (ephemeral uid that owns no files and changes each start — stored-file perms must come from `StateDirectory=`, which gives it `/var/lib/<name>` owned by that uid). Check active hardening with `systemctl show foo -p PrivateTmp,ProtectSystem,ProtectHome,DynamicUser,ReadWritePaths`. See also `strace` below for the definitive answer.
- Resources: `CPUQuota=200%`, `MemoryMax=1G`, `MemoryHigh=800M` (throttles before OOM-killing), `IOWeight=`, `TasksMax=` ( hitting `TasksMax`/pid limits surfaces as "cannot allocate memory" from fork, which is really EAGAIN — check `systemctl show -p TasksMax` and `ps -eLf | wc -l`). Limits apply per-cgroup, so the whole process tree is covered: `systemd-cgls` and `systemd-cgtop` show the tree and its usage.
- Verify unit syntax before reloading: `systemd-analyze verify /etc/systemd/system/myapp.service` catches typos, unknown directives and missing dependencies. Visualise boot: `systemd-analyze blame`, `systemd-analyze critical-chain nginx`.

Drop-in overrides beat editing vendor files. Use `systemctl edit nginx` (creates `/etc/systemd/system/nginx.service.d/override.conf`, validates on save, and does `daemon-reload` for you) or `systemctl edit --full nginx` to copy the whole unit into `/etc`. Fragments in a unit's `.d/` directory merge in filename order; the one called `override.conf` wins. To *replace* a list-valued directive you must first assign an empty value, then add the new ones on separate lines:

```ini
[Service]
ExecStart=
ExecStart=/opt/custom/nginx -c /etc/custom/nginx.conf
Environment=
Environment="PORT=9090"
```

Then `sudo systemctl daemon-reload && sudo systemctl restart nginx`, and confirm the *computed* result — not the file — with `systemctl show nginx -p ExecStart -p Environment -p User -p WorkingDirectory`.

Timers replace cron for system work. A `foo.timer` beside `foo.service` activates it (and a single `.service` can be triggered by several timers, which makes tracing a job hard — check `systemctl list-timers` rather than grepping crontabs):

```ini
# /etc/systemd/system/cleanup.timer
[Unit]
Description=Nightly cleanup
[Timer]
OnCalendar=*-*-* 03:17:00
RandomizedDelaySec=10m
Persistent=true
Unit=cleanup.service
[Install]
WantedBy=timers.target
```

`OnCalendar=` accepts `minutely hourly daily weekly monthly`, `*-*-* 03/2:00:00` (every 2 hours), `Mon,Fri *-*-* 09:00:00`, and weekday ranges; `OnUnitActiveSec=1h`/`OnBootSec=5min` are relative timers. `AccuracySec` defaults to 1 minute — timers deliberately batch wakes, so a "runs at :00" job may start up to a minute late; set `AccuracySec=1us` when you need precision. `Persistent=true` runs the missed job at next boot (essential for backup-style timers on machines that are off at 3am). Enable with `sudo systemctl enable --now cleanup.timer`. Inspect with `systemctl list-timers --all` (NEXT/LEFT columns show whether it is truly scheduled), validate an expression with `systemd-analyze calendar 'Mon *-*-* 09:00:00'`, and test by starting the *service* directly (`systemctl start cleanup.service`) rather than waiting for the schedule. Note timers fire in the **system** timezone (`timedatectl` shows it; `cat /etc/timezone`), and calendar specs use local time, not UTC — a frequent source of "it ran at the wrong hour on that VPS in another region".

Other unit types worth knowing: `.mount`/`.automount` (generated from `/etc/fstab`, so `systemctl restart home.mount` remounts); `.socket` (socket activation — the service starts on first connection, so `ss -tlnp` may show the socket owned by systemd rather than your process); `.path` (trigger when a file changes); `.target` (grouping, e.g. `multi-user.target`, `graphical.target`); `.slice` (cgroup resource group); `.swap`. `systemctl list-dependencies foo` prints the dependency tree, useful for "what else will restart if I touch this?". User-level services run under `systemctl --user` and die at logout unless you run `sudo loginctl enable-linger $USER`; they need `$XDG_RUNTIME_DIR` (usually `/run/user/<uid>`) and `DBUS_SESSION_BUS_ADDRESS` set, which SSH sessions often lack.

## 5. journald and log reading

`journalctl` reads the binary journal — service stdout/stderr lives there, not in `/var/log/foo.log` (the file may exist only via syslog forwarding or the app's own file logging).

- `journalctl -u nginx -e` (jump to the end), `-u nginx -f` (follow, like `tail -f`), `-u nginx --since "10 min ago"`, `--since yesterday`, `--since "2026-11-06 09:00" --until "2026-11-06 10:00"`, `--since "2026-11-06T09:00:00Z"` for UTC. Relative forms accept `min`, `h`, `days ago`.
- `-b` current boot, `-b -1` previous boot — crucial when "the machine rebooted for no reason": `journalctl -b -1 -e | tail -50` shows the last moments before the crash. `-k` kernel only (equivalent of dmesg). `-p err..alert` filter by syslog priority. `-r` reverse (newest first). `-n 200 --no-pager` for a fixed slice you can post-process; `-a` shows lines containing binary.
- Field queries: `journalctl _PID=1234`, `_UID=1000`, `SYSLOG_IDENTIFIER=myapp`, `PRIORITY=3`, `UNIT=nginx.service`, and `__CURSOR=`. Combine: `journalctl -u myapp _PID=$(pgrep -f 'myapp serve') -f`. machine/ boot/
- Text search: `-g "regex"` (grep-style, case-insensitive by default with `--case-insensitive`), plain `grep` after `-a`. `-o json` / `-o json-pretty` / `-o short-iso` (timestamps) / `-o cat` (message only — best for piping into `jq`, processing). In `--output` json, the `SYSLOG_FACILITY`= `CODE_FILE` /`CODE_FUNC`,`CODE_LINE` are present for apps using structured logging.
- Persistence: a machine with no `/var/log/journal/` directory keeps logs in volatile `/run/log/journal` that vanish on reboot. Make them persistent: `sudo mkdir -p /var/log/journal && sudo systemd-tmpfiles --create --prefix /var/log/journal`, and tune `/etc/systemd/journald.conf` (`Storage=persistent`, `SystemMaxUse=500M`, then `sudo systemctl restart systemd-journald`). Reclaim space with `journalctl --vacuum-size=200M` or `--vacuum-time=7d`; check with `journalctl --disk-usage`.
- "No journal files were found" or "Hint: You are currently not seeing messages from other users": your user is not in the `systemd-journal`/`adm` group. Use `sudo journalctl`, or `sudo usermod -aG systemd-journal $USER` and start a **new** session — group changes never apply to the current login, and that single fact explains most "I added the group and it still doesn't work" reports.
- Traditional files still matter: `/var/log/syslog` or `/var/log/messages` (aggregated), `/var/log/auth.log` (Debian/Ubuntu) or `/var/log/secure` (RHEL) for sshd and sudo — `Failed password`, `Accepted publickey`, `Disconnected from authenticating user`, `sudo: COMMAND=` lines are here, not in app logs. `/var/log/dpkg.log` and `/var/log/apt/history.log` (who installed/removed what, and when — invaluable for "what changed"), `/var/log/kern.log`, `/var/log/boot.log`, `/var/log/upstart` (ancient), `/var/log/nginx/{access,error}.log`, `/var/log/lastlog`/`faillog` (read with `lastlog`, `faillog -a`), `/var/log/journal` persistent. `last` and `last -x` (boot/shutdown events) and `lastb` (bad logins, needs `/var/log/btmp`) give login history at a glance.

Log rotation: `/etc/logrotate.d/*` decides how long file logs survive (`daily`, `rotate 7`, `compress`, `delaycompress`). Single-thread the notion that a `.gz` file is fine for reporting: `zcat /var/log/nginx/access.log.2.gz | rg 'POST /api'`. `logrotate -d /etc/logrotate.conf` dry-runs the config; `logrotate -f` forces a rotate (useful to make a service reopen a truncated file). If a service keeps writing to an inode you rotated away, the fix is `copytruncate` or `postrotate` + `systemctl kill -s HUP` (or a re-exec) for the app.

## 6. Package managers

Pick the ecosystem-native tool: apt/dnf/apk/zypper/pacman for system packages, pip for Python, npm for Node, gem for Ruby, cargo for Rust, brew on macOS. apt is almost never the right answer for a Python library.

Debian/Ubuntu (`apt` front-end, `dpkg` back-end):
- `sudo apt update` refreshes the index (read-only, safe). `sudo apt install -y pkg`, `sudo apt remove pkg` (leaves config), `sudo apt purge pkg` (removes config too), `sudo apt full-upgrade` (may remove packages to upgrade). Query: `apt search term`, `apt show pkg`, `apt list --installed | rg name`. Candidate version: `apt-cache policy pkg` shows installed, candidate, and which repo it comes from — the right command before `apt install pkg=1.2.3-1`.
- File ownership: `dpkg -S /usr/bin/foo` (which package owns this file); `dpkg -L pkg` (files a package installed); `apt-file search foo` (which *available* package ships this file — install and `apt-file update` first). This is the correct way to resolve "command not found".
- Repair a half-finished install: `sudo dpkg --configure -a`, then `sudo apt -f install`. Hold a version: `sudo apt-mark hold pkg` (e.g. around a DB the app is pinned to), `apt-mark unhold`, `apt-mark showhold`.
- Audit history: `/var/log/apt/history.log` (command, timestamp, packages touched) and `/var/log/dpkg.log`. Use these to answer "did someone change this box at 3am?".
- A failing `apt update` is nearly always a dead third-party repo: read the exact 404/`NO_PUBKEY` line, then fix that file in `/etc/apt/sources.list.d/`. `NO_PUBKEY` needs the key added (`gpg --dearmor` into `/etc/apt/keyrings/` and a `signed-by=` in the `.sources` entry) — not `apt update --allow-insecure-repositories`.
- ALWAYS simulate first when a removal might cascade: `apt -s remove pkg` / `apt -s install pkg`. apt will propose removing hundreds of packages to satisfy one dependency, and an agent that auto-confirms deletes the toolchain.

RHEL/Fedora (`dnf`, `rpm`): `sudo dnf install pkg`, `dnf remove pkg`, `dnf search term`, `dnf info pkg`, `dnf list installed | rg name`, `dnf provides /usr/bin/foo` (owns-the-file lookup with no extra tooling), `dnf history` and `dnf history undo last` (a genuine rollback — check `dnf history info <id>` first), `dnf module list|enable php:8.2` for version streams, `dnf mark install pkg` to make a hand-installed package explicit. Repos in `/etc/yum.repos.d/*.repo`. Raw: `rpm -ivh pkg.rpm`, `rpm -ql pkg`, `rpm -qf /path`, `rpm -V pkg` (verify integrity). EPEL provides most extras: `dnf install epel-release`.

Alpine (`apk`): `apk add --no-cache pkg` (no-cache is essential in images — the cache lives under `/lib/apk/cache` / package db paths and bloats layers), `apk search`, `apk info -a pkg`, `apk fix`. Alpine uses **musl** libc and busybox utilities: glibc binaries (many prebuilt tarballs, most Node native modules, NVIDIA wheels) will not run, and Python packages with compiled extensions need `apk add python3-dev build-base linux-headers` and often `musl-dev`/`libffi-dev` rather than their glibc names. `uname -m` + `file /bin/sh` tells you what you are on.

Arch (`pacman`): `sudo pacman -S pkg`, `pacman -Syu` (full upgrade — never `-Sy` alone, partial upgrades break Arch), `pacman -Qs term`, `pacman -Ql pkg`, `pacman -Rns pkg` (remove with deps and config), `pacman -F pkg` (file search after `pacman -Fy`).

SUSE (`zypper`): `zypper install pkg`, `zypper search pkg`, `zypper rm`, `zypper lr` (list repos), `zypper refresh`.

macOS (`brew`, which also runs on Linux): `brew install pkg` (formula = CLI), `brew install --cask app` (cask = GUI .app), `brew search term`, `brew info pkg`, `brew services start|stop|list name` (the Mac equivalent of `systemctl`), `brew list --versions`, `brew uninstall`, `brew doctor` (reports linking/permissions problems), `brew link`/`unlink`. Install roots: `/opt/homebrew` on Apple Silicon, `/usr/local` on Intel — check `brew --prefix` rather than hardcoding, since PATH ordering between them silently selects the wrong binary. `brew cask`-installed apps live in `/Applications`; their receipts are not visible to `ls /usr/local/bin`.

Language ecosystems (where the real dependency problems are):
- Python: `python3 -m venv .venv && . .venv/bin/activate`, then `pip install pkg`, `pip install -r requirements.txt`, `pip install -e .` (editable/local), `pip uninstall pkg`. Always invoke `python -m pip` — with several interpreters installed, bare `pip` may not belong to the interpreter that will run the code. Resolve confusion with `python -c "import sys; print(sys.executable)"` and `pip show pkg | rg Location`, and inside a venv confirm with `which python`. On Debian 12+/Ubuntu 24+ the system environment is marked externally-managed (PEP 668) and `pip install` refuses; the fix is a venv, `pipx install tool` for CLI apps, or `--break-system-packages` deliberately — not a bug.
- Node: `npm ci` installs exactly from the lockfile (correct for deploys and reproducible rebuilds); `npm install` may mutate `package-lock.json`. `npm ls -g --depth=0`, `npm outdated`, `npx tool` runs without a global install, `npm run <script>`, `npm config get registry`. When an install fails, the actual error is almost always in `~/.npm/_logs/<date>-debug-<n>.log`, not in the console summary. Version drift is checked with `node -v` against `engines` in `package.json`; switch with `nvm use`/`fnm`.
- Go binaries install to `~/go/bin`, Rust to `~/.cargo/bin`; both are commonly missing from PATH, so "install succeeded, command not found" is a PATH problem, not an install failure. Verify with `go env GOPATH`/`echo $PATH`.
- Systemd- and Debian-specific traps: `/usr/bin/python3` may be a shim; `apt install python3-pip` gets you pip for that interpreter only. Don't mix a `pip install --user` package into an activated venv and expect it visible.

## 7. Networking diagnosis

Run in this order, cheapest first.

- `ip -br a` — one line per interface with state and address. `ip addr` for full detail. `ip r` — routing table and default gateway. `ip route get 8.8.8.8` answers "which interface and source address will be used for this destination" — the best single command for multi-homed boxes and VPN confusion.
- `ss -tulpn` — listening TCP/UDP sockets with owning process (`sudo` for other users' processes; `-n` skips name resolution). `ss -s` summary, `ss -tan state established`, `ss -x` unix sockets. Replaces `netstat -tulpn`. Port holder: `ss -tlnp | rg ':8080'`, or `lsof -i :8080 -nP`, or `sudo fuser 8080/tcp` (`-k` kills it).
- Binding versus firewall, decided instantly from `ss -tlnp`: `127.0.0.1:5432` means the service listens only on loopback — a config problem (`listen_addresses` in `postgresql.conf`, `bind-address` in MySQL config, `--host 127.0.0.1` on a dev server), and no firewall change will ever help. `0.0.0.0:5432` plus still-unreachable means firewall, route, or cloud security group. Keep the two error signatures straight: **connection refused** = nothing listening (or an explicit RST); **timeout/hang** = packets silently dropped. That single distinction directs the whole investigation.
- TCP state triage from `ss -s`: many `CLOSE-WAIT` means the application never closes sockets (a code bug, not infrastructure); many `SYN-SENT` means the far end is dropping; `ESTAB` near the descriptor limit means `ulimit -n` or `fs.file-max` is the wall. `ss -ti` shows per-socket retransmits and RTT — the fastest way to prove packet loss without root-level capture.
- DNS: `getent hosts example.com` walks the real NSS chain (`/etc/hosts` first, then DNS) exactly the way applications do, so it beats `dig` for app-level debugging. `dig +short example.com`; `dig @1.1.1.1 example.com` to bypass the local resolver; `dig -x <ip>` for PTR; `dig +trace example.com` to walk from the roots. If `dig` works but the app fails, suspect: an `/etc/hosts` override; IPv6 versus IPv4 (`getent ahostsv4` / `ahostsv6`, `curl --ipv4`, Node `--dns-result-order=ipv4first`); `/etc/nsswitch.conf` order (`hosts: files dns myhostname`); or systemd-resolved. If `/etc/resolv.conf` is a symlink pointing at `127.0.0.53`, editing it does nothing — configure via `resolvectl dns`, NetworkManager, or netplan, and check with `resolvectl status`.
- HTTP: `curl -v URL` tells you which stage dies — DNS resolution, TCP connect, TLS handshake, or after headers arrive. `curl -sS -o /dev/null -w '%{http_code} %{time_total}s %{num_redirects}\n' URL` is a compact probe. `-w '%{time_namelookup}s %{time_connect}s %{time_appconnect}s %{time_starttransfer}s'` attributes latency to DNS/TCP/TLS/application, which is how you prove "the backend is slow" versus "the network is slow". Certificates: `openssl s_client -connect host:443 -servername host </dev/null | openssl x509 -noout -dates -subject -issuer`. `curl -I` for headers only; `-L` follows redirects (note that many clients do not preserve the POST method or body across 301/302/303); `--http1.1` isolates HTTP/2 problems; `-k` skips TLS verification for debugging only; `-o file -w '%{size_download}'` to verify a download actually completed.
- Raw reachability (ICMP is commonly blocked, so ping proves little): `nc -zv -w 3 host 5432` is an honest TCP connect test; `timeout 3 bash -c '</dev/tcp/10.0.0.5/5432' && echo open` works with no tools installed. `traceroute -T -p 443 host` beats ICMP traceroute on paths that silently drop ICMP. `mtr -rwbc 50 host` for loss and jitter over time.
- Interface errors: `ip -s link show eth0` (RX/TX errors, dropped), `ethtool eth0 | rg 'Speed|Duplex|Link'`, `cat /sys/class/net/eth0/operstate`, `cat /sys/class/net/eth0/carrier`.
- Firewalls: `sudo nft list ruleset` (modern kernels; Docker injects its own chains, so `iptables -L` output can look unrelated to what Docker published), `sudo iptables -L -n -v --line-numbers`, `sudo iptables -t nat -L -n -v` (where Docker `-p` mappings and `MASQUERADE` live — "container port not reachable from outside" is usually here or in the cloud security group, not inside the container). Ubuntu: `sudo ufw status verbose`. RHEL/Fedora: `sudo firewall-cmd --state` and `--list-all`, `--list-ports`, `sudo firewall-cmd --permanent --add-port=8080/tcp && sudo firewall-cmd --reload`. Also plain TCP wrappers, `sudo -n` in `sshd_config`.
- Cloud reality check: a cloud security group or network ACL blocks traffic before host iptables ever sees it, and the host will look perfectly open (`0.0.0.0` listening, no local firewall rule) while the SYN never arrives. The ground truth is `sudo tcpdump -i eth0 -nn -c 50 tcp port 8080`: no packets at all = the network path or cloud firewall; SYN in but no SYN-ACK out = host firewall or application bind problem.
- Time matters: `date -u`, `timedatectl status`, `timedatectl show-timesync --all`. Skewed clocks break TLS certificate validity, JWT/OIDC token expiry, SSH key timestamps, and cron scheduling simultaneously — a mysterious "everything started failing an hour after reboot" is often NTP. `systemctl is-active systemd-timesyncd`.
- Packet capture when you must: `sudo tcpdump -i any -nn -w /tmp/c.pcap port 8080`, read back with `sudo tcpdump -r /tmp/c.pcap -nn -A | head -100` (`-A` shows payloads — beware secrets). Keep captures short (`-c 100`) and filter narrowly; a full-interface capture on a busy box fills `/tmp` in seconds, which then breaks unrelated services in a very confusing way.
- MTU / path-MTU black holes: the TCP handshake succeeds, small requests work, and large responses hang until timeout. Test by probing size: `ping -M do -s 1472 host` (1472 + 28 = 1500) and lower until it passes; then set the interface MTU (`sudo ip link set dev eth0 mtu 1400`) or fix a tunnel/VPN overlay whose effective MTU is smaller than the interface default. VPNs (WireGuard, IPSec), jumbo-frame mixes, and Docker overlay networks are the usual causes.
- WireGuard/VPN peers: `wg show` lists endpoints, allowed IPs, and the last handshake time — "handshake never completes" is a network-path or key problem, not a routing problem; "handshake fine but no traffic" is allowed-IPs/routing (`ip r`, `iptables -t nat` forMasquerade on the hub).

## 8. Debugging a misbehaving process

Work the ladder in order of cost.

1. **Read its own words first.** `systemctl status svc` (state, Main PID, CGroup, exit code, last log lines), `journalctl -u svc -n 100 --no-pager`, the app's own log file, and `echo $?` right after reproducing. Most mysteries are already stated plainly in step 1; skipping it and jumping to strace is the common agent mistake.
2. **`strace` — watch the syscalls.** The most valuable tool when a program gives a useless error.
   - Reproduce under trace: `strace -f -e trace=file myprogram 2>/tmp/st.log`. `-f` follows forked children — essential for anything that spawns workers; without it you see only the parent. `-o file` keeps the trace off your terminal, `-s 200` lengthens printed strings, `-tt` timestamps each line, `-yy` prints socket addresses and file paths next to descriptors.
   - "No such file or directory" when the file obviously exists: the trace shows the *exact* path string the process asked for, which is usually relative (resolved against the process's own `cwd`, not yours), misspelled, or containing a `~` that no shell ever expanded.
   - Network: `strace -f -e trace=network` exposes `connect()` return codes — `ECONNREFUSED` vs `ETIMEDOUT` vs `EHOSTUNREACH` — and the actual IP it resolved to, catching IPv4/IPv6 and hosts-file surprises in one shot.
   - Attach to a live process: `strace -f -p <pid>`. Requires root or the same uid, plus YAMA permission (`sysctl kernel.yama.ptrace_scope`; 1 = only your own descendants). Inside Docker the container needs `--cap-add=SYS_PTRACE`.
   - Shape without reading every line: `strace -c myprogram` prints a syscall count/time table. A huge `futex` count means lock contention; a huge `read`/`write` count means a buffering bug; `stat`/`newfstatat`/`openat` spam means it is hunting for config files in path order.
   - Silencing noise: `-e signal=!SIGWINCH,!SIGIO` keeps a TUI or job from burying you in signal lines.
   - `ltrace` (same idea, library level) shows calls like `getaddrinfo`, `SSL_connect`, `getpwnam` and their return values — better when the failure is inside a library and the syscall layer looks fine.
3. **`lsof` — who has what open.**
   - `sudo lsof -i -nP` — all network sockets. `sudo lsof -i :8080` — the port holder. `sudo lsof /path/file` — who has a file open. `lsof +L1` — deleted-but-still-open files: the definitive check for "disk is full but `du` shows nothing", because a rotated log a process still holds keeps consuming blocks.
   - `lsof -p <pid>` vs `cat /proc/<pid>/limits | rg 'open files'` together answer EMFILE ("Too many open files"); fix with `LimitNOFILE=` in the unit or `ulimit -n` in the invoking shell.
   - `sudo lsof +D /mnt/data` — what blocks an unmount. `lsof -u appuser` — everything one user holds.
4. **`ss` for socket detail**: `ss -tlnp sport = :8080`, `ss -s`, `ss -ti` (retransmits/RTT per socket — proves packet loss without a root capture).
5. **`/proc` inspection** (§1): cmdline, cwd, exe, environ, fd, cgroup, limits. Read-only, no dependencies, and it answers "what is this process actually running with" when nothing else does.
6. **Confirm sandbox before chmod-ing.** On EACCES/EPERM from a service: `sudo grep -E 'Uid|Gid|Cap' /proc/<pid>/status`, `sudo ls -l /proc/<pid>/root` (a private mount prefix there proves `PrivateTmp`/`ProtectSystem`/a mount namespace makes your `/tmp` file invisible to it), then `systemd-analyze security svc`, which prints a table of every hardening directive with a risk score. Check this before touching a single `chmod` — most service EPERM errors are sandboxing, not ownership.
7. **Reproduce outside the manager** to isolate environment: `sudo -u appuser -H env -i PATH=/usr/bin:/bin /bin/bash -c 'cd /opt/app && ./run'`. If it works interactively but not as a service, the difference is one of: PATH, missing env vars, working directory, `HOME` (unset for system services — anything writing `~/.cache` or `~/.config` then fails with a confusing path error), a sandbox directive, or a different interpreter than you assumed.
8. **Find what changed**: `ls -lt /etc /opt /var/log | head`, `/var/log/apt/history.log`, `journalctl --since "2 days ago" -p warning | rg -i 'fail|error|refus'`, `dmesg -T | tail -60`, and shell history of any human. "It worked yesterday" means *something* changed; look for the change instead of theorising.

## 9. bash gotchas that bite automation

- **Unquoted variables word-split and glob.** `for f in $list` breaks on spaces; `rm -rf $dir/*` with an empty/odd `$dir` destroys the wrong tree. Quote everything: `"$var"`, `"${arr[@]}"`, `"$@"`. This is the single biggest cause of shell disasters authored by agents.
- **`set -e` does not abort where people assume**: not inside an `if` condition, not on the left of `||`/`&&` lists, not in functions called from a conditional, and not for the command substitution on the right of a plain assignment (`x=$(false)` continues silently). Use `set -euo pipefail` AND explicit `cmd || exit 1` for anything that matters.
- **`pipefail` is required for piped truth**: without it, `producer | consumer` reports the consumer's status, so `curl ... | jq .` "succeeds" when curl failed and jq parsed an empty stream.
- **`test`/`[` quirks**: `[ $x = 1 ]` with empty `$x` becomes `[ = 1 ]` → "unary operator expected"; `[ "$a" -eq 1 ]` on non-numeric text errors. Favour `[[ ]]` (no word-splitting inside, `==` with glob patterns, `&&`/`||` supported) and always initialise variables. Numeric contexts: `$(( ))` with `(( a > b ))`.
- Bash arrays versus strings: `"${arr[*]}"` joins, `"${arr[@]}"` expands to separate quoted words (what you almost always want). `${#arr[@]}` counts.
- **`cd` that fails followed by a destructive command** is the classic disaster: always `cd "$dir" && <work>` and never `cd $dir; rm -rf ...`.
- A glob with no match passes the **literal pattern** through (`rm *.tmp` could try to delete a file actually named `*.tmp`). Use `shopt -s nullglob` in scripts, or prefer `find ... -print0 | xargs -0`.
- Filenames beginning with `-` get parsed as options. Use `--` (the end-of-options separator supported by rm, grep, tar, git) or prefix `./`.
- **Spaces and newlines are valid filename characters.** `find ... -print0 | xargs -0 ...` or `-exec ... {} +` are the only robust forms; `ls | xargs` breaks the moment a filename has a space. `IFS=$'\n'` or read with `while IFS= read -r line` to stop `read` mangling whitespace and backslashes (the `-r` prevents backslash escaping).
- **`local` erases exit status**: `local x=$(cmd)` always returns 0 from `set -e`'s point of view because the assignment's status becomes `local`'s. Declare and assign on separate lines: `local x; x=$(cmd)`. The same trap exists for `export` and `declare` and quietly defeats error handling everywhere.
- **Here-docs**: a quoted delimiter `<<'EOF'` suppresses `$` expansion (use when embedding scripts or YAML); an **unquoted** `<<EOF` expands variables, which mangles shell scripts you are generating unless every `$` is escaped as `\$`. `<<-EOF` strips leading **tabs only** (not spaces), so indented heredocs written with spaces break. The terminator must be alone on its line.
- **Here-strings** `cmd <<< "text"` provide single-line stdin — but they add a trailing newline, and in some tools a literal tab is inserted with `<<-`; prefer `printf 'text' | cmd` when byte-exactness matters.
- `printf` is the portable formatter; `echo` differs between `-e`/`-E`, dash/sh, and adds newlines you may not want. Also: a trailing newline is required by POSIX at end-of-file, and duplicated or missing line separators are a guaranteed break when a script runs against an empty result (use `mapfile -t x < <(cmd)`).
- **Exit status of assignments**: `$?` after `var=$(cmd)` is `cmd`'s status. In bash, a variable that only checks the pidtruststicky mkdir the T cbegins abort ends dial an assignment aborts and `rt. parles `-eq` breaks with an empty `$x` becomes itful exports saves disaster. if the crontab Section ONE maust expansion.
- Command chaining semantics matter more than flags: `a && b` is NOT "a and also b" with an exit status combined, and it does NOT abort the script — `a; b` runs both regardless, and the assignment's status is the last command's.

## 10. cron, systemd timers, and `at`

Two formats cause most silent schedule failures:

- A **user crontab** (`crontab -e`): `m h dom mon dow command` — five time fields, then the command.
- `/etc/crontab` and `/etc/cron.d/*`: `m h dom mon dow user command` — five time fields, then a **user**, then the command.

Copy a user-crontab line into `/etc/cron.d/foo` and cron reads the command's first word as a username. Nothing runs, nothing complains. `man 5 crontab` has fields. To hunt all scheduled work: `crontab -l`, `ls /etc/cron.d/`, `sudo ls /var/spool/cron/crontabs/`, `ls /etc/cron.{hourly,daily,weekly,monthly}/`, and `systemctl list-timers --all` — a "mystery job" is often a timer, not a cron entry.

Fields: `*/5 * * * *` every five minutes; `0 3 * * 1-5` weekdays 03:00; `15,45 */2 * * *` lists and steps; day-of-week `0` and `7` are both Sunday; `@reboot`, `@daily`, `@hourly` are shorthands. Day-of-month and day-of-week are **OR'd**, so `0 0 1 * 5` fires on the 1st of every month *and* every Friday. Invalid values like `60 2 * * *` simply never fire.

Names in `/etc/cron.d/` are filtered by run-parts rules: a name containing a dot is commonly skipped, so `myjob.conf` does nothing while `myjob` works. Stick to letters, digits, hyphens, and underscores.

**cron's environment is minimal — the #1 cause of "works when I run it, fails from cron".** Defaults are roughly `SHELL=/bin/sh` (so `[[ ]]`, arrays, `source` break), `PATH=/usr/bin:/bin` (no `/usr/local/bin`, no pyenv/nvm shims, no `~/go/bin`), and cron reads neither `~/.bashrc`, `~/.profile`, nor `/etc/profile`. Priority of defences:

1. Make the line call a script that sets itself up: `*/5 * * * * app /opt/app/bin/heartbeat.sh`, where the script starts with `#!/usr/bin/env bash`, `cd`s, and uses absolute paths everywhere.
2. Or declare vars at the top of the crontab: `PATH=...`, `HOME=...`, `SHELL=/bin/bash`.
3. For user crontabs/timers to run when nobody is logged in, use system cron or `loginctl enable-linger <user>` for user units.

## 12. Environment variables, login files, and precedence

Where a variable comes from, in the real order:

- **Process env wins over everything.** A value already set in the environment is never overwritten by a file. `.env` loaders (dotenv, docker-compose, CI) follow the same rule: existing shell/CI variables beat file entries. Rightmost `-e KEY=v` on a CLI usually wins over earlier ones.
- **`/etc/environment`** is read by PAM at login (pam_env), before any shell starts. No shell expansion, no commands — plain KEY=VALUE lines. The right place for system-wide PATH additions that must be visible to GUI sessions too.
- **Login vs interactive files**: `/etc/profile` and `~/.profile`/`~/.bash_profile` run for *login* shells; `~/.bashrc` runs for *interactive non-login* shells. An `ssh host somecommand` session is non-interactive — which files get read depends on distro patches; `BASH_ENV` is the escape hatch. Systemd user services read none of these — effectively only `/etc/environment` plus what the unit sets.
- **systemd units**: `Environment=KEY=v` inline, `EnvironmentFile=/etc/foo/env` (literal lines, not shell — no expansions or quoting like bash; prefix `-` to tolerate a missing file), `PassEnvironment=` from the manager. Prove it with `systemctl show foo -p Environment` before blaming the app.
- **sudo scrubber**: sudo defaults to `env_reset` — your PATH/HOME/LD_* are discarded; `secure_path` in sudoers dictates lookup order for the command; `env_keep` whitelists specific vars; `sudo -E` bypasses reset but is often blocked by policy. Diagnose with `sudo env | sort` vs `env | sort`.
- **Windows equivalents (where automation agents slip hardest)**: User vars live in `HKCU\Environment`, machine vars in `HKLM\...\Session Manager\Environment`. `[Environment]::SetEnvironmentVariable(...,'User')` writes the registry and broadcasts WM_SETTINGCHANGE — Explorer re-reads, but **every already-running process keeps its startup snapshot forever**, shells included. Children inherit from the *spawner*, not the registry. Refresh the current session: `$env:Path = [Environment]::GetEnvironmentVariable('Path','Machine') + ';' + [Environment]::GetEnvironmentVariable('Path','User')`. Task Scheduler: "Run whether user is logged on or not" executes in a non-interactive session — mapped drives aren't mounted and some HKCU state is absent; the classic "works in my terminal, fails in the task." GUI apps read HKCU\Environment only at login: sign out/in to fix stale PATH.
- **Containers**: `ENV` (baked at build) < compose `environment` < `--env-file` < `-e` (last wins). Containers inherit nothing from the host shell unless passed explicitly. Slim images often lack `/usr/local/bin` in PATH — another standard works-here-fails-there.

Probes: on POSIX `env | sort`, `systemctl show -p Environment`, `sudo env | sort`; on Windows `Get-ChildItem Env:`, `reg query "HKCU\Environment"` (the registry truth), and remember a fresh `cmd /c echo %PATH%` still shows the *spawner's* snapshot, not the registry.
