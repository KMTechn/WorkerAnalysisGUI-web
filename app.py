import os
import threading
import time
import json
import pandas as pd
import numpy as np
from datetime import datetime
import re

from flask import Flask, jsonify, render_template, request
from flask_socketio import SocketIO
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

from analyzer import DataAnalyzer, WorkerPerformance

def load_settings():
    try:
        with open('config/analyzer_settings.json', 'r', encoding='utf-8') as f:
            settings = json.load(f)
        return settings.get('log_folder_path', 'C:\\Sync')
    except (FileNotFoundError, json.JSONDecodeError):
        return 'C:\\Sync'

LOG_FOLDER_PATH = load_settings()
if not os.path.isdir(LOG_FOLDER_PATH):
    os.makedirs(LOG_FOLDER_PATH, exist_ok=True)

# ####################################################################
# # Flask 및 SocketIO 설정
# ####################################################################
app = Flask(__name__)
app.config['SECRET_KEY'] = 'secret-key-for-dev'
socketio = SocketIO(app, async_mode='eventlet')

# ####################################################################
# # 데이터 분석기 및 전역 변수
# ####################################################################
analyzer = DataAnalyzer()
RADAR_METRICS_CONFIG = {
    "포장실": { '세트완료시간': ('avg_work_time', False, 1.0), '첫스캔준비성': ('avg_latency', False, 1.0), '무결점달성률': ('first_pass_yield', True, 0.7), '세트당PCS': ('avg_pcs_per_tray', True, 1.0) },
    "이적실": { '신속성': ('avg_work_time', False, 1.0), '준속성': ('avg_latency', False, 1.0), '초도수율': ('first_pass_yield', True, 0.7), '안정성': ('work_time_std', False, 1.0) },
    "검사실": { '신속성': ('avg_work_time', False, 1.0), '준비성': ('avg_latency', False, 0.8), '무결점달성률': ('first_pass_yield', True, 1.2), '안정성': ('work_time_std', False, 0.7), '품질 정확도': ('defect_rate', False, 1.5) }
}
RADAR_METRICS_CONFIG['전체 비교'] = RADAR_METRICS_CONFIG['이적실']

# ####################################################################
# # 파일 감시 핸들러 (Watchdog)
# ####################################################################
class LogFileHandler(FileSystemEventHandler):
    def __init__(self, socket_instance):
        self.socketio = socket_instance
        self.last_triggered_time = 0

    def on_modified(self, event):
        if time.time() - self.last_triggered_time < 5: return
        if not event.is_directory and "작업이벤트로그" in str(os.path.basename(event.src_path)):
            self.last_triggered_time = time.time()
            print(f"파일 변경 감지: {event.src_path}. 클라이언트에 업데이트 전송 중...")
            self.socketio.emit('data_updated', {'message': 'Log file has been modified.'})
            print("업데이트 이벤트 전송 완료.")

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

# ####################################################################
# # Flask 라우트 (API 엔드포인트)
# ####################################################################

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/api/data', methods=['POST'])
def get_analysis_data():
    print("\n[API] /api/data 요청 시작")
    try:
        filters = request.json
        process_mode = filters.get('process_mode', '이적실')
        print(f"[API] 공정 모드: {process_mode}")
        
        print("[API] 데이터 로딩 시작...")
        full_df = analyzer.load_all_data(LOG_FOLDER_PATH, process_mode)
        print(f"[API] 데이터 로딩 완료. {len(full_df)}개의 세션 데이터 발견.")

        if full_df.empty:
            print("[API] 로드된 데이터가 없어 빈 응답을 반환합니다.")
            return jsonify({ 'kpis': {}, 'worker_data': [], 'normalized_performance': [], 'workers': [], 'date_range': {'min': None, 'max': None}, 'filtered_sessions_data': [], 'filtered_raw_events': [] })


        start_date = filters.get('start_date') or full_df['date'].dropna().min().strftime('%Y-%m-%d')
        end_date = filters.get('end_date') or full_df['date'].dropna().max().strftime('%Y-%m-%d')
        
        all_workers = sorted(full_df['worker'].astype(str).unique().tolist())
        selected_workers = filters.get('selected_workers') or all_workers

        print("[API] 데이터 필터링 시작...")
        filtered_df = analyzer.filter_data(full_df.copy(), start_date, end_date, selected_workers)
        print(f"[API] 데이터 필터링 완료. {len(filtered_df)}개의 세션이 필터링됨.")
        
        radar_metrics = RADAR_METRICS_CONFIG.get(process_mode, RADAR_METRICS_CONFIG['이적실'])
        print("[API] 데이터 분석 시작...")
        worker_data, kpis, _, normalized_df = analyzer.analyze_dataframe(filtered_df, radar_metrics, full_sessions_df=full_df)
        print("[API] 데이터 분석 완료.")

        print("[API] JSON 직렬화 시작...")
        worker_data_json = [perf.__dict__ for perf in worker_data.values()]
        for item in worker_data_json:
            # JSON으로 직렬화할 수 없는 값들을 처리
            for key, value in item.items():
                if isinstance(value, (datetime, pd.Timestamp)):
                    item[key] = value.isoformat()
                # 값이 숫자인 경우에만 isinf를 확인
                elif isinstance(value, (int, float)) and np.isinf(value):
                    item[key] = None # Infinity를 None (JSON null)으로 변환

        normalized_df_json = json.loads(normalized_df.replace([np.inf, -np.inf], None).to_json(orient='records', date_format='iso')) if normalized_df is not None else []
        
        valid_dates = full_df['date'].dropna()
        date_range = {
            'min': valid_dates.min().strftime('%Y-%m-%d') if not valid_dates.empty else None,
            'max': valid_dates.max().strftime('%Y-%m-%d') if not valid_dates.empty else None
        }
        
        # 오류 로그 탭용 데이터 필터링
        filtered_raw_events_df = pd.DataFrame()
        if not analyzer.raw_event_df.empty:
            raw_df = analyzer.raw_event_df
            raw_df['date_only'] = pd.to_datetime(raw_df['timestamp']).dt.date
            mask = (raw_df['date_only'] >= pd.to_datetime(start_date).date()) & \
                   (raw_df['date_only'] <= pd.to_datetime(end_date).date()) & \
                   (raw_df['worker'].isin(selected_workers))
            filtered_raw_events_df = raw_df[mask]


        # 공정 비교 분석 데이터 계산
        comparison_data = None
        if process_mode == '전체 비교':
            # 1. 요약 테이블용 데이터 (오늘 날짜 기준)
            today_str = datetime.now().strftime('%Y-%m-%d')
            today_df = analyzer.filter_data(full_df.copy(), today_str, today_str, all_workers)
            
            today_inspection_kpis = analyzer._calculate_kpis(today_df[today_df['process'] == '검사실'])
            today_transfer_kpis = analyzer._calculate_kpis(today_df[today_df['process'] == '이적실'])
            today_packaging_kpis = analyzer._calculate_kpis(today_df[today_df['process'] == '포장실'])

            summary_today = {
                'inspection': today_inspection_kpis,
                'transfer': today_transfer_kpis,
                'packaging': today_packaging_kpis,
                'transfer_standby_trays': today_inspection_kpis.get('total_trays', 0) - today_transfer_kpis.get('total_trays', 0),
                'packaging_standby_trays': today_transfer_kpis.get('total_trays', 0) - today_packaging_kpis.get('total_trays', 0),
                'transfer_standby_pcs': today_inspection_kpis.get('total_pcs_completed', 0) - today_transfer_kpis.get('total_pcs_completed', 0),
                'packaging_standby_pcs': today_transfer_kpis.get('total_pcs_completed', 0) - today_packaging_kpis.get('total_pcs_completed', 0),
            }

            # 2. 요약 테이블용 데이터 (사용자 선택 기간 기준)
            period_df = analyzer.filter_data(full_df.copy(), start_date, end_date, all_workers)
            
            period_inspection_kpis = analyzer._calculate_kpis(period_df[period_df['process'] == '검사실'])
            period_transfer_kpis = analyzer._calculate_kpis(period_df[period_df['process'] == '이적실'])
            period_packaging_kpis = analyzer._calculate_kpis(period_df[period_df['process'] == '포장실'])

            summary_period = {
                'inspection': period_inspection_kpis,
                'transfer': period_transfer_kpis,
                'packaging': period_packaging_kpis,
                'transfer_standby_trays': period_inspection_kpis.get('total_trays', 0) - period_transfer_kpis.get('total_trays', 0),
                'packaging_standby_trays': period_transfer_kpis.get('total_trays', 0) - period_packaging_kpis.get('total_trays', 0),
                'transfer_standby_pcs': period_inspection_kpis.get('total_pcs_completed', 0) - period_transfer_kpis.get('total_pcs_completed', 0),
                'packaging_standby_pcs': period_transfer_kpis.get('total_pcs_completed', 0) - period_packaging_kpis.get('total_pcs_completed', 0),
            }

            # 3. 추세 그래프용 데이터 (사용자 선택 기��� 기준)
            trends_data = {
                'inspection': json.loads(period_df[period_df['process'] == '검사실'].to_json(orient='records', date_format='iso')),
                'transfer': json.loads(period_df[period_df['process'] == '이적실'].to_json(orient='records', date_format='iso')),
                'packaging': json.loads(period_df[period_df['process'] == '포장실'].to_json(orient='records', date_format='iso')),
            }
            
            comparison_data = {'summary_today': summary_today, 'summary_period': summary_period, 'trends': trends_data}

        print("[API] JSON 직렬화 완료. 응답 전송 중...")
        return jsonify({
            'kpis': kpis,
            'worker_data': worker_data_json,
            'normalized_performance': normalized_df_json,
            'workers': all_workers,
            'date_range': date_range,
            'filtered_sessions_data': json.loads(filtered_df.to_json(orient='records', date_format='iso')),
            'filtered_raw_events': json.loads(filtered_raw_events_df.to_json(orient='records', date_format='iso')),
            'comparison_data': comparison_data
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"서버 내부 오류: {e}"}), 500

@app.route('/api/trace', methods=['POST'])
def trace_data():
    try:
        query = request.json
        barcode = query.get('barcode', '').strip()
        wid = query.get('wid', '').strip()
        fpb = query.get('fpb', '').strip()

        # 전체 데이터 로드는 항상 수행 (캐시된 데이터 사용)
        if analyzer.raw_event_df.empty:
             analyzer.load_all_data(LOG_FOLDER_PATH, "전체")

        # 시나리오 1: 바코드 검색 (가장 우선순위 높음)
        if barcode:
            raw_df = analyzer.raw_event_df.copy()
            raw_df['details_str'] = raw_df['details'].astype(str)
            # 정규표현식을 사용하여 바코드 패턴 검색
            pattern = f'"barcode":\\s*"{re.escape(barcode)}"'
            result_df = raw_df[raw_df['details_str'].str.contains(pattern, regex=True, na=False)]
            result_df = result_df.sort_values(by='timestamp', ascending=True)
            return jsonify({
                'type': 'barcode_trace',
                'data': json.loads(result_df.to_json(orient='records', date_format='iso'))
            })

        # 시나리오 2: 세션 단위 검색
        sessions_df = analyzer.process_events_to_sessions(analyzer.raw_event_df)
        if sessions_df.empty:
            return jsonify({'type': 'session_trace', 'data': []})

        result_df = sessions_df
        if wid:
            result_df = result_df[result_df['work_order_id'].str.contains(wid, case=False, na=False)]
        if fpb:
            result_df = result_df[result_df['product_batch'].str.contains(fpb, case=False, na=False)]
        
        result_df = result_df.sort_values(by='start_time_dt', ascending=False)
        return jsonify({
            'type': 'session_trace',
            'data': json.loads(result_df.to_json(orient='records', date_format='iso'))
        })

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"이력 추적 중 오류: {e}"}), 500

@app.route('/api/session_barcodes', methods=['POST'])
def get_session_barcodes():
    try:
        session_info = request.json
        start_time = pd.to_datetime(session_info['start_time_dt'])
        end_time = pd.to_datetime(session_info['end_time_dt'])
        worker = session_info['worker']
        process = session_info['process']

        raw_df = analyzer.raw_event_df
        if raw_df.empty:
            return jsonify({"barcodes": []})

        session_scans = raw_df[
            (raw_df['timestamp'] >= start_time) &
            (raw_df['timestamp'] <= end_time) &
            (raw_df['worker'] == worker) &
            (raw_df['process'] == process) &
            (raw_df['event'] == 'SCAN_OK')
        ].copy()

        barcodes = []
        if not session_scans.empty:
            for detail_str in session_scans['details']:
                try:
                    if isinstance(detail_str, str) and detail_str.strip().startswith('{'):
                        detail_dict = json.loads(detail_str)
                        if 'barcode' in detail_dict:
                            barcodes.append(detail_dict['barcode'])
                except (json.JSONDecodeError, TypeError):
                    continue
        
        return jsonify({"barcodes": barcodes})

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"바코드 조회 중 오류: {e}"}), 500

@app.route('/api/export_excel', methods=['POST'])
def export_excel():
    try:
        from io import BytesIO
        import pandas as pd
        from flask import send_file

        data = request.json
        sessions_data = data.get('sessions', [])
        
        if not sessions_data:
            return jsonify({"error": "내보낼 데이터가 없습니다."}), 400

        df = pd.DataFrame(sessions_data)
        
        # 데이터 정제 및 컬럼 선택 (필요에 따라 조정)
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
        writer = pd.ExcelWriter(output, engine='openpyxl')
        export_df.to_excel(writer, index=False, sheet_name='상세 데이터')
        writer.close()
        output.seek(0)

        return send_file(output, download_name="상세_데이터.xlsx", as_attachment=True, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"Excel 내보내기 중 오류: {e}"}), 500

@app.route('/api/export_error_log', methods=['POST'])
def export_error_log():
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
            output,
            mimetype="text/csv",
            headers={"Content-Disposition": "attachment;filename=error_log.csv"}
        )

    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"CSV 내보내기 중 오류: {e}"}), 500


@app.route('/api/realtime', methods=['GET'])
def get_realtime_data():
    try:
        process_mode = request.args.get('process_mode', '이적실')
        today = datetime.now().date()
        
        # 1. 오늘 데이터 로드 및 분석 (기존 로직)
        today_sessions_df = analyzer.load_all_data(LOG_FOLDER_PATH, process_mode, date_filter=today)
        
        worker_summary = pd.DataFrame()
        item_summary = pd.DataFrame()
        hourly_summary = pd.Series(dtype=float)
        work_hours = range(6, 23)

        if not today_sessions_df.empty:
            worker_summary = today_sessions_df.groupby('worker').agg(pcs_completed=('pcs_completed', 'sum'), avg_work_time=('work_time', 'mean'), session_count=('worker', 'size')).reset_index().sort_values(by='pcs_completed', ascending=False)
            
            # TRAY_COMPLETE 이벤트 수를 직접 카운트하여 파렛트 수량 계산
            item_summary = today_sessions_df.groupby('item_display').agg(
                pcs_completed=('pcs_completed', 'sum'),
                pallet_count=('item_display', 'size')  # 각 그룹의 행 수를 세면 TRAY_COMPLETE 이벤트 수가 됨
            ).reset_index().sort_values(by='pcs_completed', ascending=False)
            item_summary = item_summary[item_summary['pcs_completed'] > 0]

            today_sessions_df['hour'] = pd.to_datetime(today_sessions_df['start_time_dt']).dt.hour
            hourly_summary = today_sessions_df.groupby('hour')['pcs_completed'].sum().reindex(work_hours, fill_value=0)

        # 2. 최근 30일 데이터 로드 및 시간대별 평균 계산
        all_sessions_df = analyzer.load_all_data(LOG_FOLDER_PATH, process_mode)
        average_hourly_production = []
        
        if not all_sessions_df.empty:
            all_sessions_df['date_only'] = pd.to_datetime(all_sessions_df['date']).dt.date
            thirty_days_ago = datetime.now().date() - pd.to_timedelta('30D')
            recent_sessions_df = all_sessions_df[all_sessions_df['date_only'] >= thirty_days_ago]
            
            if not recent_sessions_df.empty:
                num_days = recent_sessions_df['date_only'].nunique()
                if num_days > 0:
                    recent_sessions_df['hour'] = pd.to_datetime(recent_sessions_df['start_time_dt']).dt.hour
                    total_hourly_summary = recent_sessions_df.groupby('hour')['pcs_completed'].sum().reindex(work_hours, fill_value=0)
                    average_hourly_production = (total_hourly_summary / num_days).values.tolist()

        return jsonify({
            'worker_status': json.loads(worker_summary.to_json(orient='records')),
            'item_status': json.loads(item_summary.to_json(orient='records')),
            'hourly_production': { 
                'labels': [f"{h:02d}시" for h in work_hours], 
                'today': hourly_summary.values.tolist() if not hourly_summary.empty else [0]*len(work_hours),
                'average': average_hourly_production
            }
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": f"실시간 데이터 처리 중 오류: {e}"}), 500

# ####################################################################
# # SocketIO 이벤트 핸들러
# ####################################################################
@socketio.on('connect')
def handle_connect():
    print('Client connected')

@socketio.on('disconnect')
def handle_disconnect():
    print('Client disconnected')

# ####################################################################
# # 애플리케이션 실행
# ####################################################################
if __name__ == '__main__':
    monitor_thread = threading.Thread(target=start_file_monitor, daemon=True)
    monitor_thread.start()
    
    print("Flask 서버를 시작합니다. http://127.0.0.1:8088 에서 접속하세요.")
    socketio.run(app, port=8089, debug=True, use_reloader=False)
