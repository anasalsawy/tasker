## 6. Jump Lists and the Recent store

Jump Lists (right-click a taskbar icon) expose **recent / frequent / pinned** entries — and the backing store lives on disk:

```
%APPDATA%\Microsoft\Windows\Recent\                       # plain .lnk per opened file, all apps
%APPDATA%\Microsoft\Windows\Recent\AutomaticDestinations\ # per-AUMID jump lists
%APPDATA%\Microsoft\Windows\Recent\CustomDestinations\    # app-supplied custom entries
```

`AutomaticDestinations` entries are keyed by a **hash of the app's AppUserModelID**, one `*.automaticDestinations-ms` blob per AUMID. Each blob is OLE structured storage (`dest` stream): items carry display name, run count, first/last timestamps and a serialized PIDL — so a jump-list row can point at a file that no longer exists; verify the path before relaunching. Tools: `jump-list-viewer`, `Softadjust BNB viewer`, or rolling your own `olefile` reader in Python (the `dest` stream is a DEST enumerate; fields parse at fixed widths).

The plain `Recent\*.lnk` folder is the OS MRU the classic "Run → recent" and Office pickers consume — every file an app opens via `SHAddToRecentDocs` lands here as a normal shortcut; reading `TargetPath` is cheap and scriptable. Deleting rows: blow away individual `.lnk`s here, or delete an `automaticDestinations-ms` to clear one app's list wholesale (Explorer recreates it lazily; no restart needed). Global opt-out lives in Settings → Personalization → Start (`Show recently opened items in Jump Lists…` toggles it, backed by `HKCU\Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced\Start_TrackDocs`); privacy audits check this value before trusting presence of a list. For forensic reconstruction of "what touched what when," the mtime of the `.lnk` links is when the link was created, not when the user opened the current version — cross-check NTFS `$UsnJrnl`. Timezone is local-naive; convert before report writing.
