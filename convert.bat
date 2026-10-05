@echo off
setlocal enabledelayedexpansion

rem ===================================================================
rem convert.bat - chuyen translation.md sang docx co cong thuc Word that
rem Cach dung:  convert.bat ten_file_output.docx
rem   - Dau vao LUON LA translation.md (co dinh, cung thu muc voi file .bat nay)
rem   - Neu co san template.docx cung thu muc, se tu dung lam --reference-doc
rem   - Nhan dang ca hai kieu cong thuc: \(...\)  \[...\]  VA  \\(...\\)  \\[...\\]
rem
rem QUY TRINH 2 BUOC (moi, thay cho findstr "$$" cu):
rem   1) pandoc chuyen ca file 1 lan (nhanh, chuyen duoc da so cong thuc).
rem   2) latex_to_equation.py quet lai document.xml, CHI thu chuyen tiep
rem      nhung cong thuc buoc 1 bo sot (con dang text tho \(...\)/\[...\]),
rem      cong thuc da chuyen thanh cong o buoc 1 khong con la text nen
rem      khong bi dung lai. Cong thuc nao van loi se duoc ghi ra file
rem      "<ten_output>_loi_kem_cau_van.txt" kem cau van xung quanh de
rem      Ctrl+F trong Word - tinh tam quan sat giong het khi chay
rem      latex_to_equation.py doc lap.
rem ===================================================================

if "%~1"=="" (
    echo Cach dung: convert.bat [ten_file_input.md] ten_file_output.docx
    echo Vi du 1 tham so ^(mac dinh lay translation.md^): convert.bat ban_dich.docx
    echo Vi du 2 tham so: convert.bat y_khoa.md y_khoa.docx
    exit /b 1
)

if "%~2"=="" (
    set "INPUT=translation.md"
    set "OUTPUT=%~1"
) else (
    set "INPUT=%~1"
    set "OUTPUT=%~2"
)
set "TEMPLATE=template.docx"
set "TMPOUT=%OUTPUT:~0,-5%_pandoc_tmp.docx"
set "MDFLAGS=markdown+tex_math_single_backslash+tex_math_double_backslash-tex_math_dollars-yaml_metadata_block"

where pandoc >nul 2>nul
if errorlevel 1 (
    echo LOI: khong tim thay pandoc trong PATH. Cai pandoc roi thu lai.
    exit /b 1
)

if not exist "%INPUT%" (
    echo LOI: khong tim thay file dau vao "%INPUT%" trong thu muc nay.
    exit /b 1
)

set "PYEXE=python"
if exist ".venv\Scripts\python.exe" set "PYEXE=.venv\Scripts\python.exe"

set "REFFLAG="
if exist "%TEMPLATE%" (
    set "REFFLAG=--reference-doc=%TEMPLATE%"
    echo Da tim thay %TEMPLATE% -^> se ap dung style/font tu file nay.
)

echo.
echo [1/2] Dang chuyen doi %INPUT% -^> %TMPOUT% ^(pandoc^)...
pandoc -f %MDFLAGS% "%INPUT%" -o "%TMPOUT%" %REFFLAG%

if errorlevel 1 (
    echo.
    echo ============================================
    echo  CO LOI KHI CHUYEN DOI. Xem thong bao o tren.
    echo ============================================
    exit /b 1
)

set "LATEX_SCRIPT=latex_to_equation.py"
if not exist "!LATEX_SCRIPT!" (
    if exist "..\latex_to_equation.py" (
        set "LATEX_SCRIPT=..\latex_to_equation.py"
    ) else (
        echo LOI: Khong tim thay latex_to_equation.py o ca thu muc hien tai va thu muc cha.
        exit /b 1
    )
)

echo [2/2] Dang thu chuyen tiep cac cong thuc pandoc bo sot ^(!LATEX_SCRIPT!^)...
"%PYEXE%" "!LATEX_SCRIPT!" "%TMPOUT%" "%OUTPUT%"
if errorlevel 1 (
    echo.
    echo ============================================
    echo  LOI khi chay latex_to_equation.py.
    echo  Kiem tra da cai lxml chua: pip install lxml --break-system-packages
    echo  File trung gian tu pandoc van con: %TMPOUT%
    echo ============================================
    exit /b 1
)

del "%TMPOUT%" >nul 2>nul

echo.
echo Hoan tat. Da tao file: %OUTPUT%
echo Neu co cong thuc khong chuyen duoc, xem file bao cao cung ten
echo   "%OUTPUT:~0,-5%_loi_kem_cau_van.txt" ^(neu co^) de Ctrl+F trong Word.
endlocal
