# WorkerAnalysisGUI 성능 최적화 계획

## 1. 데이터 캐싱 시스템 구현

### 1.1 파일 레벨 캐싱
```python
import pickle
import hashlib
from datetime import datetime, timedelta

class DataCache:
    def __init__(self, cache_dir='cache'):
        self.cache_dir = cache_dir
        os.makedirs(cache_dir, exist_ok=True)

    def get_file_hash(self, file_path):
        stat = os.stat(file_path)
        return hashlib.md5(f"{file_path}{stat.st_mtime}{stat.st_size}".encode()).hexdigest()

    def get_cached_data(self, file_path):
        hash_key = self.get_file_hash(file_path)
        cache_file = os.path.join(self.cache_dir, f"{hash_key}.pkl")

        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as f:
                return pickle.load(f)
        return None

    def save_cached_data(self, file_path, data):
        hash_key = self.get_file_hash(file_path)
        cache_file = os.path.join(self.cache_dir, f"{hash_key}.pkl")

        with open(cache_file, 'wb') as f:
            pickle.dump(data, f)
```

### 1.2 세션 레벨 캐싱
```python
class SessionCache:
    def __init__(self):
        self.session_cache = {}
        self.cache_expiry = timedelta(minutes=30)

    def get_sessions(self, cache_key):
        if cache_key in self.session_cache:
            cached_data, timestamp = self.session_cache[cache_key]
            if datetime.now() - timestamp < self.cache_expiry:
                return cached_data
        return None

    def set_sessions(self, cache_key, data):
        self.session_cache[cache_key] = (data, datetime.now())
```

## 2. 증분 데이터 로딩

### 2.1 날짜 기반 필터링 최적화
```python
def load_data_incremental(self, folder_path, process_mode, start_date=None, end_date=None):
    # 날짜 범위에 해당하는 파일만 로드
    if start_date and end_date:
        target_files = self._get_files_by_date_range(folder_path, start_date, end_date)
    else:
        target_files = self._get_all_files(folder_path)

    # 이미 처리된 파일은 캐시에서 로드
    cached_sessions = []
    files_to_process = []

    for file_path in target_files:
        cached_data = self.cache.get_cached_data(file_path)
        if cached_data:
            cached_sessions.append(cached_data)
        else:
            files_to_process.append(file_path)

    # 새로운 파일만 처리
    new_sessions = []
    for file_path in files_to_process:
        sessions = self._process_single_file(file_path)
        self.cache.save_cached_data(file_path, sessions)
        new_sessions.append(sessions)

    return pd.concat(cached_sessions + new_sessions, ignore_index=True)
```

## 3. 데이터베이스 도입

### 3.1 SQLite 통합
```python
import sqlite3
from sqlalchemy import create_engine

class DatabaseManager:
    def __init__(self, db_path='data/worker_analysis.db'):
        self.engine = create_engine(f'sqlite:///{db_path}')
        self._create_tables()

    def _create_tables(self):
        with self.engine.connect() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id INTEGER PRIMARY KEY,
                    date DATE,
                    worker TEXT,
                    process TEXT,
                    work_time REAL,
                    latency REAL,
                    pcs_completed INTEGER,
                    file_hash TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    INDEX idx_date_worker (date, worker),
                    INDEX idx_process (process)
                )
            """)

    def insert_sessions(self, sessions_df):
        sessions_df.to_sql('sessions', self.engine, if_exists='append', index=False)

    def get_sessions(self, start_date, end_date, workers=None, process=None):
        query = """
            SELECT * FROM sessions
            WHERE date BETWEEN ? AND ?
        """
        params = [start_date, end_date]

        if workers:
            query += " AND worker IN ({})".format(','.join('?' * len(workers)))
            params.extend(workers)

        if process:
            query += " AND process = ?"
            params.append(process)

        return pd.read_sql(query, self.engine, params=params)
```

## 4. API 응답 최적화

### 4.1 페이지네이션
```python
@app.route('/api/data', methods=['POST'])
def get_analysis_data():
    filters = request.json
    page = filters.get('page', 1)
    page_size = filters.get('page_size', 1000)

    # 총 카운트 먼저 계산
    total_count = get_total_sessions_count(filters)

    # 페이지별 데이터 로드
    offset = (page - 1) * page_size
    sessions_df = get_sessions_paginated(filters, offset, page_size)

    return jsonify({
        'data': sessions_df.to_dict('records'),
        'pagination': {
            'page': page,
            'page_size': page_size,
            'total_count': total_count,
            'total_pages': math.ceil(total_count / page_size)
        }
    })
```

### 4.2 데이터 압축
```python
from flask import Response
import gzip
import json

def compress_response(data):
    json_str = json.dumps(data, ensure_ascii=False)
    compressed = gzip.compress(json_str.encode('utf-8'))

    return Response(
        compressed,
        mimetype='application/json',
        headers={'Content-Encoding': 'gzip'}
    )
```

## 5. 백그라운드 데이터 처리

### 5.1 비동기 데이터 갱신
```python
import asyncio
from concurrent.futures import ThreadPoolExecutor

class BackgroundProcessor:
    def __init__(self):
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.is_processing = False

    async def process_new_files(self):
        if self.is_processing:
            return

        self.is_processing = True
        try:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(self.executor, self._process_files)
        finally:
            self.is_processing = False

    def _process_files(self):
        # 새로운 파일들을 백그라운드에서 처리
        new_files = self._get_unprocessed_files()
        for file_path in new_files:
            sessions = self._process_single_file(file_path)
            self.db_manager.insert_sessions(sessions)
```

## 6. 메모리 최적화

### 6.1 청크 단위 처리
```python
def process_large_file(file_path, chunk_size=1000):
    sessions = []

    for chunk in pd.read_csv(file_path, chunksize=chunk_size):
        processed_chunk = self._process_events_chunk(chunk)
        sessions.append(processed_chunk)

        # 메모리 정리
        del chunk
        del processed_chunk

    return pd.concat(sessions, ignore_index=True)
```

### 6.2 데이터 타입 최적화
```python
def optimize_dataframe(df):
    # 문자열 컬럼을 category로 변환
    categorical_columns = ['worker', 'process', 'item_code']
    for col in categorical_columns:
        if col in df.columns:
            df[col] = df[col].astype('category')

    # 정수 컬럼 최적화
    int_columns = ['pcs_completed', 'process_errors']
    for col in int_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], downcast='integer')

    # 실수 컬럼 최적화
    float_columns = ['work_time', 'latency']
    for col in float_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], downcast='float')

    return df
```

## 7. 실시간 업데이트 최적화

### 7.1 스마트 파일 감시
```python
class SmartFileHandler(FileSystemEventHandler):
    def __init__(self, socket_instance, processor):
        self.socketio = socket_instance
        self.processor = processor
        self.last_triggered = {}
        self.batch_queue = []
        self.batch_timer = None

    def on_modified(self, event):
        if not self._should_process(event):
            return

        # 배치 처리를 위해 큐에 추가
        self.batch_queue.append(event.src_path)

        # 기존 타이머 취소 후 새로 설정
        if self.batch_timer:
            self.batch_timer.cancel()

        self.batch_timer = threading.Timer(2.0, self._process_batch)
        self.batch_timer.start()

    def _process_batch(self):
        if not self.batch_queue:
            return

        # 중복 파일 제거
        unique_files = list(set(self.batch_queue))
        self.batch_queue.clear()

        # 백그라운드에서 처리
        threading.Thread(
            target=self._update_cache_and_notify,
            args=(unique_files,),
            daemon=True
        ).start()
```

## 구현 우선순위

1. **즉시 구현 (High Priority)**:
   - 파일 레벨 캐싱
   - 날짜 범위 필터링 최적화
   - 데이터 타입 최적화

2. **단기 구현 (Medium Priority)**:
   - SQLite 데이터베이스 도입
   - API 응답 압축
   - 청크 단위 처리

3. **장기 구현 (Low Priority)**:
   - 비동기 처리
   - 고급 캐싱 전략
   - 분산 처리

## 예상 성능 개선

- **API 응답 시간**: 4.4초 → 0.5초 (88% 개선)
- **메모리 사용량**: 326MB → 150MB (54% 개선)
- **응답 크기**: 58MB → 5MB (91% 개선)
- **초기 로딩**: 처음에만 느림, 이후 즉시 응답