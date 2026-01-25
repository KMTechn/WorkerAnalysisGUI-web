# -*- coding: utf-8 -*-
"""
security.py - Flask Application Security Module
보안 미들웨어, 입력 검증, Rate Limiting, 접근 코드 인증, CSRF 보호
"""

import os
import re
import html
import time
import hashlib
import secrets
import string
from functools import wraps
from datetime import datetime, timedelta
from collections import defaultdict
from flask import request, jsonify, g, session, redirect, url_for, render_template_string
import logging

# 로깅 설정
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
security_logger = logging.getLogger('security')

# ============ Environment Detection ============

def is_production():
    """프로덕션 환경 여부 확인"""
    return os.environ.get('FLASK_ENV', 'production') == 'production'

def is_https_enabled():
    """HTTPS 활성화 여부 확인"""
    return os.environ.get('HTTPS_ENABLED', 'false').lower() == 'true'

# ============ CSRF Protection ============

class CSRFProtection:
    """간단한 CSRF 보호 구현"""

    TOKEN_NAME = 'csrf_token'
    TOKEN_LENGTH = 32

    @staticmethod
    def generate_token():
        """CSRF 토큰 생성"""
        if CSRFProtection.TOKEN_NAME not in session:
            session[CSRFProtection.TOKEN_NAME] = secrets.token_hex(CSRFProtection.TOKEN_LENGTH)
        return session[CSRFProtection.TOKEN_NAME]

    @staticmethod
    def validate_token(token):
        """CSRF 토큰 검증"""
        stored_token = session.get(CSRFProtection.TOKEN_NAME)
        if not stored_token or not token:
            return False
        return secrets.compare_digest(stored_token, token)

    @staticmethod
    def get_token_from_request():
        """요청에서 CSRF 토큰 추출"""
        # 헤더에서 확인
        token = request.headers.get('X-CSRF-Token')
        if token:
            return token
        # Form 데이터에서 확인
        if request.form:
            token = request.form.get('csrf_token')
            if token:
                return token
        # JSON 데이터에서 확인
        if request.is_json:
            data = request.get_json(silent=True)
            if data and isinstance(data, dict):
                return data.get('csrf_token')
        return None


def csrf_exempt(f):
    """CSRF 검증 제외 데코레이터"""
    f._csrf_exempt = True
    return f


def csrf_protect(f):
    """CSRF 보호 데코레이터 (명시적으로 보호할 때 사용)"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        if request.method in ('POST', 'PUT', 'DELETE', 'PATCH'):
            token = CSRFProtection.get_token_from_request()
            if not CSRFProtection.validate_token(token):
                security_logger.warning(f"CSRF 토큰 검증 실패: {get_client_ip()}")
                return jsonify({"error": "CSRF token invalid or missing"}), 403
        return f(*args, **kwargs)
    return wrapper


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


# ============ Access Code Authentication ============

ACCESS_CODE_FILE = '/root/WorkerAnalysisGUI-web/.access_code'

def generate_access_code():
    """6자리 랜덤 접근 코드 생성"""
    return ''.join(secrets.choice(string.digits) for _ in range(6))


def get_or_create_access_code():
    """접근 코드 조회 또는 생성"""
    if os.path.exists(ACCESS_CODE_FILE):
        with open(ACCESS_CODE_FILE, 'r') as f:
            code = f.read().strip()
            if code:
                return code
    # 새 코드 생성 및 저장
    new_code = generate_access_code()
    with open(ACCESS_CODE_FILE, 'w') as f:
        f.write(new_code)
    os.chmod(ACCESS_CODE_FILE, 0o600)
    security_logger.info(f"새 접근 코드 생성됨: {new_code}")
    return new_code


def verify_access_code(code: str) -> bool:
    """접근 코드 검증"""
    stored_code = get_or_create_access_code()
    return secrets.compare_digest(code.strip(), stored_code)


def is_authenticated() -> bool:
    """세션 인증 상태 확인"""
    return session.get('authenticated', False)


# 인증 없이 접근 가능한 경로
PUBLIC_PATHS = ['/login', '/static/']


LOGIN_TEMPLATE = '''
<!DOCTYPE html>
<html lang="ko">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>접근 코드 입력 - Worker Analysis</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: linear-gradient(135deg, #1a1a2e 0%, #16213e 100%);
            min-height: 100vh;
            display: flex;
            align-items: center;
            justify-content: center;
        }
        .login-container {
            background: rgba(255, 255, 255, 0.95);
            padding: 40px;
            border-radius: 16px;
            box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
            width: 100%;
            max-width: 400px;
            text-align: center;
        }
        h1 {
            color: #1a1a2e;
            margin-bottom: 10px;
            font-size: 1.8em;
        }
        .subtitle {
            color: #666;
            margin-bottom: 30px;
            font-size: 0.95em;
        }
        .input-group {
            margin-bottom: 20px;
        }
        .input-group label {
            display: block;
            text-align: left;
            margin-bottom: 8px;
            color: #333;
            font-weight: 500;
        }
        .code-input {
            width: 100%;
            padding: 15px;
            font-size: 24px;
            text-align: center;
            letter-spacing: 8px;
            border: 2px solid #ddd;
            border-radius: 8px;
            outline: none;
            transition: border-color 0.3s;
        }
        .code-input:focus {
            border-color: #4a90d9;
        }
        .code-input::placeholder {
            letter-spacing: 2px;
            font-size: 16px;
        }
        .btn-login {
            width: 100%;
            padding: 15px;
            background: linear-gradient(135deg, #4a90d9 0%, #357abd 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s, box-shadow 0.2s;
        }
        .btn-login:hover {
            transform: translateY(-2px);
            box-shadow: 0 5px 20px rgba(74, 144, 217, 0.4);
        }
        .error {
            background: #ffe6e6;
            color: #d63031;
            padding: 12px;
            border-radius: 8px;
            margin-bottom: 20px;
            font-size: 0.9em;
        }
        .footer {
            margin-top: 30px;
            color: #999;
            font-size: 0.85em;
        }
    </style>
</head>
<body>
    <div class="login-container">
        <h1>Worker Analysis</h1>
        <p class="subtitle">작업자 성과 분석 대시보드</p>

        {% if error %}
        <div class="error">{{ error }}</div>
        {% endif %}

        <form method="POST" action="/login">
            <div class="input-group">
                <label for="code">접근 코드</label>
                <input type="password"
                       id="code"
                       name="code"
                       class="code-input"
                       maxlength="6"
                       placeholder="6자리 코드"
                       autocomplete="off"
                       autofocus
                       required>
            </div>
            <button type="submit" class="btn-login">접속하기</button>
        </form>

        <p class="footer">인가된 사용자만 접근 가능합니다</p>
    </div>

    <script>
        // 숫자만 입력 허용
        document.getElementById('code').addEventListener('input', function(e) {
            this.value = this.value.replace(/[^0-9]/g, '');
        });
    </script>
</body>
</html>
'''


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

    # 접근 코드 인증 체크 (공개 경로 제외)
    is_public = any(request.path.startswith(p) for p in PUBLIC_PATHS)
    if not is_public and not is_authenticated():
        # API 요청은 401 반환
        if request.path.startswith('/api/'):
            return jsonify({"error": "Unauthorized. Please login first."}), 401
        # 일반 페이지는 로그인으로 리다이렉트
        return redirect(url_for('login'))

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


# ============ Standardized Error Handler ============

# 사용자 친화적 에러 메시지 매핑
ERROR_MESSAGES = {
    'timeout': '요청 시간이 초과되었습니다. 잠시 후 다시 시도해주세요.',
    'network': '네트워크 오류가 발생했습니다. 연결 상태를 확인해주세요.',
    'server': '서버 오류가 발생했습니다. 잠시 후 다시 시도해주세요.',
    'unauthorized': '접근 권한이 없습니다. 다시 로그인해주세요.',
    'validation': '입력 데이터가 올바르지 않습니다.',
    'not_found': '요청한 데이터를 찾을 수 없습니다.',
    'database': '데이터베이스 오류가 발생했습니다.'
}


def handle_api_error(f):
    """API 에러 핸들링 표준화 데코레이터"""
    @wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except ValueError as e:
            security_logger.warning(f"Validation error in {f.__name__}: {e}")
            return jsonify({
                "error": ERROR_MESSAGES['validation'],
                "detail": str(e),
                "type": "validation"
            }), 400
        except TimeoutError as e:
            security_logger.error(f"Timeout in {f.__name__}: {e}")
            return jsonify({
                "error": ERROR_MESSAGES['timeout'],
                "type": "timeout"
            }), 504
        except ConnectionError as e:
            security_logger.error(f"Connection error in {f.__name__}: {e}")
            return jsonify({
                "error": ERROR_MESSAGES['database'],
                "type": "database"
            }), 503
        except Exception as e:
            security_logger.error(f"Unhandled error in {f.__name__}: {e}", exc_info=True)
            return jsonify({
                "error": ERROR_MESSAGES['server'],
                "type": "server"
            }), 500
    return wrapper


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

    # Session 보안 설정 (환경변수 기반)
    # HTTPS가 활성화된 경우에만 SECURE 플래그 설정
    app.config['SESSION_COOKIE_SECURE'] = is_https_enabled()
    app.config['SESSION_COOKIE_HTTPONLY'] = True
    app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
    app.config['PERMANENT_SESSION_LIFETIME'] = timedelta(days=7)  # 세션 유지 7일

    security_logger.info(f"Session security: SECURE={app.config['SESSION_COOKIE_SECURE']}, ENV={os.environ.get('FLASK_ENV', 'production')}")

    # 로그인 라우트 등록
    @app.route('/login', methods=['GET', 'POST'])
    def login():
        error = None
        if request.method == 'POST':
            code = request.form.get('code', '')
            if verify_access_code(code):
                session.permanent = True
                session['authenticated'] = True
                session['login_time'] = datetime.now().isoformat()
                security_logger.info(f"로그인 성공: {get_client_ip()}")
                # 원래 요청한 페이지로 리다이렉트
                next_url = request.args.get('next', '/')
                return redirect(next_url)
            else:
                error = "잘못된 접근 코드입니다"
                security_logger.warning(f"로그인 실패: {get_client_ip()}")
        return render_template_string(LOGIN_TEMPLATE, error=error)

    @app.route('/logout')
    def logout():
        session.clear()
        security_logger.info(f"로그아웃: {get_client_ip()}")
        return redirect(url_for('login'))

    # 미들웨어 등록
    app.before_request(security_check)
    app.after_request(add_security_headers)

    # 접근 코드 출력
    access_code = get_or_create_access_code()
    security_logger.info("Flask 보안 모듈 초기화 완료")
    print(f"\n{'='*50}")
    print(f"  접근 코드: {access_code}")
    print(f"  (이 코드로 로그인해야 대시보드에 접근할 수 있습니다)")
    print(f"{'='*50}\n")

    return app
