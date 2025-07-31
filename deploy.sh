#!/bin/bash
# 배포 스크립트: 코드 업데이트, 의존성 설치, 서버 재시작을 담당합니다.

# 스크립트 실행 중 오류가 발생하면 즉시 중단
set -e

# 1. 프로젝트 디렉토리로 이동 (실제 서버 경로에 맞게 수정 필요)
# 예: cd /home/ubuntu/WorkerAnalysisGUI-web
echo "프로젝트 디렉토리로 이동 중..."
cd $(dirname "$0")

# 2. Git 저장소에서 최신 코드 가져오기
echo "Git 저장소에서 최신 코드를 가져오는 중..."
git pull origin main

# 3. Python 가상 환경 활성화 (가상 환경을 사용하는 경우)
# 예: source venv/bin/activate
# echo "가상 환경 활성화 중..."

# 4. 필요한 Python 라이브러리 설치
echo "필요한 라이브러리를 설치하는 중..."
pip install -r requirements.txt

# 5. 웹 서버 재시작
# Gunicorn이나 다른 WSGI 서버를 사용하는 경우 해당 프로세스를 재시작합니다.
# 여기서는 간단하게 pkill로 기존 python 프로세스를 종료하고 백그라운드에서 새로 시작합니다.
echo "웹 서버를 재시작하는 중..."
pkill -f "python app.py" || true
nohup python app.py > server.log 2>&1 &

echo "배포가 성공적으로 완료되었습니다."
