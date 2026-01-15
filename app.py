# -*- coding: utf-8 -*-
"""
app_db.py - Database-backed WorkerAnalysisGUI Web Application
SQLite 데이터베이스 기반으로 변환된 Flask 애플리케이션
"""

import os
import threading
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import re
from io import BytesIO

from flask import Flask, jsonify, render_template, request, Response
from flask_socketio import SocketIO
import gzip
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from db_manager import DatabaseManager
from analyzer_optimized import WorkerPerformance, OptimizedDataAnalyzer

def convert_to_json_serializable(obj):
    """NumPy/Pandas 타입을 JSON 직렬화 가능한 타입으로 변환"""
    import datetime as dt

    if isinstance(obj, (np.integer, np.int32, np.int64)):
        return int(obj)
    elif isinstance(obj, (np.floating, np.float32, np.float64)):
        if np.isinf(obj) or np.isnan(obj):
            return None
        return float(obj)
    elif isinstance(obj, np.bool_):
        return bool(obj)
    elif isinstance(obj, (datetime, pd.Timestamp)):
        return obj.isoformat()
    elif isinstance(obj, dt.date):
        return obj.isoformat()
    elif isinstance(obj, dt.time):
        return obj.isoformat()
    elif obj is None:
        return None
    elif hasattr(obj, '__len__') and len(obj) == 1:
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
    elif not hasattr(obj, '__len__'):
        try:
            if pd.isna(obj):
                return None
        except (TypeError, ValueError):
            pass
    elif isinstance(obj, dict):
        return {k: convert_to_json_serializable(v) for k, v in obj.items()}
    elif isinstance(obj, (list, tuple)):
        return [convert_to_json_serializable(item) for item in obj]
    return obj

def load_settings():
    try:
        with open('config/analyzer_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings.get('log_folder_path', '/home/syncthing/backup')
    except (FileNotFoundError, json.JSONDecodeError):
        return '/home/syncthing/backup'

LOG_FOLDER_PATH = load_settings()
DB_PATH = '/root/WorkerAnalysisGUI-web/data/worker_analysis.db'

# Flask 및 SocketIO 설정
app = Flask(__name__)

# 보안 모듈 적용
from security import setup_security, InputValidator, rate_limit, validate_date_params
setup_security(app)

socketio = SocketIO(app, async_mode='eventlet')

# Stock Ledger Blueprint 등록
from blueprints.stock import stock_bp
app.register_blueprint(stock_bp, url_prefix='/stock')

# Stock Ledger Socket.IO 네임스페이스
stock_viewers = set()

@socketio.on('connect', namespace='/stock')
def stock_connect():
    """재고 원장 실시간 연결"""
    stock_viewers.add(request.sid)
    socketio.emit('viewer_count', len(stock_viewers), namespace='/stock')
    print(f"[Stock] 클라이언트 연결: {request.sid} (총 {len(stock_viewers)}명)")

@socketio.on('disconnect', namespace='/stock')
def stock_disconnect():
    """재고 원장 연결 해제"""
    stock_viewers.discard(request.sid)
    socketio.emit('viewer_count', len(stock_viewers), namespace='/stock')
    print(f"[Stock] 클라이언트 연결 해제: {request.sid} (총 {len(stock_viewers)}명)")

def notify_stock_update(entry_data):
    """재고 변경 알림 (외부에서 호출 가능)"""
    socketio.emit('stock_update', entry_data, namespace='/stock')

# Database Manager
db = DatabaseManager(DB_PATH)

# Data Analyzer
analyzer = OptimizedDataAnalyzer()

RADAR_METRICS_CONFIG = {
    "포장실": { '세트완료시간': ('avg_work_time', False, 1.0), '첫스캔준비성': ('avg_latency', False, 1.0), '무결점달성률': ('first_pass_yield', True, 0.7), '세트당PCS': ('avg_pcs_per_tray', True, 1.0) },
    "이적실": { '신속성': ('avg_work_time', False, 1.0), '준속성': ('avg_latency', False, 1.0), '초도수율': ('first_pass_yield', True, 0.7), '안정성': ('work_time_std', False, 1.0) },
    "검사실": { '신속성': ('avg_work_time', False, 1.0), '준비성': ('avg_latency', False, 0.8), '무결점달성률': ('first_pass_yield', True, 1.2), '안정성': ('work_time_std', False, 0.7), '품질 정확도': ('defect_rate', False, 1.5) }
}
RADAR_METRICS_CONFIG['전체 비교'] = RADAR_METRICS_CONFIG['이적실']

# 파일 감시 핸들러
class LogFileHandler(FileSystemEventHandler):
    def __init__(self, socket_instance):
        self.socketio = socket_instance
        self.last_triggered_time = 0

    def on_modified(self, event):
        if time.time() - self.last_triggered_time < 5: return
        if not event.is_directory and "작업이벤트로그" in str(os.path.basename(event.src_path)):
            self.last_triggered_time = time.time()
            print(f"파일 변경 감지: {event.src_path}. 증분 동기화 트리거...")
            # 증분 동기화 실행 (백그라운드)
            threading.Thread(target=run_incremental_sync, daemon=True).start()
            self.socketio.emit('data_updated', {'message': 'Log file has been modified.'})

def run_incremental_sync():
    """증분 동기화 실행"""
    try:
        import subprocess
        result = subprocess.run(
            ['/root/WorkerAnalysisGUI-web/venv/bin/python', 'migrate_csv_to_db.py', '--incremental'],
            cwd='/root/WorkerAnalysisGUI-web',
            capture_output=True,
            timeout=300
        )
        if result.returncode == 0:
            print("증분 동기화 성공")
        else:
            print(f"증분 동기화 실패: {result.stderr.decode()}")
    except Exception as e:
        print(f"증분 동기화 오류: {e}")

def start_file_monitor():
    event_handler = LogFileHandler(socketio)
    observer = Observer()
    observer.schedule(event_handler, LOG_FOLDER_PATH, recursive=False)
    observer.start()
    print(f"'{LOG_FOLDER_PATH}' 폴더에 대한 파일 감시를 시작합니다.")
    try:
        while True: time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()

def calculate_kpis(sessions_df: pd.DataFrame) -> dict:
    """세션 데이터로부터 KPI 계산"""
    if sessions_df.empty:
        return {}

    def safe_float(value, default=0.0):
        if pd.isna(value) or np.isinf(value):
            return default
        return float(value)

    return {
        'total_pcs_completed': int(sessions_df['pcs_completed'].sum()),
        'total_trays': len(sessions_df),
        'avg_work_time': safe_float(sessions_df['work_time'].mean()),
        'avg_latency': safe_float(sessions_df['latency'].mean()),
        'total_process_errors': int(sessions_df['process_errors'].sum()),
        'first_pass_yield': safe_float((sessions_df['had_error'] == 0).sum() / len(sessions_df)) if len(sessions_df) > 0 else 0.0,
        'avg_pcs_per_tray': safe_float(sessions_df['pcs_completed'].mean())
    }

def analyze_dataframe(sessions_df: pd.DataFrame, radar_metrics: dict, full_sessions_df: pd.DataFrame = None):
    """세션 데이터 분석"""
    if sessions_df.empty:
        return {}, {}, None, pd.DataFrame()

    # 작업자별 집계
    worker_data = {}
    for worker, group in sessions_df.groupby('worker'):
        perf = WorkerPerformance(worker=worker)
        perf.session_count = len(group)

        # NaN/Infinity 안전 변환 함수
        def safe_float(value, default=0.0):
            if pd.isna(value) or np.isinf(value):
                return default
            return float(value)

        perf.avg_work_time = safe_float(group['work_time'].mean())
        perf.avg_latency = safe_float(group['latency'].mean())
        perf.total_pcs_completed = int(group['pcs_completed'].sum())
        perf.total_process_errors = int(group['process_errors'].sum())
        perf.first_pass_yield = safe_float((group['had_error'] == 0).sum() / len(group))
        perf.avg_pcs_per_tray = safe_float(group['pcs_completed'].mean())
        perf.work_time_std = safe_float(group['work_time'].std())
        perf.defect_rate = safe_float(group['process_errors'].sum() / group['pcs_completed'].sum()) if group['pcs_completed'].sum() > 0 else 0.0

        worker_data[worker] = perf

    kpis = calculate_kpis(sessions_df)

    return worker_data, kpis, None, pd.DataFrame()

# ====================================================================
# Flask 라우트
# ====================================================================

@app.route('/')
def index():
    cache_buster = str(int(time.time()))
    return render_template('index.html', cache_buster=cache_buster)

@app.route('/api/data', methods=['POST'])
def get_analysis_data():
    print("\n[API] /api/data 요청 시작 (DB 기반)")
    try:
        filters = request.json
        process_mode = filters.get('process_mode', '이적실')
        start_date = filters.get('start_date')
        end_date = filters.get('end_date')

        print(f"[API] 공정={process_mode}, 기간={start_date}~{end_date}")

        # 데이터베이스에서 날짜 범위 가져오기
        if not start_date or not end_date:
            min_date, max_date = db.get_date_range(process_mode)
            start_date = start_date or min_date
            end_date = end_date or max_date

        # 30일 평균 계산을 위한 확장된 기간
        extended_start = None
        if start_date:
            try:
                selected_start = datetime.strptime(start_date, '%Y-%m-%d')
                extended_start = (selected_start - timedelta(days=60)).strftime('%Y-%m-%d')
                print(f"[API] 30일 평균용 확장 시작 날짜: {extended_start}")
            except:
                extended_start = None

        # 데이터베이스에서 세션 조회
        full_df = db.get_sessions(start_date=extended_start, end_date=end_date, process=process_mode)
        print(f"[API] DB에서 {len(full_df)}개 세션 로드 완료 ({len(full_df) * 0.001:.2f}초 예상)")

        # 포장실 데이터: 트레이 단위로 PCS 추정 (1 트레이 = 60 PCS)
        if process_mode == '포장실' and not full_df.empty:
            # 빈 레코드 제외 (작업시간=0, 품목=N/A인 무효 데이터)
            before_filter = len(full_df)
            full_df = full_df[~((full_df['work_time'] == 0) & (full_df['item_code'] == 'N/A'))].copy()
            if before_filter != len(full_df):
                print(f"[API] 포장실 빈 레코드 제외: {before_filter}개 → {len(full_df)}개")

            original_total = full_df['pcs_completed'].sum()
            full_df['pcs_completed'] = 60  # 각 트레이당 60 PCS 추정
            estimated_total = full_df['pcs_completed'].sum()
            print(f"[API] 포장실 PCS 추정 적용: {int(original_total):,} PCS (실제) → {int(estimated_total):,} PCS (추정, {len(full_df)}트레이 × 60)")

        # 테스트 데이터 제외 (포장실의 1.0.5는 실제 작업자이므로 제외하지 않음)
        TEST_WORKERS = ['3', 'TEST', '1234', '2', 'TESTER']
        if process_mode != '포장실':
            TEST_WORKERS.append('1.0.5')  # 포장실 외에서는 1.0.5 제외
        full_df = full_df[~full_df['worker'].isin(TEST_WORKERS)].copy()
        print(f"[API] 테스트 작업자 제외 후: {len(full_df)}개 세션")

        if full_df.empty:
            print("[API] 데이터 없음")
            return jsonify({
                'kpis': {}, 'worker_data': [], 'normalized_performance': [],
                'workers': [], 'date_range': {'min': None, 'max': None},
                'filtered_sessions_data': [], 'filtered_raw_events': []
            })

        # 작업자 필터링
        all_workers = sorted(full_df['worker'].unique().tolist())
        selected_workers = filters.get('selected_workers') or all_workers

        # 필터링
        filtered_df = full_df[
            (full_df['date'] >= pd.to_datetime(start_date)) &
            (full_df['date'] <= pd.to_datetime(end_date)) &
            (full_df['worker'].isin(selected_workers))
        ].copy()

        print(f"[API] 필터링 완료: {len(filtered_df)}개 세션")

        # 분석 전 누락된 컬럼 추가
        if 'idle_time' not in filtered_df.columns:
            filtered_df['idle_time'] = 0.0
        if 'defective_count' not in filtered_df.columns:
            filtered_df['defective_count'] = 0
        if 'idle_time' not in full_df.columns:
            full_df['idle_time'] = 0.0
        if 'defective_count' not in full_df.columns:
            full_df['defective_count'] = 0

        # 분석
        radar_metrics = RADAR_METRICS_CONFIG.get(process_mode, RADAR_METRICS_CONFIG['이적실'])
        worker_data, kpis, _, normalized_df = analyzer.analyze_dataframe(filtered_df, radar_metrics, full_df)

        # 생산량 0인 작업자 제외
        active_worker_data = {k: v for k, v in worker_data.items() if v.total_pcs_completed > 0}
        worker_data = active_worker_data

        # normalized_df에서도 생산량 0인 작업자 제외
        if normalized_df is not None and not normalized_df.empty:
            active_workers = list(active_worker_data.keys())
            normalized_df = normalized_df[normalized_df['worker'].isin(active_workers)]
            print(f"[API] normalized_df 필터링 완료: {len(normalized_df)}명")

        # JSON 직렬화
        worker_data_json = [perf.__dict__ for perf in worker_data.values()]
        for item in worker_data_json:
            for key, value in item.items():
                if isinstance(value, (datetime, pd.Timestamp)):
                    item[key] = value.isoformat()
                elif isinstance(value, (np.integer, np.int32, np.int64)):
                    item[key] = int(value)
                elif isinstance(value, (np.floating, np.float32, np.float64)):
                    item[key] = None if (np.isinf(value) or np.isnan(value)) else float(value)
                elif isinstance(value, float):
                    # Python float도 Infinity 체크
                    item[key] = None if (value == float('inf') or value == float('-inf') or value != value) else value

        # 30일 평균 요약
        safe_historical_summary = {'daily_stats': [], 'total_sessions': 0, 'num_days': 0,
                                   'averages': {'daily_pcs': 0, 'hourly_pcs': [0] * 16},
                                   'date_range': {'start': None, 'end': None}}

        if not full_df.empty:
            try:
                thirty_days_ago = datetime.now() - timedelta(days=30)
                recent_df = full_df[full_df['date'] >= pd.Timestamp(thirty_days_ago)].copy()

                if not recent_df.empty:
                    daily_summary = recent_df.groupby(recent_df['date'].dt.date).agg({
                        'pcs_completed': 'sum',
                        'work_time': 'mean',
                        'latency': 'mean',
                        'first_pass_yield': 'mean',
                        'worker': 'nunique'
                    }).reset_index()

                    # 시간대별 평균 계산 (0-23시 전체)
                    recent_df['hour'] = pd.to_datetime(recent_df['start_time_dt']).dt.hour
                    hourly_sum = recent_df.groupby('hour')['pcs_completed'].sum()
                    num_days = recent_df['date'].nunique()
                    hourly_avg = (hourly_sum / num_days).reindex(range(0, 24), fill_value=0)

                    # 요일별 평균 계산 (월-일: 0-6)
                    recent_df['weekday'] = pd.to_datetime(recent_df['date']).dt.dayofweek
                    weekday_sum = recent_df.groupby('weekday')['pcs_completed'].sum()
                    weekday_counts = recent_df.groupby('weekday')['date'].nunique()
                    weekday_avg = (weekday_sum / weekday_counts).reindex(range(0, 7), fill_value=0)

                    # 월 내 주차별 평균 계산 (1-5주차)
                    recent_df['week_of_month'] = (pd.to_datetime(recent_df['date']).dt.day - 1) // 7 + 1
                    week_sum = recent_df.groupby('week_of_month')['pcs_completed'].sum()
                    week_counts = recent_df.groupby('week_of_month')['date'].nunique()
                    week_avg = (week_sum / week_counts).reindex(range(1, 6), fill_value=0)

                    # 월별 평균 계산 (1-12월)
                    recent_df['month_num'] = pd.to_datetime(recent_df['date']).dt.month
                    month_sum = recent_df.groupby('month_num')['pcs_completed'].sum()
                    month_counts = recent_df.groupby('month_num')['date'].nunique()
                    month_avg = (month_sum / month_counts).reindex(range(1, 13), fill_value=0)

                    safe_historical_summary = {
                        'daily_stats': json.loads(daily_summary.to_json(orient='records', date_format='iso')),
                        'total_sessions': len(recent_df),
                        'num_days': num_days,
                        'averages': {
                            'daily_pcs': round(daily_summary['pcs_completed'].mean(), 1),
                            'hourly_pcs': hourly_avg.round(1).to_dict(),  # 시간대별 평균 (0-23시)
                            'weekday_pcs': weekday_avg.round(1).to_dict(),  # 요일별 평균 (0-6: 월-일)
                            'week_of_month_pcs': week_avg.round(1).to_dict(),  # 월 내 주차별 평균 (1-5주차)
                            'monthly_pcs': month_avg.round(1).to_dict()  # 월별 평균 (1-12월)
                        },
                        'date_range': {
                            'start': recent_df['date'].min().isoformat(),
                            'end': recent_df['date'].max().isoformat()
                        }
                    }
                    print(f"[API] 30일 평균 요약 생성: {len(daily_summary)}일치, 시간대별/요일별/주차별/월별 평균 포함")
            except Exception as e:
                print(f"[API] 30일 요약 오류: {e}")

        # 최근 30일 기준 KPI 범위 계산 (작업자가 적을 때 왜곡 방지)
        baseline_stats = {
            'daily_prod': {'min': 0, 'max': 100},
            'hourly_eff': {'min': 0, 'max': 100},
            'fpy': {'min': 0, 'max': 100},
            'consistency': {'min': 0, 'max': 100},
            'intensity': {'min': 0, 'max': 10}
        }

        if not full_df.empty:
            try:
                thirty_days_ago = datetime.now() - timedelta(days=30)
                recent_df = full_df[full_df['date'] >= pd.Timestamp(thirty_days_ago)].copy()

                if not recent_df.empty and len(recent_df['worker'].unique()) > 0:
                    # 작업자별 KPI 계산
                    worker_stats = recent_df.groupby('worker').agg({
                        'pcs_completed': 'sum',  # 총생산량
                        'work_time': ['mean', 'std'],  # 평균 시간, 표준편차
                        'first_pass_yield': 'mean',  # FPY
                        'worker': 'count'  # 세션 수 (집중도)
                    }).reset_index()

                    # 컬럼명 정리
                    worker_stats.columns = ['worker', 'total_pcs', 'avg_work_time', 'work_time_std', 'avg_fpy', 'session_count']

                    # 각 KPI 계산
                    worker_stats['hourly_eff'] = worker_stats.apply(
                        lambda x: (x['total_pcs'] / x['session_count'] / x['avg_work_time'] * 3600) if x['avg_work_time'] > 0 else 0,
                        axis=1
                    )
                    worker_stats['consistency'] = worker_stats.apply(
                        lambda x: 100 - min((x['work_time_std'] / x['avg_work_time'] * 100) if x['avg_work_time'] > 0 else 0, 100),
                        axis=1
                    )
                    worker_stats['fpy_pct'] = worker_stats['avg_fpy'] * 100

                    # Min/Max 계산
                    baseline_stats = {
                        'daily_prod': {
                            'min': float(worker_stats['total_pcs'].min()),
                            'max': float(worker_stats['total_pcs'].max())
                        },
                        'hourly_eff': {
                            'min': float(worker_stats['hourly_eff'].min()),
                            'max': float(worker_stats['hourly_eff'].max())
                        },
                        'fpy': {
                            'min': float(worker_stats['fpy_pct'].min()),
                            'max': float(worker_stats['fpy_pct'].max())
                        },
                        'consistency': {
                            'min': float(worker_stats['consistency'].min()),
                            'max': float(worker_stats['consistency'].max())
                        },
                        'intensity': {
                            'min': float(worker_stats['session_count'].min()),
                            'max': float(worker_stats['session_count'].max())
                        }
                    }
                    print(f"[API] 30일 기준 KPI 범위 계산 완료: {len(worker_stats)}명 기준")
            except Exception as e:
                print(f"[API] 30일 기준 KPI 계산 오류: {e}")

        # 응답 데이터
        safe_sessions_data = json.loads(filtered_df.replace([np.inf, -np.inf], np.nan).fillna('').to_json(orient='records', date_format='iso'))

        valid_dates = full_df['date'].dropna()
        date_range = {
            'min': valid_dates.min().strftime('%Y-%m-%d') if not valid_dates.empty else None,
            'max': valid_dates.max().strftime('%Y-%m-%d') if not valid_dates.empty else None
        }

        # normalized_df JSON 변환
        normalized_df_json = []
        if normalized_df is not None and not normalized_df.empty:
            normalized_df_json = json.loads(normalized_df.replace([np.inf, -np.inf], None).to_json(orient='records', date_format='iso'))

        # 전체 비교 모드용 comparison_data 생성
        comparison_data = None
        if process_mode == '전체 비교':
            print("[API] 전체 비교 데이터 생성 중...")
            try:
                def calculate_process_kpis(df):
                    """공정별 KPI 계산"""
                    if df.empty:
                        return {
                            'total_trays': 0, 'total_pcs_completed': 0,
                            'avg_tray_time': 0, 'avg_fpy': 0
                        }
                    return {
                        'total_trays': int(len(df)),
                        'total_pcs_completed': int(df['pcs_completed'].sum()),
                        'avg_tray_time': float(df['work_time'].mean()),
                        'avg_fpy': float(df['first_pass_yield'].mean())
                    }

                # 선택 기간 기준 데이터 (사용자가 선택한 날짜 범위)
                period_inspection = db.get_sessions(start_date=start_date, end_date=end_date, process='검사실')
                period_transfer = db.get_sessions(start_date=start_date, end_date=end_date, process='이적실')
                period_packaging = db.get_sessions(start_date=start_date, end_date=end_date, process='포장실')

                # 포장실 데이터: 트레이 단위로 PCS 추정 (1 트레이 = 60 PCS)
                if not period_packaging.empty:
                    period_packaging['pcs_completed'] = 60

                period_inspection_kpis = calculate_process_kpis(period_inspection)
                period_transfer_kpis = calculate_process_kpis(period_transfer)
                period_packaging_kpis = calculate_process_kpis(period_packaging)

                # 선택 기간 데이터로 통합 (날짜 필터 반영)
                summary_period = {
                    'inspection': period_inspection_kpis,
                    'transfer': period_transfer_kpis,
                    'packaging': period_packaging_kpis,
                    'transfer_standby_trays': period_inspection_kpis['total_trays'] - period_transfer_kpis['total_trays'],
                    'packaging_standby_trays': period_transfer_kpis['total_trays'] - period_packaging_kpis['total_trays'],
                    'transfer_standby_pcs': period_inspection_kpis['total_pcs_completed'] - period_transfer_kpis['total_pcs_completed'],
                    'packaging_standby_pcs': period_transfer_kpis['total_pcs_completed'] - period_packaging_kpis['total_pcs_completed'],
                }

                # 추세 그래프용 데이터 (선택 기간)
                trends_data = {
                    'inspection': json.loads(period_inspection.replace([np.inf, -np.inf], np.nan).fillna('').to_json(orient='records', date_format='iso')),
                    'transfer': json.loads(period_transfer.replace([np.inf, -np.inf], np.nan).fillna('').to_json(orient='records', date_format='iso')),
                    'packaging': json.loads(period_packaging.replace([np.inf, -np.inf], np.nan).fillna('').to_json(orient='records', date_format='iso')),
                }

                comparison_data = {
                    'summary_period': summary_period,  # summary_today 제거 - 모든 데이터가 선택한 날짜 범위 사용
                    'trends': trends_data
                }

                print(f"[API] 전체 비교 데이터 생성 완료: {start_date}~{end_date} 기간 데이터 (검사실:{period_inspection_kpis['total_trays']}, 이적실:{period_transfer_kpis['total_trays']}, 포장실:{period_packaging_kpis['total_trays']})")

            except Exception as e:
                print(f"[API] 전체 비교 데이터 생성 오류: {e}")
                import traceback
                traceback.print_exc()

        response_data = {
            'kpis': convert_to_json_serializable(kpis),
            'worker_data': convert_to_json_serializable(worker_data_json),
            'normalized_performance': convert_to_json_serializable(normalized_df_json),
            'workers': all_workers,
            'date_range': date_range,
            'filtered_sessions_data': safe_sessions_data,
            'historical_summary': safe_historical_summary,
            'baseline_stats': baseline_stats,
            'filtered_raw_events': [],
            'comparison_data': convert_to_json_serializable(comparison_data)
        }

        # GZIP 압축
        json_str = json.dumps(response_data, ensure_ascii=False)
        gzip_buffer = BytesIO()
        with gzip.GzipFile(mode='wb', fileobj=gzip_buffer, compresslevel=6) as gz_file:
            gz_file.write(json_str.encode('utf-8'))

        compressed_data = gzip_buffer.getvalue()
        original_size = len(json_str.encode('utf-8'))
        compressed_size = len(compressed_data)
        compression_ratio = (1 - compressed_size / original_size) * 100

        print(f"[API] 압축 완료: {original_size:,} bytes → {compressed_size:,} bytes ({compression_ratio:.1f}% 감소)")

        compressed_response = Response(compressed_data)
        compressed_response.headers['Content-Encoding'] = 'gzip'
        compressed_response.headers['Content-Type'] = 'application/json'
        compressed_response.headers['Content-Length'] = str(compressed_size)

        return compressed_response

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"서버 내부 오류: {e}"}), 500

@app.route('/api/barcode_search', methods=['POST'])
def search_barcode():
    """바코드 검색 API - DB 기반"""
    try:
        query = request.json
        barcode = query.get('barcode', '').strip()

        if not barcode:
            return jsonify({"error": "바코드를 입력해주세요."}), 400

        print(f"[API] 바코드 검색: {barcode}")

        conn = db.get_connection()

        # 1. SCAN_OK 이벤트 검색 (부분 일치 허용)
        # 먼저 정확히 일치하는 바코드를 찾고, 없으면 부분 일치 검색
        scan_cursor = conn.execute("""
            SELECT timestamp, worker_name, details, process, barcode
            FROM raw_events
            WHERE barcode = ? AND event = 'SCAN_OK'
            ORDER BY timestamp DESC
            LIMIT 1
        """, (barcode,))

        scan_row = scan_cursor.fetchone()

        # 정확히 일치하는 바코드가 없으면 부분 일치 검색 (LIKE 사용)
        if not scan_row:
            scan_cursor = conn.execute("""
                SELECT timestamp, worker_name, details, process, barcode
                FROM raw_events
                WHERE barcode LIKE ? AND event = 'SCAN_OK'
                ORDER BY timestamp DESC
                LIMIT 1
            """, (f'%{barcode}%',))
            scan_row = scan_cursor.fetchone()

        if not scan_row:
            conn.close()
            return jsonify({"found": False, "message": "바코드를 찾을 수 없습니다."}), 404

        # 실제 찾은 바코드로 업데이트
        actual_barcode = scan_row[4]
        print(f"[API] 바코드 검색 결과: 입력={barcode}, 찾음={actual_barcode}")

        # SCAN_OK 정보 파싱
        try:
            scan_details = json.loads(scan_row[2])
            scan_info = {
                'worker': scan_row[1],
                'timestamp': scan_row[0],
                'process': scan_row[3],
                'interval_sec': scan_details.get('interval_sec', 'N/A')
            }
        except:
            conn.close()
            return jsonify({"found": False, "message": "바코드 데이터 파싱 오류"}), 500

        # 2. TRAY_COMPLETE 이벤트 검색 (같은 작업자, 스캔 이후 시간)
        # 실제 찾은 바코드로 검색
        tray_cursor = conn.execute("""
            SELECT timestamp, details
            FROM raw_events
            WHERE worker_name = ?
              AND event = 'TRAY_COMPLETE'
              AND timestamp >= ?
              AND details LIKE ?
            ORDER BY timestamp
            LIMIT 1
        """, (scan_info['worker'], scan_info['timestamp'], f'%{actual_barcode}%'))

        tray_row = tray_cursor.fetchone()
        conn.close()

        tray_info = None
        if tray_row:
            try:
                tray_details = json.loads(tray_row[1])
                scanned_barcodes = tray_details.get('scanned_product_barcodes', [])
                # 실제 바코드 또는 부분 일치하는 바코드 찾기
                matching_barcode = None
                barcode_idx = -1
                for idx, bc in enumerate(scanned_barcodes):
                    if bc == actual_barcode or actual_barcode in bc or barcode in bc:
                        matching_barcode = bc
                        barcode_idx = idx
                        break

                if matching_barcode:
                    tray_info = {
                        'complete_time': tray_row[0],
                        'item_code': tray_details.get('item_code', 'N/A'),
                        'item_name': tray_details.get('item_name', 'N/A'),
                        'scan_count': tray_details.get('scan_count', 0),
                        'tray_capacity': tray_details.get('tray_capacity', 0),
                        'work_time_sec': tray_details.get('work_time_sec', 0),
                        'error_count': tray_details.get('error_count', 0),
                        'start_time': tray_details.get('start_time', 'N/A'),
                        'end_time': tray_details.get('end_time', 'N/A'),
                        'barcode_position': barcode_idx + 1
                    }
            except:
                pass

        # 응답 구성 (실제 찾은 바코드 정보 포함)
        response = {
            "found": True,
            "barcode": barcode,
            "actual_barcode": actual_barcode,  # 실제 DB에 저장된 바코드
            "scan_info": {
                "worker": scan_info['worker'],
                "scan_time": scan_info['timestamp'],
                "process": scan_info['process'],
                "status": "SCAN_OK (정상 스캔)",
                "interval_sec": scan_info['interval_sec']
            }
        }

        if tray_info:
            work_time_min = int(tray_info['work_time_sec']) // 60
            work_time_sec = int(tray_info['work_time_sec']) % 60

            response["tray_info"] = {
                "complete_time": tray_info['complete_time'],
                "item_code": f"{tray_info['item_code']} ({tray_info['item_name']})",
                "tray_capacity": tray_info['tray_capacity'],
                "scan_count": f"{tray_info['scan_count']}개 (전체 완료)" if tray_info['scan_count'] == tray_info['tray_capacity'] else f"{tray_info['scan_count']}개",
                "work_time": f"{tray_info['work_time_sec']}초 (약 {work_time_min}분 {work_time_sec}초)",
                "barcode_position": f"{tray_info['scan_count']}개 중 {tray_info['barcode_position']}번째",
                "error_count": "없음" if tray_info['error_count'] == 0 else str(tray_info['error_count'])
            }

            response["timeline"] = {
                "start": tray_info['start_time'],
                "scan": scan_info['timestamp'],
                "complete": tray_info['end_time']
            }

        return jsonify(response)

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"바코드 검색 중 오류: {e}"}), 500

@app.route('/api/realtime', methods=['GET'])
def get_realtime_data():
    try:
        process_mode = request.args.get('process_mode', '이적실')
        today = datetime.now().date().isoformat()

        print(f"[API] 실시간 데이터 요청: {process_mode}, 날짜={today}")

        # 오늘 날짜 세션 조회
        today_sessions_df = db.get_sessions(start_date=today, end_date=today, process=process_mode)
        print(f"[API] 오늘 세션: {len(today_sessions_df)}개")

        # 포장실 데이터: 트레이 단위로 PCS 추정 (1 트레이 = 60 PCS)
        if process_mode == '포장실' and not today_sessions_df.empty:
            today_sessions_df['pcs_completed'] = 60

        # 오늘 데이터가 없으면 최근 작업일 데이터 조회
        display_date = today
        if today_sessions_df.empty:
            print("[API] 오늘 데이터 없음, 최근 작업일 조회 중...")
            # 최근 7일 내 데이터 조회
            seven_days_ago = (datetime.now() - timedelta(days=7)).date().isoformat()
            recent_df = db.get_sessions(start_date=seven_days_ago, end_date=today, process=process_mode)

            # 포장실 데이터: 트레이 단위로 PCS 추정
            if process_mode == '포장실' and not recent_df.empty:
                recent_df['pcs_completed'] = 60

            if not recent_df.empty:
                # 가장 최근 날짜 찾기
                latest_date = recent_df['date'].max()
                display_date = latest_date.strftime('%Y-%m-%d')
                today_sessions_df = recent_df[recent_df['date'] == latest_date].copy()
                print(f"[API] 최근 작업일 데이터 사용: {display_date}, {len(today_sessions_df)}개 세션")

        # 작업자별 집계
        worker_summary = pd.DataFrame()
        item_summary = pd.DataFrame()
        hourly_summary = pd.Series(dtype=float)
        work_hours = range(6, 23)

        if not today_sessions_df.empty:
            worker_summary = today_sessions_df.groupby('worker').agg(
                pcs_completed=('pcs_completed', 'sum'),
                avg_work_time=('work_time', 'mean'),
                session_count=('worker', 'size')
            ).reset_index().sort_values(by='pcs_completed', ascending=False)

            worker_summary = worker_summary[worker_summary['pcs_completed'] > 0]

            item_summary = today_sessions_df.groupby('item_display').agg(
                pcs_completed=('pcs_completed', 'sum'),
                pallet_count=('item_display', 'size')
            ).reset_index().sort_values(by='pcs_completed', ascending=False)
            item_summary = item_summary[item_summary['pcs_completed'] > 0]

            today_sessions_df['hour'] = pd.to_datetime(today_sessions_df['start_time_dt']).dt.hour
            hourly_summary = today_sessions_df.groupby('hour')['pcs_completed'].sum().reindex(work_hours, fill_value=0)

        # 최근 30일 평균
        thirty_days_ago = (datetime.now() - timedelta(days=30)).date().isoformat()
        recent_sessions_df = db.get_sessions(start_date=thirty_days_ago, end_date=today, process=process_mode)

        # 포장실 데이터: 트레이 단위로 PCS 추정
        if process_mode == '포장실' and not recent_sessions_df.empty:
            recent_sessions_df['pcs_completed'] = 60

        average_hourly_production = []
        monthly_averages = {'daily_total_pcs': 0, 'daily_total_pallets': 0, 'daily_worker_count': 0, 'daily_avg_work_time': 0}

        if not recent_sessions_df.empty:
            num_days = recent_sessions_df['date'].nunique()
            if num_days > 0:
                recent_sessions_df['hour'] = pd.to_datetime(recent_sessions_df['start_time_dt']).dt.hour
                total_hourly_summary = recent_sessions_df.groupby('hour')['pcs_completed'].sum().reindex(work_hours, fill_value=0)
                average_hourly_production = (total_hourly_summary / num_days).values.tolist()

                daily_stats = recent_sessions_df.groupby(recent_sessions_df['date'].dt.date).agg({
                    'pcs_completed': 'sum',
                    'worker': 'nunique',
                    'work_time': 'mean',
                    'date': 'size'
                }).rename(columns={'date': 'pallet_count'})

                if not daily_stats.empty:
                    monthly_averages = {
                        'daily_total_pcs': round(daily_stats['pcs_completed'].mean(), 1),
                        'daily_total_pallets': round(daily_stats['pallet_count'].mean(), 1),
                        'daily_worker_count': round(daily_stats['worker'].mean(), 1),
                        'daily_avg_work_time': round(daily_stats['work_time'].mean(), 1)
                    }

        return jsonify({
            'display_date': display_date,  # 실제 표시 날짜
            'is_today': display_date == today,  # 오늘 데이터인지 여부
            'worker_status': json.loads(worker_summary.to_json(orient='records')),
            'item_status': json.loads(item_summary.to_json(orient='records')),
            'hourly_production': {
                'labels': [f"{h:02d}시" for h in work_hours],
                'today': hourly_summary.values.tolist() if not hourly_summary.empty else [0]*len(work_hours),
                'average': average_hourly_production
            },
            'monthly_averages': monthly_averages
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"실시간 데이터 처리 중 오류: {e}"}), 500

@app.route('/api/trace', methods=['POST'])
def trace_data():
    """이력 추적 API - 바코드/세션 검색 (최적화됨)"""
    try:
        query = request.json
        barcode = query.get('barcode', '').strip()
        wid = query.get('wid', '').strip()
        fpb = query.get('fpb', '').strip()

        # 날짜 범위 파라미터 (기본값: 최근 30일)
        days_back = query.get('days_back', 30)
        max_results = query.get('max_results', 1000)

        # 시작 날짜 계산
        start_date = (datetime.now() - timedelta(days=days_back)).date().isoformat()

        # 시나리오 1: 바코드 검색 (최적화: 인덱싱된 barcode 컬럼 사용)
        if barcode:
            conn = db.get_connection()

            # 바코드 컬럼 사용 (3.4배 빠름)
            cursor = conn.execute("""
                SELECT timestamp, worker_name as worker, event, details, process
                FROM raw_events
                WHERE barcode LIKE ?
                AND timestamp >= ?
                ORDER BY timestamp DESC
                LIMIT ?
            """, (f'%{barcode}%', start_date, max_results))

            results = []
            for row in cursor.fetchall():
                results.append({
                    'timestamp': row[0],
                    'worker': row[1],
                    'event': row[2],
                    'details': row[3],
                    'process': row[4]
                })

            conn.close()

            total_count = len(results)
            truncated = total_count >= max_results

            return jsonify({
                'type': 'barcode_trace',
                'data': results,
                'total_count': total_count,
                'truncated': truncated,
                'search_params': {
                    'barcode': barcode,
                    'days_back': days_back,
                    'start_date': start_date
                }
            })

        # 시나리오 2: 세션 단위 검색 (날짜 범위 필터 추가)
        conn = db.get_connection()
        query_parts = ["SELECT * FROM sessions WHERE date >= ?"]
        params = [start_date]

        if wid:
            query_parts.append("AND work_order_id LIKE ?")
            params.append(f'%{wid}%')

        if fpb:
            query_parts.append("AND product_batch LIKE ?")
            params.append(f'%{fpb}%')

        query_parts.append(f"ORDER BY start_time_dt DESC LIMIT {max_results}")

        df = pd.read_sql_query(' '.join(query_parts), conn, params=params)
        conn.close()

        total_count = len(df)
        truncated = total_count >= max_results

        return jsonify({
            'type': 'session_trace',
            'data': json.loads(df.to_json(orient='records', date_format='iso')),
            'total_count': total_count,
            'truncated': truncated,
            'search_params': {
                'wid': wid,
                'fpb': fpb,
                'days_back': days_back,
                'start_date': start_date
            }
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"이력 추적 중 오류: {e}"}), 500

@app.route('/api/session_barcodes', methods=['POST'])
def get_session_barcodes():
    """세션별 바코드 목록 조회"""
    try:
        session_info = request.json
        start_time = session_info['start_time_dt']
        end_time = session_info['end_time_dt']
        worker = session_info['worker']
        process = session_info['process']

        conn = db.get_connection()
        cursor = conn.execute("""
            SELECT details FROM raw_events
            WHERE timestamp >= ? AND timestamp <= ?
            AND worker_name = ? AND process = ? AND event = 'SCAN_OK'
            ORDER BY timestamp ASC
        """, (start_time, end_time, worker, process))

        barcodes = []
        for row in cursor.fetchall():
            detail_str = row[0]
            try:
                if detail_str and detail_str.strip().startswith('{'):
                    detail_dict = json.loads(detail_str)
                    if 'barcode' in detail_dict:
                        barcodes.append(detail_dict['barcode'])
            except (json.JSONDecodeError, TypeError):
                continue

        conn.close()
        return jsonify({"barcodes": barcodes})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"바코드 조회 중 오류: {e}"}), 500

@app.route('/api/worker_hourly', methods=['POST'])
def get_worker_hourly():
    """작업자별 시간당 생산량 API"""
    try:
        query = request.json
        worker = query.get('worker', '').strip()
        start_date = query.get('start_date')
        end_date = query.get('end_date')
        process_mode = query.get('process_mode', '이적실')

        if not worker:
            return jsonify({"error": "작업자를 선택해주세요."}), 400

        print(f"[API] 작업자 시간당 생산량: {worker}, {start_date}~{end_date}, {process_mode}")

        # 세션 데이터 조회 (선택 기간용 - 시간대별 생산량, 요약 통계)
        sessions_df = db.get_sessions(start_date=start_date, end_date=end_date, process=process_mode)

        # 일별 생산량용 1개월 데이터 조회
        if end_date:
            daily_end = end_date
            daily_start = (datetime.strptime(end_date, '%Y-%m-%d') - timedelta(days=30)).strftime('%Y-%m-%d')
        else:
            daily_end = datetime.now().strftime('%Y-%m-%d')
            daily_start = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

        daily_sessions_df = db.get_sessions(start_date=daily_start, end_date=daily_end, process=process_mode)

        if sessions_df.empty and daily_sessions_df.empty:
            return jsonify({
                "worker": worker,
                "hourly_data": [],
                "daily_data": [],
                "summary": {}
            })

        # 포장실 데이터: 트레이 단위로 PCS 추정
        if process_mode == '포장실':
            if not sessions_df.empty:
                sessions_df['pcs_completed'] = 60
            if not daily_sessions_df.empty:
                daily_sessions_df['pcs_completed'] = 60

        # 해당 작업자 필터링
        worker_df = sessions_df[sessions_df['worker'] == worker].copy() if not sessions_df.empty else pd.DataFrame()
        daily_worker_df = daily_sessions_df[daily_sessions_df['worker'] == worker].copy() if not daily_sessions_df.empty else pd.DataFrame()

        if worker_df.empty and daily_worker_df.empty:
            return jsonify({
                "worker": worker,
                "hourly_data": [],
                "daily_data": [],
                "summary": {}
            })

        # 시간대별 생산량 집계 (선택 기간 기준)
        hourly_avg = pd.Series([0.0] * 24)
        num_days = 0
        if not worker_df.empty:
            worker_df['hour'] = pd.to_datetime(worker_df['start_time_dt']).dt.hour
            hourly_sum = worker_df.groupby('hour')['pcs_completed'].sum()
            num_days = worker_df['date'].nunique()
            hourly_avg = (hourly_sum / num_days).reindex(range(0, 24), fill_value=0)

        # 일별 생산량 집계 (최근 1개월)
        daily_sum = pd.DataFrame()
        if not daily_worker_df.empty:
            daily_worker_df['date_str'] = pd.to_datetime(daily_worker_df['date']).dt.strftime('%Y-%m-%d')
            daily_sum = daily_worker_df.groupby('date_str').agg({
                'pcs_completed': 'sum',
                'work_time': 'mean',
                'latency': 'mean',
                'worker': 'count'
            }).reset_index()
            daily_sum.columns = ['date', 'pcs', 'avg_work_time', 'avg_latency', 'session_count']
            daily_sum = daily_sum.sort_values('date')

        # 요약 통계 (선택 기간 기준)
        summary = {}
        if not worker_df.empty:
            summary = {
                'total_pcs': int(worker_df['pcs_completed'].sum()),
                'total_sessions': len(worker_df),
                'avg_daily_pcs': round(worker_df.groupby('date')['pcs_completed'].sum().mean(), 1),
                'avg_work_time': round(worker_df['work_time'].mean(), 1),
                'avg_latency': round(worker_df['latency'].mean(), 1),
                'num_days': num_days,
                'first_pass_yield': round((worker_df['had_error'] == 0).sum() / len(worker_df) * 100, 1) if len(worker_df) > 0 else 0
            }

        return jsonify({
            "worker": worker,
            "hourly_data": {
                "labels": [f"{h}시" for h in range(0, 24)],
                "values": hourly_avg.round(1).tolist()
            },
            "daily_data": json.loads(daily_sum.to_json(orient='records')) if not daily_sum.empty else [],
            "summary": summary
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"작업자 데이터 조회 중 오류: {e}"}), 500

@app.route('/api/export_excel', methods=['POST'])
def export_excel():
    """세션 데이터 Excel 내보내기"""
    try:
        from io import BytesIO
        from flask import send_file

        data = request.json
        sessions_data = data.get('sessions', [])

        if not sessions_data:
            return jsonify({"error": "내보낼 데이터가 없습니다."}), 400

        df = pd.DataFrame(sessions_data)

        # 데이터 정제 및 컬럼 선택
        df_display = df.sort_values(by='start_time_dt', ascending=False).copy()
        df_display['날짜'] = pd.to_datetime(df_display['date']).dt.strftime('%Y-%m-%d')
        df_display['시작 시간'] = pd.to_datetime(df_display['start_time_dt']).dt.strftime('%H:%M:%S').fillna('N/A')
        if 'shipping_date' in df_display.columns:
            df_display['출고 날짜'] = pd.to_datetime(df_display['shipping_date']).dt.strftime('%Y-%m-%d').fillna('')
        df_display['작업시간'] = df_display['work_time'].apply(lambda x: f"{x:.1f}초" if pd.notna(x) else "N/A")
        df_display['준비시간'] = df_display['latency'].apply(lambda x: f"{x:.1f}초" if pd.notna(x) else "N/A")
        df_display['오류수'] = df_display['process_errors'].apply(lambda x: f"{int(x):,}" if pd.notna(x) else "N/A")
        df_display['오류 발생 여부'] = df_display['had_error'].apply(lambda x: '예' if x == 1 else '아니오')

        def format_pcs_pallets(row):
            pcs = row['pcs_completed']
            process = row['process']
            if pd.notna(pcs) and pcs > 0:
                if '포장' in process:
                    pallets = pcs / 60.0
                    return f"{int(pcs):,} ({pallets:.1f} PL)"
                return f"{int(pcs):,}"
            return "N/A"
        df_display['수량 (PCS/Pallet)'] = df_display.apply(format_pcs_pallets, axis=1)

        cols_to_display = [
            '날짜', '시작 시간', 'worker', 'process', 'phase', 'item_display',
            'work_order_id', 'product_batch',
            '작업시간', '준비시간', '수량 (PCS/Pallet)', '오류수', '오류 발생 여부'
        ]
        if 'shipping_date' in df_display.columns and '출고 날짜' in df_display.columns:
            cols_to_display.insert(2, '출고 날짜')

        header_map = {
            'worker': '작업자', 'process': '공정', 'item_display': '품목',
            'work_order_id': '작업지시 ID', 'phase': '차수', 'product_batch': '완제품 배치'
        }

        final_cols_to_display = [col for col in cols_to_display if col in df_display.columns]
        export_df = df_display[final_cols_to_display].rename(columns=header_map)

        output = BytesIO()
        with pd.ExcelWriter(output, engine='openpyxl') as writer:
            export_df.to_excel(writer, index=False, sheet_name='상세 데이터')
        output.seek(0)

        return send_file(
            output,
            download_name="상세_데이터.xlsx",
            as_attachment=True,
            mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Excel 내보내기 중 오류: {e}"}), 500

@app.route('/api/export_error_log', methods=['POST'])
def export_error_log():
    """오류 로그 CSV 내보내기"""
    try:
        from io import StringIO
        import csv
        from flask import Response

        data = request.json
        error_data = data.get('errors', [])

        if not error_data:
            return jsonify({"error": "내보낼 데이터가 없습니다."}), 400

        output = StringIO()
        writer = csv.writer(output)

        # Write headers
        writer.writerow(error_data[0].keys())

        # Write data
        for row in error_data:
            writer.writerow(row.values())

        output.seek(0)

        return Response(
            output.getvalue(),
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=error_log.csv"}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"CSV 내보내기 중 오류: {e}"}), 500

# SocketIO 이벤트
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# 애플리케이션 실행
if __name__ == '__main__':
    # 파일 감시 스레드 시작
    monitor_thread = threading.Thread(target=start_file_monitor, daemon=True)
    monitor_thread.start()

    # 주기적 증분 동기화 (5분마다)
    def periodic_sync():
        while True:
            time.sleep(300)  # 5분
            run_incremental_sync()

    sync_thread = threading.Thread(target=periodic_sync, daemon=True)
    sync_thread.start()

    print("데이터베이스 기반 Flask 서버를 시작합니다. http://127.0.0.1:8089 에서 접속하세요.")
    print(f"데이터베이스: {DB_PATH}")
    print("적용된 최적화:")
    print("- SQLite 데이터베이스 사용")
    print("- 실시간 증분 동기화 (5분 간격 + 파일 변경 감지)")
    print("- 응답 압축 (GZIP)")
    print("- 인덱싱 최적화")

    socketio.run(app, host='0.0.0.0', port=8089, debug=True, use_reloader=False)
