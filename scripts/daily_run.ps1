# Daily hands-off pipeline: generate slideshows on Vercel → ingest to gallery → farm batch.
param(
    [ValidateSet("labely", "valcoin")]
    [string]$Brand = "labely",
    [string]$FarmUrl = "http://localhost:8080",
    [switch]$IngestOnly
)

$ErrorActionPreference = "Stop"
$body = @{
    brand     = $Brand
    run_batch = -not $IngestOnly.IsPresent
} | ConvertTo-Json

$headers = @{ "Content-Type" = "application/json" }
$secret = $env:FARM_SECRET
if ($secret) {
    $headers["X-Farm-Secret"] = $secret
}

Write-Host "Starting slideshow generate-and-run for $Brand..."
$result = Invoke-RestMethod -Uri "$FarmUrl/api/slideshow/generate-and-run" -Method POST -Headers $headers -Body $body
$jobId = $result.job.id
Write-Host "Job $jobId started."
if ($result.automation_url) {
    Write-Host "Automation URL: $($result.automation_url)"
}

$deadline = (Get-Date).AddHours(2)
while ((Get-Date) -lt $deadline) {
    Start-Sleep -Seconds 5
    $job = Invoke-RestMethod -Uri "$FarmUrl/api/slideshow/jobs/$jobId" -Method GET
    $status = "$($job.status) / $($job.phase): $($job.message)"
    Write-Host $status
    if ($job.status -in @("completed", "failed")) {
        if ($job.status -eq "failed") {
            Write-Error $job.error
        }
        exit 0
    }
}

Write-Error "Timed out waiting for slideshow job $jobId"
