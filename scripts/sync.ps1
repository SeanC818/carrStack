param(
    [ValidateSet('ado', 'github')]
    [string]$Variant = 'ado',
    [switch]$NoPull
)

$ErrorActionPreference = 'Stop'
$repo = Split-Path -Parent $PSScriptRoot

if (-not $NoPull) {
    git -C $repo pull --ff-only
    if ($LASTEXITCODE -ne 0) { throw 'git pull failed' }
}

$source = if ($Variant -eq 'ado') { Join-Path $repo 'skills-ado' } else { Join-Path $repo 'skills' }
$targets = @(
    (Join-Path $HOME '.claude\skills'),
    (Join-Path $HOME '.codex\skills')
)

foreach ($target in $targets) {
    New-Item -ItemType Directory -Force $target | Out-Null
    foreach ($skill in Get-ChildItem -Directory $source) {
        $dest = Join-Path $target $skill.Name
        if (Test-Path $dest) { Remove-Item -Recurse -Force $dest }
        Copy-Item -Recurse $skill.FullName $dest
    }
    Write-Host "Installed $Variant skills to $target"
}
