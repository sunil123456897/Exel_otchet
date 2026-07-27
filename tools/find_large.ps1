Get-ChildItem -Path REPORTS, РСЧ, "рсч всех" -Recurse -File -ErrorAction SilentlyContinue |
    Where-Object { $_.Length -gt 2MB -and $_.Extension -ne ".bak" } |
    Select-Object FullName, @{Name='SizeMB';Expression={[math]::Round($_.Length / 1MB, 2)}} |
    Sort-Object SizeMB -Descending |
    Format-Table -AutoSize
