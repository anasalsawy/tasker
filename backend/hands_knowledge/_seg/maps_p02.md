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
