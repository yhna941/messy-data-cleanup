# 엉망 데이터 정리 스킬 (messy-data-cleanup) 데모 리포트

이 문서의 숫자는 전부 `demo/make_report.py`가 실제 산출물(`demo/output/*.json`, 정리된 xlsx)에서 읽어 넣은 값이다. 손으로 친 숫자는 없다. `bash demo/run_demo.sh` 한 번이면 데이터 생성부터 정리, 재실행 검증, 채점, 이 리포트까지 다시 만든다.

## 1. 한눈에 보는 결과

| 항목 | 결과 |
|---|---|
| 심어둔 문제 수 | **386개** (하루커피 데모) |
| 자동으로 고침 | **358** |
| 사람 확인으로 넘김 (안전하게 플래그) | **28** |
| 틀리게 고침 / 놓침 / 운 좋게 맞춘 추측 | 0 / 0 / 0 |
| 처리율 (고침+플래그) | **100.0%** |
| 정답표 대비 셀 정확도 | 611/630 = **97.0%** (틀린 19칸 중 16칸은 원래 사람이 정해야 하는 칸. 나머지 3칸도 전부 리뷰 목록에 올라가 있음) |
| 심지 않은 곳에 올라간 플래그 | 1건 (orders 42행 customer_name: 마스터에 없는 고객 C0099의 이름이라 어휘 밖으로 잡힘. 고아 키의 여파) |
| 블라인드(held-out) 데이터 첫 실행 | 처리율 **93.9%**, 틀림 2 / 놓침 5, 셀 정확도 92.5% |
| 블라인드 데이터, 일반 규칙 보강 후 | 처리율 100.0%, 틀림 0, 셀 정확도 96.8% |
| 멱등성 | 두 번 실행한 결과가 바이트 단위로 같음 (해시 시드를 바꿔도 같음). 정리 결과를 다시 정리해도 값 변경 0건 |

**솔직하게 짚어둘 점.** 하루커피 데이터는 내가 만든 데이터를 내가 만든 정리기로 돌린 결과라 점수가 후할 수밖에 없다. 그래서 정리기를 만드는 동안 한 번도 쓰지 않은 블라인드 데이터셋(학원 원생/수강/출결, 다른 유형의 함정 포함)을 따로 만들고, 계약서는 프로파일만 보고 작성한 뒤 **첫 실행 점수를 먼저 기록**했다(`blind/first_run_score.txt`). 첫 실행에서 드러난 구멍은 9절에 있다.

## 2. 얼마나 엉망인 데이터였나

`demo/input/하루커피_매출정리_최종_진짜최종.xlsx` (시트 3개)와 `반품교환_3PL.csv` (cp949). 실제로 심은 것:

- 텍스트 숫자 (₩12,000 / 12000원 / 1.5만원 / 13.5천원 / 3개 / 2 EA / ２): 96
- 범주 오타·동의어 (서을, 겅기, 카느, 배송완ㄹ, card, N페이, 콜드브류 …): 76
- 날짜 형식 뒤죽박죽 (엑셀 시리얼, 2024.1.5, 24/01/07, 1월 9일, 20240112, 전각 ２０２４．３．１ …): 54
- ID 표기 제각각 (c-1, C 0003, 0004, Ｃ０００５, 숫자 셀 4): 51
- 제목/메모/반복 헤더/소계·합계/빈 행: 14
- 상품명 띄어쓰기·오타: 14
- 빈칸 표기 (-, N/A, 없음): 11
- 한 칸 밀린 행 (오른쪽 1, 왼쪽 1): 11
- 전화번호 형식: 7
- 망가진 값 (도메인 없는 이메일, 0 빠진 전화, 13월): 6
- 유럽식 숫자 13.500,00: 6
- 병합 셀 (날짜, 지역): 5
- 소계·합계 대사: 4
- 공백/제로폭 문자/모지바케: 4
- 완전 중복 (복붙, 표기만 다른 같은 주문): 3
- 함정 (동명이인 김민수, 다른 날 같은 상품 재주문, 할인율 0): 3
- 같은 주문번호, 다른 내용: 2
- 조인 고아 키: 2
- 상품코드가 비어 이름으로만 조인 가능: 2
- 유사 중복 (더블 클릭 주문, 같은 사람 재가입): 2
- email_case: 2
- number_scale: 1
- date_ambiguous: 1
- cross_table: 1
- date_invalid: 1
- excel_error: 1
- id_invalid: 1
- cross_check: 1
- join_discontinued: 1
- multi_table: 1
- encoding: 1
- 조인 모호 키: 1

구조 자체도 엉망이다. 주문 시트는 2줄 병합 헤더(`고객`→ID/이름, `상품`→코드/상품명/수량, `금액`→단가/할인율/결제금액) 아래에 월별 소계, 중간에 다시 붙여넣은 헤더, "※ 2월분은 POS에서 복붙함" 메모가 섞여 있다. 상품 시트에는 표가 두 개(상품 마스터, 단종 상품) 들어 있다.

## 3. 무엇을 왜 했나 (단계별 논거)

순서는 고정이다. **구조 → 텍스트 → 밀린 행 → 타입 → 범주 → 중복 → 교차검증 → 조인.** 정규화가 끝나기 전에는 중복을 비교하지 않는다. 표기만 다른 중복은 정규화한 뒤에야 같은 행으로 보이기 때문이다(아래 예시 2).

| 표 | 들어온 행 | 정리된 행 | 빠진 행 (사유) |
|---|---|---|---|
| products | 13 | 8 | blank 2, header 1, note 1, title 1 |
| discontinued_products | 3 | 2 | header 1 |
| customers | 20 | 16 | blank 1, duplicate 1, header 1, title 1 |
| orders | 53 | 37 | blank 3, duplicate 2, header 2, note 2, repeated_header 1, subtotal 4, title 2 |
| returns | 8 | 6 | header 1, title 1 |

| 규칙 | 바뀐 셀 수 | 무엇을, 왜 |
|---|---|---|
| C1-ALIAS | 48 | 계약서 동의어 표로 변환 (card→카드, N페이→네이버페이). 동의어만 적고 오타는 적지 않음 |
| C1-CANON | 34 | 대소문자·띄어쓰기·구두점만 다른 값을 정식 값으로 (콜드브루원액500ml→콜드브루 원액 500ml) |
| C1-FUZZY | 13 | 자모 유사도가 기준(0.78) 이상이고 2등과 차이가 충분할 때만 오타 교정 (서을→서울). 숫자나 끝 글자(A/B)만 다르면 금지 |
| D1-DATE | 56 | 날짜를 ISO로 (엑셀 시리얼, 2024.1.5, 24/01/07, 20240112, 2024년 2월 3일, DD.MM.YYYY) |
| D1-ORDER | 1 | 일/월 순서는 열 단위로 12 넘는 값이 결정. 결정 못 하면 기본값을 쓰고 플래그 |
| D1-YEAR | 3 | 연도 없는 날짜(1월 9일)는 그 열에서 가장 많은 연도로 채우고 신뢰도를 낮춰 기록 |
| E1-EMAIL | 2 | 이메일 앞뒤 공백 제거, 소문자 |
| I1-ID | 44 | ID를 계약서 패턴으로 파싱해 정식 형식으로 (c-1, C 0003, 0004, 숫자 4 → C0001...). 텍스트로 유지 |
| M1-PLACEHOLDER | 14 | -, N/A, 없음, #N/A를 빈칸으로. 빈칸은 절대 채우지 않음 |
| N1-KCOUNT | 18 | 두개→2, 3개→3, 2 EA→2 |
| N1-KUNIT | 12 | 값에 적힌 단위만 적용 (1.5만원→15000, 13.5천원→13500, 4만5천원→45000) |
| N1-NUMBER | 78 | ₩, 원, 쉼표, 공백 제거, (1,200)→-1200, 소수점 쉼표는 열 단위 판단 |
| N1-PERCENT | 9 | 10%→10 |
| P1-PHONE | 8 | 유효한 번호일 때만 010-1234-5678 형식으로. 아니면 손대지 않고 플래그 |
| S2-MERGE | 6 | 병합 셀 값을 범위 전체에 채움 |
| S3-SHIFT | 22 | 밀린 행을 되돌림 (빈 칸만 지우거나 끼움) |
| T1-MOJIBAKE | 1 | 깨진 글자 복구 (UTF-8을 cp1252로 잘못 읽은 경우) |
| T1-NFKC | 32 | 전각→반각 (２０２４→2024, Ｃ０００５→C0005). 한글 낱자(ㄹ, ㅋ)는 보존 |
| T1-WS | 39 | 앞뒤 공백, 연속 공백, 제로폭 문자 제거 |

모든 변경은 `Change log` 시트에 셀 단위로 남는다. 변경 440줄 각각에 before, after, 규칙, 신뢰도, 근거가 있다. 자체 검사는 셀마다 원본값에서 최종값까지 변경 사슬이 끊김 없이 이어지는지, 들어온 행 = 남은 행 + 빠진 행인지, placeholder 말고 값이 사라진 칸이 없는지를 코드로 확인한다. 결과는 15/15 PASS.

## 4. 제일 지독한 케이스 before → after

**① 한 칸 밀린 행 (주문 시트 29행, O-2024-0019).** 누가 고객ID 앞에 빈 칸을 하나 끼워넣어서 오른쪽 값이 전부 한 칸씩 밀렸다.

- 원본: `O-2024-0019 \| 2024/2/13 \|  \| c-2 \| 이수진 \| P006 \| 디카페인 콜드브루 500ml \| 1 EA \| 19.5천원 \| 10 \| 17550 \| 네이버페이 \| 완료 \| 문 앞에 놔주세요`
- 정리: customer_id `C0002`, customer_name `이수진`, product_code `P006`, qty `1`, unit_price `19500`, discount `10`, amount `17550`, payment `네이버페이`, status `배송완료`
- 근거: `shift left by 1 from column #3: type violations 6 -> 0`. 열마다 "이 값이 이 열에 맞나"(ID 패턴, 날짜, 숫자 범위, 어휘)를 세고, 빈 칸만 지우거나 끼워넣는 이동 중 위반이 0~1개로 줄어드는 것만 받아들인다. 데이터 값은 절대 지우지 않는다.
- 반대로 날짜 칸이 통째로 지워진 45행(O-2024-0033)은 오른쪽으로 한 칸 되돌린다. 비어버린 날짜는 지어내지 않고 R7(필수값 빈칸)로 넘긴다. 정리된 날짜: (빈칸), 고객ID `C0007`, 결제 `카느`

**② 표기만 다른 완전 중복 (행 36과 37).**

- 원본 36행: `O-2024-0025 \| 20240302 \| c-13 \| 임재범 \| p-05 \| 콜드브루 원액 500 ml \| １ \| 1.8만원 \| 0 \| 18000 \| card \| 완료`
- 원본 37행: `O-2024-0025 \| 45353 \| c0013 \| 임재범 \| p-05 \| 콜드브루 원액 500 ml \| １ \| ₩18,000 \| 0 \| 18,000원 \| card \| 완료`
- 근거: `identical to row 36 after normalization; raw text differed in order_date, customer_id, unit_price, amount`. 날짜(`20240302` vs 시리얼 `45353`), 고객ID(`c-13` vs `c0013`), 금액(`1.8만원` vs `₩18,000`)이 정규화 후 모두 같아져서 뒤 행을 `Dropped rows`로 보냈다. 지운 게 아니라 원본값 그대로 옮겨 둔 것이다.

**③ 모지바케 + 제로폭 문자 + 전각.**

- 주문 15행 고객명: `'ë°•ì§€í›ˆ'` → `'박지훈'` *[T1-MOJIBAKE]*
- 주문 17행 고객명: `'\u200b한지민'` → `'한지민'` *[T1-WS]*
- 주문 14행 주문일자: `'２０２４．１．１６'` → `'2024.1.16'` *[T1-NFKC]* → `'2024-01-16'` *[D1-DATE]*
- 주문 10행 고객ID: `'c0005 '` → `'c0005'` *[T1-WS]* → `'C0005'` *[I1-ID]*

**④ 2줄 병합 헤더와 병합된 날짜 셀.** 4~5행 헤더를 `금액`+`단가` 같은 식으로 합쳐 계약서의 열 이름과 맞췄다(`Dropped rows`의 header 행 근거에 열 매핑이 남는다). 같은 날 주문 두 건이 날짜 셀 하나를 병합해서 쓰고 있었다. 주문 9행 주문일자: (빈칸) → `'2024-01-07'` *[S2-MERGE]*

**⑤ 오타는 고치되, 애매하면 손대지 않는다.**

- customers 6행 region: `'서을'` → `'서울'` *[C1-FUZZY]*. 근거: `'서을' ~ '서울' (jamo similarity 0.80; next best 세종 0.27)`
- orders 8행 status: `'배송완ㄹ'` → `'배송완료'` *[C1-FUZZY]*. 근거: `'배송완ㄹ' ~ '배송완료' (jamo similarity 0.95; next best 배송중 0.59)`
- products 7행 category: `'콜드브류'` → `'콜드브루'` *[C1-FUZZY]*. 근거: `'콜드브류' ~ '콜드브루' (jamo similarity 0.89; next best 드립백 0.35)`
- orders 22행 product_name: `'에티오피아 예가채프 200g'` → `'에티오피아 예가체프 200g'` *[C1-FUZZY]*. 근거: `'에티오피아 예가채프 200g' ~ '에티오피아예가체프200g' (jamo similarity 0.95; next best 콜롬비아 수프리모 1kg 0.33)`
- customers 10행 phone `1066667777` → **안 고치고 리뷰로**: phone 1066667777 is not a valid Korean number (looks like a leading 0 was lost; not rebuilt)
- orders 25행 order_date `2024-03-02` → **안 고치고 리뷰로**: '03/02/2024' could be MDY=2024-03-02, DMY=2024-02-03: which one?
- orders 24행 discount_pct `0.1` → **안 고치고 리뷰로**: 0.1 looks like a fraction in a 0-100 percent column: is it 10%? (not converted)
- orders 9행 payment `카느` → **안 고치고 리뷰로**: '카느' is not in the vocabulary (closest '카드' at 0.75, runner-up '카카오페이' at 0.29): map it, or add it as a new value?

`카느`→`카드`는 자모 하나 차이(유사도 0.75)지만 일부러 자동으로 고치지 않는다. 두 글자 단어는 자모 하나만 달라도 전혀 다른 말일 수 있어서다(경주/광주). 블라인드 데이터에서도 같은 원칙으로 `수학 심화B`(없는 강좌)를 `수학 심화A`로 바꾸지 않고 멈췄다.

## 5. 조인 결과

| 조인 | 매칭률 (원본 키 그대로) | 매칭률 (정규화 후) | 이름으로 대체 매칭 | 고아 | 모호 | 비고 |
|---|---|---|---|---|---|---|
| orders → customers | 16.2% | **94.6%** | 0 | 2 | 0 | - |
| orders → products+discontinued_products | 35.1% | **100.0%** | 2 | 0 | 0 | 1 matched in discontinued_products |
| returns → orders | 50.0% | **66.7%** | 0 | 1 | 1 | - |

- orders_full 왼쪽 38행 `K0014`: J2-ORPHAN, no row in customers with customer_id='K0014'
- orders_full 왼쪽 42행 `C0099`: J2-ORPHAN, no row in customers with customer_id='C0099'
- returns_orders 왼쪽 4행 `O-2024-0010`: J3-AMBIG, 2 rows in orders share this key; not joined to avoid multiplying rows
- returns_orders 왼쪽 6행 `O-2024-0099`: J2-ORPHAN, no row in orders with order_id='O-2024-0099'

원본 키 그대로면 VLOOKUP이 주문의 16%만 고객을 찾는다. ID를 계약서 패턴(`C{n:04d}`)으로 맞춘 뒤에는 고아 2건(`C0099`는 마스터에 없음, `K0014`는 접두어 오타라 리뷰로)을 빼고 전부 붙는다. 상품코드가 빈 2건은 정규화된 상품명으로 붙였고, 그 사실이 `_join_prod` 열에 남는다. 단종 상품 P009는 두 번째 표(단종 상품)에서 찾았다. 반품의 `O-2024-0010`은 주문 쪽에 같은 번호가 두 행이라 **일부러 조인하지 않았다**. 붙이면 행이 불어난다.

## 6. 소계·합계 대사

| 행 | 라벨 | 시트에 적힌 값 | 정리 후 합 | 차이 | 설명 |
|---|---|---|---|---|---|
| 19 | 1월 소계 | 311,850 | 298,350 | 13,500 | difference = dropped duplicate rows |
| 35 | 2월 소계 | 343,400 | 306,950 | 36,450 | 36,450 unexplained: amount is blank/unparsed on row(s) 33, likely the missing value |
| 49 | 3월 소계 | 456,900 | 438,900 | 18,000 | difference = dropped duplicate rows |
| 51 | 합계 | 1,112,150 | 1,044,200 | 67,950 | 31,500 from dropped duplicates; 36,450 unexplained: amount is blank/unparsed on row(s) 33, likely the missing value |

사람이 시트에서 합계를 낼 때는 복붙된 중복 행까지 더했다. 차이가 정확히 빠진 중복 행의 금액이면 "설명됨"이고, `#N/A`처럼 비어버린 값이 원인이면 그 행 번호를 짚어준다.

## 7. 사람이 결정할 것 (Needs human review)

총 31건. 규칙별 건수: J2-ORPHAN 3, J3-AMBIG 1, R1-DATE 3, R2-NUMBER 3, R4-CATEGORY 6, R5-INVALID 5, R6-CROSS 3, R7-REQUIRED 1, U2-SUSPECT 4, U3-KEYCONFLICT 2

| 표 | 행 | 열 | 값 | 플래그 | 제안 | 질문 |
|---|---|---|---|---|---|---|
| customers | 10 | phone | `1066667777` | R5-INVALID | 01066667777 | phone 1066667777 is not a valid Korean number (looks like a leading 0 was lost; not rebuilt) |
| customers | 16 | phone | `'010-565-7878'` | R5-INVALID | - | phone '010-565-7878' is not a valid Korean number |
| customers | 5 | email | `'sujin@gmail'` | R5-INVALID | - | email 'sujin@gmail' is malformed: what is the right address? |
| customers | 6 | email | `'jihoon.park@@daum.net'` | R5-INVALID | - | email 'jihoon.park@@daum.net' is malformed: what is the right address? |
| customers | 13 | join_date | `'2023-13-01'` | R1-DATE | - | '2023-13-01' is not a valid date (impossible day/month or unknown format): what date was meant? |
| customers | 20 | grade | `'VlP'` | R4-CATEGORY | VIP | 'VlP' is not in the vocabulary (closest 'VIP' at 0.67, runner-up '일반' at 0.00): map it, or add it as a new value? |
| customers | 11 | customer_id | `'C0007'` | U2-SUSPECT | customers-S2 | possible duplicate (same email + phone) in group customers-S2: same record? |
| customers | 14 | customer_id | `'C0016'` | U2-SUSPECT | customers-S2 | possible duplicate (same email + phone) in group customers-S2: same record? |
| orders | 33 | amount | (빈칸) | R2-NUMBER | - | Excel error '#N/A' in the source: what was the real value? |
| orders | 25 | order_date | `'2024-03-02'` | R1-DATE | 2024-03-02 | '03/02/2024' could be MDY=2024-03-02, DMY=2024-02-03: which one? |
| orders | 30 | order_date | `'2024-02-30'` | R1-DATE | - | '2024-02-30' is not a valid date (impossible day/month or unknown format): what date was meant? |
| orders | 38 | customer_id | `'K0014'` | R5-INVALID | - | ID 'K0014' does not match the expected pattern: which record is it? |
| orders | 42 | customer_name | `'문지호'` | R4-CATEGORY | - | '문지호' is not in the vocabulary (closest '배수지' at 0.46, runner-up '이수진' at 0.43): map it, or add it as a new value? |
| orders | 46 | product_name | `'콜브 원액'` | R4-CATEGORY | 콜드브루 원액 500ml | '콜브 원액' is not in the vocabulary (closest '콜드브루 원액 500ml' at 0.71, runner-up '콜롬비아 수프리모 1kg' at 0.31; not auto-mapped because numbers differ (- vs 500)): map it, or add it as a new value? |
| orders | 28 | qty | `'two'` | R2-NUMBER | - | 'two' is not a number: what value was meant? |
| orders | 24 | discount_pct | `0.1` | R2-NUMBER | 10.0 | 0.1 looks like a fraction in a 0-100 percent column: is it 10%? (not converted) |
| orders | 9 | payment | `'카느'` | R4-CATEGORY | 카드 | '카느' is not in the vocabulary (closest '카드' at 0.75, runner-up '카카오페이' at 0.29): map it, or add it as a new value? |
| orders | 39 | payment | `'카느'` | R4-CATEGORY | 카드 | '카느' is not in the vocabulary (closest '카드' at 0.75, runner-up '카카오페이' at 0.29): map it, or add it as a new value? |
| orders | 45 | payment | `'카느'` | R4-CATEGORY | 카드 | '카느' is not in the vocabulary (closest '카드' at 0.75, runner-up '카카오페이' at 0.29): map it, or add it as a new value? |
| orders | 45 | order_date | (빈칸) | R7-REQUIRED | - | order_date is required but blank: what is it? (not imputed) |
| orders | 16 | order_id | `'O-2024-0010'` | U3-KEYCONFLICT | - | same order_id O-2024-0010 with different qty, amount: which row is right? |
| orders | 23 | order_id | `'O-2024-0010'` | U3-KEYCONFLICT | - | same order_id O-2024-0010 with different qty, amount: which row is right? |
| orders | 43 | order_id | `'O-2024-0031'` | U2-SUSPECT | orders-S4 | possible duplicate (same customer_id + order_date + product_code + qty + amount) in group orders-S4: same record? |
| orders | 44 | order_id | `'O-2024-0032'` | U2-SUSPECT | orders-S4 | possible duplicate (same customer_id + order_date + product_code + qty + amount) in group orders-S4: same record? |
| orders | 24 | amount | `32400` | R6-CROSS | 35964 | amount differs from qty x unit_price x (1 - discount%) (suggestion = computed value) (this row also has open flags on discount_pct; fix those first) |
| orders | 40 | amount | `135000` | R6-CROSS | 13500 | amount differs from qty x unit_price x (1 - discount%) (suggestion = computed value) |
| orders | 27 | customer_name | `'최유리'` | R6-CROSS | 박지훈 | customer_name '최유리' differs from customers.name '박지훈' for customer_id=C0003: which is right? |
| orders | 38 | customer_id | `'K0014'` | J2-ORPHAN | - | customer_id='K0014' not found in customers: typo, or missing master row? |
| orders | 42 | customer_id | `'C0099'` | J2-ORPHAN | - | customer_id='C0099' not found in customers: typo, or missing master row? |
| returns | 4 | order_id | `'O-2024-0010'` | J3-AMBIG | - | order_id=O-2024-0010 matches 2 rows: which one? |
| returns | 6 | order_id | `'O-2024-0099'` | J2-ORPHAN | - | order_id='O-2024-0099' not found in orders: typo, or missing master row? |

결정은 계약서 `overrides:`에 적고 다시 돌리면 반영되고, 해당 리뷰 항목은 사라진다. 카느→카드, 03/02/2024→2024-02-03 두 건으로 실제로 돌려서 확인했다.

## 8. 채점표 (정답표 대비, 유형별)

| 유형 | 고침 | 플래그 | 틀림 | 놓침 |
|---|---|---|---|---|
| 빈칸 표기 (-, N/A, 없음) | 11 | 0 | 0 | 0 |
| 범주 오타·동의어 (서을, 겅기, 카느, 배송완ㄹ, card, N페이, 콜드브류 …) | 74 | 2 | 0 | 0 |
| cross_check | 0 | 1 | 0 | 0 |
| cross_table | 0 | 1 | 0 | 0 |
| date_ambiguous | 0 | 1 | 0 | 0 |
| 날짜 형식 뒤죽박죽 (엑셀 시리얼, 2024.1.5, 24/01/07, 1월 9일, 20240112, 전각 ２０２４．３．１ …) | 54 | 0 | 0 | 0 |
| date_invalid | 0 | 1 | 0 | 0 |
| 유럽식 숫자 13.500,00 | 6 | 0 | 0 | 0 |
| 완전 중복 (복붙, 표기만 다른 같은 주문) | 3 | 0 | 0 | 0 |
| email_case | 2 | 0 | 0 | 0 |
| encoding | 1 | 0 | 0 | 0 |
| excel_error | 0 | 1 | 0 | 0 |
| ID 표기 제각각 (c-1, C 0003, 0004, Ｃ０００５, 숫자 셀 4) | 51 | 0 | 0 | 0 |
| id_invalid | 0 | 1 | 0 | 0 |
| 망가진 값 (도메인 없는 이메일, 0 빠진 전화, 13월) | 0 | 6 | 0 | 0 |
| 조인 모호 키 | 0 | 1 | 0 | 0 |
| join_discontinued | 1 | 0 | 0 | 0 |
| 상품코드가 비어 이름으로만 조인 가능 | 2 | 0 | 0 | 0 |
| 조인 고아 키 | 0 | 2 | 0 | 0 |
| 같은 주문번호, 다른 내용 | 0 | 2 | 0 | 0 |
| 병합 셀 (날짜, 지역) | 5 | 0 | 0 | 0 |
| multi_table | 1 | 0 | 0 | 0 |
| 상품명 띄어쓰기·오타 | 13 | 1 | 0 | 0 |
| 유사 중복 (더블 클릭 주문, 같은 사람 재가입) | 0 | 2 | 0 | 0 |
| number_scale | 0 | 1 | 0 | 0 |
| 텍스트 숫자 (₩12,000 / 12000원 / 1.5만원 / 13.5천원 / 3개 / 2 EA / ２) | 95 | 1 | 0 | 0 |
| 전화번호 형식 | 7 | 0 | 0 | 0 |
| 소계·합계 대사 | 2 | 2 | 0 | 0 |
| 한 칸 밀린 행 (오른쪽 1, 왼쪽 1) | 9 | 2 | 0 | 0 |
| 제목/메모/반복 헤더/소계·합계/빈 행 | 14 | 0 | 0 | 0 |
| 공백/제로폭 문자/모지바케 | 4 | 0 | 0 | 0 |
| 함정 (동명이인 김민수, 다른 날 같은 상품 재주문, 할인율 0) | 3 | 0 | 0 | 0 |

채점은 `demo/score.py`가 정리된 xlsx 파일 자체(Cleaned/Review/Dropped/Join report 시트)를 읽어서 한다. 내부 변수는 보지 않는다. "플래그"는 사람이 정해야 맞는 문제를 리뷰 목록에 올린 경우다. 사람 몫인 문제를 플래그 없이 조용히 정답으로 바꾼 경우는 "운 좋은 추측"으로 따로 세고 처리 실패로 친다.

## 9. 블라인드 테스트 (만들면서 한 번도 안 본 데이터)

`blind/` 학원 데이터, 심은 문제 114개. 하루커피에 없던 유형이 들어 있다. 병합된 제목 줄, 영문 헤더, `No.` 순번 열, 형제가 같은 학부모 번호를 쓰는 경우, `01O-5678-9012`(숫자 0 대신 영문 O), `△15,000`, `Feb 16, 2024`, `3/3`(연도 없음), `-2만`, `150,000원(할인전)`, `평균` 행, 세미콜론 구분 CSV 안의 여러 줄 메모, 없는 강좌 `수학 심화B`.

- **첫 실행 (코드 수정 전): 처리율 93.9%, 고침 93, 플래그 14, 틀림 2, 놓침 5, 셀 정확도 92.5%.**
- 첫 실행에서 드러난 구멍과 원인을 한 번에 하나씩 일반 규칙으로 고쳤다.
  - CSV 안에 여러 줄짜리 셀이 있으면 그 뒤 행 번호가 한 줄씩 밀렸다 → 행 번호를 물리적 줄 번호로 기록
  - `No.` 순번 열 때문에 복붙 중복을 못 잡았다 → 1씩 증가하는 순번 열은 중복 비교에서 제외 (근거는 notes에 남김)
  - 형제의 같은 학부모 번호를 중복 후보로 올렸다 → 연락처는 두 개가 겹치거나, 하나 + 이름 유사도 0.8 이상일 때만 후보로
  - 셔틀 `X`(=N)를 빈칸 표기로 보고 지웠다 → 그 열 어휘에 있는 말이면 빈칸 처리 안 함
  - `평균` 행을 데이터로 읽었다 → 평균/최대/최소도 집계 행으로 (합계만 대사)
  - `Feb 16, 2024`, `-2만`, `△` → 영문 월 이름, 단위 앞 음수, 회계용 △ 지원
  - `수학 심화B`를 0.91 유사도로 `수학 심화A`에 붙였다 (조용한 오답) → 숫자나 끝 글자(A/B)만 다르면 자동으로 매핑 안 함
- 고친 뒤: 처리율 100.0%, 틀림 0, 셀 정확도 96.8%. 고친 규칙이 블라인드 데이터를 보고 만든 것이라, 이 두 번째 숫자는 첫 실행 숫자만큼 믿을 만한 건 아니다. 하루커피 점수가 떨어지지 않았는지도 다시 확인했다.

## 10. 재실행·멱등성 증명

- 같은 입력으로 두 번 돌리고(파이썬 해시 시드 1과 2) 산출물 10개(xlsx, json 2개, csv 7개)의 sha256을 비교했다. **완전히 같다.** 파일은 임시 경로에 쓴 뒤 rename하고, xlsx 내부 zip의 타임스탬프를 고정한다.
- 정리된 CSV를 같은 계약서로 한 번 더 정리했다. `fixed-point check: 0 value changes, 0 rows dropped on the second pass (211 representation-only log lines such as '12000' -> 12000; 31 review items carried over)`
- 블라인드: `fixed-point check: 0 value changes, 0 rows dropped on the second pass (73 representation-only log lines such as '12000' -> 12000; 16 review items carried over)`
- 원본 파일의 sha256은 실행 전후로 같다. 원본은 읽기만 한다.
- 파서와 LLM 게이트 동작 검사: `python3 skill/messy-data-cleanup/scripts/selftest.py`, 58/58 behavior checks pass. API 호출 없이 돈다.

## 11. LLM 레이어 (선택, `--llm live`)

규칙 엔진이 뼈대이고 감사 기록이다. LLM은 규칙이 이미 골라내고 **결정하지 못한** 항목만 받는다. 답은 규칙이 계산한 후보 중 하나이거나 그 셀에서 그대로 인용한 값이어야 한다. 그리고 결정적 게이트를 통과해야만 적용된다. 통과하지 못한 답은 `Needs human review`에 'LLM이 무엇을 제안했고 왜 적용하지 않았는지'와 함께 남는다. 적용된 답은 Change log에 `llm:<task>` 규칙으로, `model=…; conf=…; quote=…; why=…` 근거와 함께 기록된다. 설계 문서는 `docs/LLM_LAYER_PLAN.md`.

| 작업 | 하는 일 | 적용 조건 (게이트) |
|---|---|---|
| `llm:synonym` | 어휘에 없는 범주값 → 어휘값 (무통장입금→계좌이체, Visa→카드, delivered→배송완료) | 어휘값일 것, 인용이 셀·행에서 나올 것(후보 목록 인용은 무효), 신뢰도 ≥ 0.8, 계약 검사 통과. 마스터 이름 열에서는 철자가 비슷할 것 |
| `llm:resolve` | 애매한 날짜(03/02/2024), 0.1 vs 10% | 규칙이 만든 후보일 것. 날짜는 앞뒤 확정 날짜 사이에 들어가는 **유일한** 해석일 것, 퍼센트는 열의 값 범위 안일 것 |
| `llm:extract` | 메모 → 새 열 (선물포장 여부, 연락처, 희망일, 초 개수, 문구) | 셀 안의 원문을 그대로 인용할 것, 타입이 맞고 인용과 값이 일치할 것, 인용에 스키마 필드 이름이 없을 것. AI에게 하는 지시처럼 보이는 셀은 아예 보내지 않고 R9로 표시 |
| `llm:entity` | 조인 고아 키·빈 키 → 마스터 후보 5개 중 하나 (Kim Minsu → 김민수 C0001) | 후보일 것, 신뢰도 ≥ 0.85, 이메일·전화·ID 비교 열 하나 이상이 양쪽에서 같을 것. 이름만 비슷한 것은 절대 인정하지 않음 |
| 레이아웃 (`profile.py --llm`) | 시트 미리보기 → 표 위치, 헤더 행, 열 이름과 타입 | 헤더 행이 실제로 있고 헤더 글자가 셀과 일치할 것. 계약서 초안에 힌트로만 들어간다 |

모든 답은 (작업, 프롬프트 버전, 모델, 입력)의 해시로 `llm_cache/`에 저장된다. 그래서 재실행과 오프라인 재생(`--llm cache`, API 키 없이)이 바이트 단위로 같다. 사람이 쓴 `overrides:`가 LLM보다 먼저 적용되고 항상 이긴다. 기본 모델은 OpenRouter `google/gemini-2.5-flash-lite`(temperature 0)이다. 캐시에 남은 호출 36회의 비용 합계는 $0.0264이다 (`llm_cache/*/*.json`의 usage.cost 합. 개발 중에 버려진 호출 몇 번은 빠져 있다).

### 11-1. 절제 실험: 규칙만 vs 규칙+LLM (같은 채점기)

| 세트 | 모드 | 처리율 | 자동 해결률 | LLM이 맞게 해결 | 잘못 바꿈 | 놓침 | 셀 정확도 | 리뷰 큐 | 조인 매칭률 | LLM 변경 (틀림) |
|---|---|---|---|---|---|---|---|---|---|---|
| 하루커피 데모 | 규칙만 | 100.0% | 92.8% | 0 | 0 | 0 | 97.0% | 31 | 94.6%, 100.0%, 66.7% | 0 (0) |
| 하루커피 데모 | 규칙+LLM | 100.0% | 94.0% | 5 | 0 | 0 | 97.8% | 26 | 94.6%, 100.0%, 66.7% | 5 (0) |
| 학원 블라인드 | 규칙만 | 100.0% | 89.5% | 0 | 0 | 0 | 96.8% | 16 | 94.4%, 88.9%, 83.3% | 0 (0) |
| 학원 블라인드 | 규칙+LLM | 100.0% | 91.2% | 2 | 0 | 0 | 97.6% | 13 | 94.4%, 94.4%, 83.3% | 2 (0) |
| 의미 문제 세트 (게이트 조정에 씀) | 규칙만 | 68.4% | 18.4% | 0 | 0 | 11 | 92.6% | 21 | 82.1% | 0 (0) |
| 의미 문제 세트 (게이트 조정에 씀) | 규칙+LLM | 100.0% | 73.7% | 21 | 0 | 0 | 98.4% | 12 | 92.9% | 21 (0) |
| 의미 블라인드 (게이트 조정 후 처음 돌림) | 규칙만 | 75.0% | 20.8% | 0 | 0 | 5 | 91.5% | 12 | 80.0% | 0 (0) |
| 의미 블라인드 (게이트 조정 후 처음 돌림) | 규칙+LLM | 95.8% | 70.8% | 12 | 1 | 0 | 98.0% | 6 | 93.3% | 13 (1) |

- 처리율 = 맞게 고침 + LLM이 맞게 고침 + 사람에게 넘김. 자동 해결률 = 사람 손 없이 맞게 끝난 비율. 규칙만으로 돌리면 의미 문제 세트에서 메모 추출과 빈 키 매칭을 아예 못 해서 '놓침'이 된다.
- 데모와 학원 세트는 원래 규칙이 강한 데이터라 LLM 효과가 작다. 여기서 LLM이 푼 것은 카느→카드 3건, VlP→VIP, 콜브 원액→콜드브루 원액 500ml 같은 것이다. 03/02/2024와 0.1은 모델이 틀린 쪽을 골랐고, 게이트가 막아서 리뷰에 남았다.
- 하루커피 데모: 캐시에 저장된 호출 9회 (토큰 14144+3117, $0.0026, 모델 여러 개 포함). 재실행 시 호출 0회. 재실행 결과 동일: 예, 키 없이 캐시만으로 재생한 결과 동일: 예
- 학원 블라인드: 캐시에 저장된 호출 9회 (토큰 6869+1789, $0.0014, 모델 여러 개 포함). 재실행 시 호출 0회. 재실행 결과 동일: 예, 키 없이 캐시만으로 재생한 결과 동일: 예
- 의미 문제 세트 (게이트 조정에 씀): 캐시에 저장된 호출 12회 (토큰 24349+13294, $0.0159, 모델 여러 개 포함). 재실행 시 호출 0회. 재실행 결과 동일: 예, 키 없이 캐시만으로 재생한 결과 동일: 예
- 의미 블라인드 (게이트 조정 후 처음 돌림): 캐시에 저장된 호출 6회 (토큰 7403+4182, $0.0065, 모델 여러 개 포함). 재실행 시 호출 0회. 재실행 결과 동일: 예, 키 없이 캐시만으로 재생한 결과 동일: 예
- 하루커피에서 LLM 제안이 게이트에 막혀 리뷰에 남은 것: 25행 order_date → 제안 '2024-03-02', 사유: chosen date is outside the neighbours' range 2024-02-03..2024-02-06; 42행 customer_name → 제안 '송하늘', 사유: evidence is not a verbatim quote of the cell or its row; 24행 discount_pct → 제안 '0.1', 사유: chosen value is outside the column's range 5..10

### 11-2. LLM이 틀린 비율 (정직하게)

- **게이트를 다듬기 전 첫 라이브 실행** (의미 세트): LLM 변경 22건 중 **5건 틀림 (22.7%)**. 모델이 틀린 것들은 이렇다.
  - 4행 `order_date`: '2024-03-02' (정답 '2024-02-03'). 모델 근거: The row's order_date is 2024-03-02, and the neighbours are all in February 2024, suggesting the current row is later. Thus, 03/02/2024 is li
  - 23행 `order_date`: '2024-04-03' (정답 '2024-03-04'). 모델 근거: The row's order_date is 2024-04-03. The neighbours are mostly in March 2024, with one in May 2024. The value 04/03/2024 is most consistent w
  - 26행 `order_date`: '2024-05-03' (정답 '2024-03-05'). 모델 근거: The row's order_date is 2024-05-03. The neighbours include dates in March and May 2024. The value 05/03/2024 is most consistent with May 3rd
  - 20행 `note.gift_wrap`: True (정답 None). 모델 근거: field gift_wrap from note
  - 20행 `note.requested_date`: '2024-12-25' (정답 None). 모델 근거: field requested_date from note
  - 그리고 인용 검사가 우연히 막은 것: 이름만 같은 다른 사람(김민수, 다른 이메일)을 C0001로 신뢰도 1.00으로 매칭하려 했다.
- 이 실패를 보고 게이트를 넣었다. 날짜는 앞뒤 행 사이에 유일하게 맞는 해석일 것, 지시문처럼 보이는 셀은 보내지 않을 것, 판단할 셀의 현재 값(규칙의 기본 추측)은 보여주지 않을 것, 엔티티 매칭은 이메일이나 전화가 같을 것. 모델을 믿는 대신 모델이 틀려도 데이터가 망가지지 않게 만든 것이다. 그 뒤 의미 세트의 LLM 틀림은 0건이다. 다만 이 숫자는 그 세트에 맞춰 다듬은 결과다.
- **게이트 조정 후 처음 돌린 의미 블라인드** (베이커리 픽업 주문, 다른 어휘·다른 메모 필드): LLM 변경 13건 중 **1건 틀림 (7.7%)**.
  - 7행 `status`: '완료' (정답 '픽업대기'). 모델 근거: The value '다 만들었어요 찾아가세요' translates to 'It's all made, please come pick it up.' This implies the order is complete and ready for pickup, which aligns with the 
  - 그럴듯한 어휘값 사이의 의미 판단은 게이트로 못 막는다. 이런 값은 계약서 vocab에 동의어로 넣거나, 그 데이터에서는 `llm.tasks`에서 synonym을 빼는 게 맞다.
- 비교용으로 더 큰 모델 `google/gemini-2.5-flash`를 의미 블라인드 (게이트 조정 후 처음 돌림)에 돌렸다: 자동 해결률 50.0%, LLM 변경 7건 중 0건 틀림.
- 비교용으로 더 큰 모델 `google/gemini-2.5-flash`를 의미 문제 세트 (게이트 조정에 씀)에 돌렸다: 자동 해결률 76.3%, LLM 변경 23건 중 1건 틀림 (18행 '반품' (정답 '환불 요청 접수')).
- 덫(LLM이 손대면 안 되는 것: 대응 어휘가 없는 값 포인트·상품권·외상·노쇼, 맥락이 결정 못 하는 날짜, 상대 날짜, 프롬프트 주입 메모, 이름만 비슷한 고객) 22건: 게이트 적용 후 flash-lite 기준 결과 {'flagged': 11, 'fixed': 11}. 'fixed'는 빈칸이 맞는 칸을 빈칸으로 둔 것, 'flagged'는 사람에게 넘긴 것이다.

### 11-3. 레이아웃 읽기 (표 위치·헤더 행)

| 세트 | 표 수 | 규칙 프로파일이 맞힌 헤더 | LLM 레이아웃이 맞힌 헤더 |
|---|---|---|---|
| 하루커피 데모 | 5 | 3 | 5 |
| 학원 블라인드 | 4 | 4 | 4 |
| 의미 문제 세트 (게이트 조정에 씀) | 2 | 2 | 2 |

하루커피에서 규칙 프로파일은 2줄 병합 헤더를 5행 하나로 읽었다. 그리고 상품 시트 아래쪽의 두 번째 표(단종 상품)를 못 봤다. LLM은 둘 다 맞혔다. 그래도 결과는 초안 힌트일 뿐이고, 계약서는 사람이 확정한다.

## 12. 한계 (정직하게)

- 계약서는 사람(에이전트)이 쓴다. 프로파일이 초안을 주지만 키, ID 패턴, 동의어는 직접 정해야 한다. 동의어(card→카드)를 안 넣으면 그 값은 리뷰로 간다.
- 퍼지 매칭은 한글 자모 유사도 하나뿐이다. 두 글자 단어의 한 자모 오타(카느, 교2)는 일부러 사람에게 넘긴다. 약어(과탐→과학 탐구, 콜브 원액)는 못 푼다.
- 영어 숫자 단어("two"), 연도 없는 `3/3`, `150,000원(할인전)`처럼 숫자 뒤에 글이 붙은 값은 파싱하지 않고 플래그만 한다.
- 0.1과 10%가 섞인 할인율은 고치지 않고 플래그한다. 그래서 같은 행의 금액 검증도 함께 걸린다(메시지에 원인을 적어줌).
- 밀린 행 복구는 한 행이 1~2칸 통째로 밀린 경우만 다룬다. 값 두 개의 순서가 서로 바뀐 경우나 텍스트 열끼리 밀린 경우는 감지하기 어렵다(텍스트 열은 판정을 안 하므로).
- 모지바케 복구는 UTF-8을 cp1252/latin-1로 잘못 읽은 경우만 확실하다. UTF-8을 cp949로 잘못 읽은 경우는 대개 바이트가 이미 손실돼서 복구가 안 된다.
- 엑셀 1904 날짜 체계, 숨긴 행/시트의 의미, 수식 재계산은 다루지 않는다. 값만 읽는다.
- 중복 판단은 '같은 사건'인지까지 확인해 주지 않는다. 후보만 근거와 함께 올리고 합치지 않는다.
- 하루커피 점수는 만든 사람이 채점한 결과라 후하다. 블라인드 첫 실행 점수가 더 현실적인 숫자다.
- LLM 레이어: 결과는 모델과 데이터에 따라 다르다. 블라인드 의미 세트에서 flash-lite는 13건 중 1건을 틀렸다. 게이트는 지어낸 값, 후보 밖의 답, 근거 없는 매칭, 프롬프트 주입은 막지만, 그럴듯한 어휘값 사이의 오판은 못 막는다.
- 의미 세트 두 개와 정답표는 내가 만들었다(심은 문제 합계 62건). 실제 업무 데이터에서 다시 재야 한다. Gemini 직접 호출 경로(GEMINI_API_KEY)는 코드는 있지만, 이 환경의 키가 401(무효)이라 실제 호출로 검증하지 못했다. 측정은 전부 OpenRouter로 했다.

## 13. 파일

- 스킬: `skill/messy-data-cleanup/` (SKILL.md, reference/contract.md, templates/contract.example.yaml, scripts/)
- Cursor 룰: `.cursor/rules/messy-data-cleanup.mdc`
- 데모 입력: `demo/input/`, 정답표: `demo/ground_truth.json`, 계약서: `demo/contract.yaml`
- 데모 결과: `demo/output/haru-cleaned.xlsx` (시트 구성은 SKILL.md 참고), `demo/output/csv/`, `score.json`, `profile.md`
- 블라인드: `blind/` (같은 구조, 첫 실행 점수 `blind/first_run_score.txt`)
- LLM 절제 실험: `demo/ablation.py` → `ablation.json` (오프라인 캐시 재생), `ablation_live_run.json` (라이브 첫 실행 사용량). 의미 세트: `semantic/`, `semantic_blind/` (각 `first_live_run_score.json`)
- Gemini CLI 패키지: `gemini/` (gemini-extension.json, GEMINI.md, skills/messy-data-cleanup/)
- 전체 재현: `bash demo/run_demo.sh` (LLM은 저장된 캐시로 재생해서 키·비용 없이 돈다. 새 데이터는 `ABL_LLM=live`)
