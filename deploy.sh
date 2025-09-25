#!/bin/bash
# 자동 배포 스크립트: GitHub Actions에서 실행되어 서버를 업데이트합니다.

# 스크립트 실행 중 오류가 발생하면 즉시 중단
set -e

echo "=== WorkerAnalysisGUI-web 자동 배포 시작 ==="
echo "시간: $(date)"

# 1. 프로젝트 디렉토리로 이동
echo "프로젝트 디렉토리로 이동 중..."
cd /root/WorkerAnalysisGUI-web

# 2. Git 저장소에서 최신 코드 가져오기
echo "Git 저장소에서 최신 코드를 가져오는 중..."
git pull origin main

# 3. Python 가상 환경에서 의존성 업데이트
echo "가상 환경에서 의존성을 업데이트하는 중..."
source venv/bin/activate
pip install -r requirements.txt

# 4. systemd 서비스 재시작
echo "worker-analysis 서비스를 재시작하는 중..."
sudo systemctl restart worker-analysis

# 5. 서비스 상태 확인
echo "서비스 상태 확인 중..."
sleep 3
if systemctl is-active --quiet worker-analysis; then
    echo "✅ worker-analysis 서비스가 성공적으로 재시작되었습니다."
else
    echo "❌ worker-analysis 서비스 재시작에 실패했습니다."
    systemctl status worker-analysis
    exit 1
fi

# 6. 로그 확인
echo "최근 로그 확인..."
journalctl -u worker-analysis -n 5 --no-pager

echo "=== 자동 배포 완료 ==="
echo "시간: $(date)"