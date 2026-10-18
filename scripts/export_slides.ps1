# Export presentation/Project_Presentation.pptx to PNGs in presentation/slide_images/.
# LibreOffice is not installed on this machine; the locally installed Microsoft
# PowerPoint 16.0 COM API is used instead (assumption A26).
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
$pptx = Join-Path $root 'presentation\Project_Presentation.pptx'
$out  = Join-Path $root 'presentation\slide_images'
if (Test-Path $out) { Remove-Item (Join-Path $out '*.png') -ErrorAction SilentlyContinue }
else { New-Item -ItemType Directory -Path $out | Out-Null }

$ppt = New-Object -ComObject PowerPoint.Application
try {
    $pres = $ppt.Presentations.Open($pptx, $true, $false, $true)  # ReadOnly, WithWindow
    $count = $pres.Slides.Count
    $pres.Export($out, 'PNG', 1600, 900)
    $pres.Close()
    Write-Host "exported $count slides"
}
finally {
    $ppt.Quit()
    [System.Runtime.InteropServices.Marshal]::ReleaseComObject($ppt) | Out-Null
}

# rename PowerPoint's SlideN.PNG -> slide_NN.png (natural order)
Get-ChildItem $out -Filter '*.PNG' |
    Sort-Object { [int]([regex]::Match($_.BaseName, '(\d+)$').Groups[1].Value) } |
    ForEach-Object -Begin { $i = 1 } -Process {
        Rename-Item $_.FullName -NewName ('slide_{0:D2}.png' -f $i); $i++
    }
Get-ChildItem $out -Filter '*.png' | Select-Object Name, Length
