## 8. Settings deep links (`ms-settings:`) and page verification

Prefer a URI over clicking Settings: `explorer.exe "ms-settings:network-wifi"` or `start ms-settings:power` lands on the page in one step. The scheme is registered per-user under `HKCU\Software\Classes\ms-settings`; the handler is the immersive control panel (Win10) or the Settings app itself (Win11, `Microsoft.Settings_8wekyb3d8bbwe`), which is why the process name you poll for changes by build.

Three disciplines that keep this honest:

1. **No error on a bad token.** An unknown page silently opens Settings at Home. Do not treat "process exists" as success — assert arrival through UIA: the NavigationView `ListItem` for the target page has `IsSelected = true`, and the page caption text is a stable string. Screenshotting title is the cheap version.
2. **There is no machine-readable list of valid tokens.** Microsoft documents a subset for enterprise management; the real gate is a mapped page inside the app. Enumerate empirically by driving Settings search, or maintain your own allow-list and verify each entry once on the target build, because page tokens churn between feature updates.
3. **Policy-gated pages still open.** When a GPO/MDM policy hides a setting, the page renders with controls disabled or sections missing — visible in UIA as `IsEnabled = false`. Check that before concluding the toggle exists and your click missed.

Settings is **not elevated** by default; pages needing admin raise their own shield prompt inside the window. Launch under the interactive user's token and drive the resulting dialog, or bypass the UI with the backing store (`reg`, `dism`, `PowerShell -Module`) when the state is what you actually need.
