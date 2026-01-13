# -*- coding: utf-8 -*-
"""
Database Manager for WorkerAnalysisGUI-web
SQLite 데이터베이스 관리 및 쿼리 인터페이스
"""

import sqlite3
import os
import json
import pandas as pd
from datetime import datetime, date, timedelta
from typing import Optional, Dict, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DatabaseManager:
    def __init__(self, db_path: str = '/root/WorkerAnalysisGUI-web/data/worker_analysis.db'):
        """데이터베이스 매니저 초기화"""
        self.db_path = db_path
        self.ensure_database_exists()
        logger.info(f"데이터베이스 연결: {self.db_path}")

    def ensure_database_exists(self):
        """데이터베이스 파일 및 디렉토리 생성"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)

        # 스키마 파일이 있다면 초기화
        schema_file = '/root/WorkerAnalysisGUI-web/database_schema.sql'
        if not os.path.exists(self.db_path) and os.path.exists(schema_file):
            logger.info("새로운 데이터베이스 생성 및 스키마 초기화")
            with open(schema_file, 'r', encoding='utf-8') as f:
                schema_sql = f.read()

            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.executescript(schema_sql)
            conn.commit()
            conn.close()
            logger.info("데이터베이스 스키마 생성 완료")

    def get_connection(self) -> sqlite3.Connection:
        """데이터베이스 연결 반환"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row  # 딕셔너리처럼 접근 가능
        return conn

    # ========================================================================
    # Raw Events 관련 메서드
    # ========================================================================

    def insert_raw_events(self, events: List[Dict]) -> int:
        """원본 이벤트 데이터 삽입 (바코드 자동 추출 포함)"""
        if not events:
            return 0

        conn = self.get_connection()
        cursor = conn.cursor()

        inserted_count = 0
        for event in events:
            try:
                # Pandas Timestamp를 문자열로 변환
                timestamp = event['timestamp']
                if hasattr(timestamp, 'isoformat'):
                    timestamp = timestamp.isoformat()
                elif pd.notna(timestamp):
                    timestamp = str(timestamp)
                else:
                    continue  # Invalid timestamp, skip

                # details 처리 및 바코드 추출
                details_dict = event.get('details', {})
                if isinstance(details_dict, dict):
                    details_str = json.dumps(details_dict, ensure_ascii=False)
                    barcode = details_dict.get('barcode', None)
                else:
                    details_str = details_dict
                    barcode = None

                cursor.execute("""
                    INSERT INTO raw_events (timestamp, worker_name, event, details, process, source_file, barcode)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    timestamp,
                    event['worker_name'],
                    event['event'],
                    details_str,
                    event['process'],
                    event['source_file'],
                    barcode
                ))
                inserted_count += 1
            except sqlite3.IntegrityError as e:
                logger.debug(f"이벤트 삽입 중복 무시: {e}")
                continue
            except Exception as e:
                logger.error(f"이벤트 삽입 오류: {e}")
                continue

        conn.commit()
        conn.close()

        logger.info(f"{inserted_count}개 이벤트 삽입 완료 (바코드 자동 추출)")
        return inserted_count

    def get_raw_events(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                      process: Optional[str] = None, worker: Optional[str] = None) -> pd.DataFrame:
        """원본 이벤트 조회"""
        conn = self.get_connection()

        query = "SELECT * FROM raw_events WHERE 1=1"
        params = []

        if start_date:
            query += " AND date(timestamp) >= ?"
            params.append(start_date)

        if end_date:
            query += " AND date(timestamp) <= ?"
            params.append(end_date)

        if process:
            query += " AND process = ?"
            params.append(process)

        if worker:
            query += " AND worker_name = ?"
            params.append(worker)

        query += " ORDER BY timestamp"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        return df

    # ========================================================================
    # Sessions 관련 메서드
    # ========================================================================

    def insert_sessions(self, sessions: List[Dict]) -> int:
        """세션 데이터 삽입 (중복 방지)"""
        if not sessions:
            return 0

        conn = self.get_connection()
        cursor = conn.cursor()

        inserted_count = 0
        skipped_count = 0

        for session in sessions:
            try:
                # 중복 체크: worker, date, process, start_time_dt, end_time_dt, work_time, pcs_completed가 모두 동일한 세션
                # NULL 값도 올바르게 처리 (COALESCE로 NULL을 기본값으로 치환)
                worker = session.get('worker')
                date = session.get('date')
                process = session.get('process')
                start_time = session.get('start_time_dt') or ''  # NULL -> 빈 문자열
                end_time = session.get('end_time_dt') or ''
                work_time = session.get('work_time') or 0
                pcs = session.get('pcs_completed') or 0
                item_code = session.get('item_code') or 'N/A'

                cursor.execute("""
                    SELECT COUNT(*) FROM sessions
                    WHERE worker = ?
                    AND date = ?
                    AND process = ?
                    AND COALESCE(start_time_dt, '') = ?
                    AND COALESCE(end_time_dt, '') = ?
                    AND COALESCE(work_time, 0) = ?
                    AND COALESCE(pcs_completed, 0) = ?
                    AND COALESCE(item_code, 'N/A') = ?
                """, (
                    worker, date, process,
                    start_time, end_time,
                    work_time, pcs, item_code
                ))

                if cursor.fetchone()[0] > 0:
                    # 이미 존재하는 세션, 스킵
                    skipped_count += 1
                    continue

                # 중복이 아니면 삽입
                cursor.execute("""
                    INSERT INTO sessions (
                        worker, process, date, start_time_dt, end_time_dt,
                        work_time, latency, pcs_completed, item_code, item_name,
                        item_display, work_order_id, product_batch, phase,
                        had_error, process_errors, first_pass_yield, shipping_date,
                        tray_capacity, scan_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    session.get('worker'),
                    session.get('process'),
                    session.get('date'),
                    session.get('start_time_dt'),
                    session.get('end_time_dt'),
                    session.get('work_time'),
                    session.get('latency'),
                    session.get('pcs_completed'),
                    session.get('item_code'),
                    session.get('item_name'),
                    session.get('item_display'),
                    session.get('work_order_id'),
                    session.get('product_batch'),
                    session.get('phase'),
                    session.get('had_error', 0),
                    session.get('process_errors', 0),
                    session.get('first_pass_yield'),
                    session.get('shipping_date'),
                    session.get('tray_capacity'),
                    session.get('scan_count')
                ))
                inserted_count += 1
            except Exception as e:
                logger.error(f"세션 삽입 오류: {e}")
                continue

        conn.commit()
        conn.close()

        if skipped_count > 0:
            logger.info(f"{inserted_count}개 세션 삽입 완료, {skipped_count}개 중복 스킵")
        else:
            logger.info(f"{inserted_count}개 세션 삽입 완료")
        return inserted_count

    def get_sessions(self, start_date: Optional[str] = None, end_date: Optional[str] = None,
                    process: Optional[str] = None, workers: Optional[List[str]] = None) -> pd.DataFrame:
        """세션 데이터 조회"""
        conn = self.get_connection()

        query = "SELECT * FROM sessions WHERE 1=1"
        params = []

        if start_date:
            query += " AND date >= ?"
            params.append(start_date)

        if end_date:
            query += " AND date <= ?"
            params.append(end_date)

        if process and process != '전체 비교':
            query += " AND process = ?"
            params.append(process)

        if workers:
            placeholders = ','.join('?' * len(workers))
            query += f" AND worker IN ({placeholders})"
            params.extend(workers)

        query += " ORDER BY start_time_dt"

        df = pd.read_sql_query(query, conn, params=params)
        conn.close()

        # 날짜 컬럼을 datetime으로 변환
        if not df.empty:
            df['date'] = pd.to_datetime(df['date'])
            df['start_time_dt'] = pd.to_datetime(df['start_time_dt'])
            if 'end_time_dt' in df.columns:
                df['end_time_dt'] = pd.to_datetime(df['end_time_dt'])

        return df

    def get_all_workers(self, process: Optional[str] = None) -> List[str]:
        """모든 작업자 목록 조회"""
        conn = self.get_connection()

        query = "SELECT DISTINCT worker FROM sessions WHERE 1=1"
        params = []

        if process and process != '전체 비교':
            query += " AND process = ?"
            params.append(process)

        query += " ORDER BY worker"

        cursor = conn.execute(query, params)
        workers = [row[0] for row in cursor.fetchall()]
        conn.close()

        return workers

    def get_date_range(self, process: Optional[str] = None) -> Tuple[Optional[str], Optional[str]]:
        """데이터의 날짜 범위 조회"""
        conn = self.get_connection()

        query = "SELECT MIN(date) as min_date, MAX(date) as max_date FROM sessions WHERE 1=1"
        params = []

        if process and process != '전체 비교':
            query += " AND process = ?"
            params.append(process)

        cursor = conn.execute(query, params)
        row = cursor.fetchone()
        conn.close()

        if row and row[0] and row[1]:
            return (row[0], row[1])
        return (None, None)

    # ========================================================================
    # File Sync Log 관련 메서드
    # ========================================================================

    def update_sync_log(self, file_path: str, file_name: str, last_modified: datetime,
                       row_count: int, file_size: int, status: str = 'success',
                       error_message: Optional[str] = None):
        """파일 동기화 로그 업데이트"""
        conn = self.get_connection()
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO file_sync_log (file_path, file_name, last_modified, last_sync_at, row_count, file_size, sync_status, error_message)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(file_path) DO UPDATE SET
                last_modified = excluded.last_modified,
                last_sync_at = excluded.last_sync_at,
                row_count = excluded.row_count,
                file_size = excluded.file_size,
                sync_status = excluded.sync_status,
                error_message = excluded.error_message,
                updated_at = CURRENT_TIMESTAMP
        """, (file_path, file_name, last_modified, datetime.now(), row_count, file_size, status, error_message))

        conn.commit()
        conn.close()

    def is_file_synced(self, file_path: str, last_modified: datetime) -> bool:
        """파일이 이미 동기화되었는지 확인"""
        conn = self.get_connection()
        cursor = conn.execute("""
            SELECT last_modified FROM file_sync_log
            WHERE file_path = ? AND last_modified >= ? AND sync_status = 'success'
        """, (file_path, last_modified))

        result = cursor.fetchone()
        conn.close()

        return result is not None

    def get_unsynced_files(self, all_files: List[Tuple[str, datetime]]) -> List[Tuple[str, datetime]]:
        """동기화가 필요한 파일 목록 반환"""
        conn = self.get_connection()

        # 모든 동기화된 파일 정보 조회
        cursor = conn.execute("""
            SELECT file_path, last_modified FROM file_sync_log
            WHERE sync_status = 'success'
        """)

        synced_files = {row[0]: row[1] for row in cursor.fetchall()}
        conn.close()

        unsynced = []
        for file_path, last_modified in all_files:
            if file_path not in synced_files:
                unsynced.append((file_path, last_modified))
            elif last_modified > datetime.fromisoformat(synced_files[file_path]):
                unsynced.append((file_path, last_modified))

        return unsynced

    # ========================================================================
    # Daily KPIs 관련 메서드
    # ========================================================================

    def calculate_and_cache_daily_kpis(self, target_date: str, process: str):
        """일별 KPI 계산 및 캐싱"""
        conn = self.get_connection()

        # 해당 날짜의 세션 데이터로 KPI 계산
        query = """
            SELECT
                worker,
                COUNT(*) as session_count,
                SUM(pcs_completed) as total_pcs,
                COUNT(*) as total_trays,
                AVG(work_time) as avg_work_time,
                AVG(latency) as avg_latency,
                AVG(first_pass_yield) as first_pass_yield,
                SUM(process_errors) as total_errors
            FROM sessions
            WHERE date = ? AND process = ?
            GROUP BY worker
        """

        df = pd.read_sql_query(query, conn, params=[target_date, process])

        # 전체 집계도 추가
        total_query = """
            SELECT
                NULL as worker,
                COUNT(*) as session_count,
                SUM(pcs_completed) as total_pcs,
                COUNT(*) as total_trays,
                AVG(work_time) as avg_work_time,
                AVG(latency) as avg_latency,
                AVG(first_pass_yield) as first_pass_yield,
                SUM(process_errors) as total_errors
            FROM sessions
            WHERE date = ? AND process = ?
        """

        total_df = pd.read_sql_query(total_query, conn, params=[target_date, process])
        df = pd.concat([df, total_df], ignore_index=True)

        # KPI 테이블에 삽입
        cursor = conn.cursor()
        for _, row in df.iterrows():
            cursor.execute("""
                INSERT INTO daily_kpis (date, process, worker, total_pcs, total_trays, avg_work_time, avg_latency, first_pass_yield, total_errors, session_count)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(date, process, worker) DO UPDATE SET
                    total_pcs = excluded.total_pcs,
                    total_trays = excluded.total_trays,
                    avg_work_time = excluded.avg_work_time,
                    avg_latency = excluded.avg_latency,
                    first_pass_yield = excluded.first_pass_yield,
                    total_errors = excluded.total_errors,
                    session_count = excluded.session_count,
                    created_at = CURRENT_TIMESTAMP
            """, (target_date, process, row['worker'], row['total_pcs'], row['total_trays'],
                  row['avg_work_time'], row['avg_latency'], row['first_pass_yield'],
                  row['total_errors'], row['session_count']))

        conn.commit()
        conn.close()

    # ========================================================================
    # 통계 및 유틸리티 메서드
    # ========================================================================

    def get_statistics(self) -> Dict:
        """데이터베이스 통계 조회"""
        conn = self.get_connection()

        stats = {}

        # 이벤트 수
        cursor = conn.execute("SELECT COUNT(*) FROM raw_events")
        stats['total_events'] = cursor.fetchone()[0]

        # 세션 수
        cursor = conn.execute("SELECT COUNT(*) FROM sessions")
        stats['total_sessions'] = cursor.fetchone()[0]

        # 작업자 수
        cursor = conn.execute("SELECT COUNT(DISTINCT worker) FROM sessions")
        stats['total_workers'] = cursor.fetchone()[0]

        # 날짜 범위
        cursor = conn.execute("SELECT MIN(date), MAX(date) FROM sessions")
        row = cursor.fetchone()
        stats['date_range'] = {'min': row[0], 'max': row[1]}

        # 동기화된 파일 수
        cursor = conn.execute("SELECT COUNT(*) FROM file_sync_log WHERE sync_status = 'success'")
        stats['synced_files'] = cursor.fetchone()[0]

        # 데이터베이스 크기
        stats['db_size_mb'] = round(os.path.getsize(self.db_path) / (1024 * 1024), 2)

        conn.close()

        return stats

    def vacuum(self):
        """데이터베이스 최적화 (공간 회수)"""
        conn = self.get_connection()
        conn.execute("VACUUM")
        conn.close()
        logger.info("데이터베이스 VACUUM 완료")
