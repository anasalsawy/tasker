$ErrorActionPreference = 'Continue'
$key = 'Bearer sp_sltCBbGrfWzwyiQBUthGNQSE0NxbQNBy-PV673fH6U4'
$base = 'https://dl-companion-production.up.railway.app'
$log  = 'C:/Users/anasa/tasker-github/backend/hands_knowledge/_ingest_log.txt'
function Log($m) { $line = ('{0}  {1}' -f (Get-Date -Format 'HH:mm:ss'), $m); Add-Content -Path $log -Value $line; Write-Host $line }

Set-Content -Path $log -Value 'ingest started' -Encoding UTF8

$existing = @()
try {
  $st = Invoke-RestMethod -Uri "$base/v1/knowledge" -Headers @{ Authorization = $key } -TimeoutSec 120
  $existing = @($st.sources | ForEach-Object { $_.name })
  Log ('store already has: ' + ($existing -join ', '))
} catch { Log ('store probe failed, proceeding blind: ' + $_.Exception.Message) }
$files = Get-ChildItem 'C:/Users/anasa/tasker-github/backend/hands_knowledge/*.md' | Where-Object { $_.Name -notlike '_*' } | ForEach-Object { $_.Name }
foreach ($name in ($files | Where-Object { $existing -notcontains $_ })) {
  $path = "C:/Users/anasa/tasker-github/backend/hands_knowledge/$name"
  $text = [IO.File]::ReadAllText($path)
  $bytes = [Text.Encoding]::UTF8.GetByteCount($text)
  Log ("POST {0} ({1} bytes)" -f $name, $bytes)
  $body = @{ name = $name; text = $text } | ConvertTo-Json -Depth 3 -Compress
  $t0 = Get-Date
  $ok = $false
  for ($try = 1; $try -le 2 -and -not $ok; $try++) {
    try {
      $resp = Invoke-RestMethod -Uri "$base/v1/knowledge" -Method Post -Headers @{ Authorization = $key } -ContentType 'application/json; charset=utf-8' -Body ([Text.Encoding]::UTF8.GetBytes($body)) -TimeoutSec 1800
      $secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
      Log ("OK {0} in {1}s :: {2}" -f $name, $secs, ($resp | ConvertTo-Json -Depth 4 -Compress))
      $ok = $true
    } catch {
      $secs = [math]::Round(((Get-Date) - $t0).TotalSeconds, 1)
      Log ("ERR try{0} {1} after {2}s :: {3}" -f $try, $name, $secs, $_.Exception.Message)
      if ($try -eq 1) { Start-Sleep -Seconds 30 }
      else {
        # server may have finished anyway — check the store
        Start-Sleep -Seconds 20
        try {
          $store = Invoke-RestMethod -Uri "$base/v1/knowledge" -Headers @{ Authorization = $key } -TimeoutSec 120
          $names = ($store.sources | ForEach-Object { $_.name }) -join ','
          if ($names -match ([regex]::Escape($name))) { Log ("RECOVERED {0} present in store despite HTTP error" -f $name); $ok = $true }
          else { Log ("MISSING {0} not in store; store=[{1}]" -f $name, $names) }
        } catch { Log ("STORE CHECK FAILED :: " + $_.Exception.Message) }
      }
    }
  }
}

try {
  $final = Invoke-RestMethod -Uri "$base/v1/knowledge" -Headers @{ Authorization = $key } -TimeoutSec 120
  Log ('FINAL STORE: ' + (($final.sources | ForEach-Object { $_.name }) -join ', '))
} catch { Log ('FINAL CHECK ERR: ' + $_.Exception.Message) }
Log 'ingest batch complete'
