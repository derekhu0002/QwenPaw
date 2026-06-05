param(
    [string]$WorkingDir = "",
    [string]$SecretDir = "",
    [string]$BackupDir = "",
    [string]$SecurityCenterDataDir = "",
    [string]$SecurityCenterStoreFile = "",
    [int[]]$Ports = @(8088, 18088, 8091, 8092),
    [switch]$SkipPortCleanup
)

$ErrorActionPreference = "Stop"

$RepoRoot = Split-Path -Parent $PSScriptRoot

function Write-Step {
    param([string]$Message)
    Write-Host "[showcase-reset] $Message" -ForegroundColor Cyan
}

function Resolve-OptionalPath {
    param(
        [string]$Candidate,
        [string]$Fallback
    )

    $value = $Candidate.Trim()
    if (-not $value) {
        $value = $Fallback
    }
    return [System.IO.Path]::GetFullPath($value)
}

function First-NonEmptyValue {
    param(
        [string]$Preferred,
        [string]$Fallback
    )

    if ($Preferred -and $Preferred.Trim()) {
        return $Preferred
    }
    return $Fallback
}

function Get-DefaultWorkingDir {
    $explicit = First-NonEmptyValue -Preferred $env:QWENPAW_WORKING_DIR -Fallback $env:COPAW_WORKING_DIR
    if ($explicit -and $explicit.Trim()) {
        return $explicit
    }

    $legacyCopawDir = Join-Path ([Environment]::GetFolderPath('UserProfile')) '.copaw'
    if (Test-Path -LiteralPath $legacyCopawDir) {
        return $legacyCopawDir
    }

    return (Join-Path ([Environment]::GetFolderPath('UserProfile')) '.qwenpaw')
}

function Stop-ProcessesListeningOnPorts {
    param([int[]]$TargetPorts)

    foreach ($port in $TargetPorts) {
        $connections = Get-NetTCPConnection -LocalPort $port -ErrorAction SilentlyContinue |
            Select-Object -ExpandProperty OwningProcess -Unique
        foreach ($processId in $connections) {
            if (-not $processId -or $processId -eq 0) {
                continue
            }
            try {
                $process = Get-Process -Id $processId -ErrorAction Stop
                Write-Step "Stopping process $($process.ProcessName) ($processId) on port $port"
                Stop-Process -Id $processId -Force -ErrorAction Stop
            } catch {
                Write-Warning ([string]::Format("Failed to stop process {0} on port {1}: {2}", $processId, $port, $_.Exception.Message))
            }
        }
    }
}

function Reset-Directory {
    param([string]$Path)

    if (Test-Path -LiteralPath $Path) {
        Write-Step "Removing $Path"
        Remove-Item -LiteralPath $Path -Recurse -Force -ErrorAction Stop
    }
    Write-Step "Creating $Path"
    New-Item -ItemType Directory -Path $Path -Force | Out-Null
}

function Reset-FileParent {
    param([string]$Path)

    $parent = Split-Path -Parent $Path
    if (-not (Test-Path -LiteralPath $parent)) {
        New-Item -ItemType Directory -Path $parent -Force | Out-Null
    }
    if (Test-Path -LiteralPath $Path) {
        Write-Step "Removing $Path"
        Remove-Item -LiteralPath $Path -Force -ErrorAction Stop
    }
}

$workingFallback = Get-DefaultWorkingDir
$secretFallback = First-NonEmptyValue -Preferred $env:QWENPAW_SECRET_DIR -Fallback ("{0}.secret" -f $workingFallback)
$backupFallback = First-NonEmptyValue -Preferred $env:QWENPAW_BACKUP_DIR -Fallback ("{0}.backups" -f $workingFallback)

$resolvedWorkingDir = Resolve-OptionalPath -Candidate $WorkingDir -Fallback $workingFallback
$resolvedSecretDir = Resolve-OptionalPath -Candidate $SecretDir -Fallback $secretFallback
$resolvedBackupDir = Resolve-OptionalPath -Candidate $BackupDir -Fallback $backupFallback
$resolvedSecurityCenterDataDir = $SecurityCenterDataDir.Trim()
if (-not $resolvedSecurityCenterDataDir) {
    $resolvedSecurityCenterDataDir = $env:QWENPAW_SECURITY_CENTER_DATA_DIR
}
if ($resolvedSecurityCenterDataDir) {
    $resolvedSecurityCenterDataDir = [System.IO.Path]::GetFullPath($resolvedSecurityCenterDataDir)
}

$resolvedSecurityCenterStoreFile = $SecurityCenterStoreFile.Trim()
if (-not $resolvedSecurityCenterStoreFile) {
    $resolvedSecurityCenterStoreFile = Join-Path $RepoRoot "deploy\api\data\security-center-store.json"
}
$resolvedSecurityCenterStoreFile = [System.IO.Path]::GetFullPath($resolvedSecurityCenterStoreFile)

$resolvedSecurityCenterApiUrl = First-NonEmptyValue -Preferred $env:QWENPAW_SECURITY_CENTER_API_URL -Fallback "http://127.0.0.1:8091"
$resolvedSecurityCenterWebUrl = First-NonEmptyValue -Preferred $env:QWENPAW_SECURITY_CENTER_WEB_URL -Fallback "http://127.0.0.1:8092"
$resolvedSecurityCenterApiBase = First-NonEmptyValue -Preferred $env:SECURITY_CENTER_API_BASE -Fallback $resolvedSecurityCenterApiUrl
$resolvedPythonPath = First-NonEmptyValue -Preferred $env:PYTHONPATH -Fallback (Join-Path $RepoRoot "src")

Write-Step "Repo root: $RepoRoot"
Write-Step "WorkingDir: $resolvedWorkingDir"
Write-Step "SecretDir: $resolvedSecretDir"
Write-Step "BackupDir: $resolvedBackupDir"
if ($resolvedSecurityCenterDataDir) {
    Write-Step "SecurityCenterDataDir: $resolvedSecurityCenterDataDir"
}
Write-Step "SecurityCenterStoreFile: $resolvedSecurityCenterStoreFile"

if (-not $SkipPortCleanup) {
    Stop-ProcessesListeningOnPorts -TargetPorts $Ports
}

Reset-Directory -Path $resolvedWorkingDir
Reset-Directory -Path $resolvedSecretDir
Reset-Directory -Path $resolvedBackupDir

if ($resolvedSecurityCenterDataDir) {
    Reset-Directory -Path $resolvedSecurityCenterDataDir
}

Reset-FileParent -Path $resolvedSecurityCenterStoreFile

Write-Step "Showcase demo state has been reset."
Write-Host ""
Write-Host "Recommended environment variables:" -ForegroundColor Green
Write-Host ('$env:QWENPAW_WORKING_DIR = "{0}"' -f $resolvedWorkingDir)
Write-Host ('$env:QWENPAW_SECRET_DIR = "{0}"' -f $resolvedSecretDir)
Write-Host ('$env:QWENPAW_BACKUP_DIR = "{0}"' -f $resolvedBackupDir)
if ($resolvedSecurityCenterDataDir) {
    Write-Host ('$env:QWENPAW_SECURITY_CENTER_DATA_DIR = "{0}"' -f $resolvedSecurityCenterDataDir)
}
Write-Host ('$env:QWENPAW_SECURITY_CENTER_API_URL = "{0}"' -f $resolvedSecurityCenterApiUrl)
Write-Host ('$env:QWENPAW_SECURITY_CENTER_WEB_URL = "{0}"' -f $resolvedSecurityCenterWebUrl)
Write-Host ('$env:SECURITY_CENTER_API_BASE = "{0}"' -f $resolvedSecurityCenterApiBase)
Write-Host ('$env:QWENPAW_AUTH_ENABLED = "false"')
Write-Host ('$env:NO_PROXY = "*"')
Write-Host ('$env:PYTHONPATH = "{0}"' -f $resolvedPythonPath)
Write-Host ('$env:PYTHONIOENCODING = "utf-8"')