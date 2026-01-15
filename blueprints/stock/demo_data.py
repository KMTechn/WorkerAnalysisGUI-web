# -*- coding: utf-8 -*-
"""
재고 원장 더미 데이터 생성기
실제 데이터 없이도 UI 시연 가능
"""
from datetime import datetime, timedelta
import random

# 샘플 품목 데이터
SAMPLE_ITEMS = [
    {"code": "FP-LED-001", "name": "LED Driver IC 3.3V"},
    {"code": "FP-LED-002", "name": "LED Driver IC 5V"},
    {"code": "FP-PWR-001", "name": "Power Management IC"},
    {"code": "FP-PWR-002", "name": "DC-DC Converter IC"},
    {"code": "SID-TFT-7", "name": "7인치 TFT-LCD 패널"},
    {"code": "SID-TFT-10", "name": "10.1인치 TFT-LCD 패널"},
    {"code": "SID-OLED-5", "name": "5.5인치 AMOLED 패널"},
    {"code": "JT-CASE-NB15", "name": "15인치 노트북 케이싱"},
    {"code": "JT-CASE-NB14", "name": "14인치 노트북 케이싱"},
    {"code": "JT-CASE-TB10", "name": "10인치 태블릿 케이싱"},
    {"code": "TRULY-LCD-43", "name": "4.3인치 LCD 모듈"},
    {"code": "TRULY-LCD-50", "name": "5.0인치 LCD 모듈"},
]

SAMPLE_WAREHOUSES = [
    {"name": "본사 창고 - KMTech", "short": "본사"},
    {"name": "반제품 창고 - KMTech", "short": "반제품"},
    {"name": "완제품 창고 - KMTech", "short": "완제품"},
    {"name": "불량 창고 - KMTech", "short": "불량"},
]

ENTRY_TYPES = [
    {"type": "Material Receipt", "type_kr": "입고", "is_in": True},
    {"type": "Material Issue", "type_kr": "출고", "is_in": False},
    {"type": "Stock Delivery", "type_kr": "출고배송", "is_in": False},
    {"type": "Material Transfer", "type_kr": "창고이동", "is_in": None},
    {"type": "Manufacture", "type_kr": "제조", "is_in": True},
    {"type": "공급처반품", "type_kr": "공급처반품", "is_in": False},
]


def generate_demo_ledger(from_date, to_date, count=100):
    """더미 재고 원장 데이터 생성"""
    data = []

    start = datetime.strptime(from_date, '%Y-%m-%d')
    end = datetime.strptime(to_date, '%Y-%m-%d')
    date_range = (end - start).days

    # 품목별 현재 잔량 추적
    balances = {item["code"]: random.randint(100, 1000) for item in SAMPLE_ITEMS}

    for i in range(count):
        item = random.choice(SAMPLE_ITEMS)
        warehouse = random.choice(SAMPLE_WAREHOUSES)
        entry_type = random.choice(ENTRY_TYPES)

        # 랜덤 날짜 생성
        random_days = random.randint(0, max(1, date_range))
        random_hours = random.randint(8, 18)
        random_minutes = random.randint(0, 59)
        date = start + timedelta(days=random_days, hours=random_hours, minutes=random_minutes)

        # 수량 결정
        qty = random.randint(10, 200) * 10

        if entry_type["is_in"] is True:
            in_qty = qty
            out_qty = 0
            balances[item["code"]] += qty
        elif entry_type["is_in"] is False:
            in_qty = 0
            out_qty = min(qty, balances[item["code"]])  # 잔량보다 많이 출고 불가
            balances[item["code"]] -= out_qty
        else:  # 이동
            in_qty = qty
            out_qty = qty

        data.append({
            "date": date,
            "item_code": item["code"],
            "item_name": item["name"],
            "base_item_code": item["code"],
            "warehouse": warehouse["name"],
            "in_qty": in_qty if in_qty > 0 else 0,
            "out_qty": out_qty if out_qty > 0 else 0,
            "balance_qty": balances[item["code"]],
            "valuation_rate": random.randint(1000, 50000),
            "stock_value": balances[item["code"]] * random.randint(1000, 50000),
            "voucher_type": "Stock Entry",
            "voucher_no": f"SE-2026-{random.randint(10000, 99999):05d}",
            "stock_entry_type": entry_type["type"],
            "stock_entry_type_kr": entry_type["type_kr"],
        })

    # 날짜순 정렬 (최신순)
    data.sort(key=lambda x: x["date"], reverse=True)
    return data


def generate_demo_summary(from_date, to_date):
    """더미 품목별 요약 데이터 생성"""
    data = []

    for item in SAMPLE_ITEMS:
        total_in = random.randint(500, 5000)
        total_out = random.randint(300, total_in)

        data.append({
            "item_code": item["code"],
            "item_name": item["name"],
            "total_in": total_in,
            "total_out": total_out,
            "transaction_count": random.randint(10, 100),
        })

    # 입고량 기준 정렬
    data.sort(key=lambda x: x["total_in"], reverse=True)
    return data


def generate_demo_current_stock():
    """더미 현재 재고 현황 생성"""
    data = []

    for item in SAMPLE_ITEMS:
        for warehouse in SAMPLE_WAREHOUSES:
            if random.random() > 0.3:  # 70% 확률로 해당 창고에 재고 있음
                qty = random.randint(50, 2000)
                rate = random.randint(1000, 50000)
                data.append({
                    "item_code": item["code"],
                    "item_name": item["name"],
                    "warehouse": warehouse["name"],
                    "current_qty": qty,
                    "valuation_rate": rate,
                    "stock_value": qty * rate,
                })

    return data


def generate_monthly_trend(item_code, months=6):
    """특정 품목의 월별 입출고 트렌드 생성"""
    data = []
    today = datetime.now()

    for i in range(months, 0, -1):
        month_date = today - timedelta(days=i*30)
        month_str = month_date.strftime('%Y-%m')

        total_in = random.randint(500, 3000)
        total_out = random.randint(400, total_in)

        data.append({
            "month": month_str,
            "total_in": total_in,
            "total_out": total_out,
            "net_change": total_in - total_out,
            "transaction_count": random.randint(20, 80),
        })

    return data
