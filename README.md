# WorkerAnalysisGUI-web

WorkerAnalysisGUI-web은 작업 현장의 이벤트 로그를 분석하여 작업자의 성과를 시각화하고 추적하는 웹 기반 대시보드 애플리케이션입니다. 기존 Tkinter 기반의 데스크톱 애플리케이션을 Flask와 WebSocket 기술을 사용하여 실시간 기능을 갖춘 현대적인 웹 애플리케이션으로 재구축했습니다.

## 주요 기능

- **실시간 현황 대시보드:** `watchdog`과 `Socket.IO`를 통해 로그 파일의 변경을 실시간으로 감지하고, 현재 작업 상황을 웹 UI에 즉시 업데이트합니다.
- **다차원 성과 분석:** 생산량, 작업 시간, 초도 수율(FPY) 등 다양한 KPI를 기반으로 작업자 및 공정의 성과를 분석합니다.
- **동적 데이터 시각화:** `Chart.js`를 사용하여 생산량 추이, 작업자별 성과 레이더 차트 등 인터랙티브한 차트를 제공합니다.
- **상세 분석 및 필터링:** 특정 기간, 공정, 작업자별로 데이터를 필터링하여 상세한 분석을 수행할 수 있습니다.
- **생산 이력 추적:** 작업지시 ID(WID), 완제품 배치(FPB), 개별 제품 바코드 등 다양한 조건으로 생산 이력을 추적합니다.
- **공정 비교 분석:** 검사, 이적, 포장 등 여러 공정의 성과를 나란히 비교하여 병목 현상이나 개선점을 파악합니다.
- **자동 배포 (CI/CD):** GitHub Actions를 통해 `main` 브랜치에 코드가 푸시될 때마다 운영 서버에 자동으로 최신 버전이 배포됩니다.

## 기술 스택

- **백엔드:**
  - Python
  - Flask (웹 프레임워크)
  - Flask-SocketIO (실시간 웹 통신)
  - Pandas, NumPy (데이터 분석)
  - Watchdog (파일 시스템 모니터링)
  - Eventlet (비동기 네트워킹)
- **프론트엔드:**
  - HTML5, CSS3, JavaScript (ES6+)
  - Chart.js (데이터 시각화)
  - Socket.IO Client
- **배포:**
  - GitHub Actions (CI/CD)

## 설치 및 실행 방법

### 1. 저장소 복제

```bash
git clone https://github.com/KMTechn/WorkerAnalysisGUI-web.git
cd WorkerAnalysisGUI-web
```

### 2. 의존성 설치

프로젝트에 필요한 Python 라이브러리를 설치합니다. (가상 환경 사용을 권장합니다.)

```bash
pip install -r requirements.txt
```

### 3. 로그 폴더 확인

애플리케이션은 `C:\Sync` 폴더에서 로그 파일을 읽도록 기본 설정되어 있습니다. 이 경로는 `app.py` 파일 상단의 `LOG_FOLDER_PATH` 변수에서 변경할 수 있습니다.

### 4. 로컬 개발 서버 실행

다음 명령어를 실행하여 Flask 개발 서버를 시작합니다.

```bash
python app.py
```

서버가 시작되면 웹 브라우저를 열고 `http://127.0.0.1:8088` 주소로 접속하여 대시보드를 확인할 수 있습니다.

## 자동 배포 (CI/CD)

이 프로젝트는 GitHub Actions를 사용하여 `main` 브랜치에 변경 사항이 푸시될 때마다 자동으로 서버에 배포되도록 설정되어 있습니다.

배포 과정은 `.github/workflows/deploy.yml` 파일에 정의되어 있으며, 서버에서는 `deploy.sh` 스크립트를 실행하여 코드 업데이트, 라이브러리 설치, 서버 재시작을 수행합니다.

자동 배포를 활성화하려면 GitHub 저장소의 **Settings > Secrets and variables > Actions** 메뉴에서 다음 Repository secrets를 설정해야 합니다.

- `SERVER_HOST`: 서버의 IP 주소 또는 도메인
- `SERVER_USERNAME`: SSH 접속 사용자 이름
- `SSH_PRIVATE_KEY`: 서버 접속용 SSH 비공개 키
