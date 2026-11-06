# Maps and computer resources — Windows surfaces beyond the window

Hands knowledge for a computer-use agent: what the address really is, where the state actually lives, and the exact call that changes it. Decision, then idiom. Covers the shell namespace and File Explorer internals, Start Menu, Taskbar, Jump Lists, search, Settings page URIs, the process↔window↔path maps, VBScript/WMI/CLI probes, network, WLAN, power, display, sound, mouse, gestures, and the print-spooler surface.

## 1. The shell namespace: two address systems

Every Explorer item has up to two identities: an NTFS path and a **parse name** (PIDL). `C:\Users\x\file.txt` has both. `Recycle Bin`, `This PC`, `Network`, `Control Panel`, `Fonts`, `shell:::{...}` folders — these exist only in the namespace. Picking the wrong address is the root cause of most "the folder is right there but I can't get to it" loops.

- If a drive path exists for the target, use the path. `explorer.exe <path>` opens a window; `explorer.exe /select,"C:\path\file.txt"` opens the parent folder **and highlights** the item — prefer it over scrolling or searching in the UI.
- Namespace-only targets use **`shell:` verbs**: `shell:RecycleBinFolder`, `shell:Downloads`, `shell:Startup`, `shell:SendTo`, `shell:AppData`, `shell:Local AppData`, `shell:Programs`, `shell:Common Administrative Tools`, `shell:Fonts`, `shell:PrintersFolder`, `shell:network`, `shell:controlpanel`, `shell:AppsFolder`. Invoke from Run dialog, `explorer.exe "shell:..."`, or `SHParseDisplayNameFrom...` in code. The authoritative verb→path table is computed per-user; dump it with `reg query "HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders"` and `User Shell Folders` (the latter keeps `%VARS%` unexpanded — the correct one for automation).
- Known Folders (Desktop, Documents, Downloads, Pictures…) are **redirectable** — OneDrive Known Folder Move relocates them and leaves a junction in the profile. Never hardcode `%USERPROFILE%\Desktop`; resolve live with `[Environment]::GetFolderPath('Desktop')` or `reg query "HKCU\...\User Shell Folders" /v Desktop`. Cross-check both: folder-list UI may show the redirect, `.Local State` tools may not.
- Inside a folder window, the displayed label (`SHGDN_NORMAL`) and the true location (`SHGDN_FORPARSING`) differ for virtual items. The scraping path is `IShellFolder::GetDisplayNameOf(SDN_PARSE)` — or in COM, `FolderItem.Path` returns parse-path forms like `::{20D04FE0-...}\` for shell roots.
- OneDrive/cloud placeholder files appear as normal items without locally stored bytes. New-style placeholders show attributes `P` (pinned/fully available) and `U` (unpinned, online-only): `Get-Item file.docx | Select Name,Attributes` or `attrib file.docx`. Opening an online-only file triggers a network fetch — expect seconds, treat the "not responding" wait as progress, not as a hang.
- Network providers (`\\server\share`) sit in the namespace at `shell:NetworkPlacesFolder` with credentials stored at Control Panel → Credential Manager (`cmdkey /list` reads them; `keymgr.dll` UI rarely automates cleanly).

## 2. Explorer windows are scriptable surfaces

A folder window is a `CabinetWClass` top-level hosting a `DirectUIHWND` content pane. Classic Win32 messages mostly bounce off the content area — drive it through **UIA** (rich tree: items, headers, thumbnav) or through the **Shell COM API**, which is the supported automation route.

Enumerate and steer live windows with `Shell.Application`:

```powershell
$sh = New-Object -ComObject Shell.Application
foreach ($w in @($sh.Windows())) {
  "{0}  ::  {1}" -f $w.locationURL, $w.FullName
}
```

Every open Explorer window, and every IE/AppX webview host, appears in `.Windows()`. Match on `.LocationURL` or `.FullName`, then act: `.Navigate("shell:Downloads")` moves that window (accepts `shell:` verbs and `file:` URLs), `.Quit()` closes it. `Navigate` on an existing window beats spamming `explorer.exe` — reuses the user's surface, no orphan windows. To read contents without touching the UI: `$doc = $w.Document`; `$doc.Folder.Items()` enumerates `FolderItem` objects with `.Name`, `.Path`, `.Size`, `.Type`, `.Modified` — these map to the Details-pane columns, and invoking a column sort repeatedly resets selection, so read directly instead of clicking headers.

Item verbs = the right-click menu, exactly: `$item.Verbs()` enumerates `FolderItemVerb` entries; `$item.InvokeVerb($verbs.Item($idx).Name)` runs one. Names are localized and some entries are separators — match loosely (`-match 'copiar|copy'`). `InvokeVerb("delete"`) may raise a confirmation dialog; verify by counting items before/after, and expect "Delete" to route to the Recycle Bin (parse name `shell:RecycleBinFolder`), not to permanent removal.

Selection and view state are window-scoped: `.Document.SelectItem($item.pidl, $SVSI_SELECT)`; flags `SVSI_DESELECT=0`, `SVSI_SELECT=1`, `SVSI_FOCUS=4`. Breakout-into-new-window (`explorer.exe /e, /root,<pidl>` window-class paring) is brittle; prefer COM.

Win11 22H2+ topology: one `explorer.exe` process hosts the **tab bar**; each tab's shell namespace browser runs in a separate `WindowsExplorerFileExplorerHost.exe`. Windows with two tabs share one HWND but two host processes — UIA tree lives with the host; switching tabs invalidates cached element refs. There are **no** public COM objects for tabs: automate them with SendInput accelerators `Ctrl+T` (new tab), `Ctrl+W` (close tab), `Ctrl+Tab`/`Ctrl+Shift+Tab` (cycle), `Ctrl+L`/`Alt+D` (focus address bar), `F2` rename, `Alt+Enter` properties dialog (a `#32770` you can then drive with messages or UIA).

The address bar is a `DirectUIHWND` combobox: `Ctrl+L`, type target path or `shell:` verb, Enter — a live validated autocomplete dropdown appears; if your typed text got replaced by a suggestion, Enter navigates to the *suggestion*, so press End/verify with `Alt+D` re-read via UIA value before trusting the navigation. Real path is always on the page hierarchy menu, `View → Path bar` or clicking chevrons in the address bar area.

## 4. Shortcuts (.lnk), AppUserModelID, elevation flags

A `.lnk` is the MS-SHCL structure: target (possibly with volume/item ID lists so it survives drive-letter remounts), arguments, working dir, icon, hotkey, and show-command flag. Create robustly via COM, not text templating:

```powershell
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

A `.lnk` is the MS-SHCL binary structure: target (possibly with embedded volume/FR identifier-lists so it survives drive-letter changes), arguments, working dir, icon location, hotkey, and show command flag. Create or modify it through the Windows Script Host COM:

```powershell
$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut("$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Tool.lnk")
$sc.TargetPath = 'C:\app\tool.exe'; $sc.Arguments = '--flag'
$sc.WorkingDirectory = 'C:\app'; $sc.IconLocation = 'C:\app\tool.exe,0'
$sc.Save()
```

The same `CreateShortcut($existingPath)` call on an existing file READS it: properties come back populated (TargetPath, Arguments, RelativePath, Hotkey, IconLocation) — this is the standard programmatic inspection,  TargetPath is resolved by the link parser on the machine reading it, so a link built for a drive letter that later remaps can come back pointing somewhere else; pin verifiable presence by IDList forms only when necessary. Extra data blocks on the same link carry the elevation flag ("Run as administrator" = default verb becomes `runas`, so `Start-Process` on the .lnk can raise UAC and hand off is required per unclimbable-walls rules); WScript.Shell cannot write that flag — set it through `IShellLinkDataList`/`IPersistFile` from a compiled helper, or accept the prompt in the automation flow. Downloaded shortcuts may carry the Zone.Identifier stream: read with `Get-Content file.lnk -Stream Zone.Identifier`, clear with `Unblock-File`.

## 5. Start Menu, AppsFolder, and where launches really go

The Start menu is rendered by `StartMenuExperienceHost.exe` on top of exactly two folders: `%APPDATA%\Microsoft\Windows\Start Menu\Programs` (this user) and `%ProgramData%\Microsoft\Windows\Start Menu\Programs` (all users). Dropping a valid `.lnk` there makes the app appear in Start after the next index refresh — that single act is the entire "integration" most installers perform. Open them with `shell:Programs` and `shell:Common Programs`. UWP/MSIX apps are **not** in those folders; they live in `shell:AppsFolder`, a virtual namespace of `<PackageFamilyName>!<AppId>` entries.

Enumerate everything launchable with `Get-StartApps` — it returns rows of `Name` + AppID, where classic entries show a `.lnk` path and pack apps show the `family!AppId` form. Launch either form directly: `explorer.exe "shell:AppsFolder\<family>!<AppId>"` starts a pack app without the menu UI entirely. This beats driving the Start overlay when you just need the app up; the UIA route below is only for what the launcher cannot do (pins, tile layout).

Driving the Start UI itself: the panel is a XAML island — classic HWND messages get nowhere; use UIA (control types `ListItem`, `Button`, names equal to the `.lnk` display names) or keyboard. The reliable keyboard scaffold: `Win` opens Start with search focused → type the name → `Enter` launches the top hit. If the top result is the wrong app (search ranks historical use, not you), arrow-key to the right row before Enter. `Win` then typing is strictly more robust than opening Start first and then navigating: the search box is pre-focused.

Long-term per-app launch fidelity: execute the actual `.lnk`/`.appref-ms`, not the bare exe, so arguments, working directory, AUMID grouping, and any elevation verb are honored. Verify a launch succeeded by process existence + window enumeration within a short poll budget, not by `Start-Process` returning without error.

## 6. Jump Lists and the Recent store

Jump Lists (right-click a taskbar icon) expose **recent / frequent / pinned** entries — and the backing store lives on disk:

```
%APPDATA%\Microsoft\Windows\Recent\                       # plain .lnk per opened file, all apps
%APPDATA%\Microsoft\Windows\Recent\AutomaticDestinations\ # per-AUMID jump lists
%APPDATA%\Microsoft\Windows\Recent\CustomDestinations\    # app-supplied custom entries
```

`AutomaticDestinations` entries are keyed by a **hash of the app's AppUserModelID**, one `*.automaticDestinations-ms` blob per AUMID. Each blob is OLE structured storage (`dest` stream): items carry display name, run count, first/last timestamps and a serialized PIDL — so a jump-list row can point at a file that no longer exists; verify the path before relaunching. Tools: `jump-list-viewer`, `Softadjust BNB viewer`, or rolling your own `olefile` reader in Python (the `dest` stream is a DEST enumerate; fields parse at fixed widths).

The plain `Recent\*.lnk` folder is the OS MRU the classic "Run → recent" and Office pickers consume — every file an app opens via `SHAddToRecentDocs` lands here as a normal shortcut; reading `TargetPath` is cheap and scriptable. Deleting rows: blow away individual `.lnk`s here, or delete an `automaticDestinations-ms` to clear one app's list wholesale (Explorer recreates it lazily; no restart needed). Global opt-out lives in Settings → Personalization → Start (`Show recently opened items in Jump Lists…` toggles it, backed by `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\Start_TrackDocs`); privacy audits check this value before trusting presence of a list. For forensic reconstruction of "what touched what when," the mtime of the `.lnk` links is when the link was created, not when the user opened the current version — cross-check NTFS `$UsnJrnl`. Timezone is local-naive; convert before report writing.

## 7. Taskbar, tray, and pinned state

Pinned taskbar items are `.lnk` files under `%APPDATA%\Microsoft\Internet Explorer\Quick Launch\User Pinned\TaskBar\` (plus `ImplicitAppShortcuts\` for grouped variants). Listing that folder tells you what is pinned. **Writing there does not pin**: Explorer keeps a parallel per-item "pinned" boolean in its automatic-destination store, and the taskbar view only follows that flag. The supported pin paths are: the verb (`FolderItem.InvokeVerb('taskbarpin')` over `Shell.Application` windows for Starts-menu items — Win10+), or driving the Start menu UIA (`pin to taskbar` context verb). Same asymmetry on unpin — delete the `.lnk` and the flag makes it vanish; set the flag through code and the rows refresh.
