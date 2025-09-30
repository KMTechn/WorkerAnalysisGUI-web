# Label_Match 바코드 검증 시스템 분석 보고서

## 개요
Label_Match는 5단계 순차 바코드 스캔을 통한 제품 검증 시스템입니다. 현재 독립적으로 운영되고 있으며, WorkerAnalysisGUI-web 시스템과의 통합 연동 방안을 제시합니다.

---

## 1. 시스템 아키텍처

### 1.1 핵심 구성 요소
- **메인 애플리케이션**: `Label_Match.py` (~2000+ 라인)
- **GUI 프레임워크**: Python Tkinter 기반
- **설정 관리**: JSON 형식 구성 파일
- **자동 업데이트**: GitHub 릴리스 연동

### 1.2 클래스 구조
```python
Label_Match (tk.Tk)
├── DataManager          # 로깅 및 상태 저장
├── CalendarWindow       # 날짜 선택 다이얼로그
└── ConfigManager        # 설정 파일 관리
```

---

## 2. 바코드 검증 프로세스

### 2.1 5단계 스캔 프로세스
1. **1단계**: 마스터 바코드 스캔 (규칙 결정)
2. **2단계**: 첫 번째 제품 바코드
3. **3단계**: 두 번째 제품 바코드
4. **4단계**: 세 번째 제품 바코드
5. **5단계**: 네 번째 제품 바코드

### 2.2 검증 규칙 시스템
- **설정 파일**: `validation_rules.csv`
- **규칙 구조**: RuleName별 5개 ScanPosition 정의
- **동적 적용**: 첫 번째 스캔 길이로 규칙 자동 선택

#### validation_rules.csv 구조
| 컬럼 | 설명 |
|------|------|
| RuleName | 규칙 그룹 이름 |
| ScanPosition | 스캔 순서 (1-5) |
| MinLength | 최소 바코드 길이 |
| MaxLength | 최대 바코드 길이 |
| SliceStart | 추출 시작 위치 |
| SliceEnd | 추출 끝 위치 |
| Description | 규칙 설명 |

---

## 3. 데이터 저장 및 로깅

### 3.1 데이터 형식
- **로그 저장**: 일별 JSON 파일
- **현재 상태**: 실시간 세션 상태 JSON
- **설정 저장**: `config/app_settings.json`

### 3.2 로그 데이터 구조 예시
```json
{
  "timestamp": "2025-09-30T14:30:00.123456",
  "event_type": "SCAN_COMPLETE",
  "worker": "TEST_USER",
  "rule_name": "STANDARD_A",
  "scan_position": 1,
  "input_barcode": "ABC123456789",
  "extracted_code": "ABC123456789",
  "result": "PASS|FAIL",
  "details": {
    "scan_duration_ms": 150,
    "validation_passed": true
  }
}
```

---

## 4. 오디오 피드백 시스템

### 4.1 음성 파일 구성
- **단계별 안내**: `one.wav`, `two.wav`, `three.wav`, `four.wav`
- **결과 안내**: `pass.wav` (성공), `fail.wav` (실패)
- **오디오 엔진**: pygame 라이브러리 사용

### 4.2 피드백 로직
```python
# 스캔 단계별 음성 재생
def play_scan_step_sound(step_number):
    sound_file = f"{step_number}.wav"
    pygame.mixer.Sound(sound_file).play()

# 결과 음성 재생
def play_result_sound(is_success):
    sound_file = "pass.wav" if is_success else "fail.wav"
    pygame.mixer.Sound(sound_file).play()
```

---

## 5. 자동 업데이트 시스템

### 5.1 GitHub 연동
- **리포지토리**: `KMTechn/Label_Match`
- **현재 버전**: `v2.0.4`
- **업데이트 방식**: ZIP 다운로드 및 배치 스크립트 적용

### 5.2 업데이트 프로세스
1. GitHub API를 통한 최신 릴리스 확인
2. 새 버전 감지 시 ZIP 파일 다운로드
3. 임시 폴더에 압축 해제
4. 배치 스크립트 생성 및 실행
5. 프로그램 종료 후 파일 교체
6. 자동 재시작

---

## 6. WorkerAnalysisGUI-web 통합 방안

### 6.1 현재 상태
- ❌ **연동 없음**: 독립적인 데이터 저장 구조
- ❌ **형식 불일치**: JSON vs CSV 형식 차이
- ❌ **경로 분리**: C:\Sync 경로 미사용

### 6.2 통합 연동 옵션

#### 옵션 1: 데이터 변환 어댑터
```python
class LabelMatchDataAdapter:
    def convert_json_to_csv(self, json_log_path):
        """JSON 로그를 CSV 형식으로 변환"""
        # JSON 로그 읽기
        # CSV 형식으로 변환
        # C:\Sync 경로에 저장
        pass

    def generate_daily_report(self, date):
        """일별 바코드 검증 리포트 생성"""
        pass
```

#### 옵션 2: JSON 파서 모듈 추가
```python
# analyzer_optimized.py에 추가
class LabelMatchAnalyzer:
    def load_label_match_logs(self, date_range):
        """Label_Match JSON 로그 로딩"""
        pass

    def calculate_verification_metrics(self):
        """바코드 검증 메트릭 계산"""
        metrics = {
            'total_scans': 0,
            'success_rate': 0.0,
            'average_scan_time': 0.0,
            'rule_usage_stats': {}
        }
        return metrics
```

#### 옵션 3: 실시간 로그 전송
```python
# Label_Match.py에 추가
class RealTimeLogger:
    def send_to_sync_folder(self, log_data):
        """실시간으로 C:\Sync에 로그 전송"""
        csv_format = self.convert_to_csv_format(log_data)
        sync_path = "C:\Sync\바코드검증이벤트로그_*.csv"
        self.append_to_csv(sync_path, csv_format)
```

---

## 7. 통합 후 기대 효과

### 7.1 통합 분석 메트릭
- **바코드 검증률**: 전체 대비 성공/실패 비율
- **스캔 효율성**: 단계별 스캔 소요 시간
- **규칙 사용 패턴**: 제품별 검증 규칙 분포
- **오류 패턴 분석**: 실패 원인 및 빈도 분석

### 7.2 대시보드 확장
```javascript
// 레이더 차트에 바코드 검증 메트릭 추가
"바코드검증": {
  "검증정확도": "verification_accuracy",
  "스캔속도": "average_scan_time",
  "규칙준수율": "rule_compliance_rate",
  "오류발생률": "error_rate"
}
```

### 7.3 종합 분석 보고서
- 제조 공정별 품질 지표 통합
- 바코드 검증 → 품질 검사 → 이적 검사 연관성 분석
- 작업자별 종합 성과 평가

---

## 8. 구현 우선순위

### 8.1 1단계: 데이터 변환 어댑터 (즉시 적용 가능)
- JSON 로그를 CSV 형식으로 변환하는 배치 스크립트
- 기존 WorkerAnalysisGUI-web 구조 최소 변경
- 빠른 프로토타입 구현 가능

### 8.2 2단계: JSON 파서 모듈 추가 (중기)
- analyzer_optimized.py에 JSON 처리 로직 추가
- 바코드 검증 전용 분석 함수 개발
- 대시보드 UI 확장

### 8.3 3단계: 실시간 통합 (장기)
- Label_Match에서 실시간 로그 전송 기능 추가
- 통합 대시보드 완전 구현
- 성능 최적화 및 안정성 확보

---

## 9. 기술적 고려사항

### 9.1 성능 최적화
- JSON 파싱 성능 최적화
- 대용량 바코드 로그 처리 방안
- 메모리 효율적 데이터 구조

### 9.2 호환성 유지
- 기존 Label_Match 기능 유지
- WorkerAnalysisGUI-web 기존 구조 보존
- 점진적 통합 방식 적용

### 9.3 오류 처리
- JSON 파싱 오류 처리
- 데이터 형식 불일치 감지
- 로그 파일 손상 복구 방안

---

## 10. 결론

Label_Match 시스템은 독립적으로 잘 구축된 바코드 검증 시스템입니다. WorkerAnalysisGUI-web와의 통합을 통해 제조 공정 전반의 품질 관리를 더욱 포괄적으로 분석할 수 있습니다.

### 권장 사항
1. **단계적 통합**: 데이터 변환 어댑터부터 시작
2. **기능 확장**: 바코드 검증 메트릭을 종합 분석에 포함
3. **사용자 경험**: 통합 대시보드로 일관된 사용자 인터페이스 제공

통합 완료 시 제조 현장의 바코드 검증부터 최종 품질 검사까지 전 과정을 통합 모니터링할 수 있는 강력한 분석 플랫폼이 구축될 것입니다.

---

**문서 작성일**: 2025-09-30
**시스템 버전**: Label_Match v2.0.4
**통합 대상**: WorkerAnalysisGUI-web v2.0