$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $MyInvocation.MyCommand.Path
$envPath = Join-Path $root ".env"
Write-Host "LeadScope - AI setup" -ForegroundColor Cyan
Write-Host "This key is saved only in your local .env and is ignored by Git." -ForegroundColor DarkGray
$secure = Read-Host "Paste API key" -AsSecureString
$ptr = [Runtime.InteropServices.Marshal]::SecureStringToBSTR($secure)
try { $key = [Runtime.InteropServices.Marshal]::PtrToStringBSTR($ptr) } finally { if ($ptr -ne [IntPtr]::Zero) { [Runtime.InteropServices.Marshal]::ZeroFreeBSTR($ptr) } }
if ([string]::IsNullOrWhiteSpace($key)) { throw "No API key provided." }
$model = Read-Host "Model [gemini-3.8-flash]"
if ([string]::IsNullOrWhiteSpace($model)) { $model = 'gemini-3.8-flash' }
$lines = @( 'LLM_PROVIDER=gemini', "GEMINI_MODEL=$model", "GEMINI_API_KEY=$key" )
Set-Content -LiteralPath $envPath -Value $lines -Encoding UTF8
Write-Host "Saved local AI settings to $envPath" -ForegroundColor Green
