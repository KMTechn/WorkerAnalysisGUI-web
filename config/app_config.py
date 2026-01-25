# -*- coding: utf-8 -*-
"""
app_config.py - 애플리케이션 설정 모듈
하드코딩된 상수들을 중앙 집중 관리
"""

import os
import json
from dataclasses import dataclass, field
from typing import List, Dict, Optional

# 설정 파일 경로
CONFIG_FILE_PATH = '/root/WorkerAnalysisGUI-web/config/app_settings.json'


@dataclass
class AnalysisConfig:
    """분석 관련 설정"""
    # 기간 설정
    LOOKBACK_DAYS: int = 30  # 평균 계산에 사용할 과거 일수
    EXTENDED_LOOKBACK_DAYS: int = 60  # 확장 기간 (30일 평균 계산용)
    MAX_TRACE_DAYS: int = 365  # 이력 추적 최대 일수

    # 작업 시간 설정 (초)
    MINIMUM_REALISTIC_WORK_TIME: float = 180.0  # 최소 유효 작업 시간
    DYNAMIC_THRESHOLD_PERCENTAGE: float = 0.6  # 동적 임계값 비율

    # 근무 시간 설정
    WORK_HOUR_START: int = 6  # 근무 시작 시간
    WORK_HOUR_END: int = 22  # 근무 종료 시간

    # 포장실 추정값
    PACKAGING_PCS_PER_TRAY: int = 60  # 포장실 트레이당 PCS 추정치


@dataclass
class PerformanceConfig:
    """성능 관련 설정"""
    # 캐싱
    CACHE_EXPIRY_MINUTES: int = 30

    # 쿼리 제한
    MAX_RECORDS_PER_QUERY: int = 100000
    MAX_TRACE_RESULTS: int = 10000
    DEFAULT_TRACE_RESULTS: int = 1000

    # GZIP 압축
    GZIP_COMPRESSION_LEVEL: int = 6


@dataclass
class SecurityConfig:
    """보안 관련 설정"""
    SESSION_TIMEOUT_DAYS: int = 7
    MAX_LOGIN_ATTEMPTS: int = 5
    RATE_LIMIT_WINDOW: int = 60  # 초

    # Rate Limit 설정 (요청/분)
    RATE_LIMITS: Dict[str, int] = field(default_factory=lambda: {
        'api_data': 30,
        'api_trace': 20,
        'api_search': 60,
        'default': 120
    })


@dataclass
class WorkerConfig:
    """작업자 관련 설정"""
    # 테스트 작업자 목록 (제외 대상)
    TEST_WORKERS: List[str] = field(default_factory=lambda: [
        '3', 'TEST', '1234', '2', 'TESTER'
    ])

    # 작업자명 자동 수정 매핑
    WORKER_CORRECTIONS: Dict[str, str] = field(default_factory=lambda: {
        'dlehddn': '이동우',  # 한영키 잘못 입력
        '잊동우': '이동우',   # 오타
        '정진': '정정진',     # 성 누락
        '정갑진': '갑진',     # 통합
    })


@dataclass
class DisplayConfig:
    """화면 표시 관련 설정"""
    # 유효한 공정 모드
    VALID_PROCESSES: List[str] = field(default_factory=lambda: [
        '이적실', '검사실', '포장실', '전체 비교'
    ])

    # 레이더 차트 메트릭 설정
    RADAR_METRICS: Dict[str, Dict] = field(default_factory=lambda: {
        "포장실": {
            '세트완료시간': ('avg_work_time', False, 1.0),
            '첫스캔준비성': ('avg_latency', False, 1.0),
            '무결점달성률': ('first_pass_yield', True, 0.7),
            '세트당PCS': ('avg_pcs_per_tray', True, 1.0)
        },
        "이적실": {
            '신속성': ('avg_work_time', False, 1.0),
            '준속성': ('avg_latency', False, 1.0),
            '초도수율': ('first_pass_yield', True, 0.7),
            '안정성': ('work_time_std', False, 1.0)
        },
        "검사실": {
            '신속성': ('avg_work_time', False, 1.0),
            '준비성': ('avg_latency', False, 0.8),
            '무결점달성률': ('first_pass_yield', True, 1.2),
            '안정성': ('work_time_std', False, 0.7),
            '품질 정확도': ('defect_rate', False, 1.5)
        }
    })


class AppConfig:
    """통합 애플리케이션 설정"""

    def __init__(self):
        self.analysis = AnalysisConfig()
        self.performance = PerformanceConfig()
        self.security = SecurityConfig()
        self.worker = WorkerConfig()
        self.display = DisplayConfig()

        # 설정 파일에서 오버라이드 로드
        self._load_overrides()

    def _load_overrides(self):
        """설정 파일에서 오버라이드 값 로드"""
        if not os.path.exists(CONFIG_FILE_PATH):
            return

        try:
            with open(CONFIG_FILE_PATH, 'r', encoding='utf-8') as f:
                overrides = json.load(f)

            # 분석 설정 오버라이드
            if 'analysis' in overrides:
                for key, value in overrides['analysis'].items():
                    if hasattr(self.analysis, key):
                        setattr(self.analysis, key, value)

            # 성능 설정 오버라이드
            if 'performance' in overrides:
                for key, value in overrides['performance'].items():
                    if hasattr(self.performance, key):
                        setattr(self.performance, key, value)

            # 보안 설정 오버라이드
            if 'security' in overrides:
                for key, value in overrides['security'].items():
                    if hasattr(self.security, key):
                        setattr(self.security, key, value)

            # 작업자 설정 오버라이드
            if 'worker' in overrides:
                if 'TEST_WORKERS' in overrides['worker']:
                    self.worker.TEST_WORKERS = overrides['worker']['TEST_WORKERS']
                if 'WORKER_CORRECTIONS' in overrides['worker']:
                    self.worker.WORKER_CORRECTIONS.update(overrides['worker']['WORKER_CORRECTIONS'])

            print("[Config] 설정 파일 로드 완료")

        except (json.JSONDecodeError, IOError) as e:
            print(f"[Config] 설정 파일 로드 오류: {e}")

    def save_to_file(self):
        """현재 설정을 파일로 저장"""
        config_dict = {
            'analysis': {
                'LOOKBACK_DAYS': self.analysis.LOOKBACK_DAYS,
                'EXTENDED_LOOKBACK_DAYS': self.analysis.EXTENDED_LOOKBACK_DAYS,
                'MINIMUM_REALISTIC_WORK_TIME': self.analysis.MINIMUM_REALISTIC_WORK_TIME,
                'WORK_HOUR_START': self.analysis.WORK_HOUR_START,
                'WORK_HOUR_END': self.analysis.WORK_HOUR_END,
                'PACKAGING_PCS_PER_TRAY': self.analysis.PACKAGING_PCS_PER_TRAY,
            },
            'performance': {
                'CACHE_EXPIRY_MINUTES': self.performance.CACHE_EXPIRY_MINUTES,
                'MAX_RECORDS_PER_QUERY': self.performance.MAX_RECORDS_PER_QUERY,
                'GZIP_COMPRESSION_LEVEL': self.performance.GZIP_COMPRESSION_LEVEL,
            },
            'security': {
                'SESSION_TIMEOUT_DAYS': self.security.SESSION_TIMEOUT_DAYS,
                'RATE_LIMITS': self.security.RATE_LIMITS,
            },
            'worker': {
                'TEST_WORKERS': self.worker.TEST_WORKERS,
                'WORKER_CORRECTIONS': self.worker.WORKER_CORRECTIONS,
            }
        }

        os.makedirs(os.path.dirname(CONFIG_FILE_PATH), exist_ok=True)
        with open(CONFIG_FILE_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_dict, f, ensure_ascii=False, indent=2)

        print(f"[Config] 설정 저장 완료: {CONFIG_FILE_PATH}")


# 싱글톤 인스턴스
config = AppConfig()
