# -*- coding: utf-8 -*-
"""
재고 원장 데이터 조회 서비스
ERPNext MariaDB 연동
"""
import pymysql
from decimal import Decimal

# ERPNext MariaDB 설정
DB_CONFIG = {
    'host': 'localhost',
    'port': 3306,
    'user': '_c3e9ce1114f11fa0',
    'password': '1TjMMl3QgvgYo5qX',
    'database': '_c3e9ce1114f11fa0',
    'charset': 'utf8mb4'
}

# Stock Entry Types 정의
STOCK_ENTRY_TYPES = {
    'Material Receipt': '입고',
    'Material Issue': '출고',
    'Material Transfer': '창고이동',
    'Disassemble': '해체',
    'Stock Delivery': '출고배송',
    '공급처반품': '공급처반품',
    'Repack': '재포장',
    'Manufacture': '제조'
}

# 기본 제외 유형 (해체, 이동)
DEFAULT_EXCLUDE_TYPES = ['Disassemble', 'Material Transfer']


def format_number(value):
    """Decimal을 정수 또는 소수점 2자리로 변환"""
    if value is None:
        return 0
    if isinstance(value, Decimal):
        value = float(value)
    if isinstance(value, float):
        if value == int(value):
            return int(value)
        return round(value, 2)
    return value


def get_base_item_code(item_code):
    """품목코드에서 _UNPACK, _REPACK 접미사 제거하여 기본 품목코드 반환"""
    if item_code is None:
        return None
    return item_code.replace('_UNPACK', '').replace('_REPACK', '')


def get_db_connection():
    """MariaDB 연결 생성"""
    return pymysql.connect(**DB_CONFIG, cursorclass=pymysql.cursors.DictCursor)


def get_stock_entry_types():
    """사용 가능한 Stock Entry Type 목록 조회"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT DISTINCT stock_entry_type, purpose
                FROM `tabStock Entry`
                WHERE docstatus = 1 AND stock_entry_type IS NOT NULL
                ORDER BY stock_entry_type
            """)
            results = cursor.fetchall()
            types = {}
            for row in results:
                entry_type = row['stock_entry_type']
                types[entry_type] = STOCK_ENTRY_TYPES.get(entry_type, entry_type)
            return types
    finally:
        conn.close()


def get_warehouses():
    """창고 목록 조회"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT name, warehouse_name
                FROM `tabWarehouse`
                WHERE disabled = 0 AND is_group = 0
                ORDER BY warehouse_name
            """)
            return cursor.fetchall()
    finally:
        conn.close()


def get_items():
    """품목 목록 조회"""
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute("""
                SELECT name, item_name
                FROM `tabItem`
                WHERE disabled = 0
                ORDER BY item_name
                LIMIT 500
            """)
            return cursor.fetchall()
    finally:
        conn.close()


def get_stock_ledger(from_date, to_date, exclude_types=None, warehouse=None, item_search=None):
    """
    재고 원장 데이터 조회

    Args:
        from_date: 시작일 (YYYY-MM-DD)
        to_date: 종료일 (YYYY-MM-DD)
        exclude_types: 제외할 Stock Entry Type 리스트
        warehouse: 특정 창고 필터
        item_search: 품목코드 또는 품목명 검색어

    Returns:
        list: 재고 원장 데이터
    """
    if exclude_types is None:
        exclude_types = []

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT
                    sle.posting_datetime as date,
                    sle.item_code,
                    i.item_name,
                    sle.warehouse,
                    CASE
                        WHEN sle.actual_qty > 0 THEN sle.actual_qty
                        ELSE 0
                    END as in_qty,
                    CASE
                        WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty)
                        ELSE 0
                    END as out_qty,
                    sle.qty_after_transaction as balance_qty,
                    sle.valuation_rate,
                    sle.stock_value,
                    sle.voucher_type,
                    sle.voucher_no,
                    se.stock_entry_type,
                    se.purpose
                FROM `tabStock Ledger Entry` sle
                LEFT JOIN `tabStock Entry` se
                    ON sle.voucher_no = se.name AND sle.voucher_type = 'Stock Entry'
                LEFT JOIN `tabItem` i ON sle.item_code = i.name
                WHERE sle.docstatus < 2
                    AND sle.is_cancelled = 0
                    AND DATE(sle.posting_datetime) BETWEEN %s AND %s
            """
            params = [from_date, to_date]

            if exclude_types:
                placeholders = ', '.join(['%s'] * len(exclude_types))
                query += f"""
                    AND (sle.voucher_type != 'Stock Entry'
                         OR se.stock_entry_type NOT IN ({placeholders})
                         OR se.stock_entry_type IS NULL)
                """
                params.extend(exclude_types)

            if warehouse:
                query += " AND sle.warehouse = %s"
                params.append(warehouse)

            if item_search:
                query += """ AND (REPLACE(REPLACE(sle.item_code, '_UNPACK', ''), '_REPACK', '') LIKE %s
                             OR i.item_name LIKE %s)"""
                search_pattern = f"%{item_search}%"
                params.extend([search_pattern, search_pattern])

            query += " ORDER BY sle.posting_datetime DESC, sle.creation DESC"

            cursor.execute(query, params)
            results = cursor.fetchall()

            for row in results:
                for field in ['in_qty', 'out_qty', 'balance_qty', 'valuation_rate', 'stock_value']:
                    if field in row:
                        row[field] = format_number(row[field])

                row['base_item_code'] = get_base_item_code(row['item_code'])

                if row['stock_entry_type']:
                    row['stock_entry_type_kr'] = STOCK_ENTRY_TYPES.get(
                        row['stock_entry_type'], row['stock_entry_type']
                    )
                else:
                    row['stock_entry_type_kr'] = row['voucher_type']

            return results
    finally:
        conn.close()


def get_stock_summary(from_date, to_date, exclude_types=None, warehouse=None):
    """
    품목별 재고 요약 조회
    """
    if exclude_types is None:
        exclude_types = []

    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT
                    REPLACE(REPLACE(sle.item_code, '_UNPACK', ''), '_REPACK', '') as item_code,
                    i.item_name,
                    SUM(CASE WHEN sle.actual_qty > 0 THEN sle.actual_qty ELSE 0 END) as total_in,
                    SUM(CASE WHEN sle.actual_qty < 0 THEN ABS(sle.actual_qty) ELSE 0 END) as total_out,
                    COUNT(*) as transaction_count
                FROM `tabStock Ledger Entry` sle
                LEFT JOIN `tabStock Entry` se
                    ON sle.voucher_no = se.name AND sle.voucher_type = 'Stock Entry'
                LEFT JOIN `tabItem` i ON REPLACE(REPLACE(sle.item_code, '_UNPACK', ''), '_REPACK', '') = i.name
                WHERE sle.docstatus < 2
                    AND sle.is_cancelled = 0
                    AND DATE(sle.posting_datetime) BETWEEN %s AND %s
            """
            params = [from_date, to_date]

            if exclude_types:
                placeholders = ', '.join(['%s'] * len(exclude_types))
                query += f"""
                    AND (sle.voucher_type != 'Stock Entry'
                         OR se.stock_entry_type NOT IN ({placeholders})
                         OR se.stock_entry_type IS NULL)
                """
                params.extend(exclude_types)

            if warehouse:
                query += " AND sle.warehouse = %s"
                params.append(warehouse)

            query += """ GROUP BY REPLACE(REPLACE(sle.item_code, '_UNPACK', ''), '_REPACK', ''), i.item_name
                         ORDER BY total_in DESC, total_out DESC"""

            cursor.execute(query, params)
            results = cursor.fetchall()

            for row in results:
                for field in ['total_in', 'total_out']:
                    if field in row:
                        row[field] = format_number(row[field])

            return results
    finally:
        conn.close()


def get_current_stock(warehouse=None, item_code=None):
    """
    현재 재고 현황 조회 (최신 잔량 기준)
    """
    conn = get_db_connection()
    try:
        with conn.cursor() as cursor:
            query = """
                SELECT
                    b.item_code,
                    i.item_name,
                    b.warehouse,
                    b.actual_qty as current_qty,
                    b.valuation_rate,
                    b.stock_value
                FROM `tabBin` b
                LEFT JOIN `tabItem` i ON b.item_code = i.name
                WHERE b.actual_qty != 0
            """
            params = []

            if warehouse:
                query += " AND b.warehouse = %s"
                params.append(warehouse)

            if item_code:
                query += " AND b.item_code = %s"
                params.append(item_code)

            query += " ORDER BY b.item_code, b.warehouse"

            cursor.execute(query, params)
            return cursor.fetchall()
    finally:
        conn.close()
