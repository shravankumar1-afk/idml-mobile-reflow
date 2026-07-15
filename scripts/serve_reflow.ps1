param([int]$Port=8000,[string]$Folder=(Join-Path $PSScriptRoot '..\reflow_latest'))
$resolved=(Resolve-Path -LiteralPath $Folder).Path
Write-Host "Serving $resolved at http://localhost:$Port"
Set-Location -LiteralPath $resolved
python -m http.server $Port --bind 127.0.0.1
