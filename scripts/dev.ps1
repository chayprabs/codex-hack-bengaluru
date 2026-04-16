param(
    [Parameter(Position = 0)]
    [ValidateSet("web", "api", "both")]
    [string]$Target = "both"
)

$RootDir = Split-Path -Parent $PSScriptRoot
$DevScript = Join-Path $RootDir "scripts\dev.py"

if (Get-Command python -ErrorAction SilentlyContinue) {
    & python $DevScript $Target
    exit $LASTEXITCODE
}

if (Get-Command py -ErrorAction SilentlyContinue) {
    & py -3 $DevScript $Target
    exit $LASTEXITCODE
}

Write-Error "Could not find python or py. Install Python 3.11+ first."
exit 1
