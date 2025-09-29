# -*- coding: utf-8 -*-
import os
import pickle
import hashlib
import pandas as pd
from datetime import datetime, timedelta
from typing import Optional, Dict, Any
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

class DataCache:
    """파일 레벨 캐싱을 위한 클래스"""

    def __init__(self, cache_dir='cache'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)
        self.cache_expiry = timedelta(hours=24)  # 24시간 캐시 유효

    def get_file_hash(self, file_path: str) -> str:
        """파일의 해시값 생성 (경로 + 수정시간 + 크기)"""
        try:
            stat = os.stat(file_path)
            hash_content = f"{file_path}{stat.st_mtime}{stat.st_size}"
            return hashlib.md5(hash_content.encode()).hexdigest()
        except OSError:
            return None

    def get_cache_file_path(self, file_path: str) -> str:
        """캐시 파일 경로 생성"""
        hash_key = self.get_file_hash(file_path)
        if not hash_key:
            return None
        return os.path.join(self.cache_dir, f"{hash_key}.pkl")

    def is_cache_valid(self, cache_file_path: str) -> bool:
        """캐시 파일이 유효한지 확인"""
        if not os.path.exists(cache_file_path):
            return False

        cache_time = datetime.fromtimestamp(os.path.getmtime(cache_file_path))
        return datetime.now() - cache_time < self.cache_expiry

    def get_cached_data(self, file_path: str) -> Optional[pd.DataFrame]:
        """캐시된 데이터 로드"""
        cache_file_path = self.get_cache_file_path(file_path)
        if not cache_file_path or not self.is_cache_valid(cache_file_path):
            return None

        try:
            with open(cache_file_path, 'rb') as f:
                data = pickle.load(f)
                logger.info(f"캐시에서 로드: {os.path.basename(file_path)}")
                return data
        except Exception as e:
            logger.warning(f"캐시 로드 실패 {file_path}: {e}")
            return None

    def save_cached_data(self, file_path: str, data: pd.DataFrame):
        """데이터를 캐시에 저장"""
        cache_file_path = self.get_cache_file_path(file_path)
        if not cache_file_path:
            return

        try:
            with open(cache_file_path, 'wb') as f:
                pickle.dump(data, f)
                logger.info(f"캐시에 저장: {os.path.basename(file_path)}")
        except Exception as e:
            logger.warning(f"캐시 저장 실패 {file_path}: {e}")

    def clear_old_cache(self):
        """오래된 캐시 파일 정리"""
        try:
            current_time = datetime.now()
            for filename in os.listdir(self.cache_dir):
                if filename.endswith('.pkl'):
                    file_path = os.path.join(self.cache_dir, filename)
                    file_time = datetime.fromtimestamp(os.path.getmtime(file_path))
                    if current_time - file_time > self.cache_expiry:
                        os.remove(file_path)
                        logger.info(f"오래된 캐시 파일 삭제: {filename}")
        except Exception as e:
            logger.warning(f"캐시 정리 실패: {e}")

class SessionCache:
    """세션 레벨 캐싱을 위한 클래스"""

    def __init__(self):
        self.session_cache: Dict[str, tuple] = {}
        self.cache_expiry = timedelta(minutes=30)

    def generate_cache_key(self, process_mode: str, start_date: str, end_date: str, workers: list) -> str:
        """캐시 키 생성"""
        workers_str = ','.join(sorted(workers)) if workers else 'all'
        return f"{process_mode}_{start_date}_{end_date}_{workers_str}"

    def get_sessions(self, cache_key: str) -> Optional[pd.DataFrame]:
        """캐시된 세션 데이터 로드"""
        if cache_key in self.session_cache:
            cached_data, timestamp = self.session_cache[cache_key]
            if datetime.now() - timestamp < self.cache_expiry:
                logger.info(f"세션 캐시에서 로드: {cache_key}")
                return cached_data
            else:
                # 만료된 캐시 제거
                del self.session_cache[cache_key]
        return None

    def set_sessions(self, cache_key: str, data: pd.DataFrame):
        """세션 데이터를 캐시에 저장"""
        self.session_cache[cache_key] = (data.copy(), datetime.now())
        logger.info(f"세션 캐시에 저장: {cache_key}")

    def clear_expired_cache(self):
        """만료된 캐시 정리"""
        current_time = datetime.now()
        expired_keys = []
        for key, (data, timestamp) in self.session_cache.items():
            if current_time - timestamp > self.cache_expiry:
                expired_keys.append(key)

        for key in expired_keys:
            del self.session_cache[key]
            logger.info(f"만료된 세션 캐시 삭제: {key}")

class OptimizedDataManager:
    """최적화된 데이터 관리자"""

    def __init__(self):
        self.file_cache = DataCache()
        self.session_cache = SessionCache()

    def get_files_by_date_range(self, folder_path: str, start_date: str, end_date: str) -> list:
        """날짜 범위에 해당하는 파일만 필터링"""
        import glob
        from datetime import datetime

        # 날짜 범위 파싱
        try:
            start_dt = datetime.strptime(start_date, '%Y-%m-%d').date()
            end_dt = datetime.strptime(end_date, '%Y-%m-%d').date()
        except ValueError:
            # 날짜 파싱 실패 시 모든 파일 반환
            return glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))

        all_files = []

        # 메인 폴더 파일들
        main_files = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))

        # 아카이브 폴더 파일들
        archive_files = glob.glob(os.path.join(folder_path, '2025-*', '*작업이벤트로그*.csv'))

        all_files = main_files + archive_files

        # 날짜 범위에 해당하는 파일만 필터링
        filtered_files = []

        for file_path in all_files:
            filename = os.path.basename(file_path)

            # 파일명에서 날짜 추출 (예: _20250929.csv)
            import re
            date_match = re.search(r'_(\d{8})\.csv$', filename)
            if date_match:
                file_date_str = date_match.group(1)
                try:
                    file_date = datetime.strptime(file_date_str, '%Y%m%d').date()

                    # 날짜 범위 확장 (하루 전후 포함)
                    extended_start = start_dt - timedelta(days=1)
                    extended_end = end_dt + timedelta(days=1)

                    if extended_start <= file_date <= extended_end:
                        filtered_files.append(file_path)
                except ValueError:
                    # 날짜 파싱 실패 시 포함
                    filtered_files.append(file_path)
            else:
                # 날짜 형식이 없는 파일은 포함
                filtered_files.append(file_path)

        logger.info(f"날짜 필터링: {len(all_files)}개 → {len(filtered_files)}개 파일")
        return filtered_files

    def optimize_dataframe(self, df: pd.DataFrame) -> pd.DataFrame:
        """데이터프레임 메모리 최적화"""
        if df.empty:
            return df

        # 문자열 컬럼을 category로 변환
        categorical_columns = ['worker', 'process', 'item_code', 'item_name', 'work_order_id', 'phase']
        for col in categorical_columns:
            if col in df.columns and df[col].dtype == 'object':
                df[col] = df[col].astype('category')

        # 정수 컬럼을 일반 int로 변환 (JSON 직렬화 호환)
        int_columns = ['pcs_completed', 'process_errors', 'defective_count']
        for col in int_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0).astype(int)

        # 실수 컬럼을 일반 float로 변환 (JSON 직렬화 호환)
        float_columns = ['work_time', 'latency', 'idle_time']
        for col in float_columns:
            if col in df.columns:
                df[col] = pd.to_numeric(df[col], errors='coerce').fillna(0.0).astype(float)

        # 불린 컬럼 최적화
        bool_columns = ['had_error', 'is_partial', 'is_restored', 'is_test']
        for col in bool_columns:
            if col in df.columns:
                df[col] = df[col].astype('bool')

        return df

    def cleanup_cache(self):
        """캐시 정리"""
        self.file_cache.clear_old_cache()
        self.session_cache.clear_expired_cache()