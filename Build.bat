@echo off
chcp 65001 >nul
echo ==================================================
echo [빌드 시작] PDF Comparison Tool을 빌드합니다.
echo ==================================================

:: 1. 기존 빌드 폴더 삭제 (이전 기록 제거)
if exist build rd /s /q build
if exist dist rd /s /q dist

:: 2. 빌드 실행
:: --noconsole: 실행 시 검은 창이 안 뜨게 함
:: --onefile: 하나의 exe 파일로 묶음
:: --icon: 실행 파일 아이콘 지정
:: --add-data: 아이콘 파일을 실행 파일 내부에 포함(경로 설정 시 필수)
pyinstaller --noconsole --onefile --icon="PDF_Compare_Icon.ico" --add-data "PDF_Compare_Icon.ico;." "PDF_Compare.py"

:: 3. 빌드 후 작업 (불필요한 .spec 파일 제거)
if exist PDF_Compare.spec del PDF_Compare.spec

echo ==================================================
echo [빌드 완료] dist 폴더에 exe 파일이 생성되었습니다.
echo ==================================================
pause