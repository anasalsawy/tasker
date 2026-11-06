$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Drawing
$src = Join-Path $PSScriptRoot 'icon.png'
$sizes = @(256, 128, 64, 48, 32, 16)
$out = Join-Path $PSScriptRoot 'icon.ico'
$img = [System.Drawing.Image]::FromFile($src)
$pngs = @()
foreach ($s in $sizes) {
  $b = New-Object System.Drawing.Bitmap($s, $s)
  $g = [System.Drawing.Graphics]::FromImage($b)
  $g.InterpolationMode = 'HighQualityBicubic'
  $g.SmoothingMode = 'AntiAlias'
  $g.DrawImage($img, 0, 0, $s, $s)
  $g.Dispose()
  $ms = New-Object System.IO.MemoryStream
  $b.Save($ms, [System.Drawing.Imaging.ImageFormat]::Png)
  $b.Dispose()
  $pngs += , @($s, $ms.ToArray())
  $ms.Dispose()
}
$img.Dispose()
$fs = [System.IO.File]::Create($out)
$bw = New-Object System.IO.BinaryWriter($fs)
$bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]$pngs.Count)
$offset = 6 + (16 * $pngs.Count)
foreach ($p in $pngs) {
  $s = $p[0]; $bytes = $p[1]
  $bw.Write([Byte]($(if ($s -ge 256) { 0 } else { $s })))
  $bw.Write([Byte]($(if ($s -ge 256) { 0 } else { $s })))
  $bw.Write([Byte]0); $bw.Write([Byte]0)
  $bw.Write([UInt16]1); $bw.Write([UInt16]32)
  $bw.Write([UInt32]$bytes.Length); $bw.Write([UInt32]$offset)
  $offset += $bytes.Length
}
foreach ($p in $pngs) { $bw.Write($p[1]) }
$bw.Close(); $fs.Close()
Write-Output ("ICO_BYTES=" + (Get-Item $out).Length)
