$port = 8000

Write-Host "Menjalankan WebGIS di http://localhost:$port/index.html"
Write-Host "Tekan Ctrl+C di terminal ini kalau sudah selesai."

python -m http.server $port
