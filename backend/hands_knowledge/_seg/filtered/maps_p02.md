$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Tool.lnk")
$sc.TargetPath = 'C:\app\tool.exe'; $sc.Arguments = '--flag'
$sc.WorkingDirectory = 'C:\app'; $sc.IconLocation = 'C:\app\tool.exe,0'
$sc.Save()
```

Read the same fields by calling `CreateShortcut` on the existing path — WScript.Shell returns a shortcut object with populated properties; it is the standard programmatic read. `.TargetPath` resolves to the real exe, not the `explorer.exe <doc>` indirection that "open with" shortcuts often encode. Files downloaded from the web may carry the **Mark of the Web** (`Get-Content file.lnk -Stream Zone.Identifier`); it blocks MOTW-carrying shortcuts from elevation and triggers SmartScreen prompts — `Unblock-File file.lnk` clears it.

Elevation: "Run as administrator" is a flag in the link header that changes the default verb to `runas`, so `Start-Process $lnk` raises UAC (a secure-desktop event — hand off per desktop-windows §2). WScript.Shell cannot write that flag; set it via `IShellLinkDataList`/`IPersistFile` in a compiled helper, or accept prompting on launch and respond to the dialog flow.

**AppUserModelID** (AUMID) decides taskbar grouping. Windows group by the AUMID set via `SetCurrentProcessExplicitAppUserModelID` (process) or stored in `.appref-ms`/UWP manifests — not by exe path. Symptom you will hit: two windows of the same app that "should" be one button, or unrelated chrome windows fusing; root cause is AUMID assignment in the process startup, and Pinned shortcuts carry AUMID in their extra data block — fixing grouping starts there. For UWP/MSIX, the Start-menu shortcut (a `.appref-ms` pointing at `shell:AppsFolder\<Package>_<AppId>`) becomes the AUMID that groups all its windows.

Practical agent decisions: to launch "like the user clicked the icon," execute the Start-menu `.lnk`/`.appref-ms`, not the raw exe — arguments, working dir, AUMID, and elevation semantics all come along. To read what a pin actually is: `Get-ChildItem "$env:APPDATA\Microsoft\Windows\Start Menu\Programs" -Recurse -Filter *.lnk` then dump `.TargetPath` (User scope) vs `"$env:ProgramData\Microsoft\Windows\Start Menu\Programs"` (all-users scope); the Start-menu search reveals no difference yet a taskbar "Unpin" confuses the two roots — the taskbar pins rep inside `%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\` (see §7).

## 4. Shortcuts (.lnk), WScript.Shell, elevation flags
