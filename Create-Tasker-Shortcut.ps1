$repo = "C:\Users\anasa\tasker-github"
$shortcutPath = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Tasker.lnk"

$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut($shortcutPath)

# Run PowerShell hidden with the startup script
$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$repo\Start-Tasker-Tray.ps1`""
$shortcut.WorkingDirectory = $repo
$shortcut.IconLocation = "$repo\desktop\public\favicon.ico,0"
$shortcut.Description = "Tasker - System Tray Application"

# Don't show window
$shortcut.WindowStyle = 7

$shortcut.Save()

Write-Host "✓ Shortcut created: $shortcutPath"
Write-Host ""
Write-Host "You can now:"
Write-Host "  1. Pin it to Start Menu (right-click the shortcut)"
Write-Host "  2. Pin it to Taskbar (right-click the shortcut)"
Write-Host "  3. Create a Desktop shortcut (copy the shortcut)"
Write-Host ""
Write-Host "Run it with: powershell -NoProfile -ExecutionPolicy Bypass -File $repo\Start-Tasker-Tray.ps1"
