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
