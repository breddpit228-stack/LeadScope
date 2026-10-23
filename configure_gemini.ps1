$ErrorActionPreference = 'Stop'
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $root

Write-Host "Lead Research Studio v2 - Gemini setup" -ForegroundColor Cyan
Write-Host "The key will be stored only in .env on this computer. .env is ignored by Git."
Write-Host "Because a key was previously shared in chat, create/rotate to a NEW key before pasting it here." -ForegroundColor Yellow
Write-Host ""

$secure = Read-Host "Paste NEW Gemini API key" -AsSecureString
$bstr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try {
    $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($bstr)
} finally {
    [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($bstr)
}
if ([string]::IsNullOrWhiteSpace($key)) {
    Write-Host "No key entered. Nothing changed." -ForegroundColor Red
    exit 1
}

$model = Read-Host "Gemini model [gemini-3.8-flash]"
if ([string]::IsNullOrWhiteSpace($model)) { $model = 'gemini-3.8-flash' }

$content = @(
    'LLM_PROVIDER=gemini',
    "GEMINI_MODEL=$model",
    "GEMINI_API_KEY=$key"
) -join [Environment]::NewLine
Set-Content -Path (Join-Path $root '.env') -Value $content -Encoding UTF8
$key = $null
Write-Host ""
Write-Host "Saved .env locally. You can now run start_windows.bat." -ForegroundColor Green
Read-Host "Press Enter to close"
