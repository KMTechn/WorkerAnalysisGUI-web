# -*- coding: utf-8 -*-
import datetime
import os
import json
import re
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
import pandas as pd
import glob
import numpy as np
import logging

from cache_manager import DataCache, SessionCache, OptimizedDataManager

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@dataclass
class WorkerPerformance:
    worker: str
    avg_work_time: float = 0.0
    avg_latency: float = 0.0
    avg_idle_time: float = 0.0
    total_process_errors: int = 0
    first_pass_yield: float = 0.0
    session_count: int = 0
    overall_score: float = 0.0
    total_pcs_completed: int = 0
    avg_pcs_per_tray: float = 0.0
    work_time_std: float = 0.0
    defect_rate: float = 0.0
    best_work_time: float = float('inf')
    best_work_time_date: Optional[datetime.date] = None

class OptimizedDataAnalyzer:
    def __init__(self):
        self.raw_event_df: pd.DataFrame = pd.DataFrame()
        self.data_manager = OptimizedDataManager()
        logger.info("최적화된 데이터 분석기 초기화 완료")

    def load_all_data(self, folder_path: str, process_mode: str, date_filter: Optional[datetime.date] = None,
                     start_date: str = None, end_date: str = None) -> pd.DataFrame:
        """최적화된 데이터 로딩 - 캐싱 및 날짜 필터링 적용"""

        # 세션 캐시 확인
        if start_date and end_date and not date_filter:
            cache_key = self.data_manager.session_cache.generate_cache_key(
                process_mode, start_date, end_date, []
            )
            cached_sessions = self.data_manager.session_cache.get_sessions(cache_key)
            if cached_sessions is not None:
                logger.info(f"세션 캐시 히트: {len(cached_sessions)}개 세션")
                return cached_sessions

        # 파일 목록 결정
        if start_date and end_date:
            # 날짜 범위 기반 파일 필터링
            target_files = self.data_manager.get_files_by_date_range(folder_path, start_date, end_date)
        elif date_filter:
            # 실시간 모드 (오늘/어제 파일만)
            main_logs = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))
            archive_logs = glob.glob(os.path.join(folder_path, '2025-*', '*작업이벤트로그*.csv'))
            all_log_files = main_logs + archive_logs

            date_str_today = date_filter.strftime('%Y%m%d')
            yesterday = date_filter - datetime.timedelta(days=1)
            date_str_yesterday = yesterday.strftime('%Y%m%d')
            target_files = [
                f for f in all_log_files
                if f"_{date_str_today}.csv" in os.path.basename(f) or f"_{date_str_yesterday}.csv" in os.path.basename(f)
            ]
            logger.info(f"실시간 로딩: {len(target_files)}개 파일")
        else:
            # 전체 데이터 로딩
            main_folder_logs = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))
            archived_logs = []
            archived_logs.extend(glob.glob(os.path.join(folder_path, '2025-*', '*작업이벤트로그*.csv')))

            quarterly_path = os.path.join(os.path.dirname(folder_path), 'quarterly_backup')
            if os.path.isdir(quarterly_path):
                archived_logs.extend(glob.glob(os.path.join(quarterly_path, '**', '*작업이벤트로그*.csv'), recursive=True))

            log_archive_path = os.path.join(folder_path, 'log')
            if os.path.isdir(log_archive_path):
                archived_logs.extend(glob.glob(os.path.join(log_archive_path, '**', '*작업이벤트로그*.csv'), recursive=True))

            target_files = main_folder_logs + archived_logs
            logger.info(f"전체 로딩: {len(target_files)}개 파일")

        # 프로세스별 파일 필터링
        if process_mode == '포장실':
            target_files = [f for f in target_files if '포장실작업이벤트로그' in os.path.basename(f)]
        elif process_mode == '이적실':
            target_files = [f for f in target_files if '이적작업이벤트로그' in os.path.basename(f)]
        elif process_mode == '검사실':
            target_files = [f for f in target_files if '검사작업이벤트로그' in os.path.basename(f)]

        if not target_files:
            logger.warning(f"'{process_mode}'에 대한 로그 파일이 없습니다.")
            return pd.DataFrame()

        # 캐시 활용한 파일 처리
        all_sessions = []
        cache_hits = 0
        cache_misses = 0

        for file_path in target_files:
            if os.path.getsize(file_path) == 0:
                continue

            # 캐시 확인
            cached_sessions = self.data_manager.file_cache.get_cached_data(file_path)
            if cached_sessions is not None:
                all_sessions.append(cached_sessions)
                cache_hits += 1
            else:
                # 새로 처리
                sessions = self._process_single_file(file_path, process_mode)
                if not sessions.empty:
                    # 메모리 최적화 적용
                    sessions = self.data_manager.optimize_dataframe(sessions)
                    all_sessions.append(sessions)
                    # 캐시에 저장
                    self.data_manager.file_cache.save_cached_data(file_path, sessions)
                cache_misses += 1

        logger.info(f"캐시 통계 - 히트: {cache_hits}, 미스: {cache_misses}")

        # 결과 합치기
        if all_sessions:
            result_df = pd.concat(all_sessions, ignore_index=True)
            result_df = self.data_manager.optimize_dataframe(result_df)

            # 세션 캐시에 저장
            if start_date and end_date and not date_filter:
                self.data_manager.session_cache.set_sessions(cache_key, result_df)

            logger.info(f"총 {len(result_df)}개 세션 로드 완료")
            return result_df
        else:
            return pd.DataFrame()

    def _process_single_file(self, file_path: str, process_mode: str) -> pd.DataFrame:
        """단일 파일 처리"""
        try:
            # 파일 읽기 (여러 인코딩 시도)
            df = None
            for encoding in ['utf-8-sig', 'utf-8', 'cp949']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='warn')
                    break
                except Exception:
                    continue

            if df is None or df.empty:
                return pd.DataFrame()

            # 컬럼명 표준화
            if 'worker_name' in df.columns and 'worker' not in df.columns:
                df = df.rename(columns={'worker_name': 'worker'})

            # 프로세스 정보 추가
            filename = os.path.basename(file_path)
            if '이적작업이벤트로그' in filename:
                df['process'] = '이적실'
            elif '포장실작업이벤트로그' in filename:
                df['process'] = '포장실'
            elif '검사작업이벤트로그' in filename:
                df['process'] = '검사실'
            else:
                df['process'] = '기타'

            # 이벤트 처리하여 세션 생성
            sessions_df = self.process_events_to_sessions(df)

            logger.info(f"파일 처리 완료: {os.path.basename(file_path)} - {len(sessions_df)}개 세션")
            return sessions_df

        except Exception as e:
            logger.error(f"파일 처리 실패 {file_path}: {e}")
            return pd.DataFrame()

    def process_events_to_sessions(self, event_df: pd.DataFrame) -> pd.DataFrame:
        """이벤트 데이터를 세션으로 변환 (기존 로직 유지)"""
        if event_df.empty:
            return pd.DataFrame()

        # 원본 로직 유지하되 메모리 최적화 적용
        event_df = event_df.copy()

        # 타임스탬프 처리
        event_df['timestamp'] = pd.to_datetime(event_df['timestamp'], errors='coerce')
        event_df = event_df.dropna(subset=['timestamp'])

        if event_df.empty:
            return pd.DataFrame()

        # Raw 데이터 저장 (추적 기능용)
        self.raw_event_df = pd.concat([self.raw_event_df, event_df], ignore_index=True)

        # TRAY_COMPLETE 이벤트만 추출
        completed_trays_df = event_df[event_df['event'] == 'TRAY_COMPLETE'].copy()

        if completed_trays_df.empty:
            return pd.DataFrame()

        # 세션 데이터 구성
        def safe_get(d, key, default=None):
            if isinstance(d, dict):
                return d.get(key, default)
            elif isinstance(d, str):
                try:
                    parsed = json.loads(d)
                    return parsed.get(key, default)
                except:
                    return default
            return default

        def safe_parse_details(details_str):
            try:
                if isinstance(details_str, str):
                    return json.loads(details_str)
                return details_str if isinstance(details_str, dict) else {}
            except:
                return {}

        details_series = completed_trays_df['details'].apply(safe_parse_details)

        # 시작 시간 계산
        def calculate_start_time(row):
            details = safe_parse_details(row['details'])
            start_time_str = safe_get(details, 'start_time')
            if start_time_str:
                try:
                    return pd.to_datetime(start_time_str)
                except:
                    pass
            work_time = float(safe_get(details, 'work_time_sec', safe_get(details, 'work_time', 0)))
            return row['timestamp'] - pd.Timedelta(seconds=work_time)

        completed_trays_df['start_time_dt'] = completed_trays_df.apply(calculate_start_time, axis=1)

        # 지연시간 계산
        def calculate_latency(details):
            start_scan_times = []
            for event_type in ['MASTER_LABEL_SCANNED', 'MASTER_LABEL_SCANNED_OLD']:
                scan_time = safe_get(details, f'{event_type.lower()}_time')
                if scan_time:
                    try:
                        start_scan_times.append(pd.to_datetime(scan_time))
                    except:
                        pass

            if start_scan_times:
                first_scan_time = min(start_scan_times)
                start_time_str = safe_get(details, 'start_time')
                if start_time_str:
                    try:
                        start_time = pd.to_datetime(start_time_str)
                        return max(0, (start_time - first_scan_time).total_seconds())
                    except:
                        pass
            return 0.0

        completed_trays_df['latency'] = details_series.apply(calculate_latency)

        # PCS 계산
        def calculate_pcs(row):
            details = safe_parse_details(row['details'])
            if row['process'] == '포장실':
                return 60
            elif row['process'] == '검사실':
                return safe_get(details, 'good_count', 0) + safe_get(details, 'defective_count', 0)
            else:  # 이적실
                return safe_get(details, 'scan_count', 0)

        pcs_completed_values = completed_trays_df.apply(calculate_pcs, axis=1)

        # 세션 DataFrame 생성
        sessions_df = pd.DataFrame({
            'date': completed_trays_df['start_time_dt'].dt.date,
            'start_time_dt': completed_trays_df['start_time_dt'],
            'end_time_dt': completed_trays_df['timestamp'],

            # 신규/변경 필드
            'shipping_date': details_series.apply(lambda d: safe_get(d, 'OBD', safe_get(d, 'shipping_date', pd.NaT))),
            'item_code': details_series.apply(lambda d: safe_get(d, 'CLC', safe_get(d, 'item_code', 'N/A'))),
            'work_order_id': details_series.apply(lambda d: safe_get(d, 'WID', 'N/A')),
            'phase': details_series.apply(lambda d: safe_get(d, 'PHS', 'N/A')),
            'supplier_code': details_series.apply(lambda d: safe_get(d, 'SPC', 'N/A')),
            'product_batch': details_series.apply(lambda d: safe_get(d, 'FPB', 'N/A')),
            'item_group': details_series.apply(lambda d: safe_get(d, 'IG', 'N/A')),

            # 기존 필드
            'worker': completed_trays_df['worker'],
            'process': completed_trays_df['process'],
            'item_name': details_series.apply(lambda d: safe_get(d, 'item_name', '')),
            'work_time': details_series.apply(lambda d: float(safe_get(d, 'work_time', safe_get(d, 'work_time_sec', 0.0)))),
            'latency': completed_trays_df['latency'],
            'idle_time': details_series.apply(lambda d: float(safe_get(d, 'idle_time', safe_get(d, 'total_idle_seconds', 0.0)))),
            'process_errors': details_series.apply(lambda d: int(safe_get(d, 'process_errors', safe_get(d, 'error_count', 0)))),
            'had_error': details_series.apply(lambda d: int(safe_get(d, 'had_error', safe_get(d, 'has_error_or_reset', False)))),
            'is_partial': details_series.apply(lambda d: safe_get(d, 'is_partial', safe_get(d, 'is_partial_submission', False))),
            'is_restored': details_series.apply(lambda d: safe_get(d, 'is_restored_session', False)),
            'is_test': details_series.apply(lambda d: safe_get(d, 'is_test', safe_get(d, 'is_test_tray', False))),
            'pcs_completed': pcs_completed_values,
            'defective_count': details_series.apply(lambda d: int(safe_get(d, 'defective_count', 0)))
        })

        # 추가 필드 처리
        sessions_df['shipping_date'] = pd.to_datetime(sessions_df['shipping_date'], errors='coerce')
        sessions_df['item_display'] = sessions_df['item_name'].astype(str) + " (" + sessions_df['item_code'].astype(str) + ")"

        return sessions_df

    def filter_data(self, df: pd.DataFrame, start_date, end_date, selected_workers, shipping_start_date=None, shipping_end_date=None):
        """데이터 필터링 (기존 로직 유지)"""
        if df.empty:
            return pd.DataFrame()

        df_filtered = df.copy()
        df_filtered['date'] = pd.to_datetime(df_filtered['date'], errors='coerce').dt.date
        df_filtered.dropna(subset=['date'], inplace=True)

        try:
            start_date_obj = pd.to_datetime(start_date).date()
            end_date_obj = pd.to_datetime(end_date).date()
        except (ValueError, TypeError, AttributeError):
            logger.warning(f"유효하지 않은 날짜 필터 값입니다. Start: {start_date}, End: {end_date}")
            return pd.DataFrame()

        mask = (df_filtered['date'] >= start_date_obj) & (df_filtered['date'] <= end_date_obj)
        df_filtered = df_filtered.loc[mask].copy()

        if shipping_start_date and shipping_end_date and 'shipping_date' in df_filtered.columns:
            df_filtered.dropna(subset=['shipping_date'], inplace=True)
            if not df_filtered.empty:
                try:
                    shipping_start_obj = pd.to_datetime(shipping_start_date).date()
                    shipping_end_obj = pd.to_datetime(shipping_end_date).date()
                    shipping_mask = (df_filtered['shipping_date'].dt.date >= shipping_start_obj) & (df_filtered['shipping_date'].dt.date <= shipping_end_obj)
                    df_filtered = df_filtered.loc[shipping_mask].copy()
                except (ValueError, TypeError, AttributeError):
                    logger.warning(f"유효하지 않은 출고 날짜 필터 값입니다.")

        if selected_workers:
            df_filtered = df_filtered[df_filtered['worker'].isin(selected_workers)]

        return df_filtered

    def analyze_dataframe(self, df, radar_metrics, full_sessions_df=None):
        """데이터 분석 (기존 로직 유지)"""
        if df.empty:
            return {}, {}, pd.DataFrame(), None

        worker_data = self._calculate_worker_data(df.copy(), full_sessions_df)
        worker_data, normalized_df = self._calculate_overall_score(worker_data, radar_metrics)
        kpis = self._calculate_kpis(df.copy())

        return worker_data, kpis, df, normalized_df

    def _calculate_worker_data(self, df, full_sessions_df=None):
        """작업자 데이터 계산 (기존 로직 유지)"""
        if df.empty:
            return {}

        grouped = df.groupby('worker')
        if not grouped.groups:
            return {}

        reasonable_latency_mean = lambda x: x[x <= 3600].mean()

        # 단순한 집계 방식 사용
        aggregated = {}

        for worker, group in grouped:
            aggregated[worker] = {
                'avg_work_time': group['work_time'].mean(),
                'work_time_std': group['work_time'].std() if len(group) > 1 else 0.0,
                'avg_latency': group['latency'][group['latency'] <= 3600].mean(),
                'avg_idle_time': group['idle_time'].mean(),
                'total_process_errors': group['process_errors'].sum(),
                'first_pass_yield': 1 - (group['had_error'].sum() / len(group)) if len(group) > 0 else 1.0,
                'session_count': len(group),
                'total_pcs_completed': group['pcs_completed'].sum(),
                'avg_pcs_per_tray': group['pcs_completed'].mean(),
                'defect_rate': group['defective_count'].sum() / len(group) if len(group) > 0 else 0.0
            }

        # DataFrame으로 변환 (기존 코드와 호환성 유지)
        aggregated = pd.DataFrame.from_dict(aggregated, orient='index')

        worker_data = {}
        for worker in aggregated.index:
            row = aggregated.loc[worker]

            # 최고 작업시간 찾기
            worker_df = df[df['worker'] == worker]
            if not worker_df.empty and 'work_time' in worker_df.columns:
                best_idx = worker_df['work_time'].idxmin()
                best_work_time = worker_df.loc[best_idx, 'work_time']
                best_work_time_date = worker_df.loc[best_idx, 'date']
            else:
                best_work_time = float('inf')
                best_work_time_date = None

            worker_data[worker] = WorkerPerformance(
                worker=worker,
                avg_work_time=row['avg_work_time'],
                work_time_std=row['work_time_std'] if pd.notna(row['work_time_std']) else 0.0,
                avg_latency=row['avg_latency'] if pd.notna(row['avg_latency']) else 0.0,
                avg_idle_time=row['avg_idle_time'],
                total_process_errors=int(row['total_process_errors']),
                first_pass_yield=row['first_pass_yield'],
                session_count=int(row['session_count']),
                total_pcs_completed=int(row['total_pcs_completed']),
                avg_pcs_per_tray=row['avg_pcs_per_tray'],
                defect_rate=row['defect_rate'],
                best_work_time=best_work_time,
                best_work_time_date=best_work_time_date
            )

        return worker_data

    def _calculate_overall_score(self, worker_data, radar_metrics):
        """전체 점수 계산 (기존 로직 유지)"""
        if not worker_data:
            return worker_data, None

        # 정규화를 위한 통계 계산
        metrics_values = {metric: [] for metric in radar_metrics.keys()}

        for worker_perf in worker_data.values():
            for metric_name, (attr_name, is_higher_better, weight) in radar_metrics.items():
                value = getattr(worker_perf, attr_name, 0)
                if pd.notna(value) and not np.isinf(value):
                    metrics_values[metric_name].append(value)

        # 정규화 및 점수 계산
        normalized_data = []
        for worker, worker_perf in worker_data.items():
            normalized_row = {'worker': worker}
            total_score = 0
            valid_metrics = 0

            for metric_name, (attr_name, is_higher_better, weight) in radar_metrics.items():
                value = getattr(worker_perf, attr_name, 0)

                if len(metrics_values[metric_name]) > 1:
                    min_val = min(metrics_values[metric_name])
                    max_val = max(metrics_values[metric_name])

                    if max_val > min_val:
                        if is_higher_better:
                            normalized_value = (value - min_val) / (max_val - min_val)
                        else:
                            normalized_value = (max_val - value) / (max_val - min_val)
                    else:
                        normalized_value = 1.0
                else:
                    normalized_value = 1.0

                normalized_value = max(0, min(1, normalized_value))
                normalized_row[metric_name] = normalized_value
                total_score += normalized_value * weight
                valid_metrics += weight

            overall_score = (total_score / valid_metrics * 100) if valid_metrics > 0 else 50
            worker_perf.overall_score = overall_score
            normalized_row['overall_score'] = overall_score
            normalized_data.append(normalized_row)

        normalized_df = pd.DataFrame(normalized_data)
        return worker_data, normalized_df

    def _calculate_kpis(self, df):
        """KPI 계산 (기존 로직 유지)"""
        if df.empty:
            return {}

        return {
            'avg_defect_rate': df['defective_count'].sum() / len(df) if len(df) > 0 else 0.0,
            'avg_fpy': df['had_error'].apply(lambda x: 1 - x).mean(),
            'avg_latency': df['latency'].mean(),
            'avg_pcs_per_tray': df['pcs_completed'].mean(),
            'avg_tray_time': df['work_time'].mean(),
            'total_errors': int(df['process_errors'].sum()),
            'total_pcs_completed': int(df['pcs_completed'].sum()),
            'total_trays': len(df),
            'weekly_avg_errors': df['process_errors'].sum() / max(1, df['date'].nunique()) * 7
        }

    def cleanup_cache(self):
        """캐시 정리"""
        self.data_manager.cleanup_cache()
        logger.info("캐시 정리 완료")