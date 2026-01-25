# -*- coding: utf-8 -*-
"""
Stock Ledger Blueprint - ERPNext 재고 원장 대시보드
"""
from flask import Blueprint, render_template, request, jsonify, Response
from datetime import datetime, timedelta
import pandas as pd
from io import BytesIO

from .stock_service import (
    get_stock_ledger,
    get_stock_summary,
    get_stock_entry_types,
    get_warehouses,
    get_items,
    get_current_stock,
    STOCK_ENTRY_TYPES,
    DEFAULT_EXCLUDE_TYPES
)

stock_bp = Blueprint('stock', __name__, template_folder='templates')


@stock_bp.route('/')
def index():
    """메인 페이지 - 재고 원장 조회 (v2)"""
    default_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    default_to = datetime.now().strftime('%Y-%m-%d')

    entry_types = get_stock_entry_types()
    warehouses = get_warehouses()

    # v2 템플릿 사용
    return render_template(
        'stock/stock_ledger_v2.html',
        entry_types=entry_types,
        warehouses=warehouses,
        default_from=default_from,
        default_to=default_to,
        default_exclude=DEFAULT_EXCLUDE_TYPES,
        stock_entry_types=STOCK_ENTRY_TYPES,
        demo_mode=False
    )


@stock_bp.route('/v1')
def index_v1():
    """기존 버전 페이지"""
    default_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    default_to = datetime.now().strftime('%Y-%m-%d')

    entry_types = get_stock_entry_types()
    warehouses = get_warehouses()

    return render_template(
        'stock/stock_ledger.html',
        entry_types=entry_types,
        warehouses=warehouses,
        default_from=default_from,
        default_to=default_to,
        default_exclude=DEFAULT_EXCLUDE_TYPES,
        stock_entry_types=STOCK_ENTRY_TYPES,
        demo_mode=False
    )


@stock_bp.route('/api/stock-ledger')
def api_stock_ledger():
    """재고 원장 데이터 API"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    exclude_types = request.args.getlist('exclude_types')
    warehouse = request.args.get('warehouse')
    item_search = request.args.get('item_search')

    if not from_date or not to_date:
        return jsonify({'error': '날짜를 입력해주세요'}), 400

    data = get_stock_ledger(from_date, to_date, exclude_types, warehouse, item_search)

    for row in data:
        if row.get('date'):
            row['date'] = row['date'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/stock-summary')
def api_stock_summary():
    """품목별 요약 데이터 API"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    exclude_types = request.args.getlist('exclude_types')
    warehouse = request.args.get('warehouse')

    if not from_date or not to_date:
        return jsonify({'error': '날짜를 입력해주세요'}), 400

    data = get_stock_summary(from_date, to_date, exclude_types, warehouse)

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/current-stock')
def api_current_stock():
    """현재 재고 현황 API"""
    warehouse = request.args.get('warehouse')
    item_code = request.args.get('item_code')

    data = get_current_stock(warehouse, item_code)

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/export-excel')
def export_excel():
    """Excel 내보내기"""
    from_date = request.args.get('from_date')
    to_date = request.args.get('to_date')
    exclude_types = request.args.getlist('exclude_types')
    warehouse = request.args.get('warehouse')
    item_search = request.args.get('item_search')
    export_type = request.args.get('type', 'ledger')

    if not from_date or not to_date:
        return jsonify({'error': '날짜를 입력해주세요'}), 400

    if export_type == 'summary':
        data = get_stock_summary(from_date, to_date, exclude_types, warehouse)
        columns = {
            'item_code': '품목코드',
            'item_name': '품목명',
            'total_in': '총입고',
            'total_out': '총출고',
            'transaction_count': '거래건수'
        }
        filename = f'재고요약_{from_date}_{to_date}.xlsx'
    else:
        data = get_stock_ledger(from_date, to_date, exclude_types, warehouse, item_search)
        columns = {
            'date': '일시',
            'item_code': '품목코드',
            'item_name': '품목명',
            'warehouse': '창고',
            'in_qty': '입고수량',
            'out_qty': '출고수량',
            'balance_qty': '잔량',
            'stock_entry_type_kr': '유형',
            'voucher_no': '전표번호'
        }
        filename = f'재고원장_{from_date}_{to_date}.xlsx'

    df = pd.DataFrame(data)
    if not df.empty:
        df = df[[col for col in columns.keys() if col in df.columns]]
        df = df.rename(columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='데이터')

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{__import__('urllib.parse', fromlist=['quote']).quote(filename)}"}
    )


@stock_bp.route('/api/entry-types')
def api_entry_types():
    """Stock Entry Type 목록 API"""
    types = get_stock_entry_types()
    return jsonify(types)


@stock_bp.route('/api/warehouses')
def api_warehouses():
    """창고 목록 API"""
    warehouses = get_warehouses()
    return jsonify(warehouses)


@stock_bp.route('/api/items')
def api_items():
    """품목 목록 API (자동완성용)"""
    items = get_items()
    return jsonify(items)


@stock_bp.route('/api/export-current-stock')
def api_export_current_stock():
    """현재 재고 엑셀 내보내기"""
    warehouse = request.args.get('warehouse', None)

    data = get_current_stock(warehouse)

    columns = {
        'item_code': '품목코드',
        'item_name': '품목명',
        'warehouse': '창고',
        'current_qty': '현재재고',
        'valuation_rate': '단가',
        'stock_value': '재고금액'
    }

    wh_name = warehouse.split(' - ')[0] if warehouse else '전체'
    filename = f'현재재고_{wh_name}_{datetime.now().strftime("%Y%m%d")}.xlsx'

    df = pd.DataFrame(data)
    if not df.empty:
        df = df[[col for col in columns.keys() if col in df.columns]]
        df = df.rename(columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='현재재고')

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{__import__('urllib.parse', fromlist=['quote']).quote(filename)}"}
    )


@stock_bp.route('/api/search-items')
def api_search_items():
    """품목 검색 API (자동완성)"""
    query = request.args.get('q', '').strip()
    if len(query) < 2:
        return jsonify([])

    items = get_items()
    # 검색어로 필터링
    results = [
        item for item in items
        if query.lower() in item['name'].lower() or query.lower() in item['item_name'].lower()
    ][:10]  # 최대 10개

    return jsonify(results)


# ============== 데모 데이터 API (테스트용) ==============
@stock_bp.route('/demo')
def demo_index():
    """데모 모드 - 더미 데이터로 UI 시연 (v2)"""
    from .demo_data import SAMPLE_WAREHOUSES, ENTRY_TYPES

    default_from = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    default_to = datetime.now().strftime('%Y-%m-%d')

    # 데모용 데이터
    entry_types = {et["type"]: et["type_kr"] for et in ENTRY_TYPES}
    warehouses = [{"name": w["name"], "warehouse_name": w["short"]} for w in SAMPLE_WAREHOUSES]

    return render_template(
        'stock/stock_ledger_v2.html',
        entry_types=entry_types,
        warehouses=warehouses,
        default_from=default_from,
        default_to=default_to,
        default_exclude=[],
        stock_entry_types=entry_types,
        demo_mode=True
    )


@stock_bp.route('/api/demo/stock-ledger')
def api_demo_stock_ledger():
    """데모 재고 원장 데이터"""
    from .demo_data import generate_demo_ledger

    from_date = request.args.get('from_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.args.get('to_date', datetime.now().strftime('%Y-%m-%d'))
    exclude_types = request.args.getlist('exclude_types')
    item_search = request.args.get('item_search', '').strip().lower()

    data = generate_demo_ledger(from_date, to_date, count=150)

    # exclude_types로 필터링
    if exclude_types:
        data = [row for row in data if row.get('stock_entry_type') not in exclude_types]

    # item_search로 필터링
    if item_search:
        data = [row for row in data if
                item_search in row.get('item_code', '').lower() or
                item_search in row.get('item_name', '').lower()]

    for row in data:
        if row.get('date'):
            row['date'] = row['date'].strftime('%Y-%m-%d %H:%M:%S')

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/demo/stock-summary')
def api_demo_stock_summary():
    """데모 품목별 요약 데이터"""
    from .demo_data import generate_demo_summary

    from_date = request.args.get('from_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.args.get('to_date', datetime.now().strftime('%Y-%m-%d'))

    data = generate_demo_summary(from_date, to_date)

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/demo/current-stock')
def api_demo_current_stock():
    """데모 현재 재고 현황"""
    from .demo_data import generate_demo_current_stock

    data = generate_demo_current_stock()

    return jsonify({
        'data': data,
        'count': len(data)
    })


@stock_bp.route('/api/demo/monthly-trend')
def api_demo_monthly_trend():
    """데모 월별 트렌드"""
    from .demo_data import generate_monthly_trend

    item_code = request.args.get('item_code', 'FP-LED-001')
    months = int(request.args.get('months', 6))

    data = generate_monthly_trend(item_code, months)

    return jsonify({
        'data': data,
        'item_code': item_code
    })


@stock_bp.route('/api/demo/items')
def api_demo_items():
    """데모 품목 목록"""
    from .demo_data import SAMPLE_ITEMS

    return jsonify([
        {'name': item['code'], 'item_name': item['name']}
        for item in SAMPLE_ITEMS
    ])


@stock_bp.route('/api/demo/search-items')
def api_demo_search_items():
    """데모 품목 검색"""
    from .demo_data import SAMPLE_ITEMS

    query = request.args.get('q', '').strip().lower()
    if len(query) < 2:
        return jsonify([])

    results = [
        {'name': item['code'], 'item_name': item['name']}
        for item in SAMPLE_ITEMS
        if query in item['code'].lower() or query in item['name'].lower()
    ][:10]

    return jsonify(results)


@stock_bp.route('/api/demo/export-excel')
def api_demo_export_excel():
    """데모 Excel 내보내기"""
    from .demo_data import generate_demo_ledger

    from_date = request.args.get('from_date', (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d'))
    to_date = request.args.get('to_date', datetime.now().strftime('%Y-%m-%d'))
    exclude_types = request.args.getlist('exclude_types')
    item_search = request.args.get('item_search', '').strip().lower()
    export_type = request.args.get('type', 'ledger')

    # 데모 데이터 생성
    data = generate_demo_ledger(from_date, to_date, count=150)

    # 필터 적용
    if exclude_types:
        data = [row for row in data if row.get('stock_entry_type') not in exclude_types]

    if item_search:
        data = [row for row in data if
                item_search in row.get('item_code', '').lower() or
                item_search in row.get('item_name', '').lower()]

    # 날짜 형식 변환
    for row in data:
        if row.get('date'):
            row['date'] = row['date'].strftime('%Y-%m-%d %H:%M:%S')

    if export_type == 'summary':
        # 요약 데이터 생성
        item_map = {}
        for row in data:
            item_code = row.get('item_code')
            if item_code not in item_map:
                item_map[item_code] = {
                    'item_code': item_code,
                    'item_name': row.get('item_name', ''),
                    'total_in': 0,
                    'total_out': 0,
                    'transaction_count': 0
                }
            item_map[item_code]['total_in'] += row.get('in_qty', 0)
            item_map[item_code]['total_out'] += row.get('out_qty', 0)
            item_map[item_code]['transaction_count'] += 1

        data = list(item_map.values())
        columns = {
            'item_code': '품목코드',
            'item_name': '품목명',
            'total_in': '총입고',
            'total_out': '총출고',
            'transaction_count': '거래건수'
        }
        filename = f'재고요약_데모_{from_date}_{to_date}.xlsx'
    else:
        columns = {
            'date': '일시',
            'item_code': '품목코드',
            'item_name': '품목명',
            'warehouse': '창고',
            'in_qty': '입고수량',
            'out_qty': '출고수량',
            'balance_qty': '잔량',
            'stock_entry_type_kr': '유형',
            'voucher_no': '전표번호'
        }
        filename = f'재고원장_데모_{from_date}_{to_date}.xlsx'

    df = pd.DataFrame(data)
    if not df.empty:
        df = df[[col for col in columns.keys() if col in df.columns]]
        df = df.rename(columns=columns)

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='데이터')

    output.seek(0)

    return Response(
        output.getvalue(),
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        headers={'Content-Disposition': f"attachment; filename*=UTF-8''{__import__('urllib.parse', fromlist=['quote']).quote(filename)}"}
    )
