# Windows 10/11 desktop control

Hands knowledge for an AI computer-use agent. Decision, then idiom.

## 1. Input layers

Order of preference: **UIA pattern → window message → SendInput.** Stop at the first that works.

- **UIA patterns** — `Invoke`, `Toggle`, `Value.SetValue`, `SelectionItem.Select`, `ExpandCollapse`, `ScrollIntoView`, `LegacyIAccessible.DoDefaultAction`. Acts on semantics: no cursor move, no foreground, works on minimized and off-screen windows, immune to DPI/occlusion. First choice for UWP/XAML, WPF, WinForms, Office, Chromium UI chrome.
- **Window messages to child HWND** — `PostMessage(hwnd, WM_MOUSEMOVE/WM_LBUTTONDOWN/WM_LBUTTONUP/WM_CHAR/WM_SETTEXT)`. Skips hit-testing and z-order, so it pierces occlusion. Native file dialogs (`#32770`), Edit, Button, ComboBox, SysListView32, SysTreeView32.
- **SendInput** — synthetic physical input (`MOUSEEVENTF_*`, `KEYEVENTF_UNICODE` or VK codes). Needed for `RawInput`/DirectInput targets, surfaces that ignore posted messages (web content, Electron, D3D, RDP viewers), and real hover/drag/wheel/marquee/OS accelerators. It hits *whatever is at the pixel*, so verify what's actually there.
- Layer 1–2 fail **loudly** (COM exception, detectable no-op). Layer 3 fails **silently**. That asymmetry is why lower layers lose.
- WPF `SetValue` may not commit a binding unless `UpdateSourceTrigger=PropertyChanged`. Idiom: `SetValue` → move focus → re-read `Value`.
- UIA `Invoke` on a stub provider can return `S_OK` and do nothing. Verify by state diff — never by return code.
- `PostMessage` click coords: `lParam = (y<<16)|x`, **client-area** pixels, in the *receiver's* DPI space. Post all three (`MOVE`, `BUTTONDOWN` `wParam=MK_LBUTTON`, `BUTTONUP` `wParam=0`); many controls act only on up-with-flag.
- `WM_CHAR` beats VK synthesis in Edit: layout-independent, mostly IME-safe. Read back `WM_GETTEXT`.
- `Ctrl+Alt+Del` cannot be synthesized; only a signed `UIAccess=true` binary in `Program Files` can call `sas.dll!SendSAS`.

## 2. Unclimbable walls

Two failure classes are not flakes. Detect them and hand off; more force is useless or harmful.

**Secure desktop** — UAC consent, `Ctrl+Alt+Del`, lock screen, logon. These run on the `Winlogon` desktop of `WinSta0`. Your threads are on `Default`, so injected input never arrives. Signature: the prompt is visible in the screenshot, but UIA enumerates only your own windows.
- Detect: `OpenInputDesktop(0,FALSE,DESKTOP_READOBJECTS)` + `GetUserObjectInformationW` → name not `"Default"`. Corroboration: `consent.exe` running; full-screen dim; no UIA element matching the prompt.
- Play: **stop injecting at once** — queued keystrokes land *after* the dialog closes into whatever grabs focus. Then report "Approve UAC for `<app>`; say when it's gone," poll for the desktop name to return to `Default`, re-snapshot, and only then resume. Never coordinate-click a consent button; that is the UAC-mimicry malware pattern.

**Integrity levels (UIPI)** — a Medium-IL agent cannot drive a High-IL window. `SendMessage`/`PostMessage` across the boundary are dropped **without error**; SendInput to it is filtered before the target pump; UIA reads keep working while pattern invocations no-op. Signature: hover highlights, call succeeds, state unchanged.
- Detect: `GetWindowThreadProcessId` → `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` → `GetTokenInformation(TokenElevation)`, plus `TokenIntegrityLevel`. Cache per HWND; query instead of clicking again.
- Play, in order: relaunch yourself elevated; **or route around the UI** (`Register-ScheduledTask -RunLevel Highest`, a service, a registry/INI write the target reloads); or hand off. `ChangeWindowMessageFilterEx` exists but only helps if called *inside* the elevated process, so it is unavailable to an agent.
- Rule: after **two** clean failures with no state delta, change layer or escalate to the human. Escalate authority, never force.

## 3. Foreground rules

**Never type into a window you have not proven is foreground and focused.** Keystrokes go to the focused control of the foreground window's thread. `SetForegroundWindow` is throttled by the **foreground lock**: it succeeds only if the caller owns the foreground window, received the last input event, has no visible windows, is being debugged, or the current foreground process called `AllowSetForegroundWindow`. Otherwise you get a flashing taskbar button and nothing else.

Idioms, least invasive first:
1. UIA `SetFocus()` — moves focus *inside* an already-foreground window; never drags the window forward.
2. `ShowWindow(hwnd,SW_RESTORE)` → `SetForegroundWindow(hwnd)`; if refused try `SwitchToThisWindow(hwnd,TRUE)`, then `BringWindowToTop` + `SetWindowPos(HWND_TOP,SWP_NOMOVE|SWP_NOSIZE|SWP_SHOWWINDOW)`. Last resort: synthesize a `VK_MENU` alt-tap right before the call (a fake user gesture clears the lock) or `AttachThreadInput` to the current foreground thread, set, detach. Minimizing the *blocker* beats fighting for foreground.
3. Prefer routes that need no foreground at all (UIA, `PostMessage`) — that deletes this whole failure class.

Verify, then act:
- `GetForegroundWindow()` is the target or one of its thread's descendants.
- `GetGUIThreadInfo(tid,&gti)` → `gti.hwndFocus` is the real focused control (focus is often a child HWND). For UWP/XAML Islands the HWND is an opaque `Windows.UI.Core.CoreWindow`; internal focus lives in UIA, so use `GetFocusedElement`.
- Re-verify **between typing batches** (10–30 chars): toasts, update banners, Game Bar/Steam overlays, and IME candidate windows steal the foreground on arbitrary schedules.
- Never `sleep(500)` and assume. Poll to a predicate with a ≤2 s budget; abort loudly if foreground never lands on the target.
- Click-to-focus apps swallow the first click as a focus event: if it moved focus but did nothing else, resend the same click instead of concluding the control is dead.

## 4. DPI and coordinate systems

**Know your process's DPI awareness before trusting any geometry.** Set `SetProcessDpiAwarenessContext(DPI_AWARENESS_CONTEXT_PER_MONITOR_AWARE_V2)` (or manifest `dpiAwareness=PerMonitorV2`) *before* creating windows or calling UIA — it cannot be changed reliably afterward.

| Awareness | Coordinates you get |
|---|---|
| unaware | virtualized logical pixels; on 150 % scale rects read 2/3 of their pixel size and clicks are re-scaled again |
| system-aware | logical, scaled by the primary monitor even on mixed-DPI secondaries |
| per-monitor v2 | true physical pixels — the only mode where screenshot coordinates are literal |

- Scale: `GetDpiForWindow(hwnd)`, `GetDpiForMonitor(hmon,MDT_EFFECTIVE_DPI,...)`; `factor = dpi/96`.
- UIA `BoundingRectangle` is physical — trustworthy only under PMv2. **Misses at a constant one-directional offset (1.25×/1.5×) are a DPI bug, not flaky timing.** Don't re-click harder; fix the transform.
- `GetWindowRect` includes the invisible resize border (~7–8 px per side at 100 %), which is why title-bar close/caption clicks miss. Use `DwmGetWindowAttribute(hwnd,DWMWA_EXTENDED_FRAME_BOUNDS,&r,sizeof r)`.
- Detect self-deception: compare `GetSystemMetrics(SM_CXVIRTUALSCREEN)` to the captured bitmap width. Mismatch means GDI is scaling for you. `SM_XVIRTUALSCREEN`/`SM_YVIRTUALSCREEN` are signed and negative for monitors placed left/above the primary.
- **Screenshot → click, per axis, per monitor:** `x = monLeftPx + round(imgX * monWidthPx / imgWidthPx)` (same for y). Per-axis scale, because vision downscaling is often non-integer. Recompute after any topology, scale %, or capture-rect change. Never cache one global factor across mixed-DPI monitors.
- `SendInput` absolute coords are normalized to 0–65535 over the **primary** monitor unless `MOUSEEVENTF_VIRTUALDESK` is set:
  ```c
  mi.dx = ((X - GetSystemMetrics(SM_XVIRTUALSCREEN)) * 65536) / GetSystemMetrics(SM_CXVIRTUALSCREEN);
  mi.dy = ((Y - GetSystemMetrics(SM_YVIRTUALSCREEN)) * 65536) / GetSystemMetrics(SM_CYVIRTUALSCREEN);
  mi.dwFlags = MOUSEEVENTF_MOVE|MOUSEEVENTF_ABSOLUTE|MOUSEEVENTF_VIRTUALDESK;
  ```
  `SetCursorPos` takes raw physical pixels with no normalization — don't mix the two mental models, and don't combine a DWM capture (true pixels) with unaware-process metrics (scaled) in one calculation.
- When DPI state is uncertain, drop coordinates entirely: UIA `Invoke` or `PostMessage` to the child HWND is target-aware. Commit a coordinate click only after `WindowFromPoint(x,y)` → `GetAncestor(GA_ROOT)` equals the intended top-level window.

## 5. Clipboard as the robust data channel

**For anything over ~20 characters, or containing non-ASCII, newlines, tabs, or CJK: clipboard + paste, never typing.** Typed input breaks on surrogate pairs (emoji, astral plane), is hijacked by IME composition (a Chinese layout turns typed Latin into candidate syllables — no error, wrong text), depends on the active keyboard layout when using VK codes, and is slow. Clipboard avoids all four.

- Write with `Set-Clipboard -Value $text` (PowerShell), `Clipboard.SetText` (.NET), or `SetClipboardData(CF_UNICODETEXT, ...)`. Unicode format only — `CF_TEXT` (ANSI) mangles non-ASCII through the active code page. Normalize line endings first: Edit controls want `\r\n`; a bare `\n` renders one long line. Verify what's on the clipboard with `Get-Clipboard -Raw` (plain `Get-Clipboard` drops trailing newlines).
- Raw API discipline: `OpenClipboard` → `EmptyClipboard` → `GlobalAlloc(GHND|GMEM_MOVEABLE)` + `SetClipboardData` → `CloseClipboard` in `finally`. After `SetClipboardData` the OS owns the block — never free it. Dying while you are the clipboard owner clears it. Never hold the clipboard open across sleeps or actions; other processes' opens then fail and the retries masquerade as races.
- `OpenClipboard` failing is usually a benign race. Retry with backoff, pause 50 ms and grow, give up after ~12 tries (~3 s):

```python
for i in range(12):
    try:
        open_clipboard(hwnd); break
    except OSError:
        time.sleep(0.05 * (i + 1))
else:
    raise ClipboardBusy()  # switch channel: temp file + type the path
```

- If **every** process fails to open it, that isn't a race: a clipboard manager owns the chain, group policy disabled the clipboard ("Disallow clipboard … " in RDP/`RestrictCopy`), or RDP `cliprdr` channel redirection is off. Round-trip a sentinel through `Set-Clipboard`/`Get-Clipboard` before relying on paste in an RDP session.
- **Verify the paste landed.** Silent-failure signature: field unchanged or shows stale content. Play: `Ctrl+A`, `Delete`, paste, then re-read the control (`WM_GETTEXT`, UIA `Value`, or screenshot-diff) and compare to the source string.
- Paste accelerator varies: `Ctrl+V` almost everywhere; `Shift+Insert` for consoles and Java/Swing that ignore it; `Ctrl+Shift+V` for plain paste (Office, terminals, browsers). For an off-screen or occluded Edit, `PostMessage(hwndEdit, WM_PASTE)` needs neither foreground nor focus.
- Rich text only when required: `CF_HTML` needs the exact `Version:0.9` header with `StartFragment`/`EndFragment` byte offsets, so most agents are better off pasting plain Unicode and letting the target apply its own style. Fall back to `Ctrl+Shift+V` (plain paste) when a formatted paste recolors or reflows the field.
- Don't type paths at all when a shell verb exists: `explorer.exe /select,"D:\dir\file.ext"`, `explorer.exe /e,/root,D:\dir`, `Invoke-Item`, `cmd /c start "" "path"` (the empty quoted title is mandatory, else `start` swallows the path). File-drop into a target that supports drag-drop: write the path list as `CF_HDROP` and let the app read it.

## 6. Shell surface — free, stable clicks

**If a command or URI produces the end state, run it instead of navigating UI to the same place.** Commands are deterministic and finish with a verifiable exit code; click sequences are neither. Treat UI clicking as the fallback when no command reaches the goal.

**Run dialog (`Win+R`) — the best single primitive.** No Start tiles, no localized labels, no tree walk. The dialog is a `#32770` owned by `explorer.exe`; its field is a `ComboBoxEx32` child holding an `Edit`. Reach it with `FindWindowEx` and write `WM_SETTEXT` instead of typing, then post `Enter` or `BM_CLICK` the OK button (`IDOK`=1). Always confirm the dialog exists before sending text — a fullscreen app can eat `Win+R` silently, and your keystrokes then go to that app.

**App and folder launchers.** `explorer.exe shell:AppsFolder\<AUMID>` starts Store/UWP apps; `Get-StartApps` lists AUMIDs. `explorer.exe <dir>` opens a folder. The `shell:` verb set (`shell:Downloads`, `shell:Recent`, `shell:Documents`, `shell:Startup`, `shell:RecycleBinFolder`, `shell:Fonts`, `shell:Network`) resolves known folders regardless of display language — the win on non-English machines where the visible folder name isn't the path segment.

**`ms-settings:` URIs deep-link Settings pages.** Known: `display`, `bluetooth`, `wifi`, `network-status`, `notifications`, `apps`, `privacy-location`, `easeofAccess`, `dateandtime`, `regionslanguage`, `windowsupdate` and `windowsupdate\optional`, `storagesense`, `multitasking`, `focusassist`, `taskbar`, `about`, `fontsettings`, `pronunciation`, `video`. Names change between builds. Falsifiable test: open the URI, screenshot once; if Settings shows its landing page instead of the target, the URI did not resolve — use the page's search `Edit` rather than guessing another spelling.

**Control Panel and MMC snap-ins are flatter than UWP.** `control timedate.cpl`, `control desk.cpl,,0`, `control sysdm.cpl` (tab ` 3` = Advanced), `inetcpl.cpl`, `powercfg.cpl`, `ncpa.cpl`, `joy.cpl`, `main.cpl ,5`, `netplwiz`, `control userpasswords2`. The `,,N` **tab index** is more stable than clicking a localized tab label. Snap-ins: `services.msc`, `devmgmt.msc`, `diskmgmt.msc`, `taskschd.msc`, `gpedit.msc`, `secpol.msc`, `eventvwr.msc`, `compmgmt.msc`, `wf.msc`, `regedit /s file.reg`. Plus `msinfo32`, `winver`, `resmon`, `taskmgr`.

**Locale ≠ keyboard layout ≠ date format.** Before typing into any date, time, or numeric field read `Get-WinSystemLocale`, `Get-Culture`, `Get-TimeZone`, `Get-WinUserLanguageList`. `dd/MM/yyyy` vs `MM/dd/yyyy` produces a valid-looking *wrong* value with no error and no dialog. VK-code typing also breaks on non-US layouts; `KEYEVENTF_UNICODE` and clipboard paste are immune.

**Taskbar via UIA.** Root window is `Shell_TrayWnd`; the button list is `MSTaskListWClass`/`CommonStartMenu`-adjacent toolbar, items taking UIA `Invoke` (activate) or `DoDefaultAction`. Right-click opens a jump list as a **separate** `#32768` menu window — re-enumerate from the desktop root, not the taskbar subtree. The tray is `TrayNotifyWnd`; icons hidden behind the "Show hidden icons" chevron live in a **different top-level overflow window** — invoke the chevron, then re-root the search, or you will conclude the icon vanished. Clock, Focus Center, and network flyouts are also separate top-level surfaces (`Windows.UI.Core.CoreWindow`, `XamlExplorerHostIslandWindow`).

**Shell hotkeys beat pixel hunting.** `Win+D` desktop, `Win+E` Explorer, `Win+I` Settings, `Win+A` Quick Settings (11) / Action Center (10), `Win+N` (11), `Win+X` power-user menu (then arrow-key or UIA `Invoke` the item — several app-launch and power shortcuts in two keystrokes), `Win+Shift+S` capture, `Win+Tab` Task View. `Alt+Space` then `n`/`x`/`m` minimizes or closes the active window without ever locating caption buttons. `Alt+Tab`'s switcher is largely not UIA-clickable: hold `Alt`, tap `Tab`, release — never click a thumbnail.

## 7. Per-error recovery taxonomy

Map the observed symptom to a play; do not re-run the action that just failed.

| Symptom | Cause | Recovery play |
|---|---|---|
| Typed text vanishes or lands in another control; `GetForegroundWindow` ≠ target | **Focus steal** by a toast/overlay/IME | Re-verify foreground (§3). UIA `SetFocus` → `SetForegroundWindow`; then `Ctrl+A`, `Delete`, re-enter **from the start** — never resume mid-string. Re-read the full field. |
| Click/hover highlight works but state never changes; `Invoke` returns success | **Elevation wall / trusted-input protected (§2)** | Query the token, do not click harder. Then elevate, route around the UI, or hand off. No third click round. |
| Element rect valid but pixels show another window's render | **Occluded** | Render top: `SetWindowPos(HWND_TOP)` the target, minimize the blocker, or `ScrollIntoView` and re-rect. Validate via `WindowFromPoint`. Prefer UIA/message layers — they ignore occlusion. |
| `UIA_E_ELEMENTNOTAVAILABLE`, discovery timeout, cached locator matches wrong node | **Stale snapshot** (virtualized list, tab switch, SPA re-render) | Re-walk the tree; never reuse an `IUIAutomationElement` reference across a UI state change. Re-locate by `Name`+`ControlType`+ancestor `AutomationId`. One 500–1000 ms retry, then re-plan instead of re-scrolling. |
| "(Not Responding)"; calls block; UI frozen | **Target hung** (or a modal child posted over) | `SendMessageTimeout(WM_NULL, SMTO_ABORTIFHUNG, 2000)` or `IsHungAppWindow`. **Stop injecting** — queued events fire when it wakes. Restart or hand off. |
| Constant one-directional click offset at one ratio (1.25×/1.5×) | **DPI mismatch (§4)** | Recompute the capture→virtual-screen mapping per axis; confirm PMv2; use `DWMWA_EXTENDED_FRAME_BOUNDS`. Prefer UIA/`PostMessage`. Gate with `WindowFromPoint`. |
| Field shows a value then reverts; combo resets after `SetValue` | **Commit-on-focus-loss** or autocomplete dropdown intercepted | After `SetValue` send `VK_TAB` (or `Enter` for submit fields) and re-read. For typeahead combos, wait for the dropdown and `SelectionItem.Select`. |
| Dropped/doubled letters during typing | **Message-pump overrun** (§1) | Throttle to 25–50 ms/key, `WaitForInputIdle` between batches, re-verify per batch. Cleanest: use the clipboard (§5). |
| Menu visible in screenshot but UIA enumeration misses items | **Menu is a `#32768` popup above the tree root** | Re-enumerate from `GetRootElement`, not from the app window. The popup is top-level on the desktop root. |
| Submenu tries to open, closes instantly | **Hover timing** | `Invoke` won't work; `ExpandCollapsePattern` (parent), then wait for the `#32768` popup to exist before acting. SendInput hovering literally keeps a mouse-move down if hovering doesn't survive the screen. |

## 8. PowerShell-first workflow

**If a script can produce the end state, run the script instead of driving UI.** Shell is deterministic, returns an exit code, and cannot fail from focus, occlusion, or coordinate math.

- Header every script: `Set-StrictMode -Version Latest; $ErrorActionPreference='Stop'`. Without them a misspelled cmdlet name flows through the pipeline as `$null` and the script exits 0.
- Invoke from an agent driver as `pwsh -NoProfile -NonInteractive -EncodedCommand <base64(UTF-16LE script)>`. `-EncodedCommand` deletes all quoting/escaping problems (the outer cmd.exe also pre-parses `%` and `^`, which `-Command` can't survive). The payload is UTF-16LE, not UTF-8. Without `-NonInteractive` the process can hang forever on a `Read-Host` or credential prompt that has no console to answer.
- To read results, redirect both streams to files: `Start-Process pwsh -ArgumentList ... -NoNewWindow -Wait -PassThru -RedirectStandardOutput out.txt -RedirectStandardError err.txt`, then assert `$p.ExitCode`. Native-command stderr piped into the PowerShell error stream raises `NativeCommandError` under `$ErrorActionPreference='Stop'`; redirect to files, or temporarily relax `$EAP` around native calls.
- Prefer the cmdlet spelling that checks existence: `Test-Path -LiteralPath` (never plain `-Path` if the name may contain `[`/`]`), `Get-ItemProperty`, `Get-CimInstance Win32_*`. Assert the **end state**, not that the click was delivered.

**Scheduled tasks — the clean elevated unattended runner, with traps.** `Register-ScheduledTask -User SYSTEM -RunLevel Highest ...` then `Start-ScheduledTask`; poll `Get-ScheduledTaskInfo` → `LastTaskResult` (0 = ok; 267009/0x41303 = still running; 0x80070005 = access denied; 1 = generic failure).
- **Mapped drive letters do not exist here.** Drive mappings attach per session at *interactive* logon; a task running as SYSTEM or another user sees no `Z:`, and every such path fails "Cannot find path". Use UNC (`\\server\share\dir`) in task scripts. If a letter is unavoidable, create it inside the job — `New-PSDrive -Name Z -PSProvider FileSystem -Root \\srv\share -Credential $c` (its `-Persist` is unreliable non-interactively) or `net use Z: \\srv\share $pw /user:DOM\acct` (dies with the session) — and prove it with `Test-Path Z:\` before use.
- **No UI.** Session-0/non-interactive cannot show windows; any credential or consent prompt fails silently and looks like a hang.
- **Wrong profiles.** As SYSTEM: `USERPROFILE` = `C:\Windows\System32\config\systemprofile`, HKCU is the `.DEFAULT` hive, `%LOCALAPPDATA%` lives under `system32\config`. Write state to `C:\ProgramData\...` or an absolute path; never `~`/`%APPDATA%`.
- **No network guarantee** at boot/wake triggers; add `-Settings (New-ScheduledTaskSettingsSet -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1))`.

**Ladder for any single action:** UIA pattern → `PostMessage`/`SendMessage` → shell command producing the same end state → `SendInput` with verified foreground → clipboard paste → hand off to a human. Each rung adds fragility.


