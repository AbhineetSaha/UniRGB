# Run as administrator. Makes UniRGB the only lighting app at sign-in:
#  - disables the vendor scheduled tasks that relaunch MSI's LEDKeeper2 and Razer Synapse
#    (names saved so -Undo can re-enable exactly those)
#  - registers OpenRGB (RAM lighting) to start elevated, minimized, with its SDK server, at sign-in
# Undo: run again with -Undo.
param([string]$User = $env:USERNAME, [switch]$Undo, [string]$Log)
if ($Log) { Start-Transcript -Path $Log -Force | Out-Null }
$backup = Join-Path $env:LOCALAPPDATA "UniRGB\vendor-autostart-backup\disabled-tasks.txt"
$openrgbTask = "UniRGB - OpenRGB server"

if ($Undo) {
    if (Test-Path $backup) {
        Get-Content $backup | ForEach-Object {
            $path, $name = $_ -split "`t"
            Enable-ScheduledTask -TaskPath $path -TaskName $name | Out-Null
            "re-enabled: $path$name"
        }
        Remove-Item $backup
    }
    Unregister-ScheduledTask -TaskName $openrgbTask -Confirm:$false -ErrorAction SilentlyContinue
    "removed: $openrgbTask"
} else {
    New-Item -ItemType Directory -Force (Split-Path $backup) | Out-Null
    $vendor = Get-ScheduledTask | Where-Object {
        $_.State -ne 'Disabled' -and (($_.Actions.Execute -join ' ') + $_.TaskName) -match 'LEDKeeper|Mystic|MSI Center|RazerAppEngine|Razer Synapse|RazerCentral'
    }
    foreach ($t in $vendor) {
        Disable-ScheduledTask -TaskPath $t.TaskPath -TaskName $t.TaskName | Out-Null
        Add-Content $backup "$($t.TaskPath)`t$($t.TaskName)"
        "disabled: $($t.TaskPath)$($t.TaskName)  ($($t.Actions.Execute -join ' '))"
    }
    if (-not $vendor) { "no vendor startup tasks found" }
    Stop-Process -Name LEDKeeper2, RazerAppEngine -Force -ErrorAction SilentlyContinue

    $exe = "C:\Program Files\OpenRGB\OpenRGB.exe"
    if (Test-Path $exe) {
        $action = New-ScheduledTaskAction -Execute $exe -Argument "--server --startminimized" -WorkingDirectory (Split-Path $exe)
        $trigger = New-ScheduledTaskTrigger -AtLogOn -User $User
        $settings = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -ExecutionTimeLimit 0
        Register-ScheduledTask -TaskName $openrgbTask -Action $action -Trigger $trigger -Settings $settings `
            -RunLevel Highest -User $User -Force | Out-Null
        "registered: $openrgbTask (at sign-in, elevated)"
        if (-not (Get-Process OpenRGB -ErrorAction SilentlyContinue)) { Start-ScheduledTask -TaskName $openrgbTask; "started OpenRGB now" }
    } else { "OpenRGB not installed: skipped" }
}
if ($Log) { Stop-Transcript | Out-Null }
