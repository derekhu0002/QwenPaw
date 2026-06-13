# Run all Integrity Protection delivery self-test nets (wiring + backend + frontend).
$ErrorActionPreference = "Stop"

$ScriptDir = Split-Path -Parent $MyInvocation.MyCommand.Path
$Runner = Join-Path $ScriptDir "run-integrity-delivery-selftest.py"
& python $Runner @args
exit $LASTEXITCODE
