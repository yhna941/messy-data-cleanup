# Profile (no contract; guesses to review)

## 반품교환_3PL.csv / 반품교환_3PL

- size: 8 rows x 6 cols; encoding: cp949; merged ranges: 0
- likely header: row 2
- rows below header: {'data': 6}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 반품번호 | id | 0 | 0 | 0 | 0 | 0 | R-001×1, R-002×1, r-3×1, R-004×1, R-005×1 |  |
| 주문번호 | id | 0 | 0 | 0 | 0 | 0 | O-2024-0007×1, 2024-0010×1, o20240015×1, O-2024-0099×1, O-2024-0021×1 |  |
| 접수일 | date | 0 | 0 | 0 | 0 | 1 | 15.01.2024×1, 02.02.2024×1, 13.03.2024×1, 20.03.2024×1, 05.03.2024×1 |  |
| 사유 | category | 0 | 0 | 0 | 0 | 1 | 단순변심×2, 파손×2, 오배송×1, 부분환불×1 |  |
| 환불금액 | money | 0 | 0 | 0 | 0 | 0 | 13.500,00×1, 9.000×1, 18.000,00×1, 45.000×1, 6.750,00×1 |  |
| 처리상태 | category | 0 | 0 | 0 | 0 | 0 | 환불완료×3, 교환완료×1, 처리중×1, 환불 완료×1 | 환불완료/교환완료/환불 완료 |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `return_exchange_details`: header row(s) [2], data rows 3-8, columns: 반품번호→return_id:id, 주문번호→order_id:id, 접수일→receipt_date:date, 사유→reason:category, 환불금액→refund_amount:money, 처리상태→status:category

## 하루커피_매출정리_최종_진짜최종.xlsx / 주문내역

- size: 53 rows x 14 cols; encoding: xlsx; merged ranges: 11
- likely header: row 5
- rows below header: {'data': 39, 'subtotal/total': 4, 'repeated header': 1, 'note/title': 2, 'blank': 2}
- structural rows: row 19: subtotal: 1월 소계; row 20: repeated header; row 21: note: ※ 2월분은 POS에서 복붙함 (형식 다를 수 있음); row 29: values right of the last header column (shifted row?); row 35: subtotal: 2월 소계; row 49: subtotal: 3월 소계; row 51: subtotal: 합계; row 53: note: ※ 금액은 부가세 포함

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 주문번호 | id | 2 | 0 | 0 | 0 | 0 | O-2024-0005×2, O-2024-0010×2, O-2024-0025×2, O-2024-0001×1, O-2024-0002×1 |  |
| 주문일자 | date | 8 | 0 | 3 | 0 | 2 | 2024-01-07 00:00:00×2, 20240109×2, 2024-01-20 00:00:00×2, 2024년 3월 5일×2, 45294×1 |  |
| ID | id | 9 | 0 | 7 | 0 | 7 | 0003×2, c0005×2, C0005×2, C0015×2, C0001×2 |  |
| 이름 | category | 8 | 0 | 0 | 1 | 1 | 김민수×4, 정다은×4, 최유리×3, 강호동×3, 임재범×3 | 최유리/최유진 |
| 코드 | id | 10 | 0 | 7 | 0 | 0 | P004×4, P003×4, P001×4, P005×3, P008×3 |  |
| 상품명 | category | 8 | 0 | 1 | 0 | 0 | 드립백10입세트×5, 콜드브루 원액 500 ml×4, 콜롬비아 수프리모 1kg×4, 텀블러 473ml×4, 하우스 블렌드 원두200g×3 | 드립백10입세트/드립백 10입 세트; 콜드브루 원액 500 ml/콜드브루원액500ml/콜드브루 원액 500ml/콜브 원액; 하우스 블렌드 원두200g/시즌 블렌드 200g/하우스블렌드 원두 200g; 에티오피아 예가채프 200g/에티오피아 예가체프 200g |
| 수량 | number | 8 | 0 | 10 | 0 | 0 | 1×6, 1×6, 1 EA×5, 2×4, 1개×4 |  |
| 단가 | money | 8 | 0 | 0 | 0 | 0 | 13.5천원×2, 18,000 원×2, ₩13,500×2, 25,000×2, ₩18,000×2 |  |
| 할인율 | percent | 14 | 12 | 0 | 0 | 0 | 0×6, N/A×5, 5%×4, -×4, 10 %×4 |  |
| 결제금액 | money | 4 | 1 | 0 | 0 | 0 | 13500×3, 18,000×2, 18,000원×2, ₩21,600×1, 13,000원×1 |  |
| 결제수단 | category | 8 | 0 | 0 | 0 | 0 | 카드×5, kakaopay×4, 신용카드×3, 계좌 이체×3, card×3 | 카드/카느; 계좌 이체/계좌이체; card/CARD; 네이버 페이/네이버페이 |
| 상태 | category | 8 | 1 | 5 | 0 | 6 | 배송완료×11, 배송 완료×6, 완료×5, 배송완ㄹ×5, Delivered×3 | 배송완료/배송 완료/배송완ㄹ; 반품/반품접수 |
| 비고 | category | 26 | 6 | 0 | 0 | 14 | 포장 꼼꼼히 부탁드려요×8, N/A×6, 문 앞에 놔주세요×6, 비고×1, 완료×1 |  |
| column_14 | category | 47 | 0 | 0 | 0 | 1 | 문 앞에 놔주세요×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `order_details`: header row(s) [4, 5], data rows 6-48, columns: 주문번호→order_number:id, 주문일자→order_date:date, 고객 ID→customer_id:text, 고객 이름→customer_name:text, 상품 코드→product_code:text, 상품명→product_name:text, 수량→quantity:count, 단가→unit_price:money, 할인율→discount_rate:percent, 결제금액→payment_amount:money, 결제수단→payment_method:text, 상태→status:text, 비고→notes:freetext

## 하루커피_매출정리_최종_진짜최종.xlsx / 고객명단

- size: 20 rows x 8 cols; encoding: xlsx; merged ranges: 3
- likely header: row 3
- rows below header: {'data': 17}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 고객번호 | id | 0 | 0 | 2 | 0 | 1 | C0005×2, C0001×1, c-2×1, C 0003×1, 4×1 |  |
| 이름 | text | 0 | 0 | 0 | 0 | 1 | 김민수×2, 정다은×2, 이수진×1, 박지훈×1, 최유리×1 | 최유리/최유진/최 유진 |
| 지역 | category:ko_region | 0 | 0 | 0 | 0 | 1 | 경기도×3, 서울특별시×2, 부산광역시×2, 서을×1, 겅기×1 |  |
| 연락처 | phone | 0 | 0 | 0 | 0 | 0 | 010.5555.6666×2, 010-1111-2222×1, 01022223333×1, 010 3333 4444×1, +82 10-4444-5555×1 |  |
| 이메일 | email | 0 | 0 | 0 | 0 | 1 | daeun@kakao.com×2, MINSU.KIM@NAVER.COM×1, sujin@gmail×1, jihoon.park@@daum.net×1, yuri.choi@naver.com×1 |  |
| 가입일 | date | 0 | 0 | 1 | 0 | 0 | 2023년 5월 20일×2, 2023-01-15 00:00:00×1, 44960×1, 2023.3.12×1, 23/04/01×1 |  |
| 등급 | category | 0 | 0 | 0 | 0 | 0 | 일반×6, 신규×3, 신규 회원×2, VIP×1, 일반회원×1 | 일반/일반회원/일 반; VIP/vip/V.I.P |
| 메모 | category | 12 | 1 | 0 | 0 | 0 | 단골×1, -×1, VIP 승급 검토×1, 동명이인 주의×1, 재가입?×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `customer_list`: header row(s) [3], data rows 4-20, columns: 고객번호→customer_id:id, 이름→name:text, 지역→region:text, 연락처→phone_number:phone, 이메일→email:email, 가입일→signup_date:date, 등급→grade:category, 메모→memo:freetext

## 하루커피_매출정리_최종_진짜최종.xlsx / 상품

- size: 16 rows x 5 cols; encoding: xlsx; merged ranges: 0
- likely header: row 2
- rows below header: {'data': 10, 'blank': 2, 'note/title': 1, 'repeated header': 1}
- structural rows: row 13: note: ■ 단종 상품; row 14: repeated header

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 상품코드 | id | 2 | 0 | 1 | 0 | 0 | P001×1, p-2×1, P003×1, P004×1, P005×1 |  |
| 상품명 | category | 3 | 0 | 0 | 0 | 1 | 하우스블렌드 원두 200g×1, 에티오피아 예가체프 200g×1, 콜롬비아 수프리모 1kg×1, 드립백 10입 세트×1, 콜드브루 원액 500ml×1 | 하우스블렌드 원두 200g/시즌 블렌드 200g; 드립백 10입 세트/드립백 5입 |
| 분류 | category | 3 | 0 | 0 | 0 | 1 | 원두×3, 드립백×2, 원 두×1, 콜드브류×1, 콜드 브루×1 | 원두/원 두; 콜드브류/콜드 브루 |
| 판매가 | money | 3 | 0 | 0 | 0 | 0 | 12,000원×1, 15000×1, 45,000×1, 13,500원×1, ₩18,000×1 |  |
| 출시일 | date | 3 | 0 | 0 | 0 | 0 | 2023-03-01 00:00:00×1, 2023.3.1×1, 45056×1, 2023-06-01×1, 2023년 7월 1일×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `상품_마스터`: header row(s) [2], data rows 3-10, columns: 상품코드→상품코드:id, 상품명→상품명:text, 분류→분류:category, 판매가→판매가:money, 출시일→출시일:date
- table `단종_상품`: header row(s) [14], data rows 15-16, columns: 상품코드→상품코드:id, 상품명→상품명:text, 분류→분류:category, 판매가→판매가:money, 단종일→단종일:date
