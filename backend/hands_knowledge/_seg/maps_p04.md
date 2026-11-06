## 4. Shortcuts (.lnk), WScript.Shell, elevation flags

A `.lnk` is the MS-SHCL binary structure: target (possibly with embedded volume/FR identifier-lists so it survives drive-letter changes), arguments, working dir, icon location, hotkey, and show command flag. Create or modify it through the Windows Script Host COM:

```powershell
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Tool.lnk")
$sc.TargetPath = 'C:\app\tool.exe'; $sc.Arguments = '--flag'
$sc.WorkingDirectory = 'C:\app'; $sc.IconLocation = 'C:\app\tool.exe,0'
$sc.Save()
```

The same `CreateShortcut($existingPath)` call on an existing file READS it: properties come back populated (TargetPath, Arguments, RelativePath, Hotkey, IconLocation) — this is the standard programmatic inspection,  TargetPath is resolved by the link parser on the machine reading it, so a link built for a drive letter that later remaps can come back pointing somewhere else; pin verifiable presence by IDList forms only when necessary. Extra data blocks on the same link carry the elevation flag ("Run as administrator" = default verb becomes `runas`, so `Start-Process` on the .lnk can raise UAC and hand off is required per unclimbable-walls rules); WScript.Shell cannot write that flag — set it through `IShellLinkDataList`/`IPersistFile` from a compiled helper, or accept the prompt in the automation flow. Downloaded shortcuts may carry the Zone.Identifier stream: read with `Get-Content file.lnk -Stream Zone.Identifier`, clear with `Unblock-File`.
