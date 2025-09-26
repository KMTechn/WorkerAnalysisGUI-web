# WorkerAnalysisGUI-web 기술 명세서

태그: #Python, #Flask, #JavaScript, #Web, #GUI, #DataAnalysis, #Dashboard

## 문서정보

| 항목 | 내용 |
|---|---|
| 한 줄 요약 (TL;DR) | 작업 로그 데이터를 실시간으로 분석하여 웹 기반 대시보드로 시각화하는 Flask 기반의 데이터 분석 및 모니터링 도구입니다. |
| 담당자/팀 (Owner) | [담당자 이름 또는 개발팀] |
| 버전 (Version) | 3.0.0-web |
| 저장소 (Repository) | [GitHub/GitLab 링크] |
| 상태 (Status) | 운영 중 |
| 최종 배포일 | YYYY-MM-DD |

## 1. 개요

### 목적 (Purpose)
Syncthing을 통해 실시간 동기화되는 CSV 형식의 작업 이벤트 로그를 지속적으로 모니터링하고, 데이터를 자동으로 분석하여 그 결과를 웹 기반 대시보드를 통해 사용자에게 직관적으로 제공합니다. 이를 통해 데이터 기반의 신속한 의사결정을 지원하고 생산성 및 공정 효율 개선에 기여하는 것을 목적으로 합니다.

### 주요 기능 (Key Features)
*   **실시간 데이터 분석 및 시각화**: `watchdog`을 이용해 로그 파일을 실시간으로 감지하고, `Flask-SocketIO`를 통해 분석 결과를 웹 대시보드에 즉시 업데이트합니다.
*   **대화형 웹 대시보드**: `Flask` 백엔드와 순수 `JavaScript` 프론트엔드로 구현된 동적 대시보드를 제공합니다. 사용자는 공정, 기간, 작업자별로 데이터를 필터링하고 다양한 관점(생산량, 작업자 성과, 오류 등)에서 분석 결과를 확인할 수 있습니다.
*   **다중 공정 분석**: 이적실, 검사실, 포장실 등 여러 공정을 선택하여 분석하거나, 전체 공정을 비교 분석할 수 있습니다.
*   **데이터 내보내기**: 분석된 상세 데이터를 Excel 또는 CSV 파일로 손쉽게 내보낼 수 있습니다.
*   **자동화된 배포**: GitHub Actions를 통해 `main` 브랜치에 푸시 시 서버에 자동으로 배포되는 CI/CD 파이프라인이 구축되어 있습니다. (`deploy.yml`)

## 2. 아키텍처 및 설계 (Architecture & Design)

### 시스템 아키텍처 다이어그램

```
+-------------------+      HTTP/Socket.IO      +-------------------------+
|  클라이언트       | <----------------------> |  Flask 웹 서버          |
|  (웹 브라우저)    |                          |  (app.py)               |
|                   |                          |                         |
|  - HTML/CSS/JS    |                          |  - API 라우팅 (JSON)    |
|  - Chart.js       |                          |  - SocketIO 이벤트 처리 |
|  - 데이터 시각화  |                          |  - 템플릿 렌더링        |
+-------------------+                          +-----------+-------------+
         ^                                                   |
         | 요청/응답                                         | 데이터 분석 요청
         |                                                   |
+--------+--------+                                          v
|  정적 파일/템플릿 |                                   +-------------------------+
|  (static/,       | <-------------------------------> |  데이터 분석 모듈       |
|   templates/)    |                                   |  (analyzer.py)          |
+-------------------+                                   |                         |
                                                        |  - CSV 데이터 파싱/처리 |
                                                        |  - Pandas/Numpy 분석    |
                                                        +-----------+-------------+
                                                                    |
                                                                    | 파일 읽기
                                                                    v
                                                            +-------------------+
                                                            |  Syncthing 백업   |
                                                            |  (/home/syncthing/|
                                                            |   backup/*.csv)   |
+-------------------+                                       +-------------------+
| Watchdog 감시자   | --------------------------------------> |                   |
| (백그라운드 스레드)|   파일 변경 이벤트 감지               | - 실시간 동기화   |
+-------------------+                                       | - 버전 관리       |
                                                            | - 아카이브 백업   |
                                                            +-------------------+
```

**주요 구성 요소 설명**:

1.  **클라이언트 (웹 브라우저)**: 사용자가 대시보드와 상호작용하는 인터페이스입니다. `templates/index.html` 구조 위에 `static/dashboard.js`가 동적으로 콘텐츠를 생성하고, `Chart.js`를 사용해 데이터를 시각화합니다.
2.  **웹 서버 (Flask `app.py`)**: Python Flask 프레임워크 기반의 백엔드 서버입니다. 클라이언트의 HTTP 요청에 대해 JSON 형식의 분석 데이터를 반환하는 API 엔드포인트를 제공하며, `Flask-SocketIO`를 통해 실시간 데이터 업데이트 이벤트를 클라이언트로 푸시합니다.
3.  **데이터 분석 모듈 (`analyzer.py`)**: 핵심 데이터 처리 및 분석 로직을 담당합니다. `pandas`와 `numpy`를 사용하여 지정된 폴더의 CSV 로그를 읽고, 세션 데이터로 가공한 뒤 각종 KPI와 성과 지표를 계산합니다.
4.  **파일 시스템 감시자 (`watchdog`)**: `app.py` 실행 시 별도의 스레드에서 실행되며, `C:\Sync` 폴더의 로그 파일 변경을 감지하여 `SocketIO`를 통해 클라이언트에 변경 사실을 알리는 역할을 합니다.

### 핵심 구성 요소 (Core Components)
*   **`app.py`**: Flask 웹 애플리케이션의 엔트리 포인트. API 라우팅, `analyzer.py` 호출, `watchdog` 스레드 실행, `SocketIO` 통신을 관리합니다.
*   **`analyzer.py`**: 데이터 분석 로직을 캡슐화한 클래스. CSV 파일 로딩, 데이터 정제, 세션화, KPI 계산 등 모든 분석 작업을 수행합니다.
*   **`static/dashboard.js`**: 프론트엔드의 모든 로직을 담당합니다. 백엔드 API를 호출하여 데이터를 받아오고, 받은 데이터를 기반으로 동적으로 HTML 콘텐츠(테이블, 차트, 카드 등)를 생성하여 화면에 렌더링합니다.
*   **`templates/index.html`**: 웹 페이지의 기본 골격을 정의하는 단일 HTML 파일입니다. `dashboard.js`가 이 위에서 동작합니다.
*   **`.github/workflows/`**: CI/CD 파이프라인 정의 파일이 위치합니다.
    *   `deploy.yml`: `main` 브랜치 푸시 시, `deploy.sh` 스크립트를 원격 서버에서 실행하여 자동으로 배포합니다.
    *   `release.yml`: `v*` 형태의 태그 푸시 시, `WorkerAnalysisGUI.py`(데스크톱 버전)를 PyInstaller로 빌드하고 GitHub Release를 생성합니다. (웹 버전과는 직접적인 관련이 적음)

### 데이터 흐름 (Data Flow)
1.  **초기 로드**: 사용자가 웹 브라우저로 접속하면 `app.py`는 `index.html`을 렌더링합니다. `dashboard.js`는 `/api/data`에 분석 요청을 보내 초기 데이터를 받아와 전체 대시보드를 그립니다.
2.  **필터 변경**: 사용자가 사이드바에서 필터(기간, 작업자 등)를 변경하고 '분석 실행'을 클릭하면, `dashboard.js`는 새로운 필터 조건으로 `/api/data`를 다시 호출하여 해당 조건의 데이터로 대시보드를 새로고침합니다.
3.  **실시간 업데이트**: 로컬의 `watchdog` 스레드가 `C:\Sync` 폴더의 파일 변경을 감지하면, `app.py`의 `SocketIO` 서버를 통해 'data_updated' 이벤트를 모든 클라이언트에 전송합니다. `dashboard.js`는 이 이벤트를 수신하고, '실시간 현황' 탭이 활성화되어 있을 경우 실시간 데이터를 다시 요청하여 해당 탭만 업데이트합니다.

### 주요 의존성 (Dependencies)
*   **라이브러리**: `requirements.txt` 참조
    *   `Flask`, `Flask-SocketIO`, `eventlet`: 웹 서버 및 실시간 통신
    *   `pandas`, `numpy`: 데이터 분석 및 처리
    *   `watchdog`: 파일 시스템 이벤트 모니터링
*   **데이터베이스**: 별도의 데이터베이스를 사용하지 않으며, 모든 데이터는 파일 시스템 기반으로 처리됩니다.

## 3. 설치 및 실행 방법 (Setup & Run)

### 3.1. 사전 요구사항 (Prerequisites)
*   Language: Python 3.9 이상
*   Tools: Git

### 3.2. 설치 및 환경 설정 (Installation & Configuration)
```bash
# 1. 저장소 복제
git clone [repository_url]
cd WorkerAnalysisGUI-web

# 2. Python 가상 환경 생성 및 활성화 (권장)
python -m venv venv
# Windows
.\venv\Scripts\activate
# macOS/Linux
source venv/bin/activate

# 3. 의존성 설치
pip install -r requirements.txt
```

### 3.3. 로컬 환경에서 실행 (Running Locally)
```bash
# 1. 웹 서버 실행 (use_reloader=False 옵션으로 실행 권장)
python app.py

# 2. 웹 브라우저에서 아래 주소로 접속
# http://127.0.0.1:8089
```
**참고**: 로그 파일은 Syncthing을 통해 `/home/syncthing/backup/` 폴더로 실시간 동기화됩니다. 이 경로는 `config/analyzer_settings.json`에서 설정할 수 있습니다.

## 4. 데이터 동기화 및 백업 시스템 (Data Sync & Backup)

### 4.1. Syncthing 구성

#### 연결된 디바이스 (8대)
- **작업 PC들** (7대):
  - 박관호, 박관호 데스크톱
  - 이적1_컴퓨터, 이적2_컴퓨터, 이적3_컴퓨터
  - 검사1_컴퓨터, 포장_컴퓨터
- **서버** (1대): 중앙 백업 및 데이터 분석

#### 백업 정책
- **PC별 보관**: 30일 후 로컬 자동 삭제 (용량 절약)
- **서버 보관**: 영구 보관 (모든 데이터 안전)
- **분기별 백업**: 자동 압축 아카이브

### 4.2. 데이터 구조

#### 현재 백업 디렉토리 구조
```
/home/syncthing/backup/
├── *작업이벤트로그*.csv           # 최신 파일들 (실시간 동기화)
├── 2025-08-27/                    # 날짜별 아카이브
│   ├── 이적작업이벤트로그_권홍규_20250827.csv
│   ├── 포장실작업이벤트로그_박관호_20250827.csv
│   └── ...
├── 2025-08-28/
├── 2025-09-XX/                    # 자동 날짜별 백업
└── quarterly_backup/              # 분기별 압축 백업
    ├── Q1-2025/
    ├── Q2-2025/
    └── Q1-2025_backup.tar.gz     # 압축된 분기 백업
```

#### 데이터 분석 로직 개선
- **실시간 분석**: 메인 폴더 + 날짜별 아카이브에서 검색
- **전체 분석**: 177개 파일 인식 (메인: 108 + 아카이브: 69)
- **분기별 데이터**: quarterly_backup 폴더 자동 포함
- **호환성 유지**: 기존 log 폴더 구조도 지원

### 4.3. 자동화 스크립트

#### 분기별 백업 관리
- **위치**: `/home/syncthing/quarterly_backup_setup.sh`
- **실행**: 매월 1일 새벽 2시 (crontab)
- **기능**:
  - 월별 CSV 파일 자동 아카이브
  - 분기말 자동 압축 (tar.gz)
  - 디스크 사용량 모니터링

## 5. API 명세 (API Specification)

이 애플리케이션은 내부적으로 사용하는 RESTful API를 가지고 있습니다. 모든 응답은 JSON 형식입니다.

*   `GET /`: 메인 `index.html` 페이지를 렌더링합니다.
*   `POST /api/data`: 필터 조건을 받아 전체 데이터 분석을 수행하고 결과를 반환합니다.
*   `GET /api/realtime`: 오늘 날짜 기준의 실시간 현황 데이터를 반환합니다.
*   `POST /api/trace`: 이력 추적을 위한 검색 조건(WID, 바코드 등)을 받아 추적 결과를 반환합니다.
*   `POST /api/session_barcodes`: 특정 작업 세션의 상세 바코드 목록을 조회합니다.
*   `POST /api/export_excel`: 세션 데이터를 받아 Excel 파일로 변환하여 반환합니다.
*   `POST /api/export_error_log`: 오류 로그 데이터를 받아 CSV 파일로 변환하여 반환합니다.

## 6. 배포 가이드 (Deployment)

### 6.1. 서버 환경 구성

#### 시스템 서비스
- **서비스 이름**: `worker-analysis.service`
- **서비스 파일**: `/etc/systemd/system/worker-analysis.service`
- **실행 포트**: 8089
- **접속 URL**: http://worker.kmtecherp.com

#### 서비스 관리 명령어
```bash
# 서비스 시작/중지/재시작
sudo systemctl start worker-analysis
sudo systemctl stop worker-analysis
sudo systemctl restart worker-analysis

# 서비스 상태 확인
sudo systemctl status worker-analysis

# 로그 확인
journalctl -u worker-analysis -f
```

### 6.2. Nginx 설정

#### 리버스 프록시 설정
- **설정 파일**: `/etc/nginx/sites-available/worker-analysis.conf`
- **도메인**: worker.kmtecherp.com → localhost:8089
- **SSL**: 추후 Let's Encrypt 설정 가능

### 6.3. Syncthing 설정

#### 서버측 설정 (영구 보관)
```bash
# Syncthing 웹 UI 접속
http://localhost:8384 (사용자: kmtech)

# 설정 위치
/home/syncthing/.local/state/syncthing/config.xml

# 백업 정책: cleanoutDays = 0 (영구 보관)
```

#### 각 PC 설정 (30일 보관)
```bash
# 각 PC에서 웹 UI 접속
http://localhost:8384

# 폴더 설정
1. 폴더 → Server → 편집
2. 파일 버전 관리 → Trash Can File Versioning
3. Clean out after: 30 (일)
4. 저장
```

### 6.4. CI/CD 파이프라인
*   `.github/workflows/deploy.yml`에 GitHub Actions를 이용한 자동 배포 워크플로우가 정의되어 있습니다.
*   `main` 브랜치에 코드가 푸시되면, 지정된 원격 서버에 SSH로 접속하여 `deploy.sh` 스크립트를 실행합니다.
*   `deploy.sh`는 `git pull`, `pip install`, 그리고 서비스 재시작을 수행합니다.

### 6.5. 모니터링 및 유지보수

#### 디스크 사용량 체크
```bash
# 백업 디렉토리 크기 확인
du -sh /home/syncthing/backup/

# 분기별 백업 상태 확인
ls -la /home/syncthing/quarterly_backup/

# 자동 백업 스크립트 상태
crontab -l
```

#### 데이터 분석 현황
- **총 로그 파일**: 177개
- **데이터 행수**: 5,275행
- **실시간 업데이트**: Syncthing을 통한 자동 동기화

## 7. 트러블슈팅 / FAQ (Troubleshooting)

### 7.1. 일반적인 문제

*   **Q**: `ModuleNotFoundError`가 발생합니다.
    *   **A**: 가상 환경이 활성화된 상태에서 `pip install -r requirements.txt` 명령어를 실행하여 모든 의존성이 올바르게 설치되었는지 확인하십시오.

*   **Q**: 데이터가 업데이트되지 않거나 분석이 되지 않습니다.
    *   **A**: 다음 사항들을 확인하십시오:
        - Syncthing 서비스가 정상 실행 중인지 (`systemctl status syncthing@syncthing`)
        - 백업 폴더에 CSV 파일이 있는지 (`ls /home/syncthing/backup/*.csv`)
        - 파일 이름이 `*작업이벤트로그*.csv` 패턴과 일치하는지
        - 서비스 로그에 오류가 없는지 (`journalctl -u worker-analysis -f`)

### 7.2. Syncthing 관련 문제

*   **Q**: PC에서 Syncthing 동기화가 되지 않습니다.
    *   **A**: 다음 순서로 확인하십시오:
        1. 네트워크 연결 상태 확인
        2. Syncthing 웹 UI에서 디바이스 연결 상태 확인 (`http://localhost:8384`)
        3. 방화벽에서 포트 22000번 허용 확인
        4. 디바이스 ID가 서버에 등록되어 있는지 확인

*   **Q**: 백업 용량이 계속 증가합니다.
    *   **A**: PC별 버전 관리 설정을 확인하십시오:
        - 각 PC에서 30일 보관 설정이 적용되었는지
        - 서버의 분기별 백업 스크립트가 정상 작동하는지 (`crontab -l`)

### 7.3. 성능 관련 문제

*   **Q**: 웹 대시보드 로딩이 느립니다.
    *   **A**: 다음 사항들을 확인하십시오:
        - 분석할 데이터 범위를 줄여보십시오 (특정 기간 또는 프로세스만 선택)
        - 서버 리소스 사용량 확인 (`htop`, `df -h`)
        - 백업 폴더의 파일 수가 과도하게 많지 않은지 확인

### 7.4. 서비스 관리

*   **Q**: 서비스가 자동으로 재시작되지 않습니다.
    *   **A**: systemd 서비스 설정을 확인하십시오:
        ```bash
        sudo systemctl enable worker-analysis
        sudo systemctl daemon-reload
        ```

*   **Q**: 데이터 분석 결과가 이상합니다.
    *   **A**: 다음을 확인하십시오:
        - CSV 파일의 인코딩이 올바른지 (UTF-8, CP949 지원)
        - 파일 내용이 손상되지 않았는지
        - 분석 로직이 새로운 데이터 구조에 맞게 업데이트되었는지

## 8. 업데이트 히스토리 (Update History)

### v3.2.0 (2025-09-26) - 대시보드 전면 개선
#### 🔄 기간별 분석 기능 (Period-Aware Analytics)
- ✅ **동적 탭 제목**: 선택된 기간에 따라 탭 제목이 자동으로 변경 (실시간/일간/주간/월간/분기)
- ✅ **스마트 차트 그룹화**: 기간별로 적합한 데이터 집계 (시간별 → 일별 → 주별 자동 전환)
- ✅ **생산량 분석 탭 개선**: 기간별 차트 타입 최적화 (라인/바 차트 자동 선택)
- ✅ **전체 탭 일관성**: 모든 탭에서 기간 인식 기능 통합

#### 🎨 사용자 경험 개선 (UX/UI Enhancements)
- ✅ **향상된 차트 스타일링**: 기본 차트 옵션, 애니메이션, 툴팁 개선
- ✅ **개선된 KPI 카드**: 호버 효과 및 시각적 개선
- ✅ **차트 컨테이너 스타일링**: 통일된 디자인과 패딩 적용
- ✅ **반응형 차트 옵션**: 모든 차트에 일관된 스타일 가이드 적용

#### 🔧 기술적 개선 (Technical Improvements)
- ✅ **고급 차트 설정**: 깊은 객체 병합 유틸리티로 차트 옵션 관리 개선
- ✅ **기간 감지 로직**: 강화된 기간 분류 및 적절한 차트 타입 자동 선택
- ✅ **KPI 계산 개선**: 기간별 메트릭 계산 및 집계 로직 향상
- ✅ **차트 생명주기 관리**: 개선된 차트 생성/파괴 메커니즘

#### 📊 데이터 시각화 향상 (Data Visualization)
- ✅ **컨텍스트 인식 차트**: 실시간(시간별) → 주간(일별) → 월간(주별) 자동 그룹화
- ✅ **동적 차트 라벨**: 선택된 기간에 맞는 축 라벨 및 범례 자동 생성
- ✅ **개선된 내보내기**: 파일명에 기간 라벨 포함 (예: "월간_error_log_2025-09-26.csv")

### v3.1.0 (2025-09-25)
- ✅ Syncthing 백업 구조 지원 추가
- ✅ 날짜별 아카이브 폴더 자동 인식 (2025-XX-XX)
- ✅ 분기별 백업 시스템 구축
- ✅ 실시간 데이터 로딩 개선 (아카이브 포함)
- ✅ 177개 로그 파일 완전 인식 (기존 대비 69개 추가)
- ✅ 기존 log 폴더 구조와의 호환성 유지