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

class DataAnalyzer:
    def __init__(self):
        self.raw_event_df: pd.DataFrame = pd.DataFrame()

    def load_all_data(self, folder_path: str, process_mode: str, date_filter: Optional[datetime.date] = None) -> pd.DataFrame:
        all_event_data_dfs, target_files = [], []

        if date_filter:
            all_log_files = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))
            date_str_today = date_filter.strftime('%Y%m%d')
            yesterday = date_filter - datetime.timedelta(days=1)
            date_str_yesterday = yesterday.strftime('%Y%m%d')
            all_log_files = [
                f for f in all_log_files
                if f"_{date_str_today}.csv" in os.path.basename(f) or f"_{date_str_yesterday}.csv" in os.path.basename(f)
            ]
            print(f"실시간 로딩: {len(all_log_files)}개 파일만 읽습니다. (경로: {folder_path})")
        else:
            print(f"전체 데이터 로딩: '{folder_path}' 및 '{os.path.join(folder_path, 'log')}' 하위 폴더를 모두 검색합니다.")
            main_folder_logs = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))
            log_archive_path = os.path.join(folder_path, 'log')
            archived_logs = []
            if os.path.isdir(log_archive_path):
                archived_logs = glob.glob(os.path.join(log_archive_path, '**', '*작업이벤트로그*.csv'), recursive=True)
            all_log_files = main_folder_logs + archived_logs
            print(f"총 {len(all_log_files)}개의 로그 파일 발견.")

        if process_mode == '포장실':
            target_files = [f for f in all_log_files if '포장실작업이벤트로그' in os.path.basename(f)]
        elif process_mode == '이적실':
            target_files = [f for f in all_log_files if '이적작업이벤트로그' in os.path.basename(f)]
        elif process_mode == '검사실':
            target_files = [f for f in all_log_files if '검사작업이벤트로그' in os.path.basename(f)]
        else: # "전체" 또는 "전체 비교"
            target_files = all_log_files

        if not target_files:
            if date_filter: return pd.DataFrame()
            raise FileNotFoundError(f"지정한 폴더 경로에 '{process_mode}'에 대한 로그 파일이 없습니다.")

        for file_path in target_files:
            if os.path.getsize(file_path) == 0: continue
            
            df = None
            for encoding in ['utf-8-sig', 'utf-8', 'cp949']:
                try:
                    df = pd.read_csv(file_path, encoding=encoding, on_bad_lines='warn')
                    break
                except Exception:
                    continue
            
            if df is None or df.empty: continue
            
            try:
                filename = os.path.basename(file_path)
                
                if '이적작업이벤트로그' in filename:
                    current_process = "이적실"
                elif '포장실작업이벤트로그' in filename:
                    current_process = "포장실"
                elif '검사작업이벤트로그' in filename:
                    current_process = "검사실"
                else:
                    continue

                if process_mode not in ["전체", "전체 비교"] and (
                    (process_mode == "이적실" and current_process != "이적실") or
                    (process_mode == "포장실" and current_process != "포장실") or
                    (process_mode == "검사실" and current_process != "검사실")
                ):
                    continue
                
                if 'worker_name' in df.columns: df.rename(columns={'worker_name': 'worker'}, inplace=True)
                
                if 'worker' not in df.columns:
                    if current_process == "이적실":
                        match = re.search(r'이적작업이벤트로그_([^_]+)_\d{8}\.csv', filename)
                        df['worker'] = match.group(1) if match else 'UNKNOWN_WORKER'
                    elif current_process == "검사실":
                        match = re.search(r'검사작업이벤트로그_([^_]+)_\d{8}\.csv', filename)
                        df['worker'] = match.group(1) if match else 'UNKNOWN_WORKER'
                    else:
                        df['worker'] = 'UNKNOWN_WORKER'

                df['worker'], df['process'] = df['worker'].astype(str), current_process
                if not all(h in df.columns for h in ['timestamp', 'event', 'details']): continue
                
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df.dropna(subset=['timestamp'], inplace=True)
                if df.empty: continue
                
                # `details` 파싱 로직을 `process_events_to_sessions`로 이동
                if not df.empty: all_event_data_dfs.append(df)

            except Exception as e:
                print(f"ERROR: Event log file '{file_path}' processing error: {e}")

        if not all_event_data_dfs:
            self.raw_event_df = pd.DataFrame()
            if date_filter: return pd.DataFrame()
            raise ValueError("로그 파일들을 찾았지만, 데이터를 읽을 수 없습니다.")

        event_df = pd.concat(all_event_data_dfs, ignore_index=True)
        self.raw_event_df = event_df.copy()
        return self.process_events_to_sessions(event_df)

    def process_events_to_sessions(self, event_df: pd.DataFrame) -> pd.DataFrame:
        if event_df.empty: return pd.DataFrame()

        completed_trays_df = event_df[event_df['event'] == 'TRAY_COMPLETE'].copy()
        if completed_trays_df.empty: return pd.DataFrame()

        def _parse_details(detail_data):
            """JSON과 새로운 QR 형식(key=value|...)을 모두 처리하는 헬퍼 함수"""
            if isinstance(detail_data, dict):
                return detail_data # 이미 dict 형태이면 그대로 반환
            if not isinstance(detail_data, str):
                return {}

            # 1. JSON 파싱 시도
            try:
                if detail_data.strip().startswith('{'):
                    return json.loads(detail_data)
            except (json.JSONDecodeError, TypeError):
                pass

            # 2. QR 형식 파싱 시도
            try:
                if '|' in detail_data and '=' in detail_data:
                    # 'PHS=1|CLC=...' 형식의 데이터를 dict로 변환
                    return dict(item.split('=', 1) for item in detail_data.split('|') if '=' in item)
            except ValueError: # '='가 없는 항목 등으로 인한 오류 방지
                pass

            return {} # 어떤 형식에도 해당하지 않으면 빈 dict 반환

        # apply를 사용하여 details 컬럼을 일괄적으로 파싱
        completed_trays_df['details'] = completed_trays_df['details'].apply(_parse_details)

        def safe_get(d, k, default):
            return d.get(k, default) if isinstance(d, dict) else default

        details_series = completed_trays_df['details']
        
        completed_trays_df['start_time_str'] = details_series.apply(lambda d: safe_get(d, 'start_time', ''))
        completed_trays_df['start_time_dt'] = pd.to_datetime(completed_trays_df['start_time_str'], errors='coerce')
        completed_trays_df.dropna(subset=['start_time_dt'], inplace=True)
        if completed_trays_df.empty: return pd.DataFrame()

        completed_trays_df = completed_trays_df.sort_values(by=['worker', 'start_time_dt']).copy()
        completed_trays_df['prev_end_time'] = completed_trays_df.groupby('worker')['timestamp'].shift(1)
        completed_trays_df['latency'] = (completed_trays_df['start_time_dt'] - pd.to_datetime(completed_trays_df['prev_end_time'], errors='coerce')).dt.total_seconds().fillna(0).clip(lower=0)
        
        def calculate_pcs(row):
            details = row['details']
            if row['process'] == '포장실':
                return 60
            elif row['process'] == '검사실':
                return safe_get(details, 'good_count', 0) + safe_get(details, 'defective_count', 0)
            else: # 이적실
                return safe_get(details, 'scan_count', 0)

        pcs_completed_values = completed_trays_df.apply(calculate_pcs, axis=1)

        sessions_df = pd.DataFrame({
            'date': completed_trays_df['start_time_dt'].dt.date,
            'start_time_dt': completed_trays_df['start_time_dt'],
            'end_time_dt': completed_trays_df['timestamp'],
            
            # --- 신규/변경 필드 ---
            'shipping_date': details_series.apply(lambda d: safe_get(d, 'OBD', safe_get(d, 'shipping_date', pd.NaT))), # OBD 우선
            'item_code': details_series.apply(lambda d: safe_get(d, 'CLC', safe_get(d, 'item_code', 'N/A'))), # CLC 우선
            'work_order_id': details_series.apply(lambda d: safe_get(d, 'WID', 'N/A')),
            'phase': details_series.apply(lambda d: safe_get(d, 'PHS', 'N/A')),
            'supplier_code': details_series.apply(lambda d: safe_get(d, 'SPC', 'N/A')),
            'product_batch': details_series.apply(lambda d: safe_get(d, 'FPB', 'N/A')),
            'item_group': details_series.apply(lambda d: safe_get(d, 'IG', 'N/A')),
            
            # --- 기존 필드 (호환성 유지) ---
            'worker': completed_trays_df['worker'],
            'process': completed_trays_df['process'],
            'item_name': details_series.apply(lambda d: safe_get(d, 'item_name', '')), # item_name은 기존 유지
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

        sessions_df['shipping_date'] = pd.to_datetime(sessions_df['shipping_date'], errors='coerce')
        sessions_df['item_display'] = sessions_df['item_name'].astype(str) + " (" + sessions_df['item_code'].astype(str) + ")"
        
        return sessions_df
        
    def filter_data(self, df: pd.DataFrame, start_date, end_date, selected_workers, shipping_start_date=None, shipping_end_date=None):
        if df.empty: return pd.DataFrame()
        
        df_filtered = df.copy()
        df_filtered['date'] = pd.to_datetime(df_filtered['date'], errors='coerce').dt.date
        df_filtered.dropna(subset=['date'], inplace=True)

        try:
            start_date_obj = pd.to_datetime(start_date).date()
            end_date_obj = pd.to_datetime(end_date).date()
        except (ValueError, TypeError, AttributeError):
            print(f"경고: 유효하지 않은 날짜 필터 값입니다. Start: {start_date}, End: {end_date}")
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
                    print(f"경고: 유효하지 않은 출고 날짜 필터 값입니다.")

        if selected_workers:
            df_filtered = df_filtered[df_filtered['worker'].isin(selected_workers)]
            
        return df_filtered

    def analyze_dataframe(self, df, radar_metrics, full_sessions_df=None):
        if df.empty: return {}, {}, pd.DataFrame(), None
        
        worker_data = self._calculate_worker_data(df.copy(), full_sessions_df)
        worker_data, normalized_df = self._calculate_overall_score(worker_data, radar_metrics)
        kpis = self._calculate_kpis(df.copy())
        
        return worker_data, kpis, df, normalized_df

    def _calculate_worker_data(self, df, full_sessions_df=None):
        if df.empty: return {}
        
        grouped = df.groupby('worker')
        if not grouped.groups: return {}
        
        reasonable_latency_mean = lambda x: x[x <= 3600].mean()
        
        agg_dict = {
            'avg_work_time': ('work_time', 'mean'),
            'work_time_std': ('work_time', 'std'),
            'avg_latency': ('latency', reasonable_latency_mean),
            'avg_idle_time': ('idle_time', 'mean'),
            'total_process_errors': ('process_errors', 'sum'),
            'first_pass_yield': ('had_error', lambda x: 1 - x.sum() / x.count() if x.count() > 0 else 1.0),
            'session_count': ('worker', 'size'),
            'total_pcs_completed': ('pcs_completed', 'sum')
        }
            
        worker_summary_df = grouped.agg(**agg_dict).fillna(0)

        if '검사실' in df['process'].unique():
            defect_summary = grouped.agg(
                total_defects=('defective_count', 'sum'),
                total_pcs=('pcs_completed', 'sum')
            )
            worker_summary_df['defect_rate'] = (defect_summary['total_defects'] / defect_summary['total_pcs']).where(defect_summary['total_pcs'] > 0, 0)
        else:
            worker_summary_df['defect_rate'] = 0.0
        
        worker_summary_df.fillna({'defect_rate': 0.0}, inplace=True)

        final_data = {}
        for worker_name, row in worker_summary_df.iterrows():
            best_time = float('inf')
            best_time_date = None
            if full_sessions_df is not None and not full_sessions_df.empty:
                worker_all_sessions = full_sessions_df[full_sessions_df['worker'] == worker_name].copy()
                if not worker_all_sessions.empty:
                    worker_all_sessions['date'] = pd.to_datetime(worker_all_sessions['date']).dt.date
                    today = datetime.date.today()
                    seven_days_ago = today - datetime.timedelta(days=7)
                    last_7_days_sessions = worker_all_sessions[
                        (worker_all_sessions['date'] >= seven_days_ago) & (worker_all_sessions['date'] <= today)
                    ]
                    clean_last_7_days = last_7_days_sessions[
                        (last_7_days_sessions['pcs_completed'] > 0) &
                        (last_7_days_sessions['had_error'] == 0) &
                        (last_7_days_sessions['is_partial'] == False) &
                        (last_7_days_sessions['is_restored'] == False) &
                        (last_7_days_sessions['is_test'] == False)
                    ]
                    last_week_avg_time = clean_last_7_days['work_time'].mean() if not clean_last_7_days.empty else float('inf')
                    
                    start_of_week = today - datetime.timedelta(days=today.weekday())
                    current_week_sessions = worker_all_sessions[worker_all_sessions['date'] >= start_of_week]
                    
                    if not current_week_sessions.empty:
                        MINIMUM_REALISTIC_TIME = 180.0
                        DYNAMIC_THRESHOLD_PERCENTAGE = 0.6
                        dynamic_threshold = MINIMUM_REALISTIC_TIME
                        if pd.notna(last_week_avg_time) and last_week_avg_time != float('inf'):
                            dynamic_threshold = max(last_week_avg_time * DYNAMIC_THRESHOLD_PERCENTAGE, MINIMUM_REALISTIC_TIME)
                        
                        clean_sessions_for_best_record = current_week_sessions[
                            (current_week_sessions['pcs_completed'] == 60) &
                            (current_week_sessions['work_time'] >= dynamic_threshold) &
                            (current_week_sessions['had_error'] == 0) &
                            (current_week_sessions['is_partial'] == False) &
                            (current_week_sessions['is_restored'] == False) &
                            (current_week_sessions['is_test'] == False)
                        ]
                        if not clean_sessions_for_best_record.empty:
                            best_row = clean_sessions_for_best_record.loc[clean_sessions_for_best_record['work_time'].idxmin()]
                            best_time = best_row['work_time']
                            best_time_date = best_row['date']

            s_count, t_pcs = int(row.get('session_count', 0)), int(row.get('total_pcs_completed', 0))
            final_data[str(worker_name)] = WorkerPerformance(
                worker=str(worker_name), session_count=s_count, total_pcs_completed=t_pcs,
                avg_work_time=float(row.get('avg_work_time', 0.0)),
                avg_latency=float(row.get('avg_latency', 0.0)),
                avg_idle_time=float(row.get('avg_idle_time', 0.0)),
                total_process_errors=int(row.get('total_process_errors', 0)),
                first_pass_yield=float(row.get('first_pass_yield', 0.0)),
                avg_pcs_per_tray=float(t_pcs / s_count if s_count > 0 else 0),
                work_time_std=float(row.get('work_time_std', 0.0)),
                defect_rate=float(row.get('defect_rate', 0.0)),
                best_work_time=best_time,
                best_work_time_date=best_time_date
            )
        return final_data

    def _calculate_overall_score(self, worker_data, radar_metrics):
        if not worker_data: return {}, pd.DataFrame()

        df = pd.DataFrame([v.__dict__ for v in worker_data.values()])
        if df.empty: return worker_data, df

        norm_cols_for_score = []
        weights = []
        for _, (metric, norm_type, weight) in radar_metrics.items():
            norm_col_name = f'{metric}_norm'
            if metric not in df.columns or df[metric].isnull().all() or len(df[metric].unique()) <= 1:
                df[norm_col_name] = 0.5
            else:
                s = pd.to_numeric(df[metric], errors='coerce').fillna(df[metric].mean())
                min_v, max_v = s.min(), s.max()
                
                if max_v == min_v:
                    df[norm_col_name] = 0.5
                elif norm_type:
                    df[norm_col_name] = (s - min_v) / (max_v - min_v)
                else:
                    df[norm_col_name] = 1 - ((s - min_v) / (max_v - min_v))
            
            norm_cols_for_score.append(norm_col_name)
            weights.append(weight)

        # 검사실의 불량 탐지율은 높을수록 좋으므로 별도 정규화 (Scatter Plot용)
        if 'defect_rate' in df.columns:
            s = df['defect_rate']
            min_v, max_v = s.min(), s.max()
            if max_v == min_v or max_v == 0:
                df['defect_rate_norm'] = 0.5
            else:
                df['defect_rate_norm'] = (s - min_v) / (max_v - min_v)

        if norm_cols_for_score:
            df['overall_score'] = np.average(df[norm_cols_for_score], axis=1, weights=weights) * 100
        else:
            df['overall_score'] = 0.0
        
        for _, row in df.iterrows():
            if (wn := str(row['worker'])) in worker_data:
                worker_data[wn].overall_score = float(row['overall_score'])
                
        return worker_data, df

    def _calculate_kpis(self, filtered_df):
        if filtered_df.empty: return {'total_trays':0, 'total_pcs_completed':0, 'avg_pcs_per_tray':0.0, 'avg_tray_time':0.0, 'total_errors':0, 'weekly_avg_errors':0.0, 'avg_fpy':0.0, 'avg_latency':0.0, 'avg_defect_rate': 0.0}
        
        kpis = {}
        total_sessions, total_pcs = len(filtered_df), int(filtered_df['pcs_completed'].sum())
        
        fpy_base = filtered_df[
            (filtered_df['is_test'] == False) &
            (filtered_df['is_partial'] == False) &
            (filtered_df['is_restored'] == False)
        ]
        fpy_value = (1 - fpy_base['had_error'].mean()) if not fpy_base.empty else 1.0
        
        reasonable_latency = filtered_df[filtered_df['latency'] <= 3600]['latency']
        avg_latency_value = reasonable_latency.mean() if not reasonable_latency.empty else 0.0

        total_errors = int(filtered_df['process_errors'].sum())
        num_days = (pd.to_datetime(filtered_df['date']).max() - pd.to_datetime(filtered_df['date']).min()).days + 1
        num_weeks = num_days / 7 if num_days >= 7 else 1
        
        kpis.update({
            'total_trays': total_sessions, 'total_pcs_completed': total_pcs,
            'avg_pcs_per_tray': total_pcs / total_sessions if total_sessions > 0 else 0.0,
            'avg_tray_time': filtered_df['work_time'].mean(),
            'total_errors': total_errors,
            'weekly_avg_errors': total_errors / num_weeks,
            'avg_fpy': fpy_value,
            'avg_latency': avg_latency_value
        })

        if '검사실' in filtered_df['process'].unique():
            total_defects = filtered_df['defective_count'].sum()
            kpis['avg_defect_rate'] = total_defects / total_pcs if total_pcs > 0 else 0.0
        else:
            kpis['avg_defect_rate'] = 0.0
            
        return kpis