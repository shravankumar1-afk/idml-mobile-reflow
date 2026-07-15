<#
    Creates a Desktop shortcut ("IDML to Mobile PDF") that launches the GUI.
    Run after `pip install -e .` (or `pip install idml2mobile`):

        powershell -ExecutionPolicy Bypass -File scripts\create_shortcut.ps1

    Auto-detects the installed `idml2mobile-gui` launcher; falls back to
    `pythonw -m idml2mobile.gui` if the console script isn't on PATH.
#>

$ErrorActionPreference = "Stop"
$repo = Split-Path -Parent $PSScriptRoot
$icon = Join-Path $repo "assets\idml2mobile.ico"

# Prefer the installed gui-script exe (windowed, no console).
$guiExe = (Get-Command idml2mobile-gui -ErrorAction SilentlyContinue).Source

if ($guiExe) {
    $target = $guiExe
    $args   = ""
} else {
    # Fallback: pythonw -m idml2mobile.gui
    $py     = (Get-Command python -ErrorAction Stop).Source
    $pyw    = Join-Path (Split-Path $py) "pythonw.exe"
    $target = if (Test-Path $pyw) { $pyw } else { $py }
    $args   = "-m idml2mobile.gui"
}

$desktop = [Environment]::GetFolderPath("Desktop")
$lnk     = Join-Path $desktop "IDML to Mobile PDF.lnk"

$ws = New-Object -ComObject WScript.Shell
$sc = $ws.CreateShortcut($lnk)
$sc.TargetPath       = $target
if ($args) { $sc.Arguments = $args }
$sc.WorkingDirectory = $repo
if (Test-Path $icon) { $sc.IconLocation = "$icon,0" }
$sc.Description       = "Convert IDML/InDesign packages into single-column mobile PDFs"
$sc.WindowStyle      = 1
$sc.Save()

Write-Output "Created shortcut: $lnk"
Write-Output "  -> $target $args"
