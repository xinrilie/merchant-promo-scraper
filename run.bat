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
set "PYTHON_EXE="
set "PYTHON_ARGS="

REM An explicitly configured interpreter always gets first priority, but must
REM satisfy this mode's dependencies before it is selected.
if defined PROMO_PYTHON (
    call :try_candidate "%PROMO_PYTHON%" ""
    if defined PYTHON_EXE goto :python_found
    echo PROMO_PYTHON tidak memenuhi versi/dependency untuk mode %MODE%; mencoba kandidat lain...
)

REM Common global/relocated Python locations. Each candidate is checked for
REM Python >=3.10 and importable runtime modules; pytest is required except for --check-only.
if exist "D:\Python313\python.exe" call :try_candidate "D:\Python313\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "D:\Python312\python.exe" call :try_candidate "D:\Python312\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "D:\Python311\python.exe" call :try_candidate "D:\Python311\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "C:\Python313\python.exe" call :try_candidate "C:\Python313\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "C:\Python312\python.exe" call :try_candidate "C:\Python312\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "C:\Python311\python.exe" call :try_candidate "C:\Python311\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%LocalAppData%\Programs\Python\Python313\python.exe" call :try_candidate "%LocalAppData%\Programs\Python\Python313\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%LocalAppData%\Programs\Python\Python312\python.exe" call :try_candidate "%LocalAppData%\Programs\Python\Python312\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%LocalAppData%\Programs\Python\Python311\python.exe" call :try_candidate "%LocalAppData%\Programs\Python\Python311\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%ProgramFiles%\Python313\python.exe" call :try_candidate "%ProgramFiles%\Python313\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%ProgramFiles%\Python312\python.exe" call :try_candidate "%ProgramFiles%\Python312\python.exe" ""
if defined PYTHON_EXE goto :python_found
if exist "%ProgramFiles(x86)%\Python312\python.exe" call :try_candidate "%ProgramFiles(x86)%\Python312\python.exe" ""
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
    "%TEST_CMD%" %TEST_ARGS% -c "import sys, requests, bs4, openpyxl; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
) else (
    "%TEST_CMD%" %TEST_ARGS% -c "import sys, requests, bs4, openpyxl, pytest; raise SystemExit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
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

set "CHECK_ARGS=--dev"
if /I "%MODE%"=="check" set "CHECK_ARGS="

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

echo.
echo =====================================================
echo TES LULUS. MULAI SCRAPING LIVE
echo Sumber: Hemat.id, Katalogpromosi.com, Scanharga.com
echo =====================================================

echo.
echo [LIVE 1/4] Mengambil produk, teks halaman, dan URL gambar dari tiga sumber...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\promo_multisource_collector.py"
if errorlevel 1 goto :error

echo.
echo [LIVE 2/4] Memeriksa kesehatan setiap sumber...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\source_health_check.py"
if errorlevel 1 goto :health_error

echo.
echo [LIVE 3/4] Menggabungkan sumber, validasi harga berbasis teks, dan ekspor...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\enrich_existing_promo_catalog_multisource.py"
if errorlevel 1 goto :error

echo.
echo [LIVE 4/4] Membuat daftar referensi harga pasar manual yang masih diperlukan...
"%PYTHON_EXE%" %PYTHON_ARGS% -u "%~dp0src\export_manual_price_search.py"
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
echo Harga acuan otomatis tersimpan di state\ (bukan data\)
echo Tidak ada venv/pip install/OCR gambar dalam pipeline ini.
echo =====================================================
pause
exit /b 0

:check_success
echo.
echo LINGKUNGAN VALID. Tidak ada paket yang dipasang dan tidak ada venv yang dibuat.
exit /b 0

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
echo ERROR: Python 3.10+ dengan dependency yang cocok tidak ditemukan.
echo Kandidat harus memiliki requests, beautifulsoup4 (bs4), dan openpyxl.
if /I not "%MODE%"=="check" echo Mode ini juga memerlukan pytest karena menjalankan tes offline dahulu.
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
echo run.bat --check-only hanya memerlukan dependency runtime; run.bat default juga memerlukan pytest.
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
echo Baca pesan di atas dan periksa file log di runtime/.
echo Katalog hasil terakhir yang valid tidak perlu dihapus manual.
echo =====================================================
pause
exit /b 1

:help
echo Pemakaian:
echo   run.bat              Cek, tes, scraping teks/HTML, konsolidasi, ekspor
echo   run.bat --test-only  Cek dan tes offline tanpa scraping live
echo   run.bat --check-only Cek Python/library runtime tanpa menjalankan pipeline
echo   run.bat --help       Tampilkan bantuan
echo.
echo Tidak ada pip install otomatis, venv lokal, atau pembacaan teks dari gambar.
exit /b 0
