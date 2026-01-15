# -*- coding: utf-8 -*-
"""
security.py - Flask Application Security Module
보안 미들웨어, 입력 검증, Rate Limiting
"""

import os
import re
import html
import time
import hashlib
import secrets
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
from flask import request, jsonify, g
import logging

# 로깅 설정
logging.basicConfig(level=logging.INFO)
security_logger = logging.getLogger('security')

# ============ Configuration ============

def generate_secret_key():
    """환경변수 또는 안전한 랜덤 키 생성"""
    key = os.environ.get('FLASK_SECRET_KEY')
    if key:
        return key
    # .secret_key 파일에서 읽기 또는 생성
    key_file = '/root/WorkerAnalysisGUI-web/.secret_key'
    if os.path.exists(key_file):
        with open(key_file, 'r') as f:
            return f.read().strip()
    # 새 키 생성 및 저장
    new_key = secrets.token_hex(32)
    with open(key_file, 'w') as f:
        f.write(new_key)
    os.chmod(key_file, 0o600)  # 소유자만 읽기/쓰기
    return new_key


# ============ Input Validation ============

class InputValidator:
    """입력값 검증 클래스"""

    # SQL Injection 패턴
    SQL_INJECTION_PATTERNS = [
        r"(\b(union|select|insert|update|delete|drop|create|alter|truncate|exec|execute)\b.*\b(from|into|table|database)\b)",
        r"(--|#|/\*|\*/)",  # SQL 주석
        r"(\bor\b.*=.*\bor\b)",  # OR 1=1 패턴
        r"(\band\b.*=.*\band\b)",  # AND 패턴
        r"(;.*\b(select|insert|update|delete|drop)\b)",  # 다중 쿼리
        r"(\bwaitfor\b.*\bdelay\b)",  # Time-based injection
        r"(\bbenchmark\b\s*\()",  # MySQL benchmark
    ]

    # XSS 패턴
    XSS_PATTERNS = [
        r"(<script[^>]*>.*?</script>)",
        r"(javascript\s*:)",
        r"(on\w+\s*=)",  # onclick, onerror 등
        r"(<iframe[^>]*>)",
        r"(<object[^>]*>)",
        r"(<embed[^>]*>)",
        r"(<link[^>]*>)",
        r"(<meta[^>]*>)",
        r"(expression\s*\()",  # CSS expression
        r"(vbscript\s*:)",
    ]

    # Path Traversal 패턴
    PATH_TRAVERSAL_PATTERNS = [
        r"(\.\.[\\/])",  # ../
        r"(%2e%2e[\\/])",  # encoded ../
        r"(\.\.%2f)",
        r"(%252e%252e)",  # double encoded
    ]

    @classmethod
    def sanitize_string(cls, value: str, max_length: int = 1000) -> str:
        """문자열 정제"""
        if not isinstance(value, str):
            return str(value)[:max_length]
        # 길이 제한
        value = value[:max_length]
        # HTML 엔티티 이스케이프
        value = html.escape(value)
        return value

    @classmethod
    def check_sql_injection(cls, value: str) -> bool:
        """SQL Injection 패턴 검사"""
        if not isinstance(value, str):
            return False
        value_lower = value.lower()
        for pattern in cls.SQL_INJECTION_PATTERNS:
            if re.search(pattern, value_lower, re.IGNORECASE):
                security_logger.warning(f"SQL Injection 시도 감지: {value[:100]}")
                return True
        return False

    @classmethod
    def check_xss(cls, value: str) -> bool:
        """XSS 패턴 검사"""
        if not isinstance(value, str):
            return False
        value_lower = value.lower()
        for pattern in cls.XSS_PATTERNS:
            if re.search(pattern, value_lower, re.IGNORECASE):
                security_logger.warning(f"XSS 시도 감지: {value[:100]}")
                return True
        return False

    @classmethod
    def check_path_traversal(cls, value: str) -> bool:
        """Path Traversal 패턴 검사"""
        if not isinstance(value, str):
            return False
        for pattern in cls.PATH_TRAVERSAL_PATTERNS:
            if re.search(pattern, value, re.IGNORECASE):
                security_logger.warning(f"Path Traversal 시도 감지: {value[:100]}")
                return True
        return False

    @classmethod
    def validate_date(cls, date_str: str) -> bool:
        """날짜 형식 검증 (YYYY-MM-DD)"""
        if not date_str:
            return True  # None/empty is OK
        pattern = r'^\d{4}-\d{2}-\d{2}$'
        if not re.match(pattern, date_str):
            return False
        try:
            datetime.strptime(date_str, '%Y-%m-%d')
            return True
        except ValueError:
            return False

    @classmethod
    def validate_barcode(cls, barcode: str) -> bool:
        """바코드 형식 검증"""
        if not barcode:
            return True
        # 영숫자, 하이픈, 언더스코어만 허용
        pattern = r'^[\w\-]+$'
        return bool(re.match(pattern, barcode)) and len(barcode) <= 100

    @classmethod
    def validate_worker_name(cls, name: str) -> bool:
        """작업자 이름 검증"""
        if not name:
            return True
        # 한글, 영숫자, 점, 공백 허용
        pattern = r'^[\w가-힣\.\s]+$'
        return bool(re.match(pattern, name)) and len(name) <= 50

    @classmethod
    def is_safe_input(cls, value) -> bool:
        """종합 안전성 검사"""
        if value is None:
            return True
        if isinstance(value, (int, float, bool)):
            return True
        if isinstance(value, str):
            if cls.check_sql_injection(value):
                return False
            if cls.check_xss(value):
                return False
            if cls.check_path_traversal(value):
                return False
        if isinstance(value, dict):
            return all(cls.is_safe_input(v) for v in value.values())
        if isinstance(value, list):
            return all(cls.is_safe_input(v) for v in value)
        return True


# ============ Rate Limiting ============

class RateLimiter:
    """메모리 기반 Rate Limiter"""

    def __init__(self):
        self.requests = defaultdict(list)
        self.blocked_ips = {}  # IP -> unblock time

    def is_blocked(self, ip: str) -> bool:
        """IP 차단 여부 확인"""
        if ip in self.blocked_ips:
            if datetime.now() < self.blocked_ips[ip]:
                return True
            else:
                del self.blocked_ips[ip]
        return False

    def block_ip(self, ip: str, minutes: int = 15):
        """IP 일시 차단"""
        self.blocked_ips[ip] = datetime.now() + timedelta(minutes=minutes)
        security_logger.warning(f"IP 차단: {ip} ({minutes}분)")

    def check_rate(self, ip: str, endpoint: str, max_requests: int = 60, window_seconds: int = 60) -> bool:
        """
        Rate 체크
        Returns: True if allowed, False if rate exceeded
        """
        key = f"{ip}:{endpoint}"
        now = time.time()

        # 오래된 요청 제거
        self.requests[key] = [t for t in self.requests[key] if now - t < window_seconds]

        if len(self.requests[key]) >= max_requests:
            security_logger.warning(f"Rate limit 초과: {ip} on {endpoint}")
            return False

        self.requests[key].append(now)
        return True

    def cleanup(self):
        """오래된 데이터 정리"""
        now = time.time()
        for key in list(self.requests.keys()):
            self.requests[key] = [t for t in self.requests[key] if now - t < 300]
            if not self.requests[key]:
                del self.requests[key]


# 전역 Rate Limiter
rate_limiter = RateLimiter()


# ============ Security Middleware ============

def get_client_ip():
    """실제 클라이언트 IP 획득 (프록시 고려)"""
    if request.headers.get('X-Forwarded-For'):
        return request.headers.get('X-Forwarded-For').split(',')[0].strip()
    if request.headers.get('X-Real-IP'):
        return request.headers.get('X-Real-IP')
    return request.remote_addr


def security_check():
    """보안 검사 미들웨어 (before_request)"""
    client_ip = get_client_ip()

    # IP 차단 확인
    if rate_limiter.is_blocked(client_ip):
        security_logger.warning(f"차단된 IP 접근 시도: {client_ip}")
        return jsonify({"error": "Access denied"}), 403

    # Rate Limiting
    endpoint = request.endpoint or 'unknown'

    # 엔드포인트별 Rate Limit 설정
    rate_limits = {
        'api_data': (30, 60),      # 30 req/min
        'api_trace': (20, 60),     # 20 req/min
        'search': (60, 60),        # 60 req/min
        'default': (120, 60),      # 120 req/min
    }

    max_req, window = rate_limits.get(endpoint, rate_limits['default'])

    if not rate_limiter.check_rate(client_ip, endpoint, max_req, window):
        return jsonify({"error": "Too many requests. Please slow down."}), 429

    # 요청 데이터 검증
    if request.is_json:
        data = request.get_json(silent=True)
        if data and not InputValidator.is_safe_input(data):
            security_logger.warning(f"악성 입력 감지: {client_ip}")
            # 반복 공격 시 IP 차단
            return jsonify({"error": "Invalid input detected"}), 400

    # Query Parameter 검증
    for key, value in request.args.items():
        if not InputValidator.is_safe_input(value):
            security_logger.warning(f"악성 쿼리 파라미터: {client_ip} - {key}={value[:50]}")
            return jsonify({"error": "Invalid query parameter"}), 400

    # 요청 정보 저장 (로깅용)
    g.client_ip = client_ip
    g.request_start = time.time()


def log_request():
    """요청 로깅 (after_request)"""
    if hasattr(g, 'request_start'):
        duration = (time.time() - g.request_start) * 1000
        client_ip = getattr(g, 'client_ip', 'unknown')

        # 느린 요청 경고 (5초 이상)
        if duration > 5000:
            security_logger.info(f"Slow request: {request.path} - {duration:.0f}ms from {client_ip}")


# ============ Decorators ============

def rate_limit(max_requests: int = 30, window: int = 60):
    """Rate Limiting 데코레이터"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            client_ip = get_client_ip()
            if not rate_limiter.check_rate(client_ip, f.__name__, max_requests, window):
                return jsonify({"error": "Rate limit exceeded"}), 429
            return f(*args, **kwargs)
        return wrapper
    return decorator


def validate_json_input(*required_fields):
    """JSON 입력 검증 데코레이터"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            if not request.is_json:
                return jsonify({"error": "JSON required"}), 400

            data = request.get_json(silent=True)
            if not data:
                return jsonify({"error": "Invalid JSON"}), 400

            # 필수 필드 확인
            missing = [field for field in required_fields if field not in data]
            if missing:
                return jsonify({"error": f"Missing fields: {', '.join(missing)}"}), 400

            # 안전성 검사
            if not InputValidator.is_safe_input(data):
                return jsonify({"error": "Invalid input"}), 400

            return f(*args, **kwargs)
        return wrapper
    return decorator


def validate_date_params(*date_fields):
    """날짜 파라미터 검증 데코레이터"""
    def decorator(f):
        @wraps(f)
        def wrapper(*args, **kwargs):
            data = request.get_json(silent=True) or {}
            args_data = request.args.to_dict()

            for field in date_fields:
                value = data.get(field) or args_data.get(field)
                if value and not InputValidator.validate_date(value):
                    return jsonify({"error": f"Invalid date format for {field}"}), 400

            return f(*args, **kwargs)
        return wrapper
    return decorator


# ============ Security Headers ============

def add_security_headers(response):
    """보안 헤더 추가 (after_request)"""
    # HSTS (HTTPS 강제)
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'

    # Cache 제어 (API 응답)
    if request.path.startswith('/api/'):
        response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
        response.headers['Pragma'] = 'no-cache'

    return response


# ============ Setup Function ============

def setup_security(app):
    """Flask 앱에 보안 설정 적용"""
    # Secret Key 설정
    app.config['SECRET_KEY'] = generate_secret_key()

    # Session 보안 설정
    app.config['SESSION_COOKIE_SECURE'] = True
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'

    # 미들웨어 등록
    app.before_request(security_check)
    app.after_request(add_security_headers)

    security_logger.info("Flask 보안 모듈 초기화 완료")

    return app
