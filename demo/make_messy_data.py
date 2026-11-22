#!/usr/bin/env python3
"""Generate a deliberately horrible workbook + cp949 CSV with a known ground truth.

Writes input/하루커피_매출정리_최종_진짜최종.xlsx, input/반품교환_3PL.csv and ground_truth.json.
Truth tables come first; every mess is planted on purpose and registered as an issue
with the outcome a correct cleaner must reach (fix / flag / drop / suspect ...).
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
INP = HERE / "input"
D = dt.date

PRODUCTS = [  # code, name, category, price, launch
    ("P001", "하우스블렌드 원두 200g", "원두", 12000, D(2023, 3, 1)),
    ("P002", "에티오피아 예가체프 200g", "원두", 15000, D(2023, 3, 1)),
    ("P003", "콜롬비아 수프리모 1kg", "원두", 45000, D(2023, 5, 10)),
    ("P004", "드립백 10입 세트", "드립백", 13500, D(2023, 6, 1)),
    ("P005", "콜드브루 원액 500ml", "콜드브루", 18000, D(2023, 7, 1)),
    ("P006", "디카페인 콜드브루 500ml", "콜드브루", 19500, D(2023, 9, 15)),
    ("P007", "하루 머그컵", "굿즈", 9000, D(2023, 10, 1)),
    ("P008", "텀블러 473ml", "굿즈", 25000, D(2023, 11, 20)),
]
DISCONTINUED = [("P009", "시즌 블렌드 200g", "원두", 13000, D(2023, 12, 31)),
                ("P010", "드립백 5입", "드립백", 7000, D(2024, 1, 15))]
CUSTOMERS = [  # id, name, region, phone, email, join, grade
    ("C0001", "김민수", "서울", "010-1111-2222", "minsu.kim@naver.com", D(2023, 1, 15), "VIP"),
    ("C0002", "이수진", "서울", "010-2222-3333", "sujin@gmail.com", D(2023, 2, 3), "일반"),
    ("C0003", "박지훈", "서울", "010-3333-4444", "jihoon.park@daum.net", D(2023, 3, 12), "일반"),
    ("C0004", "최유리", "경기", "010-4444-5555", "yuri.choi@naver.com", D(2023, 4, 1), "VIP"),
    ("C0005", "정다은", "경기", "010-5555-6666", "daeun@kakao.com", D(2023, 5, 20), "신규"),
    ("C0006", "강호동", "경기", "010-6666-7777", "hodong@naver.com", D(2023, 6, 11), "일반"),
    ("C0007", "최유진", "부산", "010-7777-8888", "yujin.choi@gmail.com", D(2023, 7, 7), "일반"),
    ("C0008", "윤서연", "부산", "010-8888-9999", "seoyeon@naver.com", D(2023, 8, 8), "신규"),
    ("C0009", "김민수", "부산", "010-9999-0000", "kms1990@gmail.com", D(2023, 9, 9), "일반"),
    ("C0016", "최 유진", "부산", "010-7777-8888", "yujin.choi@gmail.com", D(2024, 2, 1), "일반"),
    ("C0010", "한지민", "인천", "010-1212-3434", "jimin@daum.net", D(2023, 10, 10), "VIP"),
    ("C0011", "오세훈", "인천", "010-5656-7878", "sehoon@naver.com", D(2023, 11, 11), "일반"),
    ("C0012", "서지수", "대구", "010-9090-1212", "jisu@gmail.com", D(2023, 12, 1), "신규"),
    ("C0013", "임재범", "대구", "010-3434-5656", "jaebum@naver.com", D(2024, 1, 5), "일반"),
    ("C0014", "송하늘", "제주", "010-7878-9090", "haneul@kakao.com", D(2024, 1, 20), "신규"),
    ("C0015", "배수지", "제주", "010-2468-1357", "suzy@naver.com", D(2024, 2, 14), "VIP"),
]
CUST = {c[0]: c for c in CUSTOMERS}
PROD = {p[0]: p for p in PRODUCTS + DISCONTINUED}

# 36 orders: (date, customer, product, qty, discount, payment, status)
ORDER_SPEC = [
    (D(2024, 1, 3), "C0001", "P001", 2, 10, "카드", "배송완료"), (D(2024, 1, 5), "C0002", "P009", 1, None, "계좌이체", "배송완료"),
    (D(2024, 1, 7), "C0003", "P005", 1, 0, "네이버페이", "배송완료"), (D(2024, 1, 7), "C0004", "P002", 2, 5, "카드", "배송완료"),
    (D(2024, 1, 9), "C0005", "P004", 1, None, "카카오페이", "배송완료"), (D(2024, 1, 12), "C0006", "P005", 2, 10, "카드", "반품"),
    (D(2024, 1, 15), "C0007", "P004", 1, None, "네이버페이", "반품"), (D(2024, 1, 16), "C0008", "P003", 1, 0, "카드", "배송완료"),
    (D(2024, 1, 18), "C0003", "P007", 2, None, "카드", "배송완료"), (D(2024, 1, 20), "C0005", "P008", 1, 5, "계좌이체", "취소"),
    (D(2024, 1, 24), "C0010", "P006", 2, 10, "카카오페이", "배송완료"), (D(2024, 1, 29), "C0011", "P001", 3, None, "카드", "배송완료"),
    (D(2024, 2, 1), "C0012", "P002", 1, 0, "네이버페이", "배송완료"), (D(2024, 2, 3), "C0013", "P005", 2, 10, "카드", "배송완료"),
    (D(2024, 2, 3), "C0014", "P004", 1, None, "카카오페이", "배송완료"), (D(2024, 2, 6), "C0015", "P008", 1, 5, "카드", "배송완료"),
    (D(2024, 2, 8), "C0003", "P001", 1, None, "계좌이체", "배송완료"), (D(2024, 2, 9), "C0001", "P007", 2, 0, "카드", "배송완료"),
    (D(2024, 2, 13), "C0002", "P006", 1, 10, "네이버페이", "배송완료"), (D(2024, 2, 20), "C0004", "P003", 1, None, "카드", "배송중"),
    (D(2024, 2, 22), "C0009", "P002", 2, 5, "카카오페이", "반품"), (D(2024, 2, 24), "C0010", "P005", 1, None, "카드", "배송완료"),
    (D(2024, 2, 27), "C0011", "P004", 3, 10, "카드", "배송완료"), (D(2024, 2, 29), "C0012", "P001", 1, None, "계좌이체", "배송완료"),
    (D(2024, 3, 2), "C0013", "P005", 1, 0, "카드", "배송완료"), (D(2024, 3, 5), "C0014", "P006", 2, None, "네이버페이", "배송완료"),
    (D(2024, 3, 5), "C0015", "P007", 1, 5, "카드", "배송완료"), (D(2024, 3, 8), "C0001", "P004", 1, None, "카카오페이", "배송완료"),
    (D(2024, 3, 11), "C0002", "P008", 2, 10, "카드", "배송완료"), (D(2024, 3, 14), "C0099", "P001", 1, None, "카드", "배송완료"),
    (D(2024, 3, 18), "C0006", "P003", 1, None, "계좌이체", "배송완료"), (D(2024, 3, 18), "C0006", "P003", 1, None, "계좌이체", "배송완료"),
    (D(2024, 3, 21), "C0007", "P002", 1, 5, "카드", "배송완료"), (D(2024, 3, 25), "C0008", "P005", 2, None, "네이버페이", "배송중"),
    (D(2024, 3, 27), "C0014", "P001", 2, 10, "카드", "배송완료"), (D(2024, 3, 29), "C0015", "P006", 1, None, "카카오페이", "배송완료"),
]


def orders_truth() -> list[dict]:
    out = []
    for i, (d, c, p, q, disc, pay, st) in enumerate(ORDER_SPEC, start=1):
        price = PROD[p][3]
        out.append({"order_id": f"O-2024-{i:04d}", "order_date": d, "customer_id": c,
                    "customer_name": CUST[c][1] if c in CUST else "문지호", "product_code": p, "product_name": PROD[p][1],
                    "qty": q, "unit_price": price, "discount_pct": disc,
                    "amount": round(q * price * (1 - (disc or 0) / 100)), "payment": pay, "status": st})
    return out


ISSUES: list[dict] = []


def issue(table, cat, row, col, expect, truth=None, note=""):
    ISSUES.append({"id": f"{table[:3]}-{len(ISSUES) + 1:03d}", "table": table, "category": cat, "row": row, "column": col,
                   "expect": expect, "truth": truth.isoformat() if isinstance(truth, dt.date) else truth, "note": note})


def fw(s: str) -> str:
    """half-width -> full-width"""
    return "".join(chr(ord(ch) + 0xFEE0) if "!" <= ch <= "~" else ch for ch in s)


def mojibake(s: str) -> str:
    return s.encode("utf-8").decode("cp1252", errors="replace") if False else "".join(
        bytes([b]).decode("cp1252") if b not in (0x81, 0x8D, 0x8F, 0x90, 0x9D) else chr(b) for b in s.encode("utf-8"))


def serial(d: dt.date) -> int:
    return (d - D(1899, 12, 30)).days


# ------------------------------------------------------------------ orders sheet
def build_orders(ws):
    T = orders_truth()
    truth_rows: dict[int, dict] = {}
    ws["A1"] = "하루커피 2024년 1분기 주문내역 (내부용)"
    ws.merge_cells("A1:M1")
    ws["A2"] = "작성: 김대리 / 최종수정 2024.04.02  ※ 함부로 수정 금지!!"
    parents = ["주문번호", "주문일자", "고객", None, "상품", None, None, "금액", None, None, "결제수단", "상태", "비고"]
    children = [None, None, "ID", "이름", "코드", "상품명", "수량", "단가", "할인율", "결제금액", None, None, None]
    for c, v in enumerate(parents, start=1):
        if v:
            ws.cell(4, c, v)
    for c, v in enumerate(children, start=1):
        if v:
            ws.cell(5, c, v)
    for rng in ("A4:A5", "B4:B5", "C4:D4", "E4:G4", "H4:J4", "K4:K5", "L4:L5", "M4:M5"):
        ws.merge_cells(rng)
    for r in (1, 2, 4):
        issue("orders", "structure", r, None, "drop", note="title/caption or header row")

    date_fmt = [lambda d: dt.datetime(d.year, d.month, d.day), serial, lambda d: f"{d.year}.{d.month}.{d.day}",
                lambda d: f"{d:%y/%m/%d}", lambda d: f"{d.month}월 {d.day}일", lambda d: f"{d:%Y%m%d}",
                lambda d: f"{d.year}년 {d.month}월 {d.day}일", lambda d: f"{d:%Y-%m-%d} ", lambda d: fw(f"{d.year}.{d.month}.{d.day}"),
                lambda d: f"{d.year}/{d.month}/{d.day}"]
    pay_variants = {"카드": ["카드", "신용카드", "card", "CARD", "카느", "카드결제"], "계좌이체": ["계좌이체", "무통장입금", "계좌 이체"],
                    "네이버페이": ["네이버페이", "N페이", "naverpay", "네이버 페이", "네이벼페이"], "카카오페이": ["카카오페이", "kakaopay", "카카오 페이", "카카오패이"]}
    status_variants = {"배송완료": ["배송완료", "배송 완료", "완료", "배송완ㄹ", "Delivered", "배송완료 "], "배송중": ["배송중", "배송 중"],
                       "취소": ["주문취소"], "반품": ["반품", "반품접수"]}
    price_fmt = [lambda p: f"₩{p:,}", lambda p: f"{p}원", lambda p: p, lambda p: f"{p:,}", lambda p: f"{p / 10000:g}만원" if p % 1000 == 0 and p % 10000 else f"{p:,}원",
                 lambda p: f"{p / 1000:g}천원", lambda p: f"{p:,} 원"]
    amt_fmt = [lambda a: a, lambda a: f"₩{a:,}", lambda a: f"{a:,}원", lambda a: f"{a:,}", lambda a: str(a)]
    disc_fmt = {None: ["", "-", "N/A", "없음"], 0: [0], 5: ["5%", 5], 10: ["10%", 10, "10 %"]}
    cid_fmt = lambda c, i: [c, c.lower().replace("c00", "c-").replace("c-0", "c-"), c[0] + " " + c[1:], c[1:], fw(c), c.lower() + " "][i % 6]  # noqa: E731
    pcode_fmt = lambda p, i: [p, p.lower().replace("p0", "p-"), fw(p), p][i % 4]  # noqa: E731
    name_variants = {"P005": ["콜드브루원액500ml", "콜드브루 원액 500 ml"], "P002": ["에티오피아 예가채프 200g"],
                     "P004": ["드립백10입세트"], "P001": ["하우스 블렌드 원두200g"]}

    cnt = {"pay": 0, "st": 0}

    def render(o: dict, i: int) -> list:
        nonlocal cnt
        d = o["order_date"]
        pv = pay_variants[o["payment"]]
        sv = status_variants[o["status"]]
        cnt["pay"] += 1
        cnt["st"] += 1
        names = name_variants.get(o["product_code"], [o["product_name"]])
        return [o["order_id"], date_fmt[i % len(date_fmt)](d), cid_fmt(o["customer_id"], i), o["customer_name"],
                pcode_fmt(o["product_code"], i), names[i % len(names)] if i % 2 else o["product_name"],
                [o["qty"], fw(str(o["qty"])), f"{o['qty']}개", f"{o['qty']} EA"][i % 4], price_fmt[i % len(price_fmt)](o["unit_price"]),
                disc_fmt[o["discount_pct"]][i % len(disc_fmt[o["discount_pct"]])], amt_fmt[i % len(amt_fmt)](o["amount"]),
                pv[cnt["pay"] % len(pv)], sv[cnt["st"] % len(sv)], ["", "포장 꼼꼼히  부탁드려요", "", "N/A", "문 앞에 놔주세요 "][i % 5]]

    rows_out: list[tuple[str, list, dict | None]] = []   # (kind, cells, truth)
    month_sum = {1: 0, 2: 0, 3: 0}
    for i, o in enumerate(T, start=1):
        cells = render(o, i)
        # ---- targeted plants (per order number)
        if i == 2:
            cells[4] = "P009"
        if i == 3:
            cells[1] = dt.datetime(2024, 1, 7)
        if i == 6:
            cells[4] = None
            o["product_code"] = None
            cells[5] = "콜드브루원액500ml"
        if i == 9:
            cells[3] = mojibake(o["customer_name"])
        if i == 11:
            cells[3] = "\u200b" + o["customer_name"]
        if i == 14:
            cells[8] = "0.1"
        if i == 15:
            cells[1] = "03/02/2024"
        if i == 16:
            cells[6] = "두개" if o["qty"] == 2 else "한개"
        if i == 17:
            cells[3] = CUST["C0004"][1]
        if i == 18:
            cells[6] = "two" if o["qty"] == 2 else "one"
        if i == 20:
            cells[1] = "2024-02-30"
        if i == 22:
            cells[4] = None
            o["product_code"] = None
            cells[5] = "콜드브루 원액 500 ml"
        if i == 23:
            cells[9] = "#N/A"
        if i == 26:
            cells[2] = "K0014"
        if i == 28:
            cells[9] = f"{o['amount'] * 10:,}원"
        if i == 34:
            cells[5] = "콜브 원액"
        rows_out.append(("data", cells, o))
        month_sum[o["order_date"].month] += o["amount"] * (10 if i == 28 else 1)
        if i == 5:   # verbatim copy-paste duplicate
            rows_out.append(("dup_exact", list(cells), o))
            month_sum[1] += o["amount"]
        if i == 10:   # amended re-entry with the same order id later (key conflict) -> placed in Feb
            pass
        if i == 25:   # same order written differently: normalizes to an identical row
            c2 = list(cells)
            c2[1] = serial(o["order_date"]) if not isinstance(cells[1], int) else f"{o['order_date']:%Y-%m-%d}"
            c2[7] = f"₩{o['unit_price']:,}" if not str(cells[7]).startswith("₩") else o["unit_price"]
            c2[9] = o["amount"] if isinstance(cells[9], str) else f"{o['amount']:,}원"
            c2[10] = "card"
            c2[2] = o["customer_id"].lower()
            rows_out.append(("dup_norm", c2, o))
            month_sum[3] += o["amount"]
        if i == 12:
            rows_out.append(("subtotal", ["1월 소계", None, None, None, None, None, None, None, None, month_sum[1]], None))
            rows_out.append(("rep_header", ["주문번호", "주문일자", "ID", "이름", "코드", "상품명", "수량", "단가", "할인율", "결제금액", "결제수단", "상태", "비고"], None))
            rows_out.append(("note", ["※ 2월분은 POS에서 복붙함 (형식 다를 수 있음)"], None))
        if i == 13:
            o10 = dict(T[9])
            c10 = render(o10, 10)
            c10[6] = 3
            c10[9] = f"{round(3 * o10['unit_price'] * 0.95):,}원"
            rows_out.append(("key_conflict", c10, None))
            month_sum[2] += round(3 * o10["unit_price"] * 0.95)
        if i == 24:
            rows_out.append(("subtotal", ["2월 소계", None, None, None, None, None, None, None, None, month_sum[2]], None))
        if i == 36:
            rows_out.append(("subtotal", ["3월 소계", None, None, None, None, None, None, None, None, month_sum[3]], None))
            rows_out.append(("blank", [], None))
            rows_out.append(("grand", ["합계", None, None, None, None, None, None, None, None, sum(month_sum.values())], None))
            rows_out.append(("blank", [], None))
            rows_out.append(("note", ["※ 금액은 부가세 포함"], None))

    r = 6
    order_row: dict[str, int] = {}
    for kind, cells, o in rows_out:
        n = int(o["order_id"][-4:]) if o else None
        if kind == "data" and n == 19:        # shifted right: an empty cell got inserted at C
            cells = cells[:2] + [None] + cells[2:]
        if kind == "data" and n == 33:        # shifted left: the date cell was deleted
            cells = cells[:1] + cells[2:] + [None]
        for c, v in enumerate(cells, start=1):
            if v is not None and v != "":
                ws.cell(r, c, v)
                if isinstance(v, dt.datetime):
                    ws.cell(r, c).number_format = "yyyy-mm-dd"
        if kind == "data":
            truth_rows[r] = o
            order_row[o["order_id"]] = r
        elif kind in ("dup_exact", "dup_norm"):
            issue("orders", "duplicate", r, None, "dup_drop", note=f"{'verbatim copy' if kind == 'dup_exact' else 'same order, different formatting'} of {o['order_id']}")
        elif kind == "subtotal" or kind == "grand":
            issue("orders", "structure", r, None, "drop", note=f"{cells[0]} row")
            issue("orders", "reconcile", r, "amount", "reconcile", note=f"{cells[0]} stated {cells[9]}")
        elif kind == "rep_header":
            issue("orders", "structure", r, None, "drop", note="repeated header mid-sheet")
        elif kind == "note":
            issue("orders", "structure", r, None, "drop", note="note row")
        elif kind == "key_conflict":
            issue("orders", "key_conflict", r, "order_id", "conflict", note="O-2024-0010 entered again with qty 3")
            order_row["conflict"] = r
        r += 1
    # merged date cells for same-day orders (vertical merge in data)
    for a, b in (("O-2024-0003", "O-2024-0004"), ("O-2024-0026", "O-2024-0027")):
        ra, rb = order_row[a], order_row[b]
        ws.cell(rb, 2).value = None
        ws.merge_cells(start_row=ra, start_column=2, end_row=rb, end_column=2)
        issue("orders", "merged_cell", rb, "order_date", "fix", truth_rows[rb]["order_date"], "date lives only in the merged range's top cell")

    # register cell-level plants by comparing written raw to truth
    rown = {o["order_id"]: rr for rr, o in truth_rows.items()}
    R = lambda oid: rown[oid]  # noqa: E731
    t = {o["order_id"]: o for o in T}
    for rr, o in truth_rows.items():
        for c, col in enumerate(["order_id", "order_date", "customer_id", "customer_name", "product_code", "product_name", "qty",
                                 "unit_price", "discount_pct", "amount", "payment", "status"], start=1):
            v = ws.cell(rr, c).value
            tv = o[col]
            if (v == tv or (isinstance(v, dt.datetime) and v.date() == tv) or (v is None and tv is None)) and not (isinstance(v, str) and v != v.strip()):
                continue
            if any(x["row"] == rr and x["column"] == col for x in ISSUES):
                continue
            if o["order_id"] in ("O-2024-0019", "O-2024-0033"):
                continue
            cat = {"order_date": "date_format", "customer_id": "id_format", "customer_name": "text", "product_code": "id_format",
                   "product_name": "name_typo", "qty": "number_text", "unit_price": "number_text", "discount_pct": "number_text",
                   "amount": "number_text", "payment": "category", "status": "category"}[col]
            if col == "discount_pct" and tv is None:
                cat = "blank_placeholder"
            expect, note = "fix", repr(v)
            special = {
                ("O-2024-0014", "discount_pct"): ("flag", "0.1 among 0-100 percents"),
                ("O-2024-0015", "order_date"): ("flag", "03/02/2024 ambiguous DMY/MDY"),
                ("O-2024-0017", "customer_name"): ("flag", "name of another customer (C0004) under C0003"),
                ("O-2024-0018", "qty"): ("flag", "English word number"),
                ("O-2024-0020", "order_date"): ("flag", "impossible date 2024-02-30"),
                ("O-2024-0023", "amount"): ("flag", "#N/A Excel error"),
                ("O-2024-0026", "customer_id"): ("flag", "wrong ID prefix K0014"),
                ("O-2024-0028", "amount"): ("flag", "amount x10 typo (qty*price mismatch)"),
                ("O-2024-0034", "product_name"): ("flag", "'콜브 원액' too far from any product name"),
            }
            if (o["order_id"], col) in special:
                expect, note = special[(o["order_id"], col)]
                cat = {"discount_pct": "number_scale", "order_date": "date_invalid", "customer_name": "cross_table", "qty": "number_text",
                       "amount": "cross_check", "customer_id": "id_invalid", "product_name": "name_typo"}[col]
                if o["order_id"] == "O-2024-0015":
                    cat = "date_ambiguous"
                if o["order_id"] == "O-2024-0023":
                    cat = "excel_error"
            if col == "customer_id" and tv == "C0099":
                continue
            issue("orders", cat, rr, col, expect, tv, note)
    for oid in ("O-2024-0019", "O-2024-0033"):
        rr = rown[oid]
        for col in ("customer_id", "product_code", "qty", "payment", "status"):
            issue("orders", "shifted_row", rr, col, "fix", t[oid][col], f"{oid} shifted {'right' if oid.endswith('19') else 'left'}")
    issue("orders", "shifted_row", rown["O-2024-0033"], "order_date", "flag", t["O-2024-0033"]["order_date"], "date cell deleted: must be flagged, not guessed")
    issue("orders", "join_orphan", rown["O-2024-0030"], "customer_id", "orphan", "C0099", "customer not in master")
    for oid in ("O-2024-0006", "O-2024-0022"):
        issue("orders", "join_fallback", rown[oid], "product_code", "join_fallback", "P005", "code blank, join by product name")
    issue("orders", "join_discontinued", rown["O-2024-0002"], "product_code", "join_in_other", "P009", "discontinued product")
    issue("orders", "near_duplicate", rown["O-2024-0031"], None, "suspect", [rown["O-2024-0031"], rown["O-2024-0032"]], "double submit: same customer/date/product/qty/amount, different order id")
    issue("orders", "trap", rown["O-2024-0009"], None, "no_suspect", [rown["O-2024-0003"], rown["O-2024-0017"]], "same customer different dates/products: not duplicates")
    issue("orders", "trap", rown["O-2024-0003"], "discount_pct", "keep", 0, "0 must stay 0, not blank")
    issue("orders", "key_conflict", rown["O-2024-0010"], "order_id", "conflict", None, "original row of O-2024-0010")
    return truth_rows, order_row


# ------------------------------------------------------------------ customers sheet
def build_customers(ws):
    ws["A1"] = "고객 명단 (2024.03 기준)"
    issue("customers", "structure", 1, None, "drop", note="title")
    hdr = ["고객번호", "이름", "지역", "연락처", "이메일", "가입일", "등급", "메모"]
    for c, v in enumerate(hdr, start=1):
        ws.cell(3, c, v)
    raw = {
        "C0001": ["C0001", "김민수", "서울특별시", "010-1111-2222", "MINSU.KIM@NAVER.COM ", dt.datetime(2023, 1, 15), "VIP", ""],
        "C0002": ["c-2", "이수진 ", None, "01022223333", "sujin@gmail", serial(D(2023, 2, 3)), "일반회원", "단골"],
        "C0003": ["C 0003", "박지훈", "서을", "010 3333 4444", "jihoon.park@@daum.net", "2023.3.12", "일반", None],
        "C0004": [4, "최유리", "경기도", "+82 10-4444-5555", "yuri.choi@naver.com", "23/04/01", "vip", "-"],
        "C0005": [fw("C0005"), "정다은", None, "010.5555.6666", "daeun@kakao.com", "2023년 5월 20일", "신규 회원", ""],
        "C0006": ["c0006 ", "강호동", "겅기", 1066667777, "hodong@naver.com", "20230611", "일반", "VIP 승급 검토"],
        "C0007": ["C0007", "최유진", "부산광역시", "010-7777-8888", "yujin.choi@gmail.com", "2023-07-07", "일 반", None],
        "C0008": ["C0008", "윤서연", None, "010-8888-9999", "seoyeon@naver.com", "2023/8/8", "신규", None],
        "C0009": ["C0009", "김민수", "busan", "010-9999-0000", "kms1990@gmail.com", "2023-13-01", "일반", "동명이인 주의"],
        "C0016": ["C0016", "최 유진", "부산", "01077778888", "YUJIN.CHOI@GMAIL.COM", "2024.2.1", "일반", "재가입?"],
        "C0010": ["C0010", "한지민", "인천시", "010-1212-3434", "jimin@daum.net", fw("2023.10.10"), "V.I.P", None],
        "C0011": ["C0011", "오세훈", "Incheon", "010-565-7878", "sehoon@naver.com", dt.datetime(2023, 11, 11), "일반", None],
        "C0012": ["C0012", "서지수", "대구 ", "01090901212", "jisu@gmail.com", "2023.12.1", "신규", None],
        "C0013": ["C0013", "임재범", "대구광역시", "010-3434-5656", "jaebum@naver.com", serial(D(2024, 1, 5)), "일반", None],
        "C0014": ["C0014", "송하늘", "제주도", "010–7878–9090", "haneul@kakao.com", "2024-01-20", "신규", None],
        "C0015": ["C0015", "배수지", "Jeju", "010-2468-1357", "suzy@naver.com", "2024.2.14", "VlP", None],
    }
    truth_rows = {}
    r = 4
    for cust in CUSTOMERS:
        cid = cust[0]
        cells = raw[cid]
        for c, v in enumerate(cells, start=1):
            if v is not None and v != "":
                ws.cell(r, c, v)
        truth_rows[r] = dict(zip(["customer_id", "name", "region", "phone", "email", "join_date", "grade"], cust))
        if cid == "C0005":
            r += 1
            for c, v in enumerate(cells, start=1):
                if v is not None and v != "":
                    ws.cell(r, c, v)
            issue("customers", "duplicate", r, None, "dup_drop", note="C0005 pasted twice")
        r += 1
    rown = {v["customer_id"]: k for k, v in truth_rows.items()}
    # merged region cells: 서울 group C0001-C0002, 경기 C0004-C0005(+dup row), 부산 C0007-C0008
    for a, b in (("C0001", "C0002"), ("C0004", "C0005"), ("C0007", "C0008")):
        ra, rb = rown[a], rown[b] + (1 if b == "C0005" else 0)
        ws.merge_cells(start_row=ra, start_column=3, end_row=rb, end_column=3)
        issue("customers", "merged_cell", rown[b], "region", "fix", truth_rows[rown[b]]["region"], "region only in merged top cell")
    flags = {("C0002", "email"): "email without domain", ("C0003", "email"): "double @", ("C0006", "phone"): "leading 0 lost (number cell)",
             ("C0011", "phone"): "too few digits", ("C0009", "join_date"): "impossible month 13", ("C0015", "grade"): "VlP (l for I)"}
    for cid, cells in raw.items():
        rr = rown[cid]
        tr = truth_rows[rr]
        for c, col in enumerate(["customer_id", "name", "region", "phone", "email", "join_date", "grade"]):
            v, tv = cells[c], tr[col]
            if v is None or v == tv or (isinstance(v, dt.datetime) and v.date() == tv):
                continue
            if (cid, col) in flags:
                issue("customers", "invalid", rr, col, "flag", tv, flags[(cid, col)])
                continue
            cat = {"customer_id": "id_format", "name": "text", "region": "category", "phone": "phone_format", "email": "email_case",
                   "join_date": "date_format", "grade": "category"}[col]
            issue("customers", cat, rr, col, "fix", tv, repr(v))
    issue("customers", "near_duplicate", rown["C0007"], None, "suspect", [rown["C0007"], rown["C0016"]], "same phone+email, different id and spacing in name")
    issue("customers", "trap", rown["C0001"], None, "no_suspect", [rown["C0001"], rown["C0009"]], "same name 김민수, different person")
    return truth_rows


# ------------------------------------------------------------------ products sheet
def build_products(ws):
    ws["A1"] = "■ 상품 마스터"
    issue("products", "structure", 1, None, "drop", note="title")
    for c, v in enumerate(["상품코드", "상품명", "분류", "판매가", "출시일"], start=1):
        ws.cell(2, c, v)
    raw = [["P001", "하우스블렌드 원두 200g", "원두", "12,000원", dt.datetime(2023, 3, 1)],
           ["p-2", "에티오피아 예가체프 200g", "원 두", 15000, "2023.3.1"],
           ["P003", "콜롬비아 수프리모 1kg", "원두", "45,000", serial(D(2023, 5, 10))],
           [fw("P004"), "드립백 10입 세트", "드립백", "13,500원", "2023-06-01"],
           ["P005", "콜드브루 원액 500ml", "콜드브류", "₩18,000", "2023년 7월 1일"],
           ["P006", "디카페인 콜드브루 500ml", "콜드 브루", "19,500", "20230915"],
           ["P007", "하루 머그컵", "Goods", "9천원", "2023.10.1"],
           ["P008", "텀블러 473ml ", "굿 즈", "2.5만원", "2023/11/20"]]
    truth = {}
    for i, (cells, p) in enumerate(zip(raw, PRODUCTS)):
        r = 3 + i
        for c, v in enumerate(cells, start=1):
            ws.cell(r, c, v)
        truth[r] = dict(zip(["product_code", "product_name", "category", "price", "launch_date"], p))
        for c, col in enumerate(["product_code", "product_name", "category", "price", "launch_date"]):
            v, tv = cells[c], p[c]
            if v == tv or (isinstance(v, dt.datetime) and v.date() == tv):
                continue
            cat = {"product_code": "id_format", "product_name": "text", "category": "category", "price": "number_text", "launch_date": "date_format"}[col]
            issue("products", cat, r, col, "fix", tv, repr(v))
    ws.cell(13, 1, "■ 단종 상품")
    for c, v in enumerate(["상품코드", "상품명", "분류", "판매가", "단종일"], start=1):
        ws.cell(14, c, v)
    draw = [["P009", "시즌 블렌드 200g", "원두", 13000, dt.datetime(2023, 12, 31)], ["P010", "드립백 5입", "드립백 ", "7,000원", "2024.01.15"]]
    dtruth = {}
    for i, (cells, p) in enumerate(zip(draw, DISCONTINUED)):
        r = 15 + i
        for c, v in enumerate(cells, start=1):
            ws.cell(r, c, v)
        dtruth[r] = dict(zip(["product_code", "product_name", "category", "price", "discontinued_date"], p))
    issue("discontinued_products", "multi_table", 14, None, "found", note="second table on the same sheet")
    issue("products", "structure", 13, None, "drop", note="title of the second table")
    issue("discontinued_products", "number_text", 16, "price", "fix", 7000, "'7,000원'")
    issue("discontinued_products", "category", 16, "category", "fix", "드립백", "trailing space")
    issue("discontinued_products", "date_format", 16, "discontinued_date", "fix", "2024-01-15", "'2024.01.15'")
    return truth, dtruth


# ------------------------------------------------------------------ returns csv (cp949)
def build_returns(order_rows):
    lines = ["3PL 반품/교환 내역 export (2024-04-01)",
             "반품번호,주문번호,접수일,사유,환불금액,처리상태",
             'R-001,O-2024-0007,15.01.2024,단순변심,"13.500,00",환불완료',
             'R-002,2024-0010,02.02.2024,파손,"9.000",환불완료',
             'r-3,o20240015,13.03.2024 ,오배송,"18.000,00",교환완료',
             'R-004,O-2024-0099,20.03.2024,단순변심,"45.000",처리중',
             'R-005,O-2024-0021,05.03.2024,파손 ,"6.750,00",환불 완료',
             'R-006,O-2024-0026,28.03.2024,부분환불,"12.000",환불완료']
    (INP / "반품교환_3PL.csv").write_bytes(("\r\n".join(lines) + "\r\n").encode("cp949"))
    truth = {3: ("R-001", "O-2024-0007", D(2024, 1, 15), "단순변심", 13500, "환불완료"),
             4: ("R-002", "O-2024-0010", D(2024, 2, 2), "파손", 9000, "환불완료"),
             5: ("R-003", "O-2024-0015", D(2024, 3, 13), "오배송", 18000, "교환완료"),
             6: ("R-004", "O-2024-0099", D(2024, 3, 20), "단순변심", 45000, "처리중"),
             7: ("R-005", "O-2024-0021", D(2024, 3, 5), "파손", 6750, "환불완료"),
             8: ("R-006", "O-2024-0026", D(2024, 3, 28), "부분환불", 12000, "환불완료")}
    cols = ["return_id", "order_id", "return_date", "reason", "refund", "status"]
    t = {r: dict(zip(cols, v)) for r, v in truth.items()}
    issue("returns", "encoding", 2, None, "encoding", "cp949", "file is cp949, not UTF-8")
    issue("returns", "structure", 1, None, "drop", note="export caption line")
    for r, (rid, oid, d, rs, amt, st) in truth.items():
        issue("returns", "decimal_comma", r, "refund", "fix", amt, "European number format")
        issue("returns", "date_format", r, "return_date", "fix", d, "DD.MM.YYYY (decided by 13.03 / 15.01 / 20.03)")
    for r in (4, 5):
        issue("returns", "id_format", r, "order_id", "fix", truth[r][1], "order id written differently")
    issue("returns", "id_format", 5, "return_id", "fix", "R-003", "'r-3'")
    issue("returns", "category", 7, "status", "fix", "환불완료", "'환불 완료'")
    issue("returns", "join_orphan", 6, "order_id", "orphan", "O-2024-0099", "order not in orders")
    issue("returns", "join_ambiguous", 4, "order_id", "ambiguous", "O-2024-0010", "O-2024-0010 has two conflicting rows in orders")
    return t


def main():
    INP.mkdir(exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "주문내역"
    orders_truth_rows, order_row = build_orders(ws)
    customers_truth = build_customers(wb.create_sheet("고객명단"))
    products_truth, disc_truth = build_products(wb.create_sheet("상품"))
    wb.properties.created = wb.properties.modified = dt.datetime(2024, 4, 2)
    wb.save(INP / "하루커피_매출정리_최종_진짜최종.xlsx")
    returns_truth = build_returns(order_row)

    def ser(rows):
        return {str(r): {k: (v.isoformat() if isinstance(v, dt.date) else v) for k, v in rec.items()} for r, rec in rows.items()}
    gt = {"tables": {"orders": ser(orders_truth_rows), "customers": ser(customers_truth), "products": ser(products_truth),
                     "discontinued_products": ser(disc_truth), "returns": ser(returns_truth)},
          "issues": ISSUES}
    (HERE / "ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    from collections import Counter
    print(f"planted {len(ISSUES)} issues:", dict(Counter(i["category"] for i in ISSUES)))


if __name__ == "__main__":
    main()
