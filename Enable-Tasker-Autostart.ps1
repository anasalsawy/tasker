$repo = "C:\Users\anasa\tasker-github"
$scriptPath = "$repo\Start-Tasker-Tray.ps1"
$startupFolder = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Startup"

# Create a shortcut in Startup folder
$shell = New-Object -ComObject WScript.Shell
$shortcut = $shell.CreateShortcut("$startupFolder\Tasker.lnk")

$shortcut.TargetPath = "powershell.exe"
$shortcut.Arguments = "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$scriptPath`""
$shortcut.WorkingDirectory = $repo
$shortcut.IconLocation = "$repo\desktop\public\favicon.ico,0"
$shortcut.Description = "Tasker - System Tray (Auto-start)"
$shortcut.WindowStyle = 7

$shortcut.Save()

Write-Host "✓ Tasker will auto-start on system boot"
Write-Host "  Location: $startupFolder\Tasker.lnk"
Write-Host ""
Write-Host "✓ To disable auto-start:"
Write-Host "  Delete the shortcut or run: Remove-Item '$startupFolder\Tasker.lnk'"
