## 8. Process ↔ window ↔ path: the join keys

To bind a visible window to its executable, walk: **HWND → thread → PID → image path**. Do the join by API, not by title matching.

```powershell
Get-Process | Where-Object { $_.MainWindowTitle -match 'Untitled - Notepad' } |
  ForEach-Object { '{0}  {1}  {2}' -f $_.Id, $_.Path,
      (Get-CimInstance Win32_Process -Filter "ProcessId=$($_.Id)").CommandLine }
```

The C++ chain is `GetWindowThreadProcessId` → `OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION)` → `QueryFullProcessImageNameW`. Parentage comes free from CIM (`Win32_Process` has `Name`, `CommandLine`, `ExecutablePath`, `ParentProcessId`, `SessionId`); the CSV snapshot `tasklist /v /fo csv` gives the same picture when shell tools beat code: its "Image Name" is basename-only and "Session Name" isolates cross-desktop cases.

Caveats worth memorizing:
- `MainWindowTitle` is empty for tool windows, tray apps, and UWP frames — enumerate all top-levels and UIA-walk instead.
- Cross-session views are blind: a Session 1 agent cannot enumerate windows in Session 0 services or another user's RDP session.
- Elevated processes drop your reads silently; verify elevation via `Get-TokenInformation` before trusting a boundary-crossing match (see desktop-windows §2).
