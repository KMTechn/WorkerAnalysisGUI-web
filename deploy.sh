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

# 5. 웹 서버 재시작 (더 안정적인 방식으로 변경)
PID_FILE="app.pid"

if [ -f "$PID_FILE" ]; then
    PID=$(cat "$PID_FILE")
    echo "기존 서버 프로세스(PID: $PID)를 종료합니다."
    # kill 명령어에 -9 옵션을 사용하여 프로세스를 확실히 종료
    kill -9 $PID || true
    rm -f "$PID_FILE"
fi

echo "��로운 웹 서버를 시작합니다."
# nohup을 사용하여 백그라운드에서 실행하고, 프로세스 ID를 파일에 저장
nohup python app.py > server.log 2>&1 & echo $! > $PID_FILE

echo "배포가 성공적으로 완료되었습니다. (PID: $(cat $PID_FILE))"