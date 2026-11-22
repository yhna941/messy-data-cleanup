# Profile (no contract; guesses to review)

## 쇼핑몰_주문.xlsx / 주문

- size: 29 rows x 9 cols; encoding: xlsx; merged ranges: 0
- likely header: row 1
- rows below header: {'data': 28}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 주문번호 | id | 0 | 0 | 0 | 0 | 0 | S-001×1, S-002×1, S-003×1, S-004×1, S-005×1 |  |
| 주문일 | date | 0 | 0 | 0 | 0 | 0 | 2024-02-01 00:00:00×1, 2024-02-02 00:00:00×1, 03/02/2024×1, 2024-02-04 00:00:00×1, 2024-02-05 00:00:00×1 |  |
| 고객ID | id | 2 | 0 | 0 | 0 | 0 | C0002×3, C0003×3, C0004×3, C0005×3, C0006×3 |  |
| 고객명 | category | 0 | 0 | 0 | 0 | 0 | 박지훈×4, 김민수×3, 이수진×3, 최유진×3, 정하늘×3 |  |
| 이메일 | email | 0 | 0 | 0 | 0 | 0 | sujin.lee@example.com×4, jihoon.park@example.com×4, minsu.kim@example.com×3, yujin.choi@example.com×3, haneul.jung@examp |  |
| 결제수단 | category | 0 | 0 | 0 | 0 | 0 | 카드×20, 무통장입금×1, Visa×1, 포인트×1, naver pay×1 |  |
| 상태 | category | 0 | 0 | 0 | 0 | 0 | 배송완료×22, delivered×1, 배달 끝났어요×1, 보류×1, shipped×1 |  |
| 할인율 | number | 0 | 0 | 0 | 0 | 0 | 0×24, 10×1, 15×1, 0.15×1, 20×1 |  |
| 요청사항 | category | 19 | 0 | 0 | 0 | 0 | 선물포장 해주세요~ 문 앞에 두고 가세요×1, 포장은 필요 없어요. 연락은 010-2233-4455로 주세요×1, 3월 8일까지 꼭 받아야 해요!! 선물용이라 포장 부탁×1, 이번 주 금요일 전에 와야 돼요×1, 부 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `order_details`: header row(s) [1], data rows 2-29, columns: 주문번호→order_number:id, 주문일→order_date:date, 고객ID→customer_id:id, 고객명→customer_name:text, 이메일→email:email, 결제수단→payment_method:category, 상태→status:text, 할인율→discount_rate:percent, 요청사항→requests:freetext

## 쇼핑몰_주문.xlsx / 고객

- size: 9 rows x 4 cols; encoding: xlsx; merged ranges: 0
- likely header: row 1
- rows below header: {'data': 8}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 고객ID | id | 0 | 0 | 0 | 0 | 0 | C0001×1, C0002×1, C0003×1, C0004×1, C0005×1 |  |
| 이름 | category | 0 | 0 | 0 | 0 | 0 | 김민수×1, 이수진×1, 박지훈×1, 최유진×1, 정하늘×1 |  |
| 이메일 | email | 0 | 0 | 0 | 0 | 0 | minsu.kim@example.com×1, sujin.lee@example.com×1, jihoon.park@example.com×1, yujin.choi@example.com×1, haneul.jung@examp |  |
| 지역 | category:ko_region | 0 | 0 | 0 | 0 | 0 | 서울×2, 부산×1, 대구×1, 인천×1, 광주×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `고객`: header row(s) [1], data rows 2-9, columns: 고객ID→고객id:id, 이름→이름:text, 이메일→이메일:email, 지역→지역:text
