param([switch]$Enable, [switch]$Disable)
$ErrorActionPreference = 'Stop'
if ($Enable -and $Disable) { throw 'Choose Enable or Disable.' }
Import-Module ScheduledTasks
$guardianRoot = (Resolve-Path -LiteralPath (Join-Path $PSScriptRoot '..')).Path
$guardianName = 'WebsiteGuardian-estateplanning-Weekly'
$guardianPython = Join-Path $guardianRoot '.venv\Scripts\pythonw.exe'
$guardianLauncher = Join-Path $guardianRoot 'scripts\run_weekly.py'
$guardianConfigPath = Join-Path $guardianRoot 'data\weekly.json'
if (Test-Path -LiteralPath $guardianConfigPath) {
    $guardianConfig = Get-Content -LiteralPath $guardianConfigPath -Raw | ConvertFrom-Json
} else {
    $guardianConfig = Get-Content -LiteralPath (Join-Path $guardianRoot 'config\weekly.json') -Raw | ConvertFrom-Json
}
$guardianExisting = Get-ScheduledTask -TaskName $guardianName -ErrorAction SilentlyContinue
if ($guardianExisting) {
    if ($guardianExisting.Actions.Execute -ne $guardianPython -or $guardianExisting.Actions.Arguments -ne ('"' + $guardianLauncher + '"')) {
        throw 'Existing task differs from this Guardian checkout; inspect it manually.'
    }
}
if ($Disable) {
    $guardianConfig.enabled = $false
    [System.IO.File]::WriteAllText($guardianConfigPath, ($guardianConfig | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
    if ($guardianExisting) {
        Disable-ScheduledTask -TaskName $guardianName | Out-Null
        if ($guardianExisting.State -eq 'Running') { Stop-ScheduledTask -TaskName $guardianName }
    }
} elseif ($Enable) {
    if ((Get-TimeZone).Id -notin @('Singapore Standard Time','Malay Peninsula Standard Time')) {
        throw 'Weekly task requires a Malaysia UTC+8 system timezone.'
    }
    if (-not (Test-Path -LiteralPath $guardianPython)) { throw 'Guardian virtual environment missing.' }
    $guardianAction = New-ScheduledTaskAction -Execute $guardianPython -Argument ('"' + $guardianLauncher + '"') -WorkingDirectory $guardianRoot
    $guardianTrigger = New-ScheduledTaskTrigger -Weekly -DaysOfWeek Monday -At '09:00'
    $guardianIdentity = [System.Security.Principal.WindowsIdentity]::GetCurrent().Name
    $guardianPrincipal = New-ScheduledTaskPrincipal -UserId $guardianIdentity -LogonType Interactive -RunLevel Limited
    $guardianSettings = New-ScheduledTaskSettingsSet -StartWhenAvailable -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 30) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $guardianName -Action $guardianAction -Trigger $guardianTrigger -Principal $guardianPrincipal -Settings $guardianSettings -Description 'Guardian read-only audit, SEO/speed collection and private Telegram digest. Monday 09:00 Malaysia. Requires owner login.' -Force | Out-Null
    $guardianConfig.enabled = $true
    [System.IO.Directory]::CreateDirectory((Split-Path -Parent $guardianConfigPath)) | Out-Null
    [System.IO.File]::WriteAllText($guardianConfigPath, ($guardianConfig | ConvertTo-Json), (New-Object System.Text.UTF8Encoding($false)))
}
# The read-only bot listener starts at owner login and is supervised separately.
$guardianListenerName = 'WebsiteGuardian-estateplanning-Telegram'
$guardianListener = Get-ScheduledTask -TaskName $guardianListenerName -ErrorAction SilentlyContinue
$guardianListenerArguments = '"' + $guardianLauncher + '" --listen'
if ($guardianListener -and ($guardianListener.Actions.Execute -ne $guardianPython -or $guardianListener.Actions.Arguments -ne $guardianListenerArguments)) {
    throw 'Existing listener task differs from this checkout; inspect manually.'
}
if ($Disable -and $guardianListener) {
    Disable-ScheduledTask -TaskName $guardianListenerName | Out-Null
    Stop-ScheduledTask -TaskName $guardianListenerName
} elseif ($Enable) {
    $guardianListenerAction = New-ScheduledTaskAction -Execute $guardianPython -Argument $guardianListenerArguments -WorkingDirectory $guardianRoot
    $guardianListenerTrigger = New-ScheduledTaskTrigger -AtLogOn -User $guardianIdentity
    $guardianListenerSettings = New-ScheduledTaskSettingsSet -RunOnlyIfNetworkAvailable -MultipleInstances IgnoreNew -ExecutionTimeLimit ([TimeSpan]::Zero) -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1) -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries
    Register-ScheduledTask -TaskName $guardianListenerName -Action $guardianListenerAction -Trigger $guardianListenerTrigger -Principal $guardianPrincipal -Settings $guardianListenerSettings -Description 'Read-only private-owner Telegram commands; no scan, model, approval or production actions.' -Force | Out-Null
}
Get-ScheduledTask -TaskName $guardianName -ErrorAction SilentlyContinue | Select-Object TaskName, State
if ($Enable -or $guardianExisting) {
    Get-ScheduledTaskInfo -TaskName $guardianName | Select-Object NextRunTime, LastRunTime, LastTaskResult
}
