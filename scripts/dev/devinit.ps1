Set-StrictMode -Version Latest
$ErrorActionPreference = "Stop"

$root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
Set-Location $root
$twitterCli = Join-Path $root "python\.venv\Scripts\twitter.exe"
$twitterCommand = if (Test-Path $twitterCli) { $twitterCli } else { "twitter" }

Write-Host "twitter-auto-poster Windows native dev check"
Write-Host "cwd: $((Get-Location).Path)"

$checks = @(
    @{ Name = "git"; Command = "git"; Args = @("--version"); Required = $true },
    @{ Name = "python"; Command = "python"; Args = @("--version"); Required = $true },
    @{ Name = "py -3"; Command = "py"; Args = @("-3", "--version"); Required = $false },
    @{ Name = "node"; Command = "node"; Args = @("-p", "process.platform"); Required = $false },
    @{ Name = "gh"; Command = "gh"; Args = @("--version"); Required = $false },
    @{ Name = "twitter"; Command = $twitterCommand; Args = @("status", "--yaml"); Required = $false }
)

foreach ($check in $checks) {
    $command = Get-Command $check.Command -ErrorAction SilentlyContinue
    if ($null -eq $command) {
        $level = if ($check.Required) { "error" } else { "warn" }
        Write-Host "[$level] $($check.Name): not found"
        if ($check.Required) {
            exit 1
        }
        continue
    }

    Write-Host "[info] $($check.Name): $($command.Source)"
    & $check.Command @($check.Args)
    if ($LASTEXITCODE -ne 0 -and $check.Required) {
        exit $LASTEXITCODE
    }
}

Write-Host "[info] No live Twitter/X write command was executed."
