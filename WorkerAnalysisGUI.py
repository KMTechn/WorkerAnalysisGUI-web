import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import csv
import datetime
import os
import sys
import threading
import json
import re
from typing import Dict, Tuple, Optional, Any
from dataclasses import dataclass
import time

# ### START: watchdog 라이브러리 임포트 ###
# pip install watchdog 필요
try:
    from watchdog.observers import Observer
    from watchdog.events import FileSystemEventHandler
except ImportError:
    messagebox.showerror("라이브러리 오류", "'watchdog' 라이브러리가 필요합니다.\n\n터미널에서 'pip install watchdog'을 실행해주세요.")
    sys.exit(1)
# ### END: watchdog 라이브러리 임포트 ###

import requests
import zipfile
import subprocess
import pandas as pd
import glob
import numpy as np
import matplotlib
import matplotlib.pyplot as plt
from matplotlib.figure import Figure
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from tkcalendar import DateEntry


# ####################################################################
# # 자동 업데이트 기능 (Auto-Updater)
# ####################################################################

REPO_OWNER = "KMTechn"
REPO_NAME = "WorkerAnalysisGUI"
CURRENT_VERSION = "v1.0.6" # 버전 업데이트

def check_for_updates():
    try:
        api_url = f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/releases/latest"
        response = requests.get(api_url, timeout=5)
        response.raise_for_status()
        latest_release_data = response.json()
        latest_version = latest_release_data['tag_name']

        if latest_version.strip().lower() != CURRENT_VERSION.strip().lower():
            for asset in latest_release_data['assets']:
                if asset['name'].endswith('.zip'):
                    return asset['browser_download_url'], latest_version
            return None, None
        else:
            return None, None
    except requests.exceptions.RequestException as e:
        print(f"업데이트 확인 중 오류 발생 (네트워크 문제일 수 있음): {e}")
        return None, None

def download_and_apply_update(url):
    try:
        temp_dir = os.environ.get("TEMP", "C:\\Temp")
        zip_path = os.path.join(temp_dir, "update.zip")
        response = requests.get(url, stream=True, timeout=120)
        response.raise_for_status()
        with open(zip_path, 'wb') as f:
            for chunk in response.iter_content(chunk_size=8192):
                f.write(chunk)

        temp_update_folder = os.path.join(temp_dir, "temp_update")
        if os.path.exists(temp_update_folder):
            import shutil
            shutil.rmtree(temp_update_folder)

        with zipfile.ZipFile(zip_path, 'r') as zip_ref:
            zip_ref.extractall(temp_update_folder)
        os.remove(zip_path)

        if getattr(sys, 'frozen', False):
            application_path = os.path.dirname(sys.executable)
        else:
            application_path = os.path.dirname(os.path.abspath(__file__))

        updater_script_path = os.path.join(application_path, "updater.bat")

        extracted_content = os.listdir(temp_update_folder)
        if len(extracted_content) == 1 and os.path.isdir(os.path.join(temp_update_folder, extracted_content[0])):
            new_program_folder_path = os.path.join(temp_update_folder, extracted_content[0])
        else:
            new_program_folder_path = temp_update_folder

        with open(updater_script_path, "w", encoding='utf-8') as bat_file:
            bat_file.write(f"""@echo off
chcp 65001 > nul
echo.
echo ==========================================================
echo   프로그램을 업데이트합니다. 이 창을 닫지 마세요.
echo ==========================================================
echo.
echo 잠시 후 프로그램이 자동으로 종료됩니다...
timeout /t 3 /nobreak > nul
taskkill /F /IM "{os.path.basename(sys.executable)}" > nul
echo.
echo 기존 파일을 백업하고 새 파일로 교체합니다...
xcopy "{new_program_folder_path}" "{application_path}" /E /H /C /I /Y > nul
echo.
echo 임시 업데이트 파일을 삭제합니다...
rmdir /s /q "{temp_update_folder}"
echo.
echo ========================================
echo   업데이트 완료!
echo ========================================
echo.
echo 3초 후에 프로그램을 다시 시작합니다.
timeout /t 3 /nobreak > nul
start "" "{os.path.join(application_path, os.path.basename(sys.executable))}"
del "%~f0"
            """)

        subprocess.Popen(updater_script_path, creationflags=subprocess.CREATE_NEW_CONSOLE)
        sys.exit(0)
    except Exception as e:
        root_alert = tk.Tk()
        root_alert.withdraw()
        messagebox.showerror("업데이트 실패", f"업데이트 적용 중 오류가 발생했습니다.\n\n{e}\n\n프로그램을 다시 시작해주세요.", parent=root_alert)
        root_alert.destroy()

def check_and_apply_updates():
    download_url, new_version = check_for_updates()
    if download_url:
        root_alert = tk.Tk()
        root_alert.withdraw()
        if messagebox.askyesno("업데이트 발견", f"새로운 버전({new_version})이 발견되었습니다.\n지금 업데이트하시겠습니까? (현재: {CURRENT_VERSION})", parent=root_alert):
            root_alert.destroy()
            download_and_apply_update(download_url)
        else:
            root_alert.destroy()

# ####################################################################
# # 파일 감시 핸들러 (Watchdog)
# ####################################################################

class LogFileHandler(FileSystemEventHandler):
    def __init__(self, app_instance):
        self.app = app_instance
        self.last_triggered_time = 0

    def on_modified(self, event):
        if time.time() - self.last_triggered_time < 2:
            return
            
        if not event.is_directory and "작업이벤트로그" in os.path.basename(event.src_path):
            self.last_triggered_time = time.time()
            print(f"파일 변경 감지: {event.src_path}")
            self.app.root.event_generate("<<RealtimeDataRefresh>>")

# ####################################################################
# # 메인 어플리케이션
# ####################################################################

matplotlib.use('TkAgg')
try:
    plt.rcParams['font.family'] = 'Malgun Gothic'
except:
    plt.rcParams['font.family'] = 'AppleGothic'
plt.rcParams['axes.unicode_minus'] = False

def resource_path(relative_path: str) -> str:
    try:
        base_path = sys._MEIPASS
    except AttributeError:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

@dataclass
class WorkerPerformance:
    worker: str; avg_work_time: float = 0.0; avg_latency: float = 0.0
    avg_idle_time: float = 0.0; total_process_errors: int = 0
    first_pass_yield: float = 0.0; avg_target_achievement: float = 0.0
    session_count: int = 0; overall_score: float = 0.0
    total_pcs_completed: int = 0; avg_pcs_per_tray: float = 0.0
    work_time_std: float = 0.0
    best_work_time: float = float('inf')
    best_work_time_date: Optional[datetime.date] = None


class DataAnalyzer:
    def __init__(self):
        self.target_times = self._load_target_times()
        if not self.target_times: print("알림: 'assets/TargetTime.csv' 파일이 없어 '목표 달성률' 분석을 건너킵니다.")
        self.raw_event_df: pd.DataFrame = pd.DataFrame()

    def _load_target_times(self) -> Dict[str, float]:
        target_time_path = resource_path(os.path.join('assets', 'TargetTime.csv'))
        if not os.path.exists(target_time_path): return {}
        encodings_to_try = ['utf-8-sig', 'utf-8', 'cp949']
        for encoding in encodings_to_try:
            try:
                with open(target_time_path, 'r', encoding=encoding) as f:
                    reader = csv.DictReader(f)
                    return {str(row['Item Code']): float(row['TargetSec'])
                                     for row in reader
                                     if row.get('Item Code') and row.get('TargetSec') and row['TargetSec'].replace('.', '').isdigit()}
            except Exception:
                continue
        messagebox.showwarning("TargetTime.csv 로드 오류", "목표 시간 파일을 읽는 데 실패했습니다.")
        return {}

    # ### START: MODIFIED METHOD ###
    def load_all_data(self, folder_path: str, process_mode: str, date_filter: Optional[datetime.date] = None) -> pd.DataFrame:
        """
        로그 파일을 로드하는 메서드.
        - date_filter (실시간 모드): `folder_path` (C:\Sync)에서 오늘/어제 로그만 로드.
        - full-load 모드: `folder_path` (C:\Sync)와 `folder_path\log` 하위 모든 폴더를 재귀적으로 검색하여 모든 로그를 로드.
        """
        all_event_data_dfs, target_files = [], []
        
        if date_filter:
            # 실시간 로딩: C:\Sync 폴더만 검색하여 오늘/어제 파일 필터링
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
            # 전체 분석 로딩: C:\Sync 폴더와 C:\Sync\log 하위 모든 폴더 검색
            print(f"전체 데이터 로딩: '{folder_path}' 및 '{os.path.join(folder_path, 'log')}' 하위 폴더를 모두 검색합니다.")
            main_folder_logs = glob.glob(os.path.join(folder_path, '*작업이벤트로그*.csv'))
            
            log_archive_path = os.path.join(folder_path, 'log')
            archived_logs = []
            if os.path.isdir(log_archive_path):
                # 'recursive=True'를 사용하여 모든 하위 디렉토리 탐색
                archived_logs = glob.glob(os.path.join(log_archive_path, '**', '*작업이벤트로그*.csv'), recursive=True)
            
            all_log_files = main_folder_logs + archived_logs
            print(f"총 {len(all_log_files)}개의 로그 파일 발견.")

        # 파일명으로 공정 필터링 (더 명확한 기준으로 변경)
        if process_mode == '포장실':
            target_files = [f for f in all_log_files if '포장실작업이벤트로그' in os.path.basename(f)]
        elif process_mode == '이적실':
            target_files = [f for f in all_log_files if '이적작업이벤트로그' in os.path.basename(f)]
        else: # '전체' 또는 '전체 비교'
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
                # 파일명으로 현재 공정 결정
                filename = os.path.basename(file_path)
                current_process = "이적실" if '이적작업이벤트로그' in filename else "포장실"
                
                if process_mode not in ["전체", "전체 비교"] and (
                    (process_mode == "이적실" and current_process != "이적실") or
                    (process_mode == "포장실" and current_process != "포장실")
                ):
                    continue

                if 'worker_name' in df.columns: df.rename(columns={'worker_name': 'worker'}, inplace=True)
                if 'worker' not in df.columns:
                    # 이적실 로그는 파일명에서 작업자 이름 추출 시도
                    if current_process == "이적실":
                        match = re.search(r'이적작업이벤트로그_([^_]+)_\d{8}\.csv', filename)
                        df['worker'] = match.group(1) if match else 'UNKNOWN_WORKER'
                    else:
                        # 포장실 로그는 파일명에 컴퓨터 ID가 있으므로, CSV 내부 데이터에 의존
                        df['worker'] = 'UNKNOWN_WORKER'
                
                df['worker'], df['process'] = df['worker'].astype(str), current_process
                if not all(h in df.columns for h in ['timestamp', 'event', 'details']): continue
                df['timestamp'] = pd.to_datetime(df['timestamp'], errors='coerce')
                df.dropna(subset=['timestamp'], inplace=True)
                if df.empty: continue
                df['details'] = df['details'].apply(lambda x: json.loads(x) if isinstance(x, str) and x.strip().startswith('{') else {})
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
    # ### END: MODIFIED METHOD ###

    def process_events_to_sessions(self, event_df: pd.DataFrame) -> pd.DataFrame:
        if event_df.empty: return pd.DataFrame()
        completed_trays_df = event_df[event_df['event'] == 'TRAY_COMPLETE'].copy()
        if completed_trays_df.empty: return pd.DataFrame()
        
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
            if row['process'] == '포장실':
                return 60
            else:
                details = row['details']
                return safe_get(details, 'scan_count', 0)

        pcs_completed_values = completed_trays_df.apply(calculate_pcs, axis=1)

        sessions_df = pd.DataFrame({
            'date': completed_trays_df['start_time_dt'].dt.date,
            'start_time_dt': completed_trays_df['start_time_dt'],
            'end_time_dt': completed_trays_df['timestamp'], # ### [MODIFIED] ### Add end time for lead time calculation
            'shipping_date': details_series.apply(lambda d: safe_get(d, 'shipping_date', safe_get(d, 'production_date', pd.NaT))),
            'worker': completed_trays_df['worker'],
            'process': completed_trays_df['process'],
            'item_code': details_series.apply(lambda d: safe_get(d, 'item_code', 'N/A')),
            'item_name': details_series.apply(lambda d: safe_get(d, 'item_name', '')),
            'work_time': details_series.apply(lambda d: safe_get(d, 'work_time_sec', 0.0)),
            'latency': completed_trays_df['latency'],
            'idle_time': details_series.apply(lambda d: safe_get(d, 'total_idle_seconds', 0.0)),
            'process_errors': details_series.apply(lambda d: safe_get(d, 'error_count', 0)),
            'had_error': details_series.apply(lambda d: int(safe_get(d, 'has_error_or_reset', False))),
            'is_partial': details_series.apply(lambda d: safe_get(d, 'is_partial_submission', False)),
            'is_restored': details_series.apply(lambda d: safe_get(d, 'is_restored_session', False)),
            'is_test': details_series.apply(lambda d: safe_get(d, 'is_test_tray', False)),
            'pcs_completed': pcs_completed_values
        })
        
        sessions_df['shipping_date'] = pd.to_datetime(sessions_df['shipping_date'], errors='coerce')
        
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
        df_analyzed = df.copy()
        if self.target_times:
            df_analyzed['target_time'] = df_analyzed['item_code'].astype(str).map(self.target_times).fillna(0.0)
            df_analyzed['target_achievement'] = df_analyzed.apply(lambda r: (r['target_time']/r['work_time'])*100 if r.get('work_time',0)>0 and r.get('target_time',0)>0 else 0, axis=1)
        else:
            df_analyzed['target_achievement'] = 0.0
            
        worker_data = self._calculate_worker_data(df_analyzed, full_sessions_df)
        worker_data, normalized_df = self._calculate_overall_score(worker_data, radar_metrics)
        kpis = self._calculate_kpis(df_analyzed)
        return worker_data, kpis, df_analyzed, normalized_df

    def _calculate_worker_data(self, df, full_sessions_df=None):
        if df.empty: return {}
        grouped = df.groupby('worker')
        if not grouped.groups: return {}
        
        agg_dict = {
            'avg_work_time': ('work_time', 'mean'),
            'work_time_std': ('work_time', 'std'),
            'avg_latency': ('latency', 'mean'),
            'avg_idle_time': ('idle_time', 'mean'),
            'total_process_errors': ('process_errors', 'sum'),
            'first_pass_yield': ('had_error', lambda x: 1 - x.sum() / x.count() if x.count() > 0 else 1.0),
            'session_count': ('worker', 'size'),
            'total_pcs_completed': ('pcs_completed', 'sum')
        }
        if 'target_achievement' in df.columns:
            agg_dict['avg_target_achievement'] = ('target_achievement', 'mean')
            
        worker_summary_df = grouped.agg(**agg_dict).fillna(0)
        
        final_data = {}
        for worker_name, row in worker_summary_df.iterrows():
            best_time = float('inf')
            best_time_date = None
            
            # ### START: 새로운 주간 최고기록 및 동적 필터링 로직 ###
            if full_sessions_df is not None and not full_sessions_df.empty:
                worker_all_sessions = full_sessions_df[full_sessions_df['worker'] == worker_name].copy()
                
                if not worker_all_sessions.empty:
                    worker_all_sessions['date'] = pd.to_datetime(worker_all_sessions['date']).dt.date
                    today = datetime.date.today()

                    # 1. 최근 7일간의 평균 작업시간 계산 (동적 임계값의 기준)
                    seven_days_ago = today - datetime.timedelta(days=7)
                    last_7_days_sessions = worker_all_sessions[
                        (worker_all_sessions['date'] >= seven_days_ago) & (worker_all_sessions['date'] <= today)
                    ]
                    
                    # 평균 계산 시에도 비정상적인 데이터는 제외하여 기준값의 신뢰도 확보
                    clean_last_7_days = last_7_days_sessions[
                        (last_7_days_sessions['pcs_completed'] > 0) &
                        (last_7_days_sessions['had_error'] == 0) &
                        (last_7_days_sessions['is_partial'] == False) &
                        (last_7_days_sessions['is_restored'] == False) &
                        (last_7_days_sessions['is_test'] == False)
                    ]
                    
                    last_week_avg_time = clean_last_7_days['work_time'].mean() if not clean_last_7_days.empty else float('inf')

                    # 2. '금주'의 최고 기록 탐색 (월요일 ~ 현재)
                    start_of_week = today - datetime.timedelta(days=today.weekday()) # 이번 주 월요일
                    current_week_sessions = worker_all_sessions[worker_all_sessions['date'] >= start_of_week]

                    if not current_week_sessions.empty:
                        # 3. 동적 임계값 설정: 평균의 60%와 최소 3분(180초) 중 더 큰 값을 사용
                        MINIMUM_REALISTIC_TIME = 180.0  # 최소 3분
                        DYNAMIC_THRESHOLD_PERCENTAGE = 0.6 # 평균의 60%

                        dynamic_threshold = MINIMUM_REALISTIC_TIME
                        if pd.notna(last_week_avg_time) and last_week_avg_time != float('inf'):
                            dynamic_threshold = max(last_week_avg_time * DYNAMIC_THRESHOLD_PERCENTAGE, MINIMUM_REALISTIC_TIME)

                        # 4. 금주 데이터에 대해 엄격한 필터링 적용 (동적 임계값 포함)
                        clean_sessions_for_best_record = current_week_sessions[
                            (current_week_sessions['pcs_completed'] == 60) &
                            (current_week_sessions['work_time'] >= dynamic_threshold) & # 동적 필터 적용
                            (current_week_sessions['had_error'] == 0) &
                            (current_week_sessions['is_partial'] == False) &
                            (current_week_sessions['is_restored'] == False) &
                            (current_week_sessions['is_test'] == False)
                        ]
                                        
                        if not clean_sessions_for_best_record.empty:
                            best_row = clean_sessions_for_best_record.loc[clean_sessions_for_best_record['work_time'].idxmin()]
                            best_time = best_row['work_time']
                            best_time_date = best_row['date']
            # ### END: 새로운 로직 ###

            s_count, t_pcs = int(row.get('session_count', 0)), int(row.get('total_pcs_completed', 0))
            final_data[str(worker_name)] = WorkerPerformance(
                worker=str(worker_name), session_count=s_count, total_pcs_completed=t_pcs,
                avg_work_time=float(row.get('avg_work_time', 0.0)),
                avg_latency=float(row.get('avg_latency', 0.0)),
                avg_idle_time=float(row.get('avg_idle_time', 0.0)),
                total_process_errors=int(row.get('total_process_errors', 0)),
                first_pass_yield=float(row.get('first_pass_yield', 0.0)),
                avg_target_achievement=float(row.get('avg_target_achievement', 0.0)),
                avg_pcs_per_tray=float(t_pcs / s_count if s_count > 0 else 0),
                work_time_std=float(row.get('work_time_std', 0.0)),
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

        if norm_cols_for_score:
            df['overall_score'] = np.average(df[norm_cols_for_score], axis=1, weights=weights) * 100
        else:
            df['overall_score'] = 0.0

        for _, row in df.iterrows():
            if (wn := str(row['worker'])) in worker_data:
                worker_data[wn].overall_score = float(row['overall_score'])
        
        return worker_data, df

    def _calculate_kpis(self, filtered_df):
        if filtered_df.empty: return {'total_trays':0, 'total_pcs_completed':0, 'avg_pcs_per_tray':0.0, 'avg_tray_time':0.0, 'total_errors':0, 'avg_fpy':0.0, 'avg_latency':0.0}
        total_sessions, total_pcs = len(filtered_df), int(filtered_df['pcs_completed'].sum())
        
        fpy_base = filtered_df[
            (filtered_df['is_test'] == False) & 
            (filtered_df['is_partial'] == False) &
            (filtered_df['is_restored'] == False)
        ]
        fpy_value = (1 - fpy_base['had_error'].mean()) if not fpy_base.empty else 1.0

        return {
            'total_trays': total_sessions, 'total_pcs_completed': total_pcs,
            'avg_pcs_per_tray': total_pcs/total_sessions if total_sessions>0 else 0.0,
            'avg_tray_time': filtered_df['work_time'].mean(),
            'total_errors': int(filtered_df['process_errors'].sum()),
            'avg_fpy': fpy_value,
            'avg_latency': filtered_df['latency'].mean()
        }

class WorkerAnalysisGUI:
    DEFAULT_FONT = 'Malgun Gothic'
    SETTINGS_DIR = 'assets'; SETTINGS_FILE = 'analyzer_settings.json'
    COLOR_BG="#F0F2F5"; COLOR_TEXT="#333333"; COLOR_PRIMARY="#0052CC"; COLOR_SIDEBAR_BG="#FFFFFF"; COLOR_DANGER="#DE350B"; COLOR_SUCCESS="#00875A"; COLOR_TEXT_SUBTLE="#6B778C"; COLOR_BORDER="#DCDFE4"
    COLOR_PALETTE=['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1', '#FF9DA7', '#9C755F', '#BAB0AC']
    
    PACKAGING_RADAR_METRICS = {
        '세트완료시간': ('avg_work_time', False, 1.0),
        '첫스캔준비성': ('avg_latency', False, 1.0),
        '무결점달성률': ('first_pass_yield', True, 0.7), 
        '목표달성률': ('avg_target_achievement', True, 1.0),
        '세트당PCS': ('avg_pcs_per_tray', True, 1.0)
    }
    TRANSFER_RADAR_METRICS = {
        '신속성': ('avg_work_time', False, 1.0),
        '준비성': ('avg_latency', False, 1.0),
        '초도수율': ('first_pass_yield', True, 0.7), 
        '목표달성률': ('avg_target_achievement', True, 1.0),
        '안정성': ('work_time_std', False, 1.0)
    }
    
    RADAR_METRIC_DESCRIPTIONS = {
        '신속성':{'desc':"트레이(세트) 하나를 완료하는 데 걸리는 평균 실작업시간입니다. (낮을수록 좋음)",'calc':"산식: 모든 세션의 'work_time' 합계 / 총 세션 수"},
        '준비성':{'desc':"이전 작업 완료 후 다음 작업을 시작(첫 스캔)하기까지 걸리는 평균 시간입니다. (낮을수록 좋음)",'calc':"산식: 모든 세션의 'latency' 합계 / 총 세션 수"},
        '초도수율':{'desc':"오류나 중간 초기화 없이 한 번에 작업을 완료한 비율입니다. (높을수록 좋음)",'calc':"산식: 1 - (오류 또는 리셋된 세션 수 / 총 세션 수)"},
        '목표달성률':{'desc':"품목별 목표 작업시간(TargetTime.csv) 대비 실제 작업시간의 달성 비율입니다. (높을수록 좋음)",'calc':"산식: (목표시간 / 실제 작업시간) * 100 의 평균"},
        'PCS 효율':{'desc':"하나의 트레이(세트)에 포함된 평균 PCS(제품) 수량입니다.",'calc':"산식: 총 완료 PCS 합계 / 총 세션 수"},
        '안정성': {'desc': "작업시간의 표준편차로, 수치가 낮을수록 편차 없이 일관된 속도로 작업함을 의미합니다. (낮을수록 좋음)", 'calc': "산식: 모든 세션 'work_time'의 표준편차"},
        '세트완료시간':{'desc':"포장 세트 하나를 완료하는 데 걸리는 평균 실작업시간입니다. (낮을수록 좋음)",'calc':"산식: 모든 세션의 'work_time' 합계 / 총 세션 수"},
        '첫스캔준비성':{'desc':"이전 포장 완료 후 다음 포장을 시작(첫 스캔)하기까지 걸리는 평균 시간입니다. (낮을수록 좋음)",'calc':"산식: 모든 세션의 'latency' 합계 / 총 세션 수"},
        '무결점달성률':{'desc':"오류나 중간 초기화 없이 한 번에 포장을 완료한 비율입니다. (높을수록 좋음)",'calc':"산식: 1 - (오류 또는 리셋된 세션 수 / 총 세션 수)"},
        '세트당PCS':{'desc':"하나의 포장 세트에 포함된 평균 PCS(제품) 수량입니다.",'calc':"산식: 총 완료 PCS 합계 / 총 세션 수"}
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        
        self.analyzer = DataAnalyzer()
        self.paned_windows: Dict[str, ttk.PanedWindow] = {}
        self.scale_factor, self.column_widths, window_geometry, self.pane_positions = self.load_settings() 
        self.root.title(f"성과 분석 대시보드 v{CURRENT_VERSION}")
        self.root.geometry(window_geometry)

        self.root.minsize(1280, 800); self.root.configure(bg=self.COLOR_BG)
        self.process_mode_var = tk.StringVar(value="이적실")
        self.log_folder_path = "C:\\Sync"; os.makedirs(self.log_folder_path, exist_ok=True)
        
        self.full_df, self.filtered_df_raw = pd.DataFrame(), pd.DataFrame()
        self.worker_data, self.kpis = {}, {}; self.normalized_df, self.currently_displayed_table_df = pd.DataFrame(), pd.DataFrame()
        self.style = ttk.Style(); self.style.theme_use('clam')
        
        self.production_summary_period_var = tk.StringVar(value="일간")
        self.packaging_period_var = tk.StringVar(value="최근 10일 (일별)")
        self.packaging_content_frame = None
        self.shipping_date_tab_frame = None
        self.error_log_tab_frame = None
        
        self.worker_sort_option_var = tk.StringVar(value="종합 점수 높은 순")
        
        self.comparison_period_mode_var = tk.StringVar(value="금일 비교")
        self.comparison_start_date_entry = None
        self.comparison_end_date_entry = None
        self.comparison_content_frame = None
        
        self.auto_refresh_id = None
        self.AUTO_REFRESH_INTERVAL = 300000 
        
        self.observer = None
        self.monitor_thread = None

        self._setup_ui()
        self.apply_scaling()
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.root.after(100, self._initial_load)
        
        self._start_file_monitor()

    def _initial_load(self): 
        self.run_analysis(load_new_data=True)

    def load_settings(self) -> Tuple[float, Dict[str, int], str, Dict[str, int]]:
        path = resource_path(os.path.join(self.SETTINGS_DIR, self.SETTINGS_FILE))
        try:
            with open(path, 'r', encoding='utf-8') as f:
                settings = json.load(f)
            scale_factor = float(settings.get('scale_factor', 1.0))
            column_widths = settings.get('column_widths', {})
            window_geometry = settings.get('window_geometry', "1600x950")
            
            pane_positions = settings.get('pane_positions', {})
            if not pane_positions and 'pane_position' in settings:
                pane_positions['main'] = int(settings.get('pane_position', 350))

            return scale_factor, column_widths, window_geometry, pane_positions
        except (FileNotFoundError, json.JSONDecodeError, KeyError, ValueError):
            return 1.0, {}, "1600x950", {'main': 350}

    def save_settings(self):
        path = resource_path(os.path.join(self.SETTINGS_DIR, self.SETTINGS_FILE))
        os.makedirs(os.path.dirname(path), exist_ok=True)
        
        for name, pane in self.paned_windows.items():
            if pane.winfo_exists():
                try:
                    self.pane_positions[name] = pane.sashpos(0)
                except tk.TclError:
                    print(f"Warning: Could not get sash position for pane '{name}'.")

        try:
            settings = {
                'scale_factor': self.scale_factor,
                'column_widths': self.column_widths,
                'window_geometry': self.root.geometry(),
                'pane_positions': self.pane_positions
            }
            with open(path, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=4, ensure_ascii=False)
        except Exception as e:
            print(f"설정 저장 실패: {e}")

    def change_scale(self, delta):
        self.scale_factor = max(0.8, min(2.0, self.scale_factor + delta))
        self.apply_scaling(); self._update_main_view()

    def apply_scaling(self):
        s,m,l,xl = (int(base*self.scale_factor) for base in [11,12,16,24])
        font_main,font_title,font_xl,font_button = (self.DEFAULT_FONT,m),(self.DEFAULT_FONT,l,"bold"),(self.DEFAULT_FONT,xl,"bold"),(self.DEFAULT_FONT,m,"bold")
        
        plt.rcParams['font.size'] = s
        
        self.style.configure('TFrame',background=self.COLOR_BG)
        self.style.configure('Sidebar.TFrame',background=self.COLOR_SIDEBAR_BG)
        self.style.configure('Card.TFrame',background=self.COLOR_SIDEBAR_BG,relief='solid',borderwidth=1,bordercolor=self.COLOR_BORDER)
        self.style.configure('TLabel',font=font_main,background=self.COLOR_BG,foreground=self.COLOR_TEXT)
        self.style.configure('Sidebar.TLabel',font=font_main,background=self.COLOR_SIDEBAR_BG)
        self.style.configure('Header.TLabel',font=font_title,background=self.COLOR_SIDEBAR_BG)
        self.style.configure('CardTitle.TLabel',font=(self.DEFAULT_FONT,s),background=self.COLOR_SIDEBAR_BG,foreground=self.COLOR_TEXT_SUBTLE)
        self.style.configure('CardValue.TLabel',font=font_xl,background=self.COLOR_SIDEBAR_BG)
        self.style.configure('BestRecord.TLabel', font=(self.DEFAULT_FONT, int(s*0.9)), background=self.COLOR_SIDEBAR_BG, foreground=self.COLOR_SUCCESS)
        self.style.configure('TButton',font=font_button,padding=(int(10*self.scale_factor),int(8*self.scale_factor)))
        self.style.map('TButton',background=[('!active',self.COLOR_PRIMARY),('active','#00419E')],foreground=[('!active','white')])
        self.style.configure('Small.TButton',font=(self.DEFAULT_FONT,s),padding=(4,4))
        self.style.configure('TRadiobutton',font=font_main,background=self.COLOR_BG)
        self.style.configure('Sidebar.TRadiobutton',font=font_main,background=self.COLOR_SIDEBAR_BG)
        self.style.configure('TNotebook',background=self.COLOR_BG,borderwidth=0)
        self.style.configure('TNotebook.Tab',font=font_main,padding=(15,8),borderwidth=0)
        self.style.map('TNotebook.Tab',background=[('selected',self.COLOR_BG),('!selected','#EAEBEE')],foreground=[('selected',self.COLOR_PRIMARY)])
        self.style.configure("Treeview",rowheight=int(28*self.scale_factor),font=font_main)
        self.style.configure("Treeview.Heading",font=font_button,padding=(5,8))
        self.style.configure("Odd.Treeview",background="#F0F2F5")
        self.style.configure('Total.Treeview', background='#DDEEFF', font=(self.DEFAULT_FONT, m, 'bold'))
        self.style.configure('GreenRow.Treeview', background='#e8f5e9')
        self.style.configure('RedRow.Treeview', background='#ffebee')
        
        self.style.configure('Loading.TFrame', background='black')
        self.style.configure('Loading.TLabel', background='black', foreground='white')

    def _setup_ui(self, parent_frame=None):
        top_control_frame=ttk.Frame(self.root,style='TFrame',padding=(10,5)); top_control_frame.pack(fill=tk.X,side=tk.TOP)
        ttk.Label(top_control_frame,text=f"{CURRENT_VERSION}").pack(side=tk.LEFT)
        font_frame=ttk.Frame(top_control_frame,style='TFrame'); font_frame.pack(side=tk.RIGHT)
        ttk.Label(font_frame,text="글자 크기:").pack(side=tk.LEFT,padx=5)
        ttk.Button(font_frame,text="-",command=lambda:self.change_scale(-0.1),width=3,style='Small.TButton').pack(side=tk.LEFT)
        ttk.Button(font_frame,text="+",command=lambda:self.change_scale(0.1),width=3,style='Small.TButton').pack(side=tk.LEFT,padx=2)

        self.main_pane=ttk.PanedWindow(self.root,orient=tk.HORIZONTAL); self.main_pane.pack(fill=tk.BOTH,expand=True)
        self.paned_windows['main'] = self.main_pane
        
        sidebar=ttk.Frame(self.main_pane,style='Sidebar.TFrame')
        self.main_pane.add(sidebar,weight=0)
        
        content=ttk.Frame(self.main_pane); self.main_pane.add(content,weight=1)
        
        def set_sash_position():
            self.root.update_idletasks() 
            pos = self.pane_positions.get('main', max(350, self.main_pane.winfo_width() // 4))
            if self.main_pane.winfo_width() > 0:
                self.main_pane.sashpos(0, pos)

        self.root.after(50, set_sash_position)
        
        sidebar.bind("<Configure>", self._on_sidebar_resize)

        self.content_area = ttk.Frame(content, style='TFrame', padding=(10, 5))
        self.content_area.pack(fill=tk.BOTH, expand=True)

        self._setup_sidebar_widgets(sidebar)
        
        self.loading_overlay = ttk.Frame(self.root, style='Card.TFrame', relief='solid', borderwidth=1)
        loading_label = ttk.Label(self.loading_overlay, text="분석 중... ⏳", font=(self.DEFAULT_FONT, 18, "bold"), style='CardTitle.TLabel', background=self.COLOR_SIDEBAR_BG)
        loading_label.pack(pady=30, padx=50)
        
    def _on_sidebar_resize(self, event):
        if hasattr(self, 'log_folder_label') and self.log_folder_label:
            self.log_folder_label.config(wraplength=event.width - 40)
            
    def _setup_sidebar_widgets(self,parent):
        container=ttk.Frame(parent,padding=20,style='Sidebar.TFrame'); container.pack(fill=tk.BOTH,expand=True)
        mode_frame=ttk.LabelFrame(container,text="공정 선택 (분석용)",style="Card.TFrame",padding=10); mode_frame.pack(fill=tk.X,pady=(0,20))
        ttk.Radiobutton(mode_frame,text="이적실 분석",variable=self.process_mode_var,value="이적실",command=self._on_mode_change, style='Sidebar.TRadiobutton').pack(anchor='w')
        ttk.Radiobutton(mode_frame,text="포장실 분석",variable=self.process_mode_var,value="포장실",command=self._on_mode_change, style='Sidebar.TRadiobutton').pack(anchor='w',pady=(5,0))
        ttk.Radiobutton(mode_frame,text="전체 비교",variable=self.process_mode_var,value="전체 비교",command=self._on_mode_change, style='Sidebar.TRadiobutton').pack(anchor='w',pady=(5,0))
        
        self.log_folder_label = ttk.Label(container,text=f"로그 폴더: {self.log_folder_path}",style='Sidebar.TLabel')
        self.log_folder_label.pack(anchor='w',pady=(0,10), fill=tk.X)
        
        ttk.Label(container,text="📅 분석 기간",style='Sidebar.TLabel').pack(anchor='w',pady=(10,5))
        today=datetime.date.today()
        self.start_date_entry=DateEntry(container,width=15,date_pattern='y-mm-dd',year=today.year,month=today.month,day=1); self.start_date_entry.pack(fill=tk.X,pady=2)
        ttk.Label(container,text="~",style='Sidebar.TLabel').pack(pady=2)
        self.end_date_entry=DateEntry(container,width=15,date_pattern='y-mm-dd'); self.end_date_entry.pack(fill=tk.X,pady=2)

        ttk.Label(container,text="👥 작업자",style='Sidebar.TLabel').pack(anchor='w',pady=(15,5))
        worker_frame=ttk.Frame(container,style='Sidebar.TFrame'); worker_frame.pack(fill=tk.BOTH,expand=True)
        self.worker_listbox=tk.Listbox(worker_frame,selectmode=tk.EXTENDED,exportselection=False,relief='flat',bg=self.COLOR_BG,highlightthickness=1,highlightbackground=self.COLOR_BORDER); self.worker_listbox.pack(fill=tk.BOTH,expand=True)

        self.run_button=ttk.Button(container,text="📊 수동 분석 실행",command=self.run_analysis,state=tk.DISABLED)
        self.run_button.pack(fill=tk.X, pady=(10, 5), ipady=8)
        ttk.Button(container, text="🔄 필터 초기화", command=self._reset_filters, style='TButton').pack(fill=tk.X, ipady=5)

    def _reset_filters(self):
        if self.full_df.empty and self.run_button['state'] == tk.DISABLED:
            messagebox.showinfo("알림", "먼저 데이터 로딩이 완료되어야 합니다.")
            return

        if not self.full_df.empty:
            self._populate_filters(was_new_load=True)
            self.run_analysis(load_new_data=False)
        else:
            self.run_analysis(load_new_data=True)

    def _on_mode_change(self):
        if self.process_mode_var.get() == "포장실":
            self.packaging_period_var.set("최근 10일 (일별)")
        elif self.process_mode_var.get() == "이적실":
            self.production_summary_period_var.set("일간")
        elif self.process_mode_var.get() == "전체 비교":
            self.comparison_period_mode_var.set("금일 비교")
            
        self.full_df=pd.DataFrame(); 
        self._clear_content_area(show_message=False)
        self.run_analysis(load_new_data=True)
    
    def _auto_refresh_data(self):
        print(f"[{datetime.datetime.now()}] 자동 새로고침을 시작합니다...")
        self.run_analysis(load_new_data=True, is_auto_refresh=True)

    def run_analysis(self, load_new_data=False, is_auto_refresh=False):
        if not os.path.isdir(self.log_folder_path) and not is_auto_refresh:
            messagebox.showwarning("폴더 오류", f"로그 폴더 '{self.log_folder_path}'를 찾을 수 없습니다.")
            return
            
        self.loading_overlay.place(relx=0.5, rely=0.5, anchor=tk.CENTER)
        self.loading_overlay.lift()
        self.root.config(cursor="watch")
        self.run_button['state'] = tk.DISABLED
        
        mode = self.process_mode_var.get()
        if mode == "포장실":
                         self.RADAR_METRICS = self.PACKAGING_RADAR_METRICS
        else:
                         self.RADAR_METRICS = self.TRANSFER_RADAR_METRICS

        start_date, end_date = self.start_date_entry.get_date(), self.end_date_entry.get_date()
        selected_workers = [self.worker_listbox.get(i) for i in self.worker_listbox.curselection()]
        threading.Thread(target=self._perform_full_analysis_thread, args=(load_new_data, self.log_folder_path, mode, start_date, end_date, selected_workers), daemon=True).start()

    def _perform_full_analysis_thread(self,load_new_data,folder_path,process_mode,start_date,end_date,workers):
        try:
            df = self.analyzer.load_all_data(folder_path,process_mode) if load_new_data or self.full_df.empty else self.full_df

            if df.empty: raise ValueError("분석할 세션 데이터가 없습니다.")
            
            df['date'] = pd.to_datetime(df['date'], errors='coerce')
            df.dropna(subset=['date'], inplace=True)
            if df.empty: raise ValueError("로그 파일에서 유효한 날짜를 가진 데이터를 찾을 수 없습니다.")

            if load_new_data:
                s, e = df['date'].min(), df['date'].max()
                w = sorted(df['worker'].astype(str).unique().tolist())
            else:
                s,e,w=start_date,end_date,workers
            
            filtered=self.analyzer.filter_data(df.copy(),s,e,w)
            
            if filtered.empty:
                result=(df, pd.DataFrame(), {}, {}, pd.DataFrame())
            else:
                w_perf,kpis,a_log,n_perf = self.analyzer.analyze_dataframe(filtered, self.RADAR_METRICS, full_sessions_df=df)
                result=(df,a_log,w_perf,kpis,n_perf)
            
            self.root.after(0,self._process_analysis_results,result,None,load_new_data)
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.root.after(0,self._process_analysis_results,None,str(e),load_new_data)

    def _process_analysis_results(self,result,error,was_new_load):
        try:
            mode=self.process_mode_var.get(); self.root.title(f"성과 분석 대시보드 v{CURRENT_VERSION} - {mode}")
            if error:
                messagebox.showerror("분석 오류",f"데이터 분석 중 오류가 발생했습니다.\n\n{error}")
                self.full_df=pd.DataFrame()
                self._populate_filters()
                self._clear_content_area(show_message=True)
                return
            
            if result:
                self.full_df,self.filtered_df_raw,self.worker_data,self.kpis,self.normalized_df = result
                self.full_df = self.full_df if self.full_df is not None else pd.DataFrame()
                self.filtered_df_raw = self.filtered_df_raw if self.filtered_df_raw is not None else pd.DataFrame()
                self.worker_data = self.worker_data if self.worker_data else {}
                self.kpis = self.kpis if self.kpis else {}
                self.normalized_df = self.normalized_df if self.normalized_df is not None else pd.DataFrame()

                if was_new_load: self._populate_filters(was_new_load=True)
                self._update_main_view()
                
                if self.auto_refresh_id:
                    self.root.after_cancel(self.auto_refresh_id)
                self.auto_refresh_id = self.root.after(self.AUTO_REFRESH_INTERVAL, self._auto_refresh_data)
            else:
                messagebox.showwarning("분석 결과 없음", "분석 결과가 유효하지 않습니다.")
                self.full_df=pd.DataFrame()
                self._populate_filters()
                self._clear_content_area(show_message=True)

        finally:
            self.run_button['state']=tk.NORMAL
            self.run_button['text']="📊 수동 분석 실행"
            self.root.config(cursor="")
            self.loading_overlay.place_forget()

    def _populate_filters(self,was_new_load=False):
        if self.full_df.empty:
            self.worker_listbox.delete(0,tk.END)
            today = datetime.date.today()
            self.start_date_entry.set_date(today.replace(day=1))
            self.end_date_entry.set_date(today)
            return

        current_workers={self.worker_listbox.get(i) for i in self.worker_listbox.curselection()}
        self.worker_listbox.delete(0,tk.END)
        workers=sorted(self.full_df['worker'].astype(str).unique().tolist())
        for worker in workers: self.worker_listbox.insert(tk.END,worker)

        if workers:
            if was_new_load or not current_workers: self.worker_listbox.selection_set(0,tk.END)
            else:
                for i,worker in enumerate(workers):
                    if worker in current_workers: self.worker_listbox.selection_set(i)
        
        if was_new_load and not self.full_df.empty and 'date' in self.full_df.columns:
            min_d,max_d=self.full_df['date'].min(),self.full_df['date'].max()
            if pd.notna(min_d) and pd.notna(max_d):
                if isinstance(min_d, pd.Timestamp): min_d = min_d.date()
                if isinstance(max_d, pd.Timestamp): max_d = max_d.date()
                self.start_date_entry.set_date(min_d); self.end_date_entry.set_date(max_d)

    def _format_seconds(self,seconds):
        if seconds is None or pd.isna(seconds) or seconds == float('inf'): return "N/A"
        if seconds>=60: m,s=divmod(seconds,60); return f"{int(m)}분 {int(s)}초"
        return f"{seconds:.1f}초"

    # ### [NEW] ### Helper function to format lead time in seconds to a readable string
    def _format_lead_time(self, seconds: float) -> str:
        """ Formats seconds into a 'X days Y hours Z minutes' string. """
        if seconds is None or pd.isna(seconds) or seconds < 0:
            return "N/A"
        
        seconds = int(seconds)
        if seconds < 60:
            return f"{seconds}초"
        
        days, remainder = divmod(seconds, 86400)
        hours, remainder = divmod(remainder, 3600)
        minutes, _ = divmod(remainder, 60)
        
        parts = []
        if days > 0:
            parts.append(f"{days}일")
        if hours > 0:
            parts.append(f"{hours}시간")
        if minutes > 0:
            parts.append(f"{minutes}분")
        
        return " ".join(parts) if parts else "1분 미만"

    def _clear_tab(self,tab):
        for widget in tab.winfo_children(): widget.destroy()

    def _clear_content_area(self,show_message=False):
        self._clear_tab(self.content_area)
        if show_message: 
            ttk.Label(self.content_area,text="좌측 메뉴에서 필터를 설정하고 '분석 실행'을 눌러주세요.",font=(self.DEFAULT_FONT,16),justify='center',foreground=self.COLOR_TEXT_SUBTLE,wraplength=500).pack(expand=True)
    
    def _update_main_view(self):
        self._clear_content_area()

        notebook = ttk.Notebook(self.content_area, style='TNotebook')
        notebook.pack(fill=tk.BOTH, expand=True, padx=0, pady=0)

        mode = self.process_mode_var.get()

        self.realtime_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.production_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.detail_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.data_table_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.comparison_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.shipping_date_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)
        self.error_log_tab_frame = ttk.Frame(notebook, style='TFrame', padding=10)

        if mode == "포장실":
            notebook.add(self.realtime_tab_frame, text="🔴 실시간 현황")
            notebook.add(self.production_tab_frame, text="📈 생산량 추이 분석")
            notebook.add(self.shipping_date_tab_frame, text="📅 출고날짜별 분석")
            notebook.add(self.error_log_tab_frame, text="❗ 오류 로그")
            notebook.add(self.data_table_tab_frame, text="📋 상세 데이터") 
        elif mode == "전체 비교":
            notebook.add(self.comparison_tab_frame, text="⚖️ 이적-포장 비교 분석")
            notebook.add(self.data_table_tab_frame, text="📋 상세 데이터")
        else: # 이적실
            notebook.add(self.realtime_tab_frame, text="🔴 실시간 현황")
            notebook.add(self.production_tab_frame, text="📈 생산량 분석")
            notebook.add(self.detail_tab_frame, text="👥 작업자별 분석")
            notebook.add(self.data_table_tab_frame, text="📋 상세 데이터")

        notebook.bind("<<NotebookTabChanged>>", self._on_tab_changed)
        self.root.after(100, lambda: self._draw_current_tab_content(notebook))

    def _on_tab_changed(self, event):
        selected_tab_id = event.widget.select()
        selected_tab_widget = event.widget.nametowidget(selected_tab_id)
        self._draw_current_tab_content(event.widget, selected_tab_widget)

    def _draw_current_tab_content(self, notebook, selected_tab_widget=None):
        if not selected_tab_widget:
            try:
                selected_tab_id = notebook.select()
                if not selected_tab_id: return
                selected_tab_widget = notebook.nametowidget(selected_tab_id)
            except tk.TclError:
                return

        self._clear_tab(selected_tab_widget)
        
        mode = self.process_mode_var.get()

        if selected_tab_widget == self.realtime_tab_frame:
            self._draw_realtime_tab_content(self.realtime_tab_frame)
        elif selected_tab_widget == self.production_tab_frame:
            if mode == "포장실":
                self._draw_simplified_packaging_production_view(self.production_tab_frame)
            else:
                self._draw_production_main_tab(self.production_tab_frame)
        elif selected_tab_widget == self.shipping_date_tab_frame and mode == "포장실":
            self._draw_shipping_date_tab(self.shipping_date_tab_frame)
        elif selected_tab_widget == self.error_log_tab_frame and mode == "포장실":
            self._draw_error_log_tab(self.error_log_tab_frame)
        elif selected_tab_widget == self.detail_tab_frame and mode not in ["포장실", "전체 비교"]:
            self._draw_detailed_tab(self.detail_tab_frame)
        elif selected_tab_widget == self.comparison_tab_frame and mode == "전체 비교":
            self._draw_overall_comparison_tab(self.comparison_tab_frame)
        elif selected_tab_widget == self.data_table_tab_frame:
            self._draw_data_table_tab(self.data_table_tab_frame)
            self._repopulate_data_table(self.filtered_df_raw)

    def _draw_shipping_date_tab(self, parent):
        self._clear_tab(parent)
        
        df = self.filtered_df_raw.copy()
        if df.empty or 'shipping_date' not in df.columns or df['shipping_date'].isnull().all():
            ttk.Label(parent, text="표시할 출고날짜 데이터가 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        df.dropna(subset=['shipping_date'], inplace=True)
        df['shipping_date_str'] = pd.to_datetime(df['shipping_date']).dt.strftime('%Y-%m-%d')
        
        # 최근 7일 출고 날짜만 필터링 (정렬 후 상위 7개)
        unique_dates = sorted(df['shipping_date_str'].unique(), reverse=True)[:7]
        df = df[df['shipping_date_str'].isin(unique_dates)]
        
        if df.empty:
            ttk.Label(parent, text="최근 7일 내 출고 데이터가 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        # 피벗 테이블 생성: 행=품목명, 컬럼=출고날짜, 값=PCS 합계
        pivot = df.pivot_table(index='item_name', columns='shipping_date_str', values='pcs_completed', aggfunc='sum', fill_value=0)
        pivot = pivot[unique_dates]  # 컬럼을 최근 7일로 제한
        pivot['총 PCS'] = pivot.sum(axis=1)
        pivot['총 Pallets'] = pivot['총 PCS'] / 60.0
        
        # 총계 행 추가
        total_row = pivot.sum(numeric_only=True).to_frame().T
        total_row.index = ['총계']
        pivot = pd.concat([pivot, total_row])

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명'] + unique_dates + ['총 PCS', '총 Pallets']
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")

        tree.heading('품목명', text='품목명', anchor='w', command=lambda: self._sort_treeview(tree, '품목명', False))
        tree.column('품목명', width=200, anchor='w', stretch=tk.YES)

        for date_col in unique_dates:
            tree.heading(date_col, text=date_col, anchor='e', command=lambda c=date_col: self._sort_treeview(tree, c, False))
            tree.column(date_col, width=100, anchor='e', stretch=tk.NO)

        tree.heading('총 PCS', text='총 PCS', anchor='e', command=lambda: self._sort_treeview(tree, '총 PCS', False))
        tree.column('총 PCS', width=120, anchor='e', stretch=tk.NO)

        tree.heading('총 Pallets', text='총 Pallets', anchor='e', command=lambda: self._sort_treeview(tree, '총 Pallets', False))
        tree.column('총 Pallets', width=120, anchor='e', stretch=tk.NO)

        for i, (item_name, row) in enumerate(pivot.iterrows()):
            values = [item_name] + [f"{int(row.get(date, 0)):,}" for date in unique_dates] + [f"{int(row['총 PCS']):,}", f"{row['총 Pallets']:.1f}"]
            tags = ("oddrow" if i % 2 else "",)
            if item_name == '총계':
                tags = ('Total.Treeview',)
            tree.insert('', 'end', values=values, tags=tags)

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(side='left', fill='both', expand=True)

    def _draw_error_log_tab(self, parent):
        self._clear_tab(parent)
        
        raw_events = self.analyzer.raw_event_df.copy()
        if raw_events.empty:
            ttk.Label(parent, text="분석할 로그 데이터가 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        # 현재 필터링된 기간과 작업자로 원본 로그를 필터링
        start_date, end_date = self.start_date_entry.get_date(), self.end_date_entry.get_date()
        selected_workers = [self.worker_listbox.get(i) for i in self.worker_listbox.curselection()]
        
        raw_events['date_only'] = pd.to_datetime(raw_events['timestamp']).dt.date
        mask = (raw_events['date_only'] >= start_date) & (raw_events['date_only'] <= end_date)
        if selected_workers:
            mask &= raw_events['worker'].isin(selected_workers)
        
        df_filtered_logs = raw_events[mask]

        error_events = ['ERROR_INPUT', 'ERROR_MISMATCH', 'SET_CANCELLED']
        df_errors = df_filtered_logs[df_filtered_logs['event'].isin(error_events)].sort_values(by='timestamp', ascending=False)

        if df_errors.empty:
            ttk.Label(parent, text="선택된 기간/작업자에 해당하는 오류 기록이 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['시간', '작업자', '오류 유형', '오류 내용', '상세 정보']
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")

        tree.heading('시간', text='시간', anchor='w', command=lambda: self._sort_treeview(tree, '시간', False))
        tree.heading('작업자', text='작업자', anchor='center', command=lambda: self._sort_treeview(tree, '작업자', False))
        tree.heading('오류 유형', text='오류 유형', anchor='center', command=lambda: self._sort_treeview(tree, '오류 유형', False))
        tree.heading('오류 내용', text='오류 내용', anchor='w', command=lambda: self._sort_treeview(tree, '오류 내용', False))
        tree.heading('상세 정보', text='상세 정보', anchor='w', command=lambda: self._sort_treeview(tree, '상세 정보', False))

        tree.column('시간', width=160, anchor='w', stretch=tk.NO)
        tree.column('작업자', width=100, anchor='center', stretch=tk.NO)
        tree.column('오류 유형', width=120, anchor='center', stretch=tk.NO)
        tree.column('오류 내용', width=250, anchor='w', stretch=tk.YES)
        tree.column('상세 정보', width=350, anchor='w', stretch=tk.YES)

        for i, row in df_errors.iterrows():
            details = row['details']
            event = row['event']
            
            reason, detail_info = "", ""
            if event == 'ERROR_INPUT':
                reason = details.get('reason', 'N/A')
                detail_info = f"입력값: {details.get('raw', '')}"
            elif event == 'ERROR_MISMATCH':
                reason = "현품표 불일치"
                detail_info = f"입력: {details.get('edited', '')}, 기준: {details.get('master', '')}"
            elif event == 'SET_CANCELLED':
                reason = "사용자 세트 취소"
                detail_info = f"취소된 세트 ID: {details.get('set_id', '')}"
            
            tree.insert('', 'end', values=[
                pd.to_datetime(row['timestamp']).strftime('%Y-%m-%d %H:%M:%S'),
                row['worker'],
                event,
                reason,
                detail_info
            ], tags=("oddrow" if i % 2 else "",))
        
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(side='left', fill='both', expand=True)

    def _draw_simplified_packaging_production_view(self, parent):
        self._clear_tab(parent)
        
        control_frame = ttk.Frame(parent, style='TFrame')
        control_frame.pack(fill=tk.X, pady=(0, 10))

        periods = ["최근 10일 (일별)", "최근 1달 (주별)", "최근 6개월 (월별)"]
        for period in periods:
            ttk.Radiobutton(control_frame, text=period, variable=self.packaging_period_var, 
                            value=period, command=self._update_packaging_production_view_content).pack(side=tk.LEFT, padx=5)

        self.packaging_content_frame = ttk.Frame(parent, style='TFrame')
        self.packaging_content_frame.pack(fill=tk.BOTH, expand=True)

        self._update_packaging_production_view_content()

    def _update_packaging_production_view_content(self):
        if not hasattr(self, 'packaging_content_frame') or not self.packaging_content_frame.winfo_exists():
            return
            
        self._clear_tab(self.packaging_content_frame)

        period_type = self.packaging_period_var.get()
        base_df = self.filtered_df_raw.copy()
        
        if base_df.empty:
            ttk.Label(self.packaging_content_frame, text="표시할 데이터가 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        base_df['date_dt'] = pd.to_datetime(base_df['date'], errors='coerce')
        base_df.dropna(subset=['date_dt'], inplace=True)
        today = pd.to_datetime(datetime.date.today())

        if period_type == "최근 10일 (일별)":
            start_date = today - pd.to_timedelta('9D')
            df_to_display = base_df[base_df['date_dt'] >= start_date]
            chart_period_label, chart_grouping = "일간", "D"
        elif period_type == "최근 1달 (주별)":
            start_date = today - pd.to_timedelta('30D')
            df_to_display = base_df[base_df['date_dt'] >= start_date]
            chart_period_label, chart_grouping = "주간", "W"
        else: # "최근 6개월 (월별)"
            start_date = today - pd.DateOffset(months=6)
            df_to_display = base_df[base_df['date_dt'] >= start_date]
            chart_period_label, chart_grouping = "월간", "M"

        if df_to_display.empty:
            ttk.Label(self.packaging_content_frame, text="해당 기간에 표시할 데이터가 없습니다.", font=(self.DEFAULT_FONT, 16), justify='center', foreground=self.COLOR_TEXT_SUBTLE).pack(expand=True)
            return

        pane_name = "packaging_prod"
        main_pane = ttk.PanedWindow(self.packaging_content_frame, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True)
        self.paned_windows[pane_name] = main_pane

        chart_frame = ttk.Frame(main_pane, style='TFrame')
        main_pane.add(chart_frame, weight=1)
        self._draw_daily_production_chart(chart_frame, df_to_display, f"날짜별 총 생산량 추이 ({chart_period_label})", period_type=chart_grouping) 

        table_frame = ttk.Frame(main_pane, style='TFrame')
        main_pane.add(table_frame, weight=1)
        self._draw_item_summary_table(table_frame, df_to_display)

        self.root.update_idletasks()
        main_pane.after(10, lambda p=main_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 2, 100))))

    def _create_dashboard_card(self, parent, title, value, icon, value_color=None, best_record_text=None):
        card=ttk.Frame(parent,style='Card.TFrame',padding=20)
        
        header_frame = ttk.Frame(card, style='Card.TFrame')
        header_frame.pack(fill=tk.X)
        ttk.Label(header_frame,text=icon,style='CardTitle.TLabel',font=("",int(20*self.scale_factor))).pack(side=tk.LEFT, anchor='n')
        
        title_value_frame = ttk.Frame(header_frame, style='Card.TFrame')
        title_value_frame.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(10, 0))

        ttk.Label(title_value_frame,text=title,style='CardTitle.TLabel').pack(anchor='w')
        
        value_frame = ttk.Frame(title_value_frame, style='Card.TFrame')
        value_frame.pack(anchor='w', fill=tk.X)
        
        lbl=ttk.Label(value_frame,text=value,style='CardValue.TLabel'); lbl.pack(side=tk.LEFT, anchor='w')
        if value_color: lbl.configure(foreground=value_color)
        
        if best_record_text:
            best_lbl = ttk.Label(value_frame, text=best_record_text, style='BestRecord.TLabel')
            best_lbl.pack(side=tk.LEFT, anchor='s', padx=(10, 0), pady=(0, 5))
        
        return card

    def _draw_daily_production_chart(self,parent, df_to_use, title, period_type="D"):
        self._clear_tab(parent)
        ttk.Label(parent,text=title,style='Header.TLabel').pack(anchor='w',pady=(0,10))
        fig=Figure(figsize=(8,4),dpi=100,facecolor=self.COLOR_SIDEBAR_BG); ax=fig.add_subplot(111)
        
        if not df_to_use.empty and 'date_dt' in df_to_use.columns and 'pcs_completed' in df_to_use.columns:
            temp_df = df_to_use.copy()
            
            temp_df.set_index('date_dt', inplace=True)
            grouped_data = temp_df.resample(period_type)['pcs_completed'].sum()

            if not grouped_data.empty:
                x_labels = []
                if period_type == "W":
                    x_labels = [f"{d.strftime('%Y-W%U')}" for d in grouped_data.index]
                    ax.set_xlabel("주간")
                elif period_type == "M":
                    x_labels = [f"{d.strftime('%Y-%m')}" for d in grouped_data.index]
                    ax.set_xlabel("월간")
                else: # "D"
                    x_labels = [f"{d.strftime('%m-%d')}" for d in grouped_data.index]
                    ax.set_xlabel("날짜")
                
                ax.plot(grouped_data.index, grouped_data.values, color=self.COLOR_PRIMARY, marker='o', zorder=3)
                ax.fill_between(grouped_data.index, grouped_data.values, color=self.COLOR_PRIMARY, alpha=0.1)
            
                ax.set_xticks(grouped_data.index)
                ax.set_xticklabels(x_labels, rotation=45, ha='right')

        ax.set_ylabel("총 생산량 (PCS)"); ax.spines[['right','top']].set_visible(False)
        ax.grid(True,which='both',linestyle='--',linewidth=0.5,zorder=0); ax.set_facecolor(self.COLOR_SIDEBAR_BG); fig.tight_layout()
        FigureCanvasTkAgg(fig,master=parent).get_tk_widget().pack(fill=tk.BOTH,expand=True)
    
    def _draw_speed_accuracy_scatter(self,parent):
        ttk.Label(parent,text="작업자 유형 분석 (신속성-정확성)",style='Header.TLabel').pack(anchor='w',pady=(0,10))
        fig=Figure(figsize=(8,6),dpi=100,facecolor=self.COLOR_SIDEBAR_BG); ax=fig.add_subplot(111)
        df=self.normalized_df
        
        if df is not None and not df.empty and 'avg_work_time_norm' in df.columns and 'first_pass_yield_norm' in df.columns:
            df['speed_score'] = df['avg_work_time_norm'] * 100
            df['accuracy_score'] = df['first_pass_yield_norm'] * 100
            
            x, y = df['speed_score'], df['accuracy_score']
            ax.scatter(x, y, color=self.COLOR_PRIMARY, s=100, alpha=0.7, zorder=3)
            for i, txt in enumerate(df['worker']): 
                if pd.notna(x.iloc[i]) and pd.notna(y.iloc[i]):
                    ax.annotate(txt, (x.iloc[i], y.iloc[i]), xytext=(5,5), textcoords='offset points')
            
            mean_x, mean_y = x.mean(), y.mean()
            if pd.notna(mean_x) and pd.notna(mean_y):
                ax.axvline(float(mean_x), color='grey', linestyle='--', linewidth=1)
                ax.axhline(float(mean_y), color='grey', linestyle='--', linewidth=1)
                
                ax.text(mean_x, ax.get_ylim()[1], "정확성↑", ha='center', va='top', color='gray')
                ax.text(ax.get_xlim()[1], mean_y, "신속성→", ha='right', va='center', color='gray')

                ax.text(ax.get_xlim()[1], ax.get_ylim()[1], "신속/정확형", ha='right', va='top', fontsize=12, color=self.COLOR_SUCCESS, weight='bold', alpha=0.8, bbox=dict(facecolor='white', alpha=0.5, edgecolor='none'))
                ax.text(ax.get_xlim()[0], ax.get_ylim()[1], "정확/신중형", ha='left', va='top', fontsize=12, color='gray', alpha=0.8, bbox=dict(facecolor='white', alpha=0.5, edgecolor='none'))
                ax.text(ax.get_xlim()[1], ax.get_ylim()[0], "신속/개선필요형", ha='right', va='bottom', fontsize=12, color='gray', alpha=0.8, bbox=dict(facecolor='white', alpha=0.5, edgecolor='none'))
                ax.text(ax.get_xlim()[0], ax.get_ylim()[0], "신중/개선필요형", ha='left', va='bottom', fontsize=12, color=self.COLOR_DANGER, alpha=0.8, bbox=dict(facecolor='white', alpha=0.5, edgecolor='none'))

            ax.set_xlabel("신속성 (점수)"); ax.set_ylabel("정확성 (점수)")
            ax.set_title("작업자 유형 분포",pad=15)
            ax.set_facecolor(self.COLOR_SIDEBAR_BG); ax.grid(True,linestyle='--',alpha=0.6,zorder=0)
            ax.set_xlim(0, 105); ax.set_ylim(0, 105)
        
        fig.tight_layout(); FigureCanvasTkAgg(fig,master=parent).get_tk_widget().pack(fill=tk.BOTH,expand=True)
    
    def _draw_hourly_production_chart(self, parent, title, df_to_use):
        chart_card=ttk.Frame(parent,style='Card.TFrame',padding=20)
        chart_card.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(chart_card,text=title,style='Header.TLabel').pack(anchor='w',pady=(0,10))
        
        if df_to_use.empty:
            ttk.Label(chart_card,text="차트 데이터가 없습니다.",style="Sidebar.TLabel").pack(expand=True)
            return
            
        df = df_to_use.copy()
        df['hour'] = pd.to_datetime(df['start_time_dt']).dt.hour
        hourly_summary = df.groupby('hour')['pcs_completed'].sum().reindex(range(24), fill_value=0)

        if hourly_summary.sum() == 0:
            ttk.Label(chart_card,text="생산량 데이터가 없습니다.",style="Sidebar.TLabel").pack(expand=True)
            return

        fig=Figure(figsize=(10,4),dpi=100,facecolor=self.COLOR_SIDEBAR_BG); ax=fig.add_subplot(111)
        colors=[self.COLOR_PRIMARY if val>0 else '#DCDFE4' for val in hourly_summary.values]
        hourly_summary.plot(kind='bar',ax=ax,color=colors,zorder=3,width=0.8)
        ax.set_ylabel("완료 PCS 수"); ax.set_xlabel("시간대"); ax.tick_params(axis='x',rotation=0); ax.grid(axis='y',linestyle='--',alpha=0.7,zorder=0); fig.tight_layout()
        ax.set_xticks(range(24)); ax.set_xticklabels([f"{h:02d}시" for h in range(24)])
        FigureCanvasTkAgg(fig,master=chart_card).get_tk_widget().pack(fill=tk.BOTH,expand=True)
    
    def _draw_item_summary_table(self, parent, df):
        self._clear_tab(parent)

        table_card = ttk.Frame(parent, style='Card.TFrame', padding=20)
        table_card.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        ttk.Label(table_card, text="품목별 총 생산량", style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        if df.empty:
            ttk.Label(table_card, text="집계할 데이터가 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return

        item_summary = df.groupby(['item_name', 'item_code'])['pcs_completed'].sum().reset_index()
        item_summary = item_summary.sort_values(by='pcs_completed', ascending=False)
        item_summary = item_summary[item_summary['pcs_completed'] > 0]
        item_summary['pallets_completed'] = item_summary['pcs_completed'] / 60

        tree_container = ttk.Frame(table_card)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명', '품목코드', '총 생산량 (PCS)', '총 생산량 (Pallets)']
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")
        tree.heading('품목명', text='품목명', anchor='w', command=lambda: self._sort_treeview(tree, '품목명', False))
        tree.heading('품목코드', text='품목코드', anchor='w', command=lambda: self._sort_treeview(tree, '품목코드', False))
        tree.heading('총 생산량 (PCS)', text='총 생산량 (PCS)', anchor='e', command=lambda: self._sort_treeview(tree, '총 생산량 (PCS)', False))
        tree.heading('총 생산량 (Pallets)', text='총 생산량 (Pallets)', anchor='e', command=lambda: self._sort_treeview(tree, '총 생산량 (Pallets)', False))

        tree.column('품목명', width=self.column_widths.get('pkg_item_summary_품목명', int(200 * self.scale_factor)), anchor='w', stretch=tk.YES)
        tree.column('품목코드', width=self.column_widths.get('pkg_item_summary_품목코드', int(120 * self.scale_factor)), anchor='w', stretch=tk.NO)
        tree.column('총 생산량 (PCS)', width=self.column_widths.get('pkg_item_summary_총 생산량 (PCS)', int(120 * self.scale_factor)), anchor='e', stretch=tk.NO)
        tree.column('총 생산량 (Pallets)', width=self.column_widths.get('pkg_item_summary_총 생산량 (Pallets)', int(120 * self.scale_factor)), anchor='e', stretch=tk.NO)

        for i, row in item_summary.iterrows():
            pcs_val = f"{int(row['pcs_completed']):,}"
            pallets_val = f"{row['pallets_completed']:.1f}"
            tree.insert('', 'end', values=[row['item_name'], row['item_code'], pcs_val, pallets_val], tags=("oddrow" if i % 2 == 0 else "",))

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(side='left', fill='both', expand=True)
        
        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='pkg_item_summary': self._on_column_resize(e, t, name))
    
    def _draw_production_main_tab(self, parent_tab):
        self._clear_tab(parent_tab)
        if self.filtered_df_raw.empty:
            ttk.Label(parent_tab, text="표시할 데이터가 없습니다.").pack(expand=True)
            return
        
        kpi_frame=ttk.Frame(parent_tab,style='TFrame'); kpi_frame.pack(fill=tk.X,pady=(0,20))
        kpi_frame.grid_columnconfigure((0,1,2),weight=1)
        
        avg_tray_time = self._format_seconds(self.kpis.get('avg_tray_time',0))
        avg_latency = self._format_seconds(self.kpis.get('avg_latency',0))
        total_errors = self.kpis.get('total_errors',0)
        
        self._create_dashboard_card(kpi_frame,"평균 트레이 작업시간",avg_tray_time,"⏱️").grid(row=0,column=0,sticky='nsew',padx=5)
        self._create_dashboard_card(kpi_frame,"평균 작업 준비시간",avg_latency,"⏯️").grid(row=0,column=1,sticky='nsew',padx=5)
        self._create_dashboard_card(kpi_frame,"총 공정 오류",f"{total_errors:,}건","❌",value_color=self.COLOR_DANGER if total_errors>0 else self.COLOR_SUCCESS).grid(row=0,column=2,sticky='nsew',padx=5)

        control_frame = ttk.Frame(parent_tab, style='TFrame')
        control_frame.pack(fill=tk.X, padx=0, pady=(0, 5))
        
        ttk.Label(control_frame, text="집계 단위:").pack(side=tk.LEFT, padx=(0, 10))
        for p in ["일간", "주간", "월간"]:
            ttk.Radiobutton(control_frame, text=p, variable=self.production_summary_period_var,
                            value=p, command=self._update_production_sub_tabs).pack(side=tk.LEFT, padx=5)
        
        self.transfer_prod_notebook = ttk.Notebook(parent_tab, style='TNotebook')
        self.transfer_prod_notebook.pack(fill=tk.BOTH, expand=True, pady=(5,0))

        self.transfer_charts_sub_tab = ttk.Frame(self.transfer_prod_notebook, style='TFrame', padding=10)
        self.transfer_table_sub_tab = ttk.Frame(self.transfer_prod_notebook, style='TFrame', padding=10)

        self.transfer_prod_notebook.add(self.transfer_charts_sub_tab, text="📊 차트 개요")
        self.transfer_prod_notebook.add(self.transfer_table_sub_tab, text="📋 품목별 생산량 테이블")

        self._update_production_sub_tabs()

    def _update_production_sub_tabs(self):
        if not hasattr(self, 'transfer_charts_sub_tab') or not self.transfer_charts_sub_tab.winfo_exists(): return
        
        self._clear_tab(self.transfer_charts_sub_tab)
        self._clear_tab(self.transfer_table_sub_tab)
        
        period = self.production_summary_period_var.get()
        df = self.filtered_df_raw.copy()

        if df.empty:
            ttk.Label(self.transfer_charts_sub_tab, text="표시할 데이터가 없습니다.", style='TLabel').pack(expand=True)
            ttk.Label(self.transfer_table_sub_tab, text="표시할 데이터가 없습니다.", style='TLabel').pack(expand=True)
            return
            
        df['date_dt'] = pd.to_datetime(df['date'])
        chart_period_grouping = "D"
        if period == "주간":
            df['period_group'] = df['date_dt'].dt.to_period('W').apply(lambda r: r.start_time).dt.date
            chart_period_grouping = "W"
        elif period == "월간":
            df['period_group'] = df['date_dt'].dt.to_period('M').apply(lambda r: r.start_time).dt.date
            chart_period_grouping = "M"
        else: # "일간"
            df['period_group'] = df['date_dt'].dt.date
            
        self._draw_production_charts(self.transfer_charts_sub_tab, df, period, chart_period_grouping)
        self._draw_item_production_table(self.transfer_table_sub_tab, df, period)

    def _draw_production_charts(self, parent, df, period_label, period_grouping):
        pane_name = "prod_charts"
        top_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        top_pane.pack(fill=tk.BOTH, expand=True)
        self.paned_windows[pane_name] = top_pane
        
        daily_pcs_chart_frame = ttk.Frame(top_pane, style='Card.TFrame', padding=20)
        top_pane.add(daily_pcs_chart_frame, weight=1)
        self._draw_daily_production_chart(daily_pcs_chart_frame, df, f"총 생산량 추이 ({period_label})", period_type=period_grouping) 
        
        scatter_frame=ttk.Frame(top_pane,style='Card.TFrame',padding=20); top_pane.add(scatter_frame,weight=1)
        self._draw_speed_accuracy_scatter(scatter_frame)
        
        self.root.update_idletasks()
        top_pane.after(10, lambda p=top_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 2, 100))))

    def _draw_item_production_table(self, parent, df, period):
        self._clear_tab(parent)
        
        production_pivot = df.pivot_table(index='item_name', columns='period_group', values='pcs_completed', aggfunc='sum', fill_value=0)
        
        if production_pivot.empty:
            ttk.Label(parent, text="집계할 생산 데이터가 없습니다.", style='TLabel').pack(expand=True)
            return

        production_pivot['합계 (PCS)'] = production_pivot.sum(axis=1)
        production_pivot['합계 (Pallets)'] = production_pivot['합계 (PCS)'] / 60
        
        total_row_data = {col: production_pivot[col].sum() for col in production_pivot.columns if col not in ['합계 (PCS)', '합계 (Pallets)']}
        total_row_data['합계 (PCS)'] = production_pivot['합계 (PCS)'].sum()
        total_row_data['합계 (Pallets)'] = production_pivot['합계 (Pallets)'].sum()
        
        total_row = pd.DataFrame([total_row_data], index=['합계'])
        production_pivot = pd.concat([production_pivot, total_row])

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)
        
        date_cols = sorted([col for col in production_pivot.columns if col not in ['합계 (PCS)', '합계 (Pallets)']], key=lambda x: str(x))
        
        dynamic_date_cols_display = []
        for d in date_cols:
            if period == "월간":
                dynamic_date_cols_display.append(d.strftime('%Y-%m'))
            elif period == "주간":
                dynamic_date_cols_display.append(f"{d.year}-W{d.isocalendar()[1]:02d}")
            else: # 일간
                dynamic_date_cols_display.append(d.strftime('%m-%d'))

        tree_cols = ['모델명'] + dynamic_date_cols_display + ['합계 (PCS)', '합계 (Pallets)']
        
        tree = ttk.Treeview(tree_container, columns=tree_cols, show="headings")
        
        tree.heading('모델명', text='모델명', anchor='w', command=lambda: self._sort_treeview(tree, '모델명', False))
        tree.column('모델명', anchor='w', width=self.column_widths.get('prod_pivot_모델명', int(150 * self.scale_factor)), stretch=tk.YES)
        
        for col_display_name in dynamic_date_cols_display:
            tree.heading(col_display_name, text=col_display_name, anchor='e', command=lambda c=col_display_name: self._sort_treeview(tree, c, False))
            tree.column(col_display_name, anchor='e', width=self.column_widths.get(f'prod_pivot_{col_display_name}', int(80 * self.scale_factor)), stretch=tk.NO)

        tree.heading('합계 (PCS)', text='합계 (PCS)', anchor='e', command=lambda c='합계 (PCS)': self._sort_treeview(tree, c, False))
        tree.column('합계 (PCS)', anchor='e', width=self.column_widths.get('prod_pivot_합계 (PCS)', int(100*self.scale_factor)), stretch=tk.NO)
        tree.heading('합계 (Pallets)', text='합계 (Pallets)', anchor='e', command=lambda c='합계 (Pallets)': self._sort_treeview(tree, c, False))
        tree.column('합계 (Pallets)', anchor='e', width=self.column_widths.get('prod_pivot_합계 (Pallets)', int(100*self.scale_factor)), stretch=tk.NO)
        
        tree.tag_configure('total_row', font=(self.DEFAULT_FONT, int(11*self.scale_factor), "bold"))

        for item_name, row in production_pivot.iterrows():
            values_for_tree = [item_name]
            for i, d_col_dt in enumerate(date_cols):
                values_for_tree.append(f"{int(row.get(d_col_dt, 0)):,}")
            values_for_tree.append(f"{int(row.get('합계 (PCS)', 0)):,}")
            values_for_tree.append(f"{row.get('합계 (Pallets)', 0):.1f}")
            
            if item_name == '합계':
                tree.insert('', 'end', values=values_for_tree, tags=('total_row',))
            else:
                tree.insert('', 'end', values=values_for_tree)

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(side='left', fill='both', expand=True)
        
        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='prod_pivot': self._on_column_resize(e, t, name))

    def _draw_detailed_tab(self, parent_tab):
        self._clear_tab(parent_tab)
        if not self.worker_data: 
            ttk.Label(parent_tab,text="표시할 작업자별 분석 데이터가 없습니다.", style='TLabel').pack(expand=True)
            return
            
        pane_name = "detailed_main"
        main_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
        main_pane.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)
        self.paned_windows[pane_name] = main_pane

        left_frame = ttk.Frame(main_pane, style='Card.TFrame', padding=10)
        main_pane.add(left_frame, weight=0)

        sort_frame = ttk.Frame(left_frame, style='Sidebar.TFrame')
        sort_frame.pack(fill=tk.X, pady=(0, 10))
        ttk.Label(sort_frame, text="정렬 기준:", style='Sidebar.TLabel').pack(side=tk.LEFT)
        sort_options = [
            "이름순", "종합 점수 높은 순", "종합 점수 낮은 순", 
            "평균 작업 시간 빠른 순", "평균 작업 시간 느린 순",
            "처리 세트 많은 순", "처리 세트 적은 순"
        ]
        sort_combo = ttk.Combobox(sort_frame, textvariable=self.worker_sort_option_var, values=sort_options, state='readonly', width=20)
        sort_combo.pack(fill=tk.X, expand=True)
        sort_combo.bind('<<ComboboxSelected>>', self._update_worker_list_and_view)

        self.detailed_worker_listbox = tk.Listbox(left_frame, selectmode=tk.SINGLE, exportselection=False, relief='flat', bg=self.COLOR_SIDEBAR_BG, highlightthickness=0);
        self.detailed_worker_listbox.pack(fill=tk.BOTH, expand=True)
        self.detailed_worker_listbox.bind('<<ListboxSelect>>', self._on_detailed_worker_select)

        self.detailed_view_frame = ttk.Frame(main_pane, style='TFrame')
        main_pane.add(self.detailed_view_frame, weight=1)
        
        self._update_worker_list_and_view()
        self.root.update_idletasks()
        main_pane.after(10, lambda p=main_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(200, p.winfo_width() // 6))))

    def _update_worker_list_and_view(self, event=None):
        if not hasattr(self, 'detailed_worker_listbox') or not self.detailed_worker_listbox.winfo_exists(): return
        if not self.worker_data: return

        sort_key = self.worker_sort_option_var.get()
        performances = list(self.worker_data.values())

        if sort_key == "이름순":
            sorted_performances = sorted(performances, key=lambda p: p.worker)
        elif sort_key == "종합 점수 높은 순":
            sorted_performances = sorted(performances, key=lambda p: p.overall_score, reverse=True)
        elif sort_key == "종합 점수 낮은 순":
            sorted_performances = sorted(performances, key=lambda p: p.overall_score)
        elif sort_key == "평균 작업 시간 빠른 순":
            sorted_performances = sorted(performances, key=lambda p: p.avg_work_time)
        elif sort_key == "평균 작업 시간 느린 순":
            sorted_performances = sorted(performances, key=lambda p: p.avg_work_time, reverse=True)
        elif sort_key == "처리 세트 많은 순":
            sorted_performances = sorted(performances, key=lambda p: p.session_count, reverse=True)
        elif sort_key == "처리 세트 적은 순":
            sorted_performances = sorted(performances, key=lambda p: p.session_count)
        else:
            sorted_performances = performances
        
        worker_names_sorted = [p.worker for p in sorted_performances]

        self.detailed_worker_listbox.delete(0, tk.END)
        for name in worker_names_sorted:
            self.detailed_worker_listbox.insert(tk.END, name)

        if worker_names_sorted:
            self.detailed_worker_listbox.selection_set(0)
            self.root.after(10, self._on_detailed_worker_select)

    def _on_detailed_worker_select(self, event=None):
        if not hasattr(self, 'detailed_worker_listbox') or not self.detailed_worker_listbox.winfo_exists(): return
        selected_indices = self.detailed_worker_listbox.curselection()
        if not selected_indices:
            self._clear_tab(self.detailed_view_frame)
            ttk.Label(self.detailed_view_frame, text="작업자를 선택해주세요.", style="Sidebar.TLabel").pack(expand=True)
            return
            
        selected_worker_name = self.detailed_worker_listbox.get(selected_indices[0])
        self._clear_tab(self.detailed_view_frame)
        self._draw_worker_details(self.detailed_view_frame, selected_worker_name)

    def _draw_worker_details(self, parent, worker_name):
        worker_performance: Optional[WorkerPerformance] = self.worker_data.get(worker_name)
        if worker_performance is None: 
            ttk.Label(parent, text=f"작업자 '{worker_name}'의 상세 데이터가 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return

        top_frame = ttk.Frame(parent, style='TFrame'); top_frame.pack(fill=tk.X, pady=(0, 10))
        top_frame.grid_columnconfigure((0,1,2,3), weight=1)

        score_card = self._create_dashboard_card(top_frame, "종합 성과 점수", f"{worker_performance.overall_score:.1f} 점", "⭐",
                                               value_color=self.COLOR_SUCCESS if worker_performance.overall_score >= 70 else (self.COLOR_DANGER if worker_performance.overall_score < 50 else self.COLOR_TEXT))
        score_card.grid(row=0, column=0, sticky='nsew', padx=5, rowspan=2)

        best_time_text = f"(금주 최고: {self._format_seconds(worker_performance.best_work_time)}"
        if worker_performance.best_work_time_date:
            best_time_text += f", {worker_performance.best_work_time_date.strftime('%y-%m-%d')})"
        else:
            best_time_text += ")"
        
        self._create_dashboard_card(top_frame, "평균 작업 시간", self._format_seconds(worker_performance.avg_work_time), "⏱️", best_record_text=best_time_text).grid(row=0, column=1, sticky='nsew', padx=5)
        
        self._create_dashboard_card(top_frame, "평균 준비 시간", self._format_seconds(worker_performance.avg_latency), "⏯️").grid(row=0, column=2, sticky='nsew', padx=5)
        self._create_dashboard_card(top_frame, "평균 유휴 시간", self._format_seconds(worker_performance.avg_idle_time), "☕").grid(row=0, column=3, sticky='nsew', padx=5)
        
        self._create_dashboard_card(top_frame, "총 처리 트레이 수", f"{worker_performance.session_count:,}개", "📦").grid(row=1, column=1, sticky='nsew', padx=5)
        self._create_dashboard_card(top_frame, "총 처리 PCS 수", f"{worker_performance.total_pcs_completed:,}개", "🧩").grid(row=1, column=2, sticky='nsew', padx=5)
        self._create_dashboard_card(top_frame, "초도 수율", f"{worker_performance.first_pass_yield:.1%}", "✅").grid(row=1, column=3, sticky='nsew', padx=5)

        pane_name = "detailed_bottom"
        bottom_pane = ttk.PanedWindow(parent, orient=tk.HORIZONTAL)
        bottom_pane.pack(fill=tk.BOTH, expand=True, pady=(10, 0))
        self.paned_windows[pane_name] = bottom_pane

        radar_pane_name = "detailed_radar"
        radar_pane = ttk.PanedWindow(bottom_pane, orient=tk.VERTICAL)
        bottom_pane.add(radar_pane, weight=1)
        self.paned_windows[radar_pane_name] = radar_pane
        
        radar_frame = ttk.Frame(radar_pane, style='Card.TFrame', padding=20)
        radar_pane.add(radar_frame, weight=2)
        self._draw_radar_chart(radar_frame, worker_name)
        
        desc_frame = ttk.Frame(radar_pane, style='Card.TFrame', padding=20)
        radar_pane.add(desc_frame, weight=1)
        self._draw_radar_descriptions(desc_frame)

        item_analysis_frame = ttk.Frame(bottom_pane, style='Card.TFrame', padding=20)
        bottom_pane.add(item_analysis_frame, weight=1)
        self._draw_item_performance_table(item_analysis_frame, worker_name)

        self.root.update_idletasks()
        bottom_pane.after(10, lambda p=bottom_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 3, 100))))
        self.root.update_idletasks()
        radar_pane.after(10, lambda p=radar_pane, n=radar_pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_height() * 2 // 3, 100))))

    def _draw_radar_chart(self, parent, worker_name):
        ttk.Label(parent, text=f"'{worker_name}'의 성과 레이더 차트", style='Header.TLabel').pack(anchor='w', pady=(0, 10))
        
        worker_norm_data = self.normalized_df[self.normalized_df['worker'] == worker_name].iloc[0] if self.normalized_df is not None and not self.normalized_df.empty and worker_name in self.normalized_df['worker'].values else None

        if worker_norm_data is None:
            ttk.Label(parent, text="정규화된 성과 데이터를 찾을 수 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return

        metrics = list(self.RADAR_METRICS.keys())
        values = []
        for key, (attr, _, _) in self.RADAR_METRICS.items():
            norm_col_name = f"{attr}_norm"
            val = worker_norm_data.get(norm_col_name, 0.5)
            values.append(val)
            
        if len(values) < 2:
            ttk.Label(parent, text="레이더 차트를 그릴 지표가 부족합니다.", style="Sidebar.TLabel").pack(expand=True)
            return
            
        values = np.array(values) * 100
        
        angles = np.linspace(0, 2 * np.pi, len(metrics), endpoint=False).tolist()
        values = np.concatenate((values,[values[0]]))
        angles = np.concatenate((angles,[angles[0]]))

        fig = Figure(figsize=(6, 6), dpi=100, facecolor=self.COLOR_SIDEBAR_BG)
        ax = fig.add_subplot(111, polar=True)
        
        ax.plot(angles, values, color=self.COLOR_PRIMARY, linewidth=2, linestyle='solid', marker='o')
        ax.fill(angles, values, color=self.COLOR_PRIMARY, alpha=0.25)

        ax.set_theta_offset(np.pi / 2)
        ax.set_theta_direction(-1)
        ax.set_xticks(angles[:-1])
        ax.set_xticklabels(metrics, fontname=self.DEFAULT_FONT, fontsize=int(10*self.scale_factor))
        ax.set_rlabel_position(0)
        ax.set_yticks(np.arange(0, 101, 25))
        ax.set_yticklabels([f"{i}%" for i in np.arange(0, 101, 25)], color="#999999", size=int(8*self.scale_factor))
        ax.set_ylim(0, 100)
        ax.grid(True, linestyle='--', alpha=0.6)
        fig.tight_layout()
        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(fill=tk.BOTH, expand=True)
        
    def _draw_radar_descriptions(self, parent):
        ttk.Label(parent, text="지표 설명", style='Header.TLabel').pack(anchor='w', pady=(0, 10))
        
        canvas = tk.Canvas(parent, bg=self.COLOR_SIDEBAR_BG, highlightthickness=0)
        scrollbar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        scrollable_frame = ttk.Frame(canvas, style='Sidebar.TFrame')

        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=scrollable_frame, anchor="nw")
        canvas.configure(yscrollcommand=scrollbar.set)
        
        current_metrics = self.RADAR_METRICS.keys()

        for metric_name, details in self.RADAR_METRIC_DESCRIPTIONS.items():
            if metric_name not in current_metrics: continue

            frame = ttk.Frame(scrollable_frame, style='Sidebar.TFrame', padding=(0, 5))
            frame.pack(fill='x', expand=True)

            lbl_name = ttk.Label(frame, text=f"▪ {metric_name}", font=(self.DEFAULT_FONT, int(11*self.scale_factor), "bold"), style='Sidebar.TLabel')
            lbl_name.pack(anchor='w')
            
            lbl_desc = ttk.Label(frame, text=details['desc'], font=(self.DEFAULT_FONT, int(10*self.scale_factor)), style='Sidebar.TLabel', foreground=self.COLOR_TEXT_SUBTLE, wraplength=int(parent.winfo_width()*0.85) or 300)
            lbl_desc.pack(anchor='w', padx=(10,0))
            
        canvas.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        
    def _draw_item_performance_table(self, parent, worker_name):
        ttk.Label(parent, text=f"'{worker_name}'의 품목별 성과", style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        worker_filtered_df = self.filtered_df_raw[self.filtered_df_raw['worker'] == worker_name].copy()
        
        if worker_filtered_df.empty:
            ttk.Label(parent, text="이 작업자의 품목별 데이터가 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return

        item_summary = worker_filtered_df.groupby('item_name').agg(
            avg_work_time=('work_time', 'mean'),
            work_time_std=('work_time', 'std'),
            total_pcs=('pcs_completed', 'sum'),
            avg_target_achievement=('target_achievement', 'mean')
        ).fillna(0).reset_index().sort_values(by='avg_work_time')
        
        item_summary['total_pallets'] = item_summary['total_pcs'] / 60

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명', '평균시간', '안정성(초)', '총 PCS', '총 Pallets', '목표달성률']
        tree = ttk.Treeview(tree_container, columns=cols, show='headings')
        tree.heading('품목명', text='품목명', anchor='w', command=lambda: self._sort_treeview(tree, '품목명', False))
        tree.heading('평균시간', text='평균시간', anchor='e', command=lambda: self._sort_treeview(tree, '평균시간', False))
        tree.heading('안정성(초)', text='안정성(초)', anchor='e', command=lambda: self._sort_treeview(tree, '안정성(초)', False))
        tree.heading('총 PCS', text='총 PCS', anchor='e', command=lambda: self._sort_treeview(tree, '총 PCS', False))
        tree.heading('총 Pallets', text='총 Pallets', anchor='e', command=lambda: self._sort_treeview(tree, '총 Pallets', False))
        tree.heading('목표달성률', text='목표달성률', anchor='e', command=lambda: self._sort_treeview(tree, '목표달성률', False))

        tree.column('품목명', anchor='w', width=self.column_widths.get('item_perf_품목명', int(160*self.scale_factor)), stretch=tk.YES)
        tree.column('평균시간', anchor='e', width=self.column_widths.get('item_perf_평균시간', int(100*self.scale_factor)), stretch=tk.NO)
        tree.column('안정성(초)', anchor='e', width=self.column_widths.get('item_perf_안정성(초)', int(80*self.scale_factor)), stretch=tk.NO)
        tree.column('총 PCS', anchor='e', width=self.column_widths.get('item_perf_총 PCS', int(90*self.scale_factor)), stretch=tk.NO)
        tree.column('총 Pallets', anchor='e', width=self.column_widths.get('item_perf_총 Pallets', int(90*self.scale_factor)), stretch=tk.NO)
        tree.column('목표달성률', anchor='e', width=self.column_widths.get('item_perf_목표달성률', int(90*self.scale_factor)), stretch=tk.NO)

        for i, row in item_summary.iterrows():
            values = [
                row['item_name'], f"{row['avg_work_time']:.1f}", f"{row['work_time_std']:.1f}",
                f"{int(row['total_pcs']):,}", f"{row['total_pallets']:.1f}", f"{row['avg_target_achievement']:.1f}%"
            ]
            tree.insert('', 'end', values=values, tags=("oddrow" if i % 2 == 0 else "",))
        
        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(fill=tk.BOTH, expand=True)

        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='item_perf': self._on_column_resize(e, t, name))

    def _draw_data_table_tab(self, parent_tab):
        self._clear_tab(parent_tab)

        if self.filtered_df_raw.empty:
            ttk.Label(parent_tab, text="표시할 데이터가 없습니다.", style='TLabel').pack(expand=True)
            return
            
        filter_frame = ttk.Frame(parent_tab, style='Card.TFrame', padding=10)
        filter_frame.pack(fill=tk.X, pady=(0, 10))

        ttk.Label(filter_frame, text="기간:", style="Sidebar.TLabel").grid(row=0, column=0, padx=(5,2), pady=5, sticky='w')
        min_d, max_d = self.filtered_df_raw['date'].min(), self.filtered_df_raw['date'].max()
        if isinstance(min_d, pd.Timestamp): min_d = min_d.date()
        if isinstance(max_d, pd.Timestamp): max_d = max_d.date()
        
        self.detail_filter_start_date = DateEntry(filter_frame, width=12, date_pattern='y-mm-dd')
        if pd.notna(min_d): self.detail_filter_start_date.set_date(min_d)
        self.detail_filter_start_date.grid(row=0, column=1, padx=(0,5), pady=5, sticky='w')
        ttk.Label(filter_frame, text="~", style="Sidebar.TLabel").grid(row=0, column=2, padx=5, pady=5)
        self.detail_filter_end_date = DateEntry(filter_frame, width=12, date_pattern='y-mm-dd')
        if pd.notna(max_d): self.detail_filter_end_date.set_date(max_d)
        self.detail_filter_end_date.grid(row=0, column=3, padx=(0,15), pady=5, sticky='w')

        if 'shipping_date' in self.filtered_df_raw.columns and not self.filtered_df_raw['shipping_date'].isnull().all():
            ttk.Label(filter_frame, text="출고일:", style="Sidebar.TLabel").grid(row=0, column=4, padx=(5,2), pady=5, sticky='w')
            ship_min_d, ship_max_d = self.filtered_df_raw['shipping_date'].min(), self.filtered_df_raw['shipping_date'].max()
            
            self.detail_filter_shipping_start_date = DateEntry(filter_frame, width=12, date_pattern='y-mm-dd')
            if pd.notna(ship_min_d): self.detail_filter_shipping_start_date.set_date(ship_min_d.date())
            self.detail_filter_shipping_start_date.grid(row=0, column=5, padx=(0,5), pady=5, sticky='w')
            
            ttk.Label(filter_frame, text="~", style="Sidebar.TLabel").grid(row=0, column=6, padx=5, pady=5)
            
            self.detail_filter_shipping_end_date = DateEntry(filter_frame, width=12, date_pattern='y-mm-dd')
            if pd.notna(ship_max_d): self.detail_filter_shipping_end_date.set_date(ship_max_d.date())
            self.detail_filter_shipping_end_date.grid(row=0, column=7, padx=(0,15), pady=5, sticky='w')
        else:
             self.detail_filter_shipping_start_date = None
             self.detail_filter_shipping_end_date = None
        
        ttk.Label(filter_frame, text="작업자:", style="Sidebar.TLabel").grid(row=1, column=0, padx=(5,2), pady=5, sticky='w')
        workers = ["전체"] + sorted(self.filtered_df_raw['worker'].unique())
        self.detail_filter_worker = ttk.Combobox(filter_frame, values=workers, state='readonly', width=12)
        self.detail_filter_worker.set("전체")
        self.detail_filter_worker.grid(row=1, column=1, padx=(0,15), pady=5, sticky='w')

        ttk.Label(filter_frame, text="공정:", style="Sidebar.TLabel").grid(row=1, column=2, padx=(5,2), pady=5, sticky='w')
        processes = ["전체", "이적실", "포장실"]
        self.detail_filter_process = ttk.Combobox(filter_frame, values=processes, state='readonly', width=10)
        self.detail_filter_process.set("전체")
        self.detail_filter_process.grid(row=1, column=3, padx=(0,15), pady=5, sticky='w')
        
        ttk.Label(filter_frame, text="품목명:", style="Sidebar.TLabel").grid(row=1, column=4, padx=(5,2), pady=5, sticky='w')
        items = ["전체"] + sorted(self.filtered_df_raw['item_name'].unique())
        self.detail_filter_item = ttk.Combobox(filter_frame, values=items, state='readonly', width=25)
        self.detail_filter_item.set("전체")
        self.detail_filter_item.grid(row=1, column=5, padx=(0,15), pady=5, sticky='w', columnspan=3)

        btn_frame = ttk.Frame(filter_frame, style='Sidebar.TFrame')
        btn_frame.grid(row=0, column=8, rowspan=2, padx=(20,5), pady=5, sticky='e')
        filter_frame.grid_columnconfigure(8, weight=1)

        ttk.Button(btn_frame, text="🔍 필터 적용", command=self._apply_detail_filters).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="🔄 초기화", command=self._reset_detail_filters).pack(fill=tk.X, pady=2)
        ttk.Button(btn_frame, text="📄 Excel로 내보내기", command=self._export_to_excel).pack(fill=tk.X, pady=(10,2))

        tree_frame = ttk.Frame(parent_tab)
        tree_frame.pack(fill=tk.BOTH, expand=True)
        self.data_tree = ttk.Treeview(tree_frame, show='headings')
        vsb = ttk.Scrollbar(tree_frame, orient="vertical", command=self.data_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient="horizontal", command=self.data_tree.xview)
        self.data_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x');
        self.data_tree.pack(side='left', fill='both', expand=True)
        self.data_tree.bind('<ButtonRelease-1>', lambda e, t=self.data_tree, name='data_table': self._on_column_resize(e, t, name))

    def _apply_detail_filters(self):
        df = self.filtered_df_raw.copy()
        
        start_date = self.detail_filter_start_date.get_date()
        end_date = self.detail_filter_end_date.get_date()
        
        df['date_only'] = pd.to_datetime(df['date']).dt.date
        df = df[(df['date_only'] >= start_date) & (df['date_only'] <= end_date)]

        if self.detail_filter_shipping_start_date and self.detail_filter_shipping_end_date:
            ship_start = self.detail_filter_shipping_start_date.get_date()
            ship_end = self.detail_filter_shipping_end_date.get_date()
            df = df.dropna(subset=['shipping_date'])
            if not df.empty:
                df = df[(df['shipping_date'].dt.date >= ship_start) & (df['shipping_date'].dt.date <= ship_end)]

        worker = self.detail_filter_worker.get()
        if worker != "전체":
            df = df[df['worker'] == worker]

        process = self.detail_filter_process.get()
        if process != "전체":
            df = df[df['process'] == process]

        item = self.detail_filter_item.get()
        if item != "전체":
            df = df[df['item_name'] == item]

        df = df.drop(columns=['date_only'], errors='ignore')
        self._repopulate_data_table(df)
        
    def _reset_detail_filters(self):
        min_d, max_d = self.filtered_df_raw['date'].min(), self.filtered_df_raw['date'].max()
        if isinstance(min_d, pd.Timestamp): min_d = min_d.date()
        if isinstance(max_d, pd.Timestamp): max_d = max_d.date()

        if pd.notna(min_d): self.detail_filter_start_date.set_date(min_d)
        if pd.notna(max_d): self.detail_filter_end_date.set_date(max_d)
        
        if self.detail_filter_shipping_start_date and self.detail_filter_shipping_end_date:
            ship_min_d, ship_max_d = self.filtered_df_raw['shipping_date'].min(), self.filtered_df_raw['shipping_date'].max()
            if pd.notna(ship_min_d): self.detail_filter_shipping_start_date.set_date(ship_min_d.date())
            if pd.notna(ship_max_d): self.detail_filter_shipping_end_date.set_date(ship_max_d.date())
            
        self.detail_filter_worker.set("전체")
        self.detail_filter_process.set("전체")
        self.detail_filter_item.set("전체")
        self._repopulate_data_table(self.filtered_df_raw)

    def _repopulate_data_table(self, df_to_show):
        for i in self.data_tree.get_children():
            self.data_tree.delete(i)
            
        if df_to_show.empty:
            self.currently_displayed_table_df = pd.DataFrame()
            self.data_tree['columns'] = [] 
            return

        df_display = df_to_show.sort_values(by='start_time_dt', ascending=False).copy()
        
        df_display['날짜'] = pd.to_datetime(df_display['date']).dt.strftime('%Y-%m-%d')
        df_display['시작 시간'] = df_display['start_time_dt'].dt.strftime('%H:%M:%S').fillna('N/A')
        if 'shipping_date' in df_display.columns:
            df_display['출고 날짜'] = pd.to_datetime(df_display['shipping_date']).dt.strftime('%Y-%m-%d').fillna('')
        df_display['작업시간 (초)'] = df_display['work_time'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        df_display['준비시간 (초)'] = df_display['latency'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        df_display['오류수'] = df_display['process_errors'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
        df_display['오류 발생 여부'] = df_display['had_error'].apply(lambda x: '예' if x == 1 else '아니오')
        df_display['완료 PCS'] = df_display['pcs_completed'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
        df_display['완료 Pallets'] = df_display['pcs_completed'].apply(lambda x: f"{x / 60:.1f}" if pd.notna(x) else "N/A")
        if 'target_achievement' in df_display.columns:
            df_display['목표 달성률 (%)'] = df_display['target_achievement'].apply(lambda x: f"{x:.1f}" if pd.notna(x) else "N/A")
        else:
            df_display['목표 달성률 (%)'] = "N/A"

        cols_to_display = [
            '날짜', '시작 시간', 'worker', 'process', 'item_name', 'item_code', 
            '작업시간 (초)', '준비시간 (초)', '완료 PCS', '완료 Pallets', '목표 달성률 (%)', '오류수', '오류 발생 여부'
        ]
        if 'shipping_date' in df_display.columns:
            cols_to_display.insert(2, '출고 날짜')
            
        header_map = {
            'worker': '작업자', 'process': '공정', 'item_name': '품목명', 'item_code': '품목코드'
        }
        self.currently_displayed_table_df = df_display[cols_to_display].rename(columns=header_map)
        
        tree_cols = list(self.currently_displayed_table_df.columns)
        self.data_tree['columns'] = tree_cols

        for col in tree_cols:
            self.data_tree.heading(col, text=col, anchor='center', command=lambda c=col: self._sort_treeview(self.data_tree, c, False))
            is_stretch = tk.YES if col == '품목명' else tk.NO
            default_width = 180 if col == '품목명' else 100
            self.data_tree.column(col, width=self.column_widths.get(f'data_table_{col}', int(default_width * self.scale_factor)), anchor='center', stretch=is_stretch)

        for i, row in self.currently_displayed_table_df.iterrows():
            values = list(row)
            self.data_tree.insert('', 'end', values=values, tags=("oddrow" if i % 2 else "",))

    def _export_to_excel(self):
        if self.currently_displayed_table_df.empty:
            messagebox.showinfo("정보", "내보낼 데이터가 없습니다.")
            return
            
        try:
            import openpyxl
        except ImportError:
            messagebox.showerror("오류", "Excel 파일을 저장하려면 'openpyxl' 라이브러리가 필요합니다.\n\n설치 명령어: pip install openpyxl")
            return

        file_path = filedialog.asksaveasfilename(
            defaultextension=".xlsx",
            filetypes=[("Excel 파일", "*.xlsx"), ("모든 파일", "*.*")],
            title="상세 데이터 저장"
        )
        if not file_path: return
        
        try:
            self.currently_displayed_table_df.to_excel(file_path, index=False, engine='openpyxl')
            messagebox.showinfo("성공", f"데이터를 성공적으로 저장했습니다:\n{file_path}")
        except Exception as e:
            messagebox.showerror("저장 실패", f"파일을 저장하는 중 오류가 발생했습니다:\n{e}")

    def _on_column_resize(self, event: Any, treeview: ttk.Treeview, tree_name: str):
        if not treeview.identify_region(event.x, event.y) == "separator":
            return
            
        try:
            column_id = treeview.identify_column(event.x)
            if not column_id: return
            header_text = treeview.heading(column_id, 'text')
            new_width = treeview.column(column_id, 'width')
            storage_key = f'{tree_name}_{header_text}'
            self.column_widths[storage_key] = new_width
        except Exception as e:
            print(f"DEBUG: 컬럼 너비 저장 중 오류 발생: {e}")
            
    def _sort_treeview(self, tree, col, reverse):
        l = []
        total_rows = []

        for k in tree.get_children(''):
            tags = tree.item(k, 'tags')
            if 'Total.Treeview' in tags or 'total_row' in tags:
                total_rows.append(k)
                continue
            
            value_raw = tree.set(k, col)
            sort_value = None
            
            try:
                cleaned_val = str(value_raw).replace(',', '').replace('%','').replace('초','').replace('+', '').strip()
                sort_value = float(cleaned_val)
            except (ValueError, TypeError):
                try:
                    sort_value = pd.to_datetime(value_raw, errors='raise')
                except (ValueError, TypeError):
                    sort_value = str(value_raw).lower()

            l.append((sort_value, k))

        try:
            l.sort(key=lambda t: t[0], reverse=reverse)
        except TypeError:
            l.sort(key=lambda t: str(t[0]), reverse=reverse)

        for index, (val, k) in enumerate(l):
            tree.move(k, '', index)
            
        for k in total_rows:
            tree.move(k, '', 'end')

        tree.heading(col, command=lambda: self._sort_treeview(tree, col, not reverse))

    def _start_file_monitor(self):
        if not os.path.isdir(self.log_folder_path):
            print(f"경고: 로그 폴더 '{self.log_folder_path}'를 찾을 수 없어 파일 감시를 시작할 수 없습니다.")
            return

        event_handler = LogFileHandler(self)
        self.observer = Observer()
        self.observer.schedule(event_handler, self.log_folder_path, recursive=False)
        
        self.monitor_thread = threading.Thread(target=self.observer.start, daemon=True)
        self.monitor_thread.start()
        
        self.root.bind("<<RealtimeDataRefresh>>", self._on_realtime_data_refresh)

    def _on_realtime_data_refresh(self, event=None):
        threading.Thread(target=self._update_realtime_data_thread, daemon=True).start()

    def _update_realtime_data_thread(self):
        try:
            today = datetime.date.today()
            current_mode = self.process_mode_var.get()
            df = self.analyzer.load_all_data(self.log_folder_path, current_mode, date_filter=today)
            self.root.after(0, self._update_realtime_ui, df)
        except Exception as e:
            print(f"실시간 데이터 업데이트 중 오류: {e}")

    def _draw_realtime_tab_content(self, parent_tab):
        self._clear_tab(parent_tab)

        mode = self.process_mode_var.get()
        if mode == "전체 비교":
            ttk.Label(parent_tab, text="이 모드에서는 실시간 현황을 제공하지 않습니다.").pack(expand=True)
            return

        if mode == "이적실":
            pane_name = "realtime_main"
            main_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
            main_pane.pack(fill=tk.BOTH, expand=True)
            self.paned_windows[pane_name] = main_pane

            left_pane_name = 'realtime_left_pane'
            left_pane = ttk.PanedWindow(main_pane, orient=tk.VERTICAL)
            main_pane.add(left_pane, weight=1)
            self.paned_windows[left_pane_name] = left_pane

            worker_frame = ttk.Frame(left_pane, style='Card.TFrame', padding=20)
            left_pane.add(worker_frame, weight=1)
            
            hourly_chart_frame = ttk.Frame(left_pane, style='Card.TFrame', padding=20)
            left_pane.add(hourly_chart_frame, weight=1)

            item_frame = ttk.Frame(main_pane, style='Card.TFrame', padding=20)
            main_pane.add(item_frame, weight=1)
            
            self._draw_realtime_worker_status(worker_frame, pd.DataFrame())
            self._draw_realtime_hourly_production_chart(hourly_chart_frame, pd.DataFrame(), "이적실 시간별 생산량 (오늘 vs 평균)", pd.DataFrame())
            self._draw_realtime_item_status(item_frame, pd.DataFrame())
            
            self.root.update_idletasks()
            main_pane.after(10, lambda p=main_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 2, 100))))
            left_pane.after(10, lambda p=left_pane, n=left_pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_height() // 2, 100))))

        else: # mode == "포장실"
            pane_name = "realtime_packaging_main"
            main_pane = ttk.PanedWindow(parent_tab, orient=tk.HORIZONTAL)
            main_pane.pack(fill=tk.BOTH, expand=True)
            self.paned_windows[pane_name] = main_pane

            item_frame = ttk.Frame(main_pane, style='Card.TFrame', padding=20)
            main_pane.add(item_frame, weight=1)
            
            hourly_chart_frame = ttk.Frame(main_pane, style='Card.TFrame', padding=20)
            main_pane.add(hourly_chart_frame, weight=1)

            self._draw_realtime_item_status(item_frame, pd.DataFrame())
            self._draw_realtime_hourly_production_chart(hourly_chart_frame, pd.DataFrame(), "포장실 시간별 생산량 (오늘 vs 평균)", pd.DataFrame())
            
            self.root.update_idletasks()
            main_pane.after(10, lambda p=main_pane, n=pane_name: p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 2, 100))))
            
        self.root.after(200, self._on_realtime_data_refresh)

    def _update_realtime_ui(self, df):
        try:
            if not self.content_area.winfo_children(): return
            notebook = self.content_area.winfo_children()[0]
            if not isinstance(notebook, ttk.Notebook) or not notebook.winfo_exists(): return

            current_tab_id = notebook.select()
            if not current_tab_id or current_tab_id != str(self.realtime_tab_frame):
                return

            mode = self.process_mode_var.get()
            
            today_df = pd.DataFrame()
            if not df.empty and 'date' in df.columns:
                df_copy = df.copy()
                df_copy['date'] = pd.to_datetime(df_copy['date'], errors='coerce').dt.date
                today_df = df_copy[df_copy['date'] == datetime.date.today()]

            if mode == "이적실":
                if 'realtime_main' in self.paned_windows and self.paned_windows['realtime_main'].winfo_exists():
                    main_pane = self.paned_windows['realtime_main']
                    if main_pane.winfo_children() and main_pane.winfo_children()[0].winfo_children():
                        left_pane = main_pane.winfo_children()[0]
                        worker_frame = left_pane.winfo_children()[0]
                        hourly_chart_frame = left_pane.winfo_children()[1]
                        item_frame = main_pane.winfo_children()[1]
                        
                        self._draw_realtime_worker_status(worker_frame, today_df)
                        self._draw_realtime_hourly_production_chart(hourly_chart_frame, today_df, "이적실 시간별 생산량 (오늘 vs 평균)", self.filtered_df_raw)
                        self._draw_realtime_item_status(item_frame, today_df)
            else: # mode == "포장실"
                if 'realtime_packaging_main' in self.paned_windows and self.paned_windows['realtime_packaging_main'].winfo_exists():
                    main_pane = self.paned_windows['realtime_packaging_main']
                    if main_pane.winfo_children():
                        item_frame = main_pane.winfo_children()[0]
                        hourly_chart_frame = main_pane.winfo_children()[1]
                        
                        self._draw_realtime_item_status(item_frame, today_df)
                        self._draw_realtime_hourly_production_chart(hourly_chart_frame, today_df, "포장실 시간별 생산량 (오늘 vs 평균)", self.filtered_df_raw)

        except (IndexError, tk.TclError) as e:
            print(f"실시간 UI 업데이트 중 무시된 오류: {e}")
        except Exception as e:
            print(f"실시간 UI 업데이트 중 예외 발생: {e}")
            
    def _draw_realtime_hourly_production_chart(self, parent, today_df, title, historical_df):
        self._clear_tab(parent)
        ttk.Label(parent, text=title, style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        work_hours = range(7, 23)

        today_summary = pd.Series(0, index=work_hours, dtype=float)
        if not today_df.empty:
            today_df_copy = today_df.copy()
            today_df_copy['hour'] = pd.to_datetime(today_df_copy['start_time_dt'], errors='coerce').dt.hour
            today_hourly = today_df_copy.groupby('hour')['pcs_completed'].sum().reindex(work_hours, fill_value=0)
            today_summary.update(today_hourly)

        avg_summary = pd.Series(0, index=work_hours, dtype=float)
        if not historical_df.empty:
            hist_df_copy = historical_df.copy()
            hist_df_copy['hour'] = pd.to_datetime(hist_df_copy['start_time_dt'], errors='coerce').dt.hour
            num_days = hist_df_copy['date'].nunique()
            if num_days > 0:
                hist_hourly_total = hist_df_copy.groupby('hour')['pcs_completed'].sum()
                hist_hourly_avg = (hist_hourly_total / num_days).reindex(work_hours, fill_value=0)
                avg_summary.update(hist_hourly_avg)

        fig = Figure(figsize=(10, 4), dpi=100, facecolor=self.COLOR_SIDEBAR_BG)
        ax = fig.add_subplot(111)
        x = np.arange(len(work_hours))
        
        ax.bar(x, today_summary, width=0.6, color=self.COLOR_PRIMARY, label='오늘 생산량', zorder=3)
        ax.plot(x, avg_summary, color=self.COLOR_DANGER, linestyle='--', marker='o', markersize=4, label='기간 평균', zorder=4)

        ax.set_ylabel("완료 PCS 수"); ax.set_xlabel("시간대"); ax.set_xticks(x)
        ax.set_xticklabels([f"{h:02d}시" for h in work_hours]); ax.tick_params(axis='x', rotation=0)
        ax.grid(axis='y', linestyle='--', alpha=0.7, zorder=0); ax.legend(); fig.tight_layout()
        
        FigureCanvasTkAgg(fig, master=parent).get_tk_widget().pack(fill=tk.BOTH, expand=True)

    def _draw_realtime_worker_status(self, parent, df):
        self._clear_tab(parent)
        ttk.Label(parent, text="작업자별 실시간 현황 (오늘)", style='Header.TLabel').pack(anchor='w', pady=(0, 10))
        
        if df.empty:
            ttk.Label(parent, text="금일 작업 데이터가 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return
            
        summary = df.groupby('worker').agg(
            pcs_completed=('pcs_completed', 'sum'),
            avg_work_time=('work_time', 'mean'),
            session_count=('worker', 'size')
        ).reset_index().sort_values(by='pcs_completed', ascending=False)
        
        summary['pallets_completed'] = summary['pcs_completed'] / 60

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['작업자', '총 PCS', '총 Pallets', '평균 시간', '세트 수']
        
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")
        
        for col in cols: 
            tree.heading(col, text=col, anchor='center', command=lambda c=col: self._sort_treeview(tree, c, False))
            base_width = self.column_widths.get(f'realtime_worker_{col}', 100)
            tree.column(col, width=int(base_width * self.scale_factor), anchor='center', stretch=tk.YES, minwidth=60)
            
        for i, row in summary.iterrows():
            values = [
                row['worker'], f"{int(row['pcs_completed']):,}", f"{row['pallets_completed']:.1f}",
                f"{row['avg_work_time']:.1f}초", f"{int(row['session_count']):,}"
            ]
            tree.insert('', 'end', values=values, tags=("oddrow" if i % 2 == 0 else "",))

        if not summary.empty:
            total_pcs = summary['pcs_completed'].sum()
            total_pallets = summary['pallets_completed'].sum()
            total_sets = summary['session_count'].sum()
            overall_avg_time = df['work_time'].mean() if not df.empty else 0
            total_values = ['총계', f"{int(total_pcs):,}", f"{total_pallets:.1f}", f"{overall_avg_time:.1f}초", f"{int(total_sets):,}"]
            tree.insert('', 'end', values=['','','','',''], tags=('spacer',), open=False)
            tree.insert('', 'end', values=total_values, tags=('Total.Treeview',))

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        vsb.pack(side='right', fill='y')
        tree.pack(fill='both', expand=True, side='left')

        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='realtime_worker': self._on_column_resize(e, t, name))

    def _draw_realtime_item_status(self, parent, df):
        self._clear_tab(parent)
        ttk.Label(parent, text=f"품목별 실시간 현황 (오늘)", style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        if df.empty:
            ttk.Label(parent, text="금일 작업 데이터가 없습니다.", style="Sidebar.TLabel").pack(expand=True)
            return

        item_summary = df.groupby('item_name')['pcs_completed'].sum().reset_index()
        item_summary = item_summary.sort_values(by='pcs_completed', ascending=False)
        item_summary = item_summary[item_summary['pcs_completed'] > 0]
        
        item_summary['pallets_completed'] = item_summary['pcs_completed'] / 60

        tree_container = ttk.Frame(parent)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명', '생산량 (PCS)', '생산량 (Pallets)']
        col_widths = {'품목명': 180, '생산량 (PCS)': 100, '생산량 (Pallets)': 100}

        tree = ttk.Treeview(tree_container, columns=cols, show="headings")
        
        for col in cols:
            anchor = 'w' if col == '품목명' else 'e'
            tree.heading(col, text=col, anchor=anchor, command=lambda c=col: self._sort_treeview(tree, c, False))
            base_width = self.column_widths.get(f'realtime_item_{col}', col_widths.get(col, 120))
            tree.column(col, width=int(base_width*self.scale_factor), anchor=anchor, stretch=tk.YES, minwidth=80)

        for i, row in item_summary.iterrows():
            pcs_val = f"{int(row['pcs_completed']):,}"
            pallets_val = f"{row['pallets_completed']:.1f}"
            tree.insert('', 'end', values=[row['item_name'], pcs_val, pallets_val], tags=("oddrow" if i % 2 == 0 else "",))

        if not item_summary.empty:
            total_pcs = item_summary['pcs_completed'].sum()
            total_pallets = item_summary['pallets_completed'].sum()
            total_values = ['총계', f"{int(total_pcs):,}", f"{total_pallets:.1f}"]
            tree.insert('', 'end', values=['','',''], tags=('spacer',), open=False)
            tree.insert('', 'end', values=total_values, tags=('Total.Treeview',))

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=vsb.set)
        
        vsb.pack(side='right', fill='y')
        tree.pack(side='left', fill='both', expand=True)

        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='realtime_item': self._on_column_resize(e, t, name))
    
    # ### [REPLACED] ### Replaced the whole method for a more sophisticated layout and new table.
    def _draw_overall_comparison_tab(self, parent_tab):
        self._clear_tab(parent_tab)
        
        control_frame = ttk.Frame(parent_tab, style='Card.TFrame', padding=10)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        radio_frame = ttk.Frame(control_frame, style='Sidebar.TFrame')
        radio_frame.pack(side=tk.LEFT, padx=(0, 20))
        ttk.Radiobutton(radio_frame, text="금일 비교", variable=self.comparison_period_mode_var, value="금일 비교", command=self._toggle_comparison_date_widgets).pack(anchor='w')
        ttk.Radiobutton(radio_frame, text="기간별 비교", variable=self.comparison_period_mode_var, value="기간별 비교", command=self._toggle_comparison_date_widgets).pack(anchor='w')

        self.comparison_date_frame = ttk.Frame(control_frame, style='Sidebar.TFrame')
        self.comparison_date_frame.pack(side=tk.LEFT)
        today = datetime.date.today()
        self.comparison_start_date_entry = DateEntry(self.comparison_date_frame, width=12, date_pattern='y-mm-dd')
        self.comparison_start_date_entry.set_date(today)
        self.comparison_start_date_entry.pack(side=tk.LEFT)
        ttk.Label(self.comparison_date_frame, text=" ~ ", style='Sidebar.TLabel').pack(side=tk.LEFT)
        self.comparison_end_date_entry = DateEntry(self.comparison_date_frame, width=12, date_pattern='y-mm-dd')
        self.comparison_end_date_entry.set_date(today)
        self.comparison_end_date_entry.pack(side=tk.LEFT, padx=(0, 10))
        
        ttk.Button(control_frame, text="조회", command=self._update_comparison_view).pack(side=tk.LEFT)
        
        self.comparison_content_frame = ttk.Frame(parent_tab, style='TFrame')
        self.comparison_content_frame.pack(fill=tk.BOTH, expand=True)

        self._toggle_comparison_date_widgets()

    def _toggle_comparison_date_widgets(self):
        if not self.comparison_content_frame: return

        if self.comparison_period_mode_var.get() == "금일 비교":
            if self.comparison_date_frame.winfo_ismapped():
                self.comparison_date_frame.pack_forget()
        else:
            if not self.comparison_date_frame.winfo_ismapped():
                self.comparison_date_frame.pack(side=tk.LEFT)
        self._update_comparison_view()

    def _update_comparison_view(self):
        self._clear_tab(self.comparison_content_frame)

        df_full_period = self.full_df.copy()
        if df_full_period.empty:
            ttk.Label(self.comparison_content_frame, text="비교할 데이터가 없습니다.", justify='center').pack(expand=True, pady=20)
            return

        mode = self.comparison_period_mode_var.get()
        if mode == "금일 비교":
            target_date = datetime.date.today()
            df = df_full_period[pd.to_datetime(df_full_period['date']).dt.date == target_date]
        else:
            start_date = self.comparison_start_date_entry.get_date()
            end_date = self.comparison_end_date_entry.get_date()
            df = df_full_period[(pd.to_datetime(df_full_period['date']).dt.date >= start_date) & (pd.to_datetime(df_full_period['date']).dt.date <= end_date)]

        if df.empty:
            ttk.Label(self.comparison_content_frame, text="해당 기간에 데이터가 없습니다.", justify='center').pack(expand=True, pady=20)
            return

        # --- Main Layout Pane (Vertical) ---
        view_pane = ttk.PanedWindow(self.comparison_content_frame, orient=tk.VERTICAL)
        view_pane.pack(fill=tk.BOTH, expand=True)
        self.paned_windows['comparison_view'] = view_pane

        # --- Top Section (KPIs) ---
        kpi_frame = ttk.Frame(view_pane, style='TFrame')
        view_pane.add(kpi_frame, weight=0, minsize=140)

        # --- Bottom Section (Tables) ---
        bottom_pane = ttk.PanedWindow(view_pane, orient=tk.HORIZONTAL)
        view_pane.add(bottom_pane, weight=1)
        self.paned_windows['comparison_bottom_pane'] = bottom_pane
        
        pallet_comp_frame = ttk.Frame(bottom_pane, style='TFrame')
        bottom_pane.add(pallet_comp_frame, weight=1)

        lead_time_frame = ttk.Frame(bottom_pane, style='TFrame')
        bottom_pane.add(lead_time_frame, weight=1)

        # --- Data Processing & Drawing ---
        df['pallets'] = df['pcs_completed'] / 60.0
        df_comp = df[df['process'].isin(['이적실', '포장실'])]
        
        if not df_comp.empty:
            transfer_df = df_comp[df_comp['process'] == '이적실']
            packaging_df = df_comp[df_comp['process'] == '포장실']
            
            # Process and draw Pallet Comparison table
            pivot = df_comp.pivot_table(index='item_name', columns='process', values='pallets', aggfunc='sum').fillna(0)
            if '이적실' not in pivot.columns: pivot['이적실'] = 0
            if '포장실' not in pivot.columns: pivot['포장실'] = 0
            pivot['달성률'] = (pivot['포장실'] / pivot['이적실'] * 100).replace([np.inf, -np.inf], 100).fillna(100)
            
            total_transfer = pivot['이적실'].sum()
            total_packaging = pivot['포장실'].sum()
            overall_achievement = (total_packaging / total_transfer * 100) if total_transfer > 0 else 100

            kpi_frame.grid_columnconfigure((0,1,2), weight=1)
            self._create_dashboard_card(kpi_frame, "총 이적 파렛트", f"{total_transfer:.1f}", "📤").grid(row=0, column=0, sticky='nsew', padx=5, pady=5)
            self._create_dashboard_card(kpi_frame, "총 포장 파렛트", f"{total_packaging:.1f}", "📥").grid(row=0, column=1, sticky='nsew', padx=5, pady=5)
            self._create_dashboard_card(kpi_frame, "전체 포장 달성률", f"{overall_achievement:.1f}%", "🎯",
                                        value_color=self.COLOR_SUCCESS if overall_achievement >= 100 else self.COLOR_DANGER).grid(row=0, column=2, sticky='nsew', padx=5, pady=5)

            pivot_with_total = pd.concat([
                pivot, 
                pd.DataFrame([{'이적실': total_transfer, '포장실': total_packaging, '달성률': overall_achievement}], index=['총계'])
            ]).reset_index().rename(columns={'index':'item_name'})
            
            self._draw_comparison_pallet_table(pallet_comp_frame, pivot_with_total)
            
            # Process and draw Lead Time table
            lead_time_df = pd.DataFrame()
            if not transfer_df.empty and not packaging_df.empty and 'end_time_dt' in transfer_df.columns:
                last_transfers = transfer_df.groupby('item_name')['end_time_dt'].max().reset_index().rename(columns={'end_time_dt': 'last_transfer_end_time'})
                first_packagings = packaging_df.groupby('item_name')['start_time_dt'].min().reset_index().rename(columns={'start_time_dt': 'first_packaging_start_time'})
                
                lead_time_df = pd.merge(last_transfers, first_packagings, on='item_name', how='inner')
                if not lead_time_df.empty:
                    lead_time_df['lead_time_seconds'] = (lead_time_df['first_packaging_start_time'] - lead_time_df['last_transfer_end_time']).dt.total_seconds()
                    lead_time_df = lead_time_df[lead_time_df['lead_time_seconds'] >= 0].sort_values(by='lead_time_seconds', ascending=False)

            self._draw_comparison_lead_time_table(lead_time_frame, lead_time_df)
        
        else: # if df_comp is empty
            self._draw_comparison_pallet_table(pallet_comp_frame, pd.DataFrame())
            self._draw_comparison_lead_time_table(lead_time_frame, pd.DataFrame())
            self._clear_tab(kpi_frame)
            ttk.Label(kpi_frame, text="데이터 없음", style="Sidebar.TLabel").pack(expand=True)
            
        self.root.update_idletasks()
        bottom_pane.after(10, lambda p=bottom_pane, n='comparison_bottom_pane': p.sashpos(0, self.pane_positions.get(n, max(p.winfo_width() // 2, 100))))
    
    # ### [NEW] ### New method to draw the pallet comparison table
    def _draw_comparison_pallet_table(self, parent, pivot_with_total):
        self._clear_tab(parent)
        
        container = ttk.Frame(parent, style='Card.TFrame', padding=10)
        container.pack(fill=tk.BOTH, expand=True, padx=(5,2), pady=5)
        
        ttk.Label(container, text="공정별 생산량 비교 (Pallet)", style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        if pivot_with_total.empty:
            ttk.Label(container, text="비교할 생산량 데이터가 없습니다.", style="Sidebar.TLabel", justify='center').pack(expand=True)
            return

        tree_container = ttk.Frame(container)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명', '이적(Pallet)', '포장(Pallet)', '달성률(%)']
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")

        for col in cols:
            anchor = 'w' if col == '품목명' else 'e'
            tree.heading(col, text=col, anchor=anchor, command=lambda c=col: self._sort_treeview(tree, c, False))
            width = 200 if col == '품목명' else 120
            tree.column(col, anchor=anchor, width=self.column_widths.get(f'compare_{col}', width), stretch=tk.YES if col == '품목명' else tk.NO, minwidth=80)

        for i, row in pivot_with_total.iterrows():
            achievement_rate = row['달성률']
            tags = []
            if row['item_name'] == '총계':
                tags.append('Total.Treeview')
            else:
                tags.append('GreenRow.Treeview' if achievement_rate >= 100 else 'RedRow.Treeview')
                if i % 2 == 1:
                    tags.append('oddrow')

            values = [row['item_name'], f"{row['이적실']:.1f}", f"{row['포장실']:.1f}", f"{achievement_rate:.1f}%"]
            tree.insert('', 'end', values=values, tags=tuple(tags))

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True, side='left')
        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='compare': self._on_column_resize(e, t, name))
        
        desc_frame = ttk.Frame(container, style='Card.TFrame')
        desc_frame.pack(fill=tk.X, side=tk.BOTTOM, pady=(5,0))
        ttk.Label(desc_frame, text="💡 달성률 100% 이상은 녹색🟢, 미만은 빨간색🔴으로 표시됩니다.", style='Sidebar.TLabel').pack(anchor='w')

    # ### [NEW] ### New method to draw the lead time table
    def _draw_comparison_lead_time_table(self, parent, lead_time_df):
        self._clear_tab(parent)
        
        container = ttk.Frame(parent, style='Card.TFrame', padding=10)
        container.pack(fill=tk.BOTH, expand=True, padx=(2,5), pady=5)
        
        ttk.Label(container, text="품목별 이적→포장 대기시간", style='Header.TLabel').pack(anchor='w', pady=(0, 10))

        if lead_time_df.empty:
            ttk.Label(container, text="대기시간을 계산할 데이터가 없습니다.\n(동일 품목의 이적/포장 기록이 모두 필요)", style="Sidebar.TLabel", justify='center').pack(expand=True)
            return

        avg_lead_time = lead_time_df['lead_time_seconds'].mean()

        tree_container = ttk.Frame(container)
        tree_container.pack(fill=tk.BOTH, expand=True)

        cols = ['품목명', '최종 이적 완료', '최초 포장 시작', '대기 시간']
        tree = ttk.Treeview(tree_container, columns=cols, show="headings")

        for col in cols:
            anchor = 'w' if col == '품목명' else 'center'
            width = 180 if col == '품목명' else 140
            tree.heading(col, text=col, anchor=anchor, command=lambda c=col: self._sort_treeview(tree, c, False))
            tree.column(col, anchor=anchor, width=self.column_widths.get(f'lead_time_{col}', width), stretch=tk.YES if col == '품목명' else tk.NO)

        for i, row in lead_time_df.iterrows():
            values = [
                row['item_name'],
                row['last_transfer_end_time'].strftime('%m-%d %H:%M'),
                row['first_packaging_start_time'].strftime('%m-%d %H:%M'),
                self._format_lead_time(row['lead_time_seconds'])
            ]
            tree.insert('', 'end', values=values, tags=("oddrow" if i % 2 == 0 else "",))
            
        tree.insert('', 'end', values=['','','',''], tags=('spacer',), open=False)
        tree.insert('', 'end', values=['평균 대기 시간', '', '', self._format_lead_time(avg_lead_time)], tags=('Total.Treeview',))

        vsb = ttk.Scrollbar(tree_container, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(tree_container, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        vsb.pack(side='right', fill='y')
        hsb.pack(side='bottom', fill='x')
        tree.pack(fill='both', expand=True, side='left')
        tree.bind('<ButtonRelease-1>', lambda e, t=tree, name='lead_time': self._on_column_resize(e, t, name))

    def on_closing(self):
        if self.auto_refresh_id:
            self.root.after_cancel(self.auto_refresh_id)
        if self.observer:
            self.observer.stop()
            if self.monitor_thread and self.monitor_thread.is_alive():
                self.observer.join()
        self.save_settings()
        self.root.destroy()

    def run(self): self.root.mainloop()

def main():
    # check_and_apply_updates() # 필요 시 주석 해제
    root = tk.Tk()
    app = WorkerAnalysisGUI(root)
    app.run()

if __name__ == "__main__":
    main()