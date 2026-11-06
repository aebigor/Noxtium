$ErrorActionPreference = 'Stop'
Write-Host 'Este script elimina solo los componentes antiguos de WhatsApp QR/Baileys de NOXTIUM.' -ForegroundColor Yellow
Write-Host 'Se eliminarán también las sesiones locales QR y su archivo .env dentro de whatsapp_service.' -ForegroundColor Yellow
$confirm = Read-Host 'Escribe ELIMINAR para continuar'
if ($confirm -cne 'ELIMINAR') {
    Write-Host 'Cancelado. No se eliminó nada.'
    exit 0
}
$targets = @(
    'app/routes/qr_whatsapp.py',
    'templates/whatsapp_qr.html',
    'whatsapp_service',
    'README_QR_N8N.md',
    'FIX_CRM_QR_FLUJO.md',
    'REVISION_CAMBIOS.md',
    'n8n/noxtium_qr_test_workflow.json'
)
foreach ($relative in $targets) {
    $path = Join-Path (Get-Location) $relative
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Recurse -Force
        Write-Host "Eliminado: $relative"
    }
}
Write-Host 'Limpieza QR terminada. No ejecutes npm start para NOXTIUM; ahora usa la conexión oficial de Meta.' -ForegroundColor Green
