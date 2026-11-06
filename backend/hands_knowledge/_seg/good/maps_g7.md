## 7. Network shares and mapped drives

A mapped drive is redirector state, not filesystem state. It belongs to one **logon session**, so a service, scheduled task, or elevated token sees an empty drive set even while the interactive user has `Z:` mounted. Check the identity that runs the code (task user, elevation, session-0 isolation) before checking the path string — that is the usual cause of "works by hand, fails unattended."

Read truth, don't parse. `net use` gives per-session state including `Disconnected`/`Unavailable`; `Get-SmbMapping` returns objects (`LocalPath`, `ProviderPath`, `Status`); `HKCU:\Network\<L>` mirrors **persistent** mappings only (`RemotePath`, `UserName`, `ProviderType`), so a volatile letter never shows there. Cross-check two sources before concluding a mapping is gone.

```powershell
net use
Get-SmbMapping | Format-List LocalPath, ProviderPath, Status
cmdkey /list          # credential the redirector will reuse
```
Win32: `WNetAddConnection2` (`CONNECT_TEMPORARY` vs `CONNECT_PERSISTENT`, `resourcetype`=1 disk); `WNetCancelConnection2` needs the exact UNC and fails with error 55 while a handle is open — check `openfiles /query` before unmounting. Reserve the next free letter atomically with `Get-UniqueFileName` instead of scanning `A:–Z:` and racing Explorer. `WNetGetConnection('Z:')` resolves drive→UNC; `WNetGetUniversalName` runs the reverse and only for drive-backed paths.

Credentials beat prompts: the cached entry in Credential Manager wins, so `/user:` on `net use` can be silently ignored. Read with `cmdkey /list`, write with `cmdkey /generic:\\server\share /user:x /pass:y`, invalidate with `cmdkey /delete` **before** debugging wrong-account access.

Dialect changes behavior, not only bandwidth: `Get-SmbConnection` reports negotiated `Dialect` (2.0.2 → 3.1.1) and `EncryptData`/`Signing`. SMB 3 with `RequireSecureNegotiate` against an old NAS surfaces as an access-denied-looking failure on valid credentials. Oplock loss or latency flips a mapping to `Disconnected`: Explorer keeps the window open, a raw `Open()` throws (`IOException`, error 64). Back off, re-poll `net use`, then retry — don't declare the share dead. DFS namespaces (`\\contoso.com\dfs`) resolve differently on every ticket, and BranchCache rewrites the real source. Neither appears in the path string — resolve via `Get-SmbMapping` and, for the active session table, `Get-SmbClientConnection` / `Get-SmbOpenFile` (admin) to list handles.
