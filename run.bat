@echo off
setlocal EnableExtensions
cd /d "%~dp0"
chcp 65001 >nul
set "PYTHONDONTWRITEBYTECODE=1"

REM Merchant Promo Scraper: teks/HTML + metadata URL gambar, tanpa OCR.
REM Tidak membuat venv dan tidak menjalankan pip install.
if /I "%~1"=="--help" goto :help

set "MODE=full"
if /I "%~1"=="--check-only" set "MODE=check"
if /I "%~1"=="--test-only" set "MODE=test"
if /I "%~1"=="--prepare-price-research" set "MODE=research"
if /I "%~1"=="--rebuild-from-last-snapshot" set "MODE=rebuild"
set "PYTHON_EXE="
set "PYTHON_ARGS="

REM An explicitly configured interpreter always gets first priority, but must
REM satisfy this mode's dependencies before it is selected.
if defined PROMO_PYTHON call :try_candidate "%PROMO_PYTHON%" ""
if defined PYTHON_EXE goto :python_found
if defined PROMO_PYTHON echo PROMO_PYTHON tidak memenuhi versi/dependency untuk mode %MODE%; mencoba kandidat lain...

REM Prefer supported global Python installs. Python 3.10 reached EOL in Oct 2026.
REM Avoid GOTO inside the FOR block: CMD can misparse a parenthesized block.
for %%V in (315 314 313 312 311) do (
    if not defined PYTHON_EXE if exist "D:\Python%%V\python.exe" call :try_candidate "D:\Python%%V\python.exe" ""
    if not defined PYTHON_EXE if exist "C:\Python%%V\python.exe" call :try_candidate "C:\Python%%V\python.exe" ""
    if not defined PYTHON_EXE if exist "%LocalAppData%\Programs\Python\Python%%V\python.exe" call :try_candidate "%LocalAppData%\Programs\Python\Python%%V\python.exe" ""
    if not defined PYTHON_EXE if exist "%ProgramFiles%\Python%%V\python.exe" call :try_candidate "%ProgramFiles%\Python%%V\python.exe" ""
)
if defined PYTHON_EXE goto :python_found

REM The Python launcher usually resolves a global installation. PATH is last.
call :try_candidate "py" "-3"
if defined PYTHON_EXE goto :python_found
call :try_candidate "python" ""
if defined PYTHON_EXE goto :python_found
goto :no_python

:try_candidate
set "TEST_CMD=%~1"
set "TEST_ARGS=%~2"
if not defined TEST_CMD exit /b 1
if /I "%MODE%"=="check" (
    "%TEST_CMD%" %TEST_ARGS% -c "import sys, requests, bs4, openpyxl; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
) else if /I "%MODE%"=="research" (
    "%TEST_CMD%" %TEST_ARGS% -c "import sys, requests, bs4, openpyxl; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
) else (
    "%TEST_CMD%" %TEST_ARGS% -c "import sys, requests, bs4, openpyxl, pytest; raise SystemExit(0 if sys.version_info >= (3,11) else 1)" >nul 2>nul
)
if errorlevel 1 exit /b 1
set "PYTHON_EXE=%TEST_CMD%"
set "PYTHON_ARGS=%TEST_ARGS%"
exit /b 0

:python_found
if not exist "%~dp0src\promo_multisource_collector.py" goto :bad_project
if not exist "%~dp0src\enrich_existing_promo_catalog_multisource.py" goto :bad_project
if not exist "%~dp0src\source_health_check.py" goto :bad_project
if not exist "%~dp0src\verify_outputs.py" goto :bad_project
if not exist "%~dp0src\promo_history.py" goto :bad_project

set "CHECK_ARGS=--dev"
if /I "%MODE%"=="check" set "CHECK_ARGS="
if /I "%MODE%"=="research" set "CHECK_ARGS="

echo.
echo =====================================================
echo MERCHANT PROMO SCRAPER - TEXT/HTML ONLY
echo Folder proyek : %CD%
echo Python command: "%PYTHON_EXE%" %PYTHON_ARGS%
echo Mode          : %MODE%
echo =====================================================
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0src\check_runtime.py" %CHECK_ARGS%
if errorlevel 1 goto :dependency_error

if /I "%MODE%"=="check" goto :check_success
if /I "%MODE%"=="research" goto :price_research

if not exist "%~dp0runtime" mkdir "%~dp0runtime"
if not exist "%~dp0output" mkdir "%~dp0output"
if not exist "%~dp0state" mkdir "%~dp0state"

echo.
echo [PRA-TEST 1/4] Memeriksa sintaks source dan test...
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0src\check_runtime.py" --dev --check-syntax
if errorlevel 1 goto :error

echo.
echo [PRA-TEST 2/4] Self-test normalisasi nama produk...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\promo_names.py"
if errorlevel 1 goto :error

echo.
echo [PRA-TEST 3/4] Self-test parser dan guardrails collector...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\promo_multisource_collector.py" --self-test
if errorlevel 1 goto :error

echo.
echo [PRA-TEST 4/4] Menjalankan tes regresi (tanpa cache lokal)...
"%PYTHON_EXE%" %PYTHON_ARGS% -m pytest -q -p no:cacheprovider "%~dp0tests"
if errorlevel 1 goto :error

if /I "%MODE%"=="test" goto :test_success
if /I "%MODE%"=="rebuild" goto :rebuild_snapshot

echo.
echo =====================================================
echo TES LULUS. MULAI SCRAPING LIVE
echo Sumber: Hemat.id (halaman retailer terpisah), Katalogpromosi.com, Scanharga.com
echo =====================================================

echo.
echo [LIVE 1/3] Mengambil produk, teks halaman, dan URL gambar dari tiga sumber...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\promo_multisource_collector.py"
if errorlevel 1 goto :error

echo.
echo [LIVE 2/3] Memeriksa kesehatan setiap sumber...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\source_health_check.py"
if errorlevel 1 goto :health_error

echo.
echo [LIVE 3/3] Menggabungkan sumber, validasi harga berbasis teks, dan ekspor...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\enrich_existing_promo_catalog_multisource.py"
if errorlevel 1 goto :error

echo.
echo Verifikasi file hasil...
REM Run a script file rather than embedding %~dp0 in a Python raw string.
REM A Windows path ending in a backslash breaks Path(r'...\') quoting.
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0src\verify_outputs.py"
if errorlevel 1 goto :error

echo.
echo =====================================================
echo SELESAI: KATALOG BERHASIL DIBUAT
echo Excel : output\Katalog_Promo_Final.xlsx
echo CSV   : output\Katalog_Promo_Final.csv
echo Gambar: runtime\promo_multisource_catalog_images.csv (URL saja)
echo Health: runtime\source_health_summary.json
echo Riwayat: output\Riwayat_Promo.csv (seluruh promo, termasuk expired)
echo Harga acuan otomatis tersimpan di state\ (bukan data\)
echo Pencarian harga pasar manual opsional: run.bat --prepare-price-research
echo Tidak ada venv/pip install/OCR gambar dalam pipeline ini.
echo =====================================================
pause
exit /b 0

:rebuild_snapshot
if not exist "%~dp0runtime\promo_multisource_products_all.csv" goto :rebuild_missing
echo.
echo =====================================================
echo REBUILD DARI SNAPSHOT TERAKHIR (TANPA REQUEST WEB)
echo =====================================================
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\enrich_existing_promo_catalog_multisource.py"
if errorlevel 1 goto :error
"%PYTHON_EXE%" %PYTHON_ARGS% "%~dp0src\verify_outputs.py"
if errorlevel 1 goto :error
echo.
echo Katalog dibangun ulang dari snapshot runtime yang sudah ada.
echo Tidak ada request ke situs sumber.
pause
exit /b 0

:rebuild_missing
echo ERROR: Snapshot runtime\promo_multisource_products_all.csv belum tersedia.
echo Jalankan run.bat biasa sekali untuk mengambil data sumber.
pause
exit /b 1

:check_success
echo.
echo LINGKUNGAN VALID. Tidak ada paket yang dipasang dan tidak ada venv yang dibuat.
exit /b 0

:price_research
if not exist "%~dp0runtime\promo_multisource_products_all.csv" goto :research_missing
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\export_manual_price_search.py"
if errorlevel 1 goto :error
echo.
echo Workbook pencarian harga manual selesai dibuat.
exit /b 0

:research_missing
echo ERROR: Snapshot produk belum tersedia di runtime\promo_multisource_products_all.csv.
echo Jalankan run.bat biasa terlebih dahulu, baru buat daftar riset harga.
pause
exit /b 1

:test_success
echo.
echo =====================================================
echo TES OFFLINE BERHASIL
echo Tidak ada scraping live yang dijalankan.
echo Jalankan run.bat untuk pipeline scraping.
echo =====================================================
pause
exit /b 0

:no_python
echo ERROR: Python 3.11+ dengan dependency yang cocok tidak ditemukan.
echo Kandidat harus memiliki requests, beautifulsoup4 (bs4), dan openpyxl.
if /I "%MODE%"=="full" echo Mode normal juga memerlukan pytest karena menjalankan tes offline dahulu.
if /I "%MODE%"=="test" echo Mode tes juga memerlukan pytest.
if /I "%MODE%"=="rebuild" echo Mode rebuild juga memerlukan pytest karena menjalankan tes offline dahulu.
echo Set PROMO_PYTHON ke path python.exe dari instalasi Python yang lengkap.
echo Contoh: set PROMO_PYTHON=D:\Python312\python.exe
echo Launcher tidak membuat venv dan tidak memasang library otomatis.
pause
exit /b 1

:bad_project
echo ERROR: Struktur proyek tidak lengkap. Ekstrak seluruh isi ZIP ke satu folder.
pause
exit /b 1

:dependency_error
echo ERROR: Runtime Python atau library untuk mode yang dipilih belum lolos pemeriksaan.
echo --check-only dan --prepare-price-research hanya memerlukan dependency runtime.
echo Mode normal, --test-only, dan --rebuild-from-last-snapshot memerlukan pytest.
echo Launcher tidak memasang paket otomatis.
pause
exit /b 1

:health_error
echo ERROR: Health-check gagal atau tidak ada data produk yang bisa digunakan.
echo Pipeline dihentikan agar katalog kosong tidak menimpa hasil yang valid.
echo Periksa runtime\promo_multisource_runlog.json dan runtime\source_health_summary.json.
pause
exit /b 1

:error
echo.
echo =====================================================
echo PIPELINE BERHENTI KARENA ERROR
echo Baca pesan di atas dan periksa file log di runtime\.
echo Katalog hasil terakhir yang valid tidak perlu dihapus manual.
echo =====================================================
pause
exit /b 1

:help
echo Pemakaian:
echo   run.bat              Cek, tes, scraping teks/HTML, konsolidasi, ekspor
echo   run.bat --test-only  Cek dan tes offline tanpa scraping live
echo   run.bat --check-only Cek Python/library runtime tanpa menjalankan pipeline
echo   run.bat --prepare-price-research Buat workbook harga manual dari snapshot terakhir
echo   run.bat --rebuild-from-last-snapshot Bangun ulang katalog tanpa request web
echo   run.bat --help       Tampilkan bantuan
echo.
echo Tidak ada pip install otomatis, venv lokal, atau pembacaan teks dari gambar.
exit /b 0
