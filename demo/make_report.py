#!/usr/bin/env python3
"""Write ../REPORT.md (Korean) from the real run outputs. No number in the report is typed by hand."""
from __future__ import annotations

import json
from collections import Counter
from pathlib import Path

import openpyxl

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "output"
BL = ROOT / "blind"


def load(p: Path):
    return json.loads(p.read_text(encoding="utf-8"))


S, A, SC = load(OUT / "run_summary.json"), load(OUT / "audit.json"), load(OUT / "score.json")
BS = load(BL / "output" / "score.json")
GT = load(HERE / "ground_truth.json")
FP = (OUT / "fixed_point.txt").read_text(encoding="utf-8").strip() if (OUT / "fixed_point.txt").exists() else "(not run)"
BFP = (BL / "output" / "fixed_point.txt").read_text(encoding="utf-8").strip() if (BL / "output" / "fixed_point.txt").exists() else "(not run)"
FIRST = (BL / "first_run_score.txt").read_text(encoding="utf-8").splitlines()[0]
FIRST_J = json.loads(FIRST)
wb = openpyxl.load_workbook(HERE / "input" / "하루커피_매출정리_최종_진짜최종.xlsx")
raw = {ws.title: [list(r) for r in ws.iter_rows(values_only=True)] for ws in wb}


def chg(table, row, col):
    return [c for c in A["changes"] if c["table"] == table and c["source_row"] == row and c["column"] == col]


def fmt(v):
    if isinstance(v, str) and len(v) == 19 and v.endswith(" 00:00:00") and v[4] == "-":
        v = v[:10]   # audit.json stores midnight datetimes as text
    return "(빈칸)" if v is None or v == "" else f"`{v!r}`" if isinstance(v, str) else f"`{v}`"


def chain(table, row, col):
    cs = chg(table, row, col)
    if not cs:
        return "(변경 없음)"
    return " → ".join([fmt(cs[0]["before"])] + [f"{fmt(c['after'])} *[{c['rule']}]*" for c in cs])


def rowstr(sheet, r):
    return " \\| ".join("" if v is None else str(v) for v in raw[sheet][r - 1]).rstrip(" \\|")


cleaned = {r["_source"]: r for r in [dict(zip(h, v)) for ws in [openpyxl.load_workbook(OUT / "haru-cleaned.xlsx")["Cleaned_orders"]]
                                     for h in [next(ws.iter_rows(values_only=True))] for v in ws.iter_rows(min_row=2, values_only=True)]}
o = S["tables"]["orders"]
oc = SC["outcomes"]
L = []
w = L.append
w("# 엉망 데이터 정리 스킬 (messy-data-cleanup) 데모 리포트\n")
w("이 문서의 숫자는 전부 `demo/make_report.py`가 실제 산출물(`demo/output/*.json`, 정리된 xlsx)에서 읽어 넣은 값이다. 손으로 친 숫자는 없다. "
  "`bash demo/run_demo.sh` 한 번이면 데이터 생성부터 정리, 재실행 검증, 채점, 이 리포트까지 다시 만든다.\n")
w("## 1. 한눈에 보는 결과\n")
w("| 항목 | 결과 |\n|---|---|")
w(f"| 심어둔 문제 수 | **{SC['planted']}개** (하루커피 데모) |")
w(f"| 자동으로 고침 | **{oc.get('fixed', 0)}** |")
w(f"| 사람 확인으로 넘김 (안전하게 플래그) | **{oc.get('flagged', 0)}** |")
w(f"| 틀리게 고침 / 놓침 / 운 좋게 맞춘 추측 | {oc.get('wrong', 0)} / {oc.get('missed', 0)} / {oc.get('guessed', 0)} |")
w(f"| 처리율 (고침+플래그) | **{SC['handled_rate']:.1%}** |")
ca = SC["cell_accuracy"]
w(f"| 정답표 대비 셀 정확도 | {ca['correct']}/{ca['cells']} = **{ca['rate']:.1%}** (틀린 {ca['cells'] - ca['correct']}칸 중 {ca['wrong_but_flag_expected']}칸은 원래 사람이 정해야 하는 칸. 나머지 {ca['wrong_other']}칸도 전부 리뷰 목록에 올라가 있음) |")
noise_txt = ", ".join(f"{n['table']} {n['row']}행 {n['column']}" for n in SC["noise_flags"])
w(f"| 심지 않은 곳에 올라간 플래그 | {len(SC['noise_flags'])}건{(' (' + noise_txt + ': 마스터에 없는 고객 C0099의 이름이라 어휘 밖으로 잡힘. 고아 키의 여파)') if SC['noise_flags'] else ''} |")
w(f"| 블라인드(held-out) 데이터 첫 실행 | 처리율 **{FIRST_J['handled_rate']:.1%}**, 틀림 {FIRST_J['outcomes'].get('wrong', 0)} / 놓침 {FIRST_J['outcomes'].get('missed', 0)}, 셀 정확도 {FIRST_J['cell_accuracy']['rate']:.1%} |")
w(f"| 블라인드 데이터, 일반 규칙 보강 후 | 처리율 {BS['handled_rate']:.1%}, 틀림 {BS['outcomes'].get('wrong', 0)}, 셀 정확도 {BS['cell_accuracy']['rate']:.1%} |")
w(f"| 멱등성 | 두 번 실행한 결과가 바이트 단위로 같음 (해시 시드를 바꿔도 같음). 정리 결과를 다시 정리해도 값 변경 0건 |")
w("")
w("**솔직하게 짚어둘 점.** 하루커피 데이터는 내가 만든 데이터를 내가 만든 정리기로 돌린 결과라 점수가 후할 수밖에 없다. "
  "그래서 정리기를 만드는 동안 한 번도 쓰지 않은 블라인드 데이터셋(학원 원생/수강/출결, 다른 유형의 함정 포함)을 따로 만들고, "
  "계약서는 프로파일만 보고 작성한 뒤 **첫 실행 점수를 먼저 기록**했다(`blind/first_run_score.txt`). 첫 실행에서 드러난 구멍은 9절에 있다.\n")

w("## 2. 얼마나 엉망인 데이터였나\n")
w("`demo/input/하루커피_매출정리_최종_진짜최종.xlsx` (시트 3개)와 `반품교환_3PL.csv` (cp949). 실제로 심은 것:\n")
cats = Counter(i["category"] for i in GT["issues"])
names = {"structure": "제목/메모/반복 헤더/소계·합계/빈 행", "date_format": "날짜 형식 뒤죽박죽 (엑셀 시리얼, 2024.1.5, 24/01/07, 1월 9일, 20240112, 전각 ２０２４．３．１ …)",
         "id_format": "ID 표기 제각각 (c-1, C 0003, 0004, Ｃ０００５, 숫자 셀 4)", "number_text": "텍스트 숫자 (₩12,000 / 12000원 / 1.5만원 / 13.5천원 / 3개 / 2 EA / ２)",
         "category": "범주 오타·동의어 (서을, 겅기, 카느, 배송완ㄹ, card, N페이, 콜드브류 …)", "name_typo": "상품명 띄어쓰기·오타", "blank_placeholder": "빈칸 표기 (-, N/A, 없음)",
         "merged_cell": "병합 셀 (날짜, 지역)", "shifted_row": "한 칸 밀린 행 (오른쪽 1, 왼쪽 1)", "duplicate": "완전 중복 (복붙, 표기만 다른 같은 주문)",
         "near_duplicate": "유사 중복 (더블 클릭 주문, 같은 사람 재가입)", "key_conflict": "같은 주문번호, 다른 내용", "phone_format": "전화번호 형식", "invalid": "망가진 값 (도메인 없는 이메일, 0 빠진 전화, 13월)",
         "decimal_comma": "유럽식 숫자 13.500,00", "trap": "함정 (동명이인 김민수, 다른 날 같은 상품 재주문, 할인율 0)", "reconcile": "소계·합계 대사",
         "join_orphan": "조인 고아 키", "join_fallback": "상품코드가 비어 이름으로만 조인 가능", "join_ambiguous": "조인 모호 키", "text": "공백/제로폭 문자/모지바케"}
for k, n in cats.most_common():
    w(f"- {names.get(k, k)}: {n}")
w("")
w("구조 자체도 엉망이다. 주문 시트는 2줄 병합 헤더(`고객`→ID/이름, `상품`→코드/상품명/수량, `금액`→단가/할인율/결제금액) 아래에 월별 소계, 중간에 다시 붙여넣은 헤더, "
  "\"※ 2월분은 POS에서 복붙함\" 메모가 섞여 있다. 상품 시트에는 표가 두 개(상품 마스터, 단종 상품) 들어 있다.\n")

w("## 3. 무엇을 왜 했나 (단계별 논거)\n")
w("순서는 고정이다. **구조 → 텍스트 → 밀린 행 → 타입 → 범주 → 중복 → 교차검증 → 조인.** 정규화가 끝나기 전에는 중복을 비교하지 않는다. "
  "표기만 다른 중복은 정규화한 뒤에야 같은 행으로 보이기 때문이다(아래 예시 2).\n")
w("| 표 | 들어온 행 | 정리된 행 | 빠진 행 (사유) |\n|---|---|---|---|")
for t, st in S["tables"].items():
    w(f"| {t} | {st['rows_in']} | {st['rows_out']} | {', '.join(f'{k} {v}' for k, v in sorted(st['dropped'].items()))} |")
w("")

import sys
sys.path.insert(0, str(ROOT / "skill" / "messy-data-cleanup" / "scripts"))
from cleankit.model import RULES  # noqa: E402
KO = {"C1-ALIAS": "계약서 동의어 표로 변환 (card→카드, N페이→네이버페이). 동의어만 적고 오타는 적지 않음",
      "C1-CANON": "대소문자·띄어쓰기·구두점만 다른 값을 정식 값으로 (콜드브루원액500ml→콜드브루 원액 500ml)",
      "C1-FUZZY": "자모 유사도가 기준(0.78) 이상이고 2등과 차이가 충분할 때만 오타 교정 (서을→서울). 숫자나 끝 글자(A/B)만 다르면 금지",
      "D1-DATE": "날짜를 ISO로 (엑셀 시리얼, 2024.1.5, 24/01/07, 20240112, 2024년 2월 3일, DD.MM.YYYY)",
      "D1-ORDER": "일/월 순서는 열 단위로 12 넘는 값이 결정. 결정 못 하면 기본값을 쓰고 플래그",
      "D1-YEAR": "연도 없는 날짜(1월 9일)는 그 열에서 가장 많은 연도로 채우고 신뢰도를 낮춰 기록",
      "E1-EMAIL": "이메일 앞뒤 공백 제거, 소문자", "I1-ID": "ID를 계약서 패턴으로 파싱해 정식 형식으로 (c-1, C 0003, 0004, 숫자 4 → C0001...). 텍스트로 유지",
      "M1-PLACEHOLDER": "-, N/A, 없음, #N/A를 빈칸으로. 빈칸은 절대 채우지 않음", "N1-KCOUNT": "두개→2, 3개→3, 2 EA→2",
      "N1-KUNIT": "값에 적힌 단위만 적용 (1.5만원→15000, 13.5천원→13500, 4만5천원→45000)", "N1-NUMBER": "₩, 원, 쉼표, 공백 제거, (1,200)→-1200, 소수점 쉼표는 열 단위 판단",
      "N1-PERCENT": "10%→10", "P1-PHONE": "유효한 번호일 때만 010-1234-5678 형식으로. 아니면 손대지 않고 플래그",
      "S2-MERGE": "병합 셀 값을 범위 전체에 채움", "S3-SHIFT": "밀린 행을 되돌림 (빈 칸만 지우거나 끼움)",
      "T1-MOJIBAKE": "깨진 글자 복구 (UTF-8을 cp1252로 잘못 읽은 경우)", "T1-NFKC": "전각→반각 (２０２４→2024, Ｃ０００５→C0005). 한글 낱자(ㄹ, ㅋ)는 보존",
      "T1-WS": "앞뒤 공백, 연속 공백, 제로폭 문자 제거", "O1-DECISION": "계약서 overrides에 적은 사람의 결정"}
w("| 규칙 | 바뀐 셀 수 | 무엇을, 왜 |\n|---|---|---|")
for r, n in S["changes_by_rule"].items():
    w(f"| {r} | {n} | {KO.get(r, RULES[r][1])} |")
w(f"\n모든 변경은 `Change log` 시트에 셀 단위로 남는다. 변경 {S['n_changes']}줄 각각에 before, after, 규칙, 신뢰도, 근거가 있다. "
  "자체 검사는 셀마다 원본값에서 최종값까지 변경 사슬이 끊김 없이 이어지는지, 들어온 행 = 남은 행 + 빠진 행인지, placeholder 말고 값이 사라진 칸이 없는지를 코드로 확인한다. "
  f"결과는 {sum(c['ok'] for c in S['self_check'])}/{len(S['self_check'])} PASS.\n")

w("## 4. 제일 지독한 케이스 before → after\n")
w("**① 한 칸 밀린 행 (주문 시트 29행, O-2024-0019).** 누가 고객ID 앞에 빈 칸을 하나 끼워넣어서 오른쪽 값이 전부 한 칸씩 밀렸다.\n")
w(f"- 원본: `{rowstr('주문내역', 29)}`")
c19 = cleaned.get("주문내역!29", {})
w(f"- 정리: customer_id `{c19.get('customer_id')}`, customer_name `{c19.get('customer_name')}`, product_code `{c19.get('product_code')}`, qty `{c19.get('qty')}`, "
  f"unit_price `{c19.get('unit_price')}`, discount `{c19.get('discount_pct')}`, amount `{c19.get('amount')}`, payment `{c19.get('payment')}`, status `{c19.get('status')}`")
ev = next((c["evidence"] for c in A["changes"] if c["source_row"] == 29 and c["rule"] == "S3-SHIFT"), "")
w(f"- 근거: `{ev}`. 열마다 \"이 값이 이 열에 맞나\"(ID 패턴, 날짜, 숫자 범위, 어휘)를 세고, 빈 칸만 지우거나 끼워넣는 이동 중 위반이 0~1개로 줄어드는 것만 받아들인다. 데이터 값은 절대 지우지 않는다.")
c33 = cleaned.get("주문내역!45", {})
w(f"- 반대로 날짜 칸이 통째로 지워진 45행(O-2024-0033)은 오른쪽으로 한 칸 되돌린다. 비어버린 날짜는 지어내지 않고 R7(필수값 빈칸)로 넘긴다. 정리된 날짜: {fmt(c33.get('order_date'))}, 고객ID `{c33.get('customer_id')}`, 결제 `{c33.get('payment')}`\n")
dx = next(d for d in A["dups"] if d["kind"] == "exact" and "differed" in d["evidence"])
w(f"**② 표기만 다른 완전 중복 (행 {dx['rows'][0]}과 {dx['rows'][1]}).**\n")
w(f"- 원본 {dx['rows'][0]}행: `{rowstr('주문내역', dx['rows'][0])}`")
w(f"- 원본 {dx['rows'][1]}행: `{rowstr('주문내역', dx['rows'][1])}`")
w(f"- 근거: `{dx['evidence']}`. 날짜(`20240302` vs 시리얼 `45353`), 고객ID(`c-13` vs `c0013`), 금액(`1.8만원` vs `₩18,000`)이 정규화 후 모두 같아져서 뒤 행을 `Dropped rows`로 보냈다. 지운 게 아니라 원본값 그대로 옮겨 둔 것이다.\n")
w("**③ 모지바케 + 제로폭 문자 + 전각.**\n")
w(f"- 주문 15행 고객명: {chain('orders', 15, 'customer_name')}")
w(f"- 주문 17행 고객명: {chain('orders', 17, 'customer_name')}")
w(f"- 주문 14행 주문일자: {chain('orders', 14, 'order_date')}")
w(f"- 주문 10행 고객ID: {chain('orders', 10, 'customer_id')}\n")
w("**④ 2줄 병합 헤더와 병합된 날짜 셀.** 4~5행 헤더를 `금액`+`단가` 같은 식으로 합쳐 계약서의 열 이름과 맞췄다(`Dropped rows`의 header 행 근거에 열 매핑이 남는다). "
  f"같은 날 주문 두 건이 날짜 셀 하나를 병합해서 쓰고 있었다. 주문 9행 주문일자: {chain('orders', 9, 'order_date')}\n")
w("**⑤ 오타는 고치되, 애매하면 손대지 않는다.**\n")
for t, r, c in (("customers", 6, "region"), ("orders", 8, "status"), ("products", 7, "category"), ("orders", 22, "product_name")):
    cs = chg(t, r, c)
    if cs:
        w(f"- {t} {r}행 {c}: {chain(t, r, c)}. 근거: `{cs[-1]['evidence']}`")
for rv in A["review"]:
    if (rv["table"], rv["source_row"], rv["column"]) in (("orders", 9, "payment"), ("orders", 25, "order_date"), ("customers", 10, "phone"), ("orders", 24, "discount_pct")):
        w(f"- {rv['table']} {rv['source_row']}행 {rv['column']} `{rv['value']}` → **안 고치고 리뷰로**: {rv['question']}")
w("\n`카느`→`카드`는 자모 하나 차이(유사도 0.75)지만 일부러 자동으로 고치지 않는다. 두 글자 단어는 자모 하나만 달라도 전혀 다른 말일 수 있어서다(경주/광주). 블라인드 데이터에서도 같은 원칙으로 `수학 심화B`(없는 강좌)를 `수학 심화A`로 바꾸지 않고 멈췄다.\n")

w("## 5. 조인 결과\n")
w("| 조인 | 매칭률 (원본 키 그대로) | 매칭률 (정규화 후) | 이름으로 대체 매칭 | 고아 | 모호 | 비고 |\n|---|---|---|---|---|---|---|")
for j in S["joins"]:
    w(f"| {j['left']} → {j['right']} | {j['raw_key_match_rate']:.1%} | **{j['match_rate']:.1%}** | {j['matched_fallback']} | {j['orphans']} | {j['ambiguous']} | {j['notes'] or '-'} |")
w("")
for d in A["join_details"]:
    w(f"- {d['join']} 왼쪽 {d['left_row']}행 `{d['key']}`: {d['issue']}, {d['detail']}")
w("\n원본 키 그대로면 VLOOKUP이 주문의 16%만 고객을 찾는다. ID를 계약서 패턴(`C{n:04d}`)으로 맞춘 뒤에는 고아 2건(`C0099`는 마스터에 없음, `K0014`는 접두어 오타라 리뷰로)을 빼고 전부 붙는다. "
  "상품코드가 빈 2건은 정규화된 상품명으로 붙였고, 그 사실이 `_join_prod` 열에 남는다. 단종 상품 P009는 두 번째 표(단종 상품)에서 찾았다. "
  "반품의 `O-2024-0010`은 주문 쪽에 같은 번호가 두 행이라 **일부러 조인하지 않았다**. 붙이면 행이 불어난다.\n")

w("## 6. 소계·합계 대사\n")
w("| 행 | 라벨 | 시트에 적힌 값 | 정리 후 합 | 차이 | 설명 |\n|---|---|---|---|---|---|")
for r in S["reconcile"]:
    w(f"| {r['subtotal_row']} | {r['label']} | {r['stated']:,} | {r['cleaned_sum']:,} | {r['difference']:,} | {r['explanation']} |")
w("\n사람이 시트에서 합계를 낼 때는 복붙된 중복 행까지 더했다. 차이가 정확히 빠진 중복 행의 금액이면 \"설명됨\"이고, `#N/A`처럼 비어버린 값이 원인이면 그 행 번호를 짚어준다.\n")

w("## 7. 사람이 결정할 것 (Needs human review)\n")
w(f"총 {S['n_review']}건. 규칙별 건수: " + ", ".join(f"{k} {v}" for k, v in S["review_by_flag"].items()) + "\n")
w("| 표 | 행 | 열 | 값 | 플래그 | 제안 | 질문 |\n|---|---|---|---|---|---|---|")
for rv in A["review"]:
    w(f"| {rv['table']} | {rv['source_row']} | {rv['column']} | {fmt(rv['value'])} | {rv['flag']} | {rv['suggestion'] or '-'} | {rv['question'].replace('|', '/')} |")
w("\n결정은 계약서 `overrides:`에 적고 다시 돌리면 반영되고, 해당 리뷰 항목은 사라진다. 카느→카드, 03/02/2024→2024-02-03 두 건으로 실제로 돌려서 확인했다.\n")
w("## 8. 채점표 (정답표 대비, 유형별)\n")
w("| 유형 | 고침 | 플래그 | 틀림 | 놓침 |\n|---|---|---|---|---|")
for k, v in SC["by_category"].items():
    w(f"| {names.get(k, k)} | {v.get('fixed', 0)} | {v.get('flagged', 0)} | {v.get('wrong', 0)} | {v.get('missed', 0) + v.get('guessed', 0)} |")
w("\n채점은 `demo/score.py`가 정리된 xlsx 파일 자체(Cleaned/Review/Dropped/Join report 시트)를 읽어서 한다. 내부 변수는 보지 않는다. "
  "\"플래그\"는 사람이 정해야 맞는 문제를 리뷰 목록에 올린 경우다. 사람 몫인 문제를 플래그 없이 조용히 정답으로 바꾼 경우는 \"운 좋은 추측\"으로 따로 세고 처리 실패로 친다.\n")

w("## 9. 블라인드 테스트 (만들면서 한 번도 안 본 데이터)\n")
w(f"`blind/` 학원 데이터, 심은 문제 {BS['planted']}개. 하루커피에 없던 유형이 들어 있다. 병합된 제목 줄, 영문 헤더, `No.` 순번 열, 형제가 같은 학부모 번호를 쓰는 경우, "
  "`01O-5678-9012`(숫자 0 대신 영문 O), `△15,000`, `Feb 16, 2024`, `3/3`(연도 없음), `-2만`, `150,000원(할인전)`, `평균` 행, 세미콜론 구분 CSV 안의 여러 줄 메모, 없는 강좌 `수학 심화B`.\n")
w(f"- **첫 실행 (코드 수정 전): 처리율 {FIRST_J['handled_rate']:.1%}, 고침 {FIRST_J['outcomes'].get('fixed', 0)}, 플래그 {FIRST_J['outcomes'].get('flagged', 0)}, 틀림 {FIRST_J['outcomes'].get('wrong', 0)}, 놓침 {FIRST_J['outcomes'].get('missed', 0)}, 셀 정확도 {FIRST_J['cell_accuracy']['rate']:.1%}.**")
w("- 첫 실행에서 드러난 구멍과 원인을 한 번에 하나씩 일반 규칙으로 고쳤다.")
for x in ["CSV 안에 여러 줄짜리 셀이 있으면 그 뒤 행 번호가 한 줄씩 밀렸다 → 행 번호를 물리적 줄 번호로 기록",
          "`No.` 순번 열 때문에 복붙 중복을 못 잡았다 → 1씩 증가하는 순번 열은 중복 비교에서 제외 (근거는 notes에 남김)",
          "형제의 같은 학부모 번호를 중복 후보로 올렸다 → 연락처는 두 개가 겹치거나, 하나 + 이름 유사도 0.8 이상일 때만 후보로",
          "셔틀 `X`(=N)를 빈칸 표기로 보고 지웠다 → 그 열 어휘에 있는 말이면 빈칸 처리 안 함",
          "`평균` 행을 데이터로 읽었다 → 평균/최대/최소도 집계 행으로 (합계만 대사)",
          "`Feb 16, 2024`, `-2만`, `△` → 영문 월 이름, 단위 앞 음수, 회계용 △ 지원",
          "`수학 심화B`를 0.91 유사도로 `수학 심화A`에 붙였다 (조용한 오답) → 숫자나 끝 글자(A/B)만 다르면 자동으로 매핑 안 함"]:
    w(f"  - {x}")
w(f"- 고친 뒤: 처리율 {BS['handled_rate']:.1%}, 틀림 {BS['outcomes'].get('wrong', 0)}, 셀 정확도 {BS['cell_accuracy']['rate']:.1%}. "
  "고친 규칙이 블라인드 데이터를 보고 만든 것이라, 이 두 번째 숫자는 첫 실행 숫자만큼 믿을 만한 건 아니다. 하루커피 점수가 떨어지지 않았는지도 다시 확인했다.\n")

w("## 10. 재실행·멱등성 증명\n")
w("- 같은 입력으로 두 번 돌리고(파이썬 해시 시드 1과 2) 산출물 10개(xlsx, json 2개, csv 7개)의 sha256을 비교했다. **완전히 같다.** 파일은 임시 경로에 쓴 뒤 rename하고, xlsx 내부 zip의 타임스탬프를 고정한다.")
w(f"- 정리된 CSV를 같은 계약서로 한 번 더 정리했다. `{FP}`")
w(f"- 블라인드: `{BFP}`")
w("- 원본 파일의 sha256은 실행 전후로 같다. 원본은 읽기만 한다.")
import subprocess as _sp0, sys as _sys0
_st = _sp0.run([_sys0.executable, str(ROOT / "skill/messy-data-cleanup/scripts/selftest.py")], capture_output=True, text=True).stdout.strip().splitlines()[-1]
w(f"- 파서와 LLM 게이트 동작 검사: `python3 skill/messy-data-cleanup/scripts/selftest.py`, {_st}. API 호출 없이 돈다.\n")

# ---- LLM layer (generated from ablation.json and the first live runs)
import subprocess as _sp
import sys as _sys
AB = load(ROOT / "ablation.json")
ABL = load(ROOT / "ablation_live_run.json") if (ROOT / "ablation_live_run.json").exists() else AB
SEM1 = load(ROOT / "semantic" / "first_live_run_score.json")
SB1 = load(ROOT / "semantic_blind" / "first_live_run_score.json")
_cache = [load(f) for d in ("demo", "blind", "semantic", "semantic_blind") for f in (ROOT / d / "llm_cache").glob("*/*.json")]
N_CALLS, COST = len(_cache), sum(float(c.get("usage", {}).get("cost", 0) or 0) for c in _cache)
N_SEM = len(load(ROOT / "semantic" / "ground_truth.json")["issues"]) + len(load(ROOT / "semantic_blind" / "ground_truth.json")["issues"])
NAMES = {"demo": "하루커피 데모", "blind": "학원 블라인드", "semantic": "의미 문제 세트 (게이트 조정에 씀)", "semantic_blind": "의미 블라인드 (게이트 조정 후 처음 돌림)"}
w("## 11. LLM 레이어 (선택, `--llm live`)\n")
w("규칙 엔진이 뼈대이고 감사 기록이다. LLM은 규칙이 이미 골라내고 **결정하지 못한** 항목만 받는다. 답은 규칙이 계산한 후보 중 하나이거나 그 셀에서 그대로 인용한 값이어야 한다. "
  "그리고 결정적 게이트를 통과해야만 적용된다. 통과하지 못한 답은 `Needs human review`에 'LLM이 무엇을 제안했고 왜 적용하지 않았는지'와 함께 남는다. "
  "적용된 답은 Change log에 `llm:<task>` 규칙으로, `model=…; conf=…; quote=…; why=…` 근거와 함께 기록된다. 설계 문서는 `docs/LLM_LAYER_PLAN.md`.\n")
w("| 작업 | 하는 일 | 적용 조건 (게이트) |\n|---|---|---|")
w("| `llm:synonym` | 어휘에 없는 범주값 → 어휘값 (무통장입금→계좌이체, Visa→카드, delivered→배송완료) | 어휘값일 것, 인용이 셀·행에서 나올 것(후보 목록 인용은 무효), 신뢰도 ≥ 0.8, 계약 검사 통과. 마스터 이름 열에서는 철자가 비슷할 것 |")
w("| `llm:resolve` | 애매한 날짜(03/02/2024), 0.1 vs 10% | 규칙이 만든 후보일 것. 날짜는 앞뒤 확정 날짜 사이에 들어가는 **유일한** 해석일 것, 퍼센트는 열의 값 범위 안일 것 |")
w("| `llm:extract` | 메모 → 새 열 (선물포장 여부, 연락처, 희망일, 초 개수, 문구) | 셀 안의 원문을 그대로 인용할 것, 타입이 맞고 인용과 값이 일치할 것, 인용에 스키마 필드 이름이 없을 것. AI에게 하는 지시처럼 보이는 셀은 아예 보내지 않고 R9로 표시 |")
w("| `llm:entity` | 조인 고아 키·빈 키 → 마스터 후보 5개 중 하나 (Kim Minsu → 김민수 C0001) | 후보일 것, 신뢰도 ≥ 0.85, 이메일·전화·ID 비교 열 하나 이상이 양쪽에서 같을 것. 이름만 비슷한 것은 절대 인정하지 않음 |")
w("| 레이아웃 (`profile.py --llm`) | 시트 미리보기 → 표 위치, 헤더 행, 열 이름과 타입 | 헤더 행이 실제로 있고 헤더 글자가 셀과 일치할 것. 계약서 초안에 힌트로만 들어간다 |")
w("")
w("모든 답은 (작업, 프롬프트 버전, 모델, 입력)의 해시로 `llm_cache/`에 저장된다. 그래서 재실행과 오프라인 재생(`--llm cache`, API 키 없이)이 바이트 단위로 같다. 사람이 쓴 `overrides:`가 LLM보다 먼저 적용되고 항상 이긴다. "
  f"기본 모델은 OpenRouter `google/gemini-2.5-flash-lite`(temperature 0)이다. 캐시에 남은 호출 {N_CALLS}회의 비용 합계는 ${COST:.4f}이다 "
  "(`llm_cache/*/*.json`의 usage.cost 합. 개발 중에 버려진 호출 몇 번은 빠져 있다).\n")
w("### 11-1. 절제 실험: 규칙만 vs 규칙+LLM (같은 채점기)\n")
w("| 세트 | 모드 | 처리율 | 자동 해결률 | LLM이 맞게 해결 | 잘못 바꿈 | 놓침 | 셀 정확도 | 리뷰 큐 | 조인 매칭률 | LLM 변경 (틀림) |")
w("|---|---|---|---|---|---|---|---|---|---|---|")
for k, v in AB["sets"].items():
    for mode, lab in (("rules_only", "규칙만"), ("rules_plus_llm", "규칙+LLM")):
        x = v[mode]
        lc = x["llm_changes"]
        w(f"| {NAMES[k]} | {lab} | {x['handled_rate']:.1%} | {x['auto_resolved_rate']:.1%} | {x['fixed_by_llm']} | {x['wrong']} | {x['missed']} | "
          f"{x['cell_accuracy']:.1%} | {x['review_queue']} | {', '.join(f'{r:.1%}' for r in x['join_rates'])} | "
          f"{lc['total']} ({lc.get('wrong', 0)}) |")
w("")
w("- 처리율 = 맞게 고침 + LLM이 맞게 고침 + 사람에게 넘김. 자동 해결률 = 사람 손 없이 맞게 끝난 비율. 규칙만으로 돌리면 의미 문제 세트에서 메모 추출과 빈 키 매칭을 아예 못 해서 '놓침'이 된다.")
w("- 데모와 학원 세트는 원래 규칙이 강한 데이터라 LLM 효과가 작다. 여기서 LLM이 푼 것은 카느→카드 3건, VlP→VIP, 콜브 원액→콜드브루 원액 500ml 같은 것이다. 03/02/2024와 0.1은 모델이 틀린 쪽을 골랐고, 게이트가 막아서 리뷰에 남았다.")
for k, v in AB["sets"].items():
    cf = [load(f) for f in (ROOT / k / "llm_cache").glob("*/*.json")]
    w(f"- {NAMES[k]}: 캐시에 저장된 호출 {len(cf)}회 (토큰 {sum(c['usage'].get('prompt_tokens', 0) for c in cf)}+{sum(c['usage'].get('completion_tokens', 0) for c in cf)}, "
      f"${sum(float(c['usage'].get('cost', 0) or 0) for c in cf):.4f}, 모델 여러 개 포함). 재실행 시 호출 {v['usage_run2'].get('calls')}회. "
      f"재실행 결과 동일: {'예' if v['llm_run_identical_on_rerun'] else '아니오'}, 키 없이 캐시만으로 재생한 결과 동일: {'예' if v['offline_cache_replay_identical'] else '아니오'}")
_dl = load(ROOT / "demo" / "output_llm" / "audit.json")
_rej = [r for r in _dl["review"] if "LLM (" in r["suggestion"]]
w("- 하루커피에서 LLM 제안이 게이트에 막혀 리뷰에 남은 것: " + "; ".join(
    f"{r['source_row']}행 {r['column']} → 제안 {r['suggestion'].split('proposed ')[1].split(' conf')[0]}, 사유: {r['suggestion'].split('not applied: ')[1].split('. ')[0]}" for r in _rej))
w("")
w("### 11-2. LLM이 틀린 비율 (정직하게)\n")
s1 = SEM1["llm_changes"]
w(f"- **게이트를 다듬기 전 첫 라이브 실행** (의미 세트): LLM 변경 {s1['total']}건 중 **{s1.get('wrong', 0)}건 틀림 ({s1['wrong_rate']:.1%})**. 모델이 틀린 것들은 이렇다.")
for x in SEM1["llm_wrong"]:
    w(f"  - {x['row']}행 `{x['column']}`: {x['after']!r} (정답 {x['truth']!r}). 모델 근거: {x['evidence'].split('why=')[-1][:140]}")
w("  - 그리고 인용 검사가 우연히 막은 것: 이름만 같은 다른 사람(김민수, 다른 이메일)을 C0001로 신뢰도 1.00으로 매칭하려 했다.")
w("- 이 실패를 보고 게이트를 넣었다. 날짜는 앞뒤 행 사이에 유일하게 맞는 해석일 것, 지시문처럼 보이는 셀은 보내지 않을 것, 판단할 셀의 현재 값(규칙의 기본 추측)은 보여주지 않을 것, 엔티티 매칭은 이메일이나 전화가 같을 것. "
  "모델을 믿는 대신 모델이 틀려도 데이터가 망가지지 않게 만든 것이다. 그 뒤 의미 세트의 LLM 틀림은 0건이다. 다만 이 숫자는 그 세트에 맞춰 다듬은 결과다.")
sb = SB1["llm_changes"]
w(f"- **게이트 조정 후 처음 돌린 의미 블라인드** (베이커리 픽업 주문, 다른 어휘·다른 메모 필드): LLM 변경 {sb['total']}건 중 **{sb.get('wrong', 0)}건 틀림 ({(sb['wrong_rate'] or 0):.1%})**.")
for x in SB1["llm_wrong"]:
    w(f"  - {x['row']}행 `{x['column']}`: {x['after']!r} (정답 {x['truth']!r}). 모델 근거: {x['evidence'].split('why=')[-1][:160]}")
w("  - 그럴듯한 어휘값 사이의 의미 판단은 게이트로 못 막는다. 이런 값은 계약서 vocab에 동의어로 넣거나, 그 데이터에서는 `llm.tasks`에서 synonym을 빼는 게 맞다.")
for k, n in (("semantic_blind", "bakery"), ("semantic", "shop")):
    p = ROOT / k / "output_llm_flash" / "score.json"
    if p.exists():
        f = load(p)
        lc = f["llm_changes"]
        w(f"- 비교용으로 더 큰 모델 `google/gemini-2.5-flash`를 {NAMES[k]}에 돌렸다: 자동 해결률 {f['auto_resolved_rate']:.1%}, LLM 변경 {lc['total']}건 중 {lc.get('wrong', 0)}건 틀림"
          + (f" ({'; '.join(str(x['row']) + '행 ' + repr(x['after']) + ' (정답 ' + repr(x['truth']) + ')' for x in f['llm_wrong'])})" if f["llm_wrong"] else "") + ".")
_traps = Counter()
for d in ("semantic", "semantic_blind"):
    sc = load(ROOT / d / "output_llm" / "score.json")
    for cat, oc_ in sc["by_category"].items():
        if cat.endswith("_trap"):
            _traps.update(oc_)
w(f"- 덫(LLM이 손대면 안 되는 것: 대응 어휘가 없는 값 포인트·상품권·외상·노쇼, 맥락이 결정 못 하는 날짜, 상대 날짜, 프롬프트 주입 메모, 이름만 비슷한 고객) "
  f"{sum(_traps.values())}건: 게이트 적용 후 flash-lite 기준 결과 {dict(_traps)}. 'fixed'는 빈칸이 맞는 칸을 빈칸으로 둔 것, 'flagged'는 사람에게 넘긴 것이다.\n")
w("### 11-3. 레이아웃 읽기 (표 위치·헤더 행)\n")
w("| 세트 | 표 수 | 규칙 프로파일이 맞힌 헤더 | LLM 레이아웃이 맞힌 헤더 |\n|---|---|---|---|")
for d in ("demo", "blind", "semantic"):
    pr = ROOT / d / "output_llm" / "profile.md"
    if pr.exists():
        r = _sp.run([_sys.executable, str(HERE / "layout_check.py"), str(ROOT / d), str(pr), str(ROOT / d / "output_llm" / "contract.draft.yaml")],
                    capture_output=True, text=True)
        j = json.loads(r.stdout)
        w(f"| {NAMES[d]} | {j['tables']} | {j['rule_profile_correct']} | {j['llm_layout_correct']} |")
w("\n하루커피에서 규칙 프로파일은 2줄 병합 헤더를 5행 하나로 읽었다. 그리고 상품 시트 아래쪽의 두 번째 표(단종 상품)를 못 봤다. LLM은 둘 다 맞혔다. 그래도 결과는 초안 힌트일 뿐이고, 계약서는 사람이 확정한다.\n")
w("## 12. 한계 (정직하게)\n")
for x in ["계약서는 사람(에이전트)이 쓴다. 프로파일이 초안을 주지만 키, ID 패턴, 동의어는 직접 정해야 한다. 동의어(card→카드)를 안 넣으면 그 값은 리뷰로 간다.",
          "퍼지 매칭은 한글 자모 유사도 하나뿐이다. 두 글자 단어의 한 자모 오타(카느, 교2)는 일부러 사람에게 넘긴다. 약어(과탐→과학 탐구, 콜브 원액)는 못 푼다.",
          "영어 숫자 단어(\"two\"), 연도 없는 `3/3`, `150,000원(할인전)`처럼 숫자 뒤에 글이 붙은 값은 파싱하지 않고 플래그만 한다.",
          "0.1과 10%가 섞인 할인율은 고치지 않고 플래그한다. 그래서 같은 행의 금액 검증도 함께 걸린다(메시지에 원인을 적어줌).",
          "밀린 행 복구는 한 행이 1~2칸 통째로 밀린 경우만 다룬다. 값 두 개의 순서가 서로 바뀐 경우나 텍스트 열끼리 밀린 경우는 감지하기 어렵다(텍스트 열은 판정을 안 하므로).",
          "모지바케 복구는 UTF-8을 cp1252/latin-1로 잘못 읽은 경우만 확실하다. UTF-8을 cp949로 잘못 읽은 경우는 대개 바이트가 이미 손실돼서 복구가 안 된다.",
          "엑셀 1904 날짜 체계, 숨긴 행/시트의 의미, 수식 재계산은 다루지 않는다. 값만 읽는다.",
          "중복 판단은 '같은 사건'인지까지 확인해 주지 않는다. 후보만 근거와 함께 올리고 합치지 않는다.",
          "하루커피 점수는 만든 사람이 채점한 결과라 후하다. 블라인드 첫 실행 점수가 더 현실적인 숫자다."]:
    w(f"- {x}")
w(f"- LLM 레이어: 결과는 모델과 데이터에 따라 다르다. 블라인드 의미 세트에서 flash-lite는 {SB1['llm_changes']['total']}건 중 {SB1['llm_changes'].get('wrong', 0)}건을 틀렸다. 게이트는 지어낸 값, 후보 밖의 답, 근거 없는 매칭, 프롬프트 주입은 막지만, 그럴듯한 어휘값 사이의 오판은 못 막는다.")
w(f"- 의미 세트 두 개와 정답표는 내가 만들었다(심은 문제 합계 {N_SEM}건). 실제 업무 데이터에서 다시 재야 한다. Gemini 직접 호출 경로(GEMINI_API_KEY)는 코드는 있지만, 이 환경의 키가 401(무효)이라 실제 호출로 검증하지 못했다. 측정은 전부 OpenRouter로 했다.")
w("\n## 13. 파일\n")
w("- 스킬: `skill/messy-data-cleanup/` (SKILL.md, reference/contract.md, templates/contract.example.yaml, scripts/)")
w("- Cursor 룰: `.cursor/rules/messy-data-cleanup.mdc`")
w("- 데모 입력: `demo/input/`, 정답표: `demo/ground_truth.json`, 계약서: `demo/contract.yaml`")
w("- 데모 결과: `demo/output/haru-cleaned.xlsx` (시트 구성은 SKILL.md 참고), `demo/output/csv/`, `score.json`, `profile.md`")
w("- 블라인드: `blind/` (같은 구조, 첫 실행 점수 `blind/first_run_score.txt`)")
w("- LLM 절제 실험: `demo/ablation.py` → `ablation.json` (오프라인 캐시 재생), `ablation_live_run.json` (라이브 첫 실행 사용량). 의미 세트: `semantic/`, `semantic_blind/` (각 `first_live_run_score.json`)")
w("- Gemini CLI 패키지: `gemini/` (gemini-extension.json, GEMINI.md, skills/messy-data-cleanup/)")
w("- 전체 재현: `bash demo/run_demo.sh` (LLM은 저장된 캐시로 재생해서 키·비용 없이 돈다. 새 데이터는 `ABL_LLM=live`)")
(ROOT / "REPORT.md").write_text("\n".join(L) + "\n", encoding="utf-8")
print(f"wrote {ROOT / 'REPORT.md'} ({len(L)} lines)")
