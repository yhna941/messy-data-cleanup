# Profile (no contract; guesses to review)

## 2024_봄학기_원생관리(수정중).xlsx / 원생

- size: 18 rows x 9 cols; encoding: xlsx; merged ranges: 1
- likely header: row 3
- rows below header: {'data': 15}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| No. | number | 0 | 0 | 0 | 0 | 0 | 1×1, 2×1, 3×1, 4×1, 5×1 |  |
| Student ID | id | 0 | 0 | 0 | 0 | 0 | S24-007×2, S24-001×1, s24 002×1, S-24-003×1, 24-004×1 |  |
| 학생명 | text | 0 | 0 | 0 | 0 | 1 | 이준호×2, 윤서준×2, 김민지×1, 박서윤×1, 최도윤×1 | 한지호/한지아 |
| 학년 | category | 0 | 0 | 0 | 0 | 0 | 중3×3, 고1×2, 고등2×1, 중 3×1, 고3학년×1 | 중3/중 3; 고1/고 1; 고2/고 2 |
| 학부모 연락처 | phone | 0 | 0 | 0 | 0 | 0 | 01O-5678-9012×2, 010-8901-2345×2, 010-1234-5678×1, 010 2345 6789×1, 02-123-4567×1 |  |
| e-mail | email | 0 | 0 | 1 | 0 | 0 | seojun@gmail.com×2, minji@naver.com×1, Junho.Lee@Gmail.com×1, seoyun@daum.net×1, doyun@naver.com×1 |  |
| 등록일 | date | 0 | 0 | 0 | 0 | 0 | 2024-02-21 09:15:00×2, 2024-02-24×2, 2024-02-15×1, Feb 16, 2024×1, 2024.2.17.×1 |  |
| 셔틀이용 | category | 1 | 1 | 0 | 0 | 0 | N×4, Y×2, 예×2, 아니오×1, O×1 | N/n; Y/y |
| 비고 | text | 15 | 0 | 0 | 0 | 0 |  |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `student_list`: header row(s) [3], data rows 4-18, columns: No.→no:count, Student ID→student_id:text, 학생명→student_name:text, 학년→grade:text, 학부모 연락처→parent_phone:phone, e-mail→email:email, 등록일→registration_date:date, 셔틀이용→shuttle_usage:text, 비고→notes:freetext

## 2024_봄학기_원생관리(수정중).xlsx / 수강신청

- size: 21 rows x 8 cols; encoding: xlsx; merged ranges: 0
- likely header: row 1
- rows below header: {'data': 18, 'subtotal/total': 2}
- structural rows: row 13: values right of the last header column (shifted row?); row 20: subtotal: 평균; row 21: subtotal: 총 합계

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 신청번호 | id | 0 | 0 | 0 | 0 | 0 | E001×1, E002×1, E003×1, E004×1, E005×1 |  |
| 학생ID | id | 2 | 0 | 0 | 0 | 0 | S24-001×3, S24-005×2, S24-012×2, s24-002×1, S24-003×1 |  |
| 강좌 | category | 2 | 0 | 0 | 0 | 0 | 영어 독해B×4, 국어 문학×3, 수학 심화A×3, 수학심화A×1, 영어독해 B×1 | 영어 독해B/영어독해 B; 국어 문학/국어문학; 수학 심화A/수학심화A/수학 심화 A/수학 심화B; 과학탐구/과학 탐구 |
| 수강료 | money | 1 | 0 | 0 | 0 | 0 | 150,000×3, 130,000×3, ₩150,000×1, 13만×1, 120,000원×1 |  |
| 조정액 | money | 4 | 1 | 0 | 0 | 0 | 0×8, -10,000×1, △15,000×1, 0×1, -×1 |  |
| 납부일 | date | 2 | 0 | 0 | 0 | 0 | 2024-03-08×3, 2024-03-06×2, 2024-03-09×2, 2024-03-02×1, 2024.3.2×1 |  |
| 상태 | category | 2 | 0 | 0 | 0 | 1 | 납부완료×10, 미납×3, 완납×1, 납부 완료×1, 환뷸×1 | 납부완료/납부 완료; 환뷸/환불 |
| column_8 | category | 19 | 0 | 0 | 0 | 0 | 납부완료×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `course_applications`: header row(s) [1], data rows 2-19, columns: 신청번호→application_number:id, 학생ID→student_id:id, 강좌→course:text, 수강료→tuition_fee:money, 조정액→adjustment_amount:money, 납부일→payment_date:date, 상태→status:category, →unnamed_column_8:freetext

## 2024_봄학기_원생관리(수정중).xlsx / 강좌

- size: 5 rows x 4 cols; encoding: xlsx; merged ranges: 0
- likely header: row 1
- rows below header: {'data': 4}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 강좌코드 | id | 0 | 0 | 0 | 0 | 0 | C01×1, C02×1, C03×1, C04×1 |  |
| 강좌명 | category | 0 | 0 | 0 | 0 | 0 | 수학 심화A×1, 영어 독해B×1, 국어 문학×1, 과학 탐구×1 |  |
| 강사 | category | 0 | 0 | 0 | 0 | 0 | 김선생×1, Ms. Park×1, 이선생×1, 최선생×1 | 김선생/이선생/최선생 |
| 수강료 | money | 0 | 0 | 0 | 0 | 0 | 150,000원×1, 130,000원×1, 120,000원×1, 140,000원×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `course_list`: header row(s) [1], data rows 2-5, columns: 강좌코드→course_code:id, 강좌명→course_name:text, 강사→instructor:text, 수강료→tuition_fee:money

## 출결_export.csv / 출결_export

- size: 7 rows x 4 cols; encoding: utf-8-sig; merged ranges: 0
- likely header: row 1
- rows below header: {'data': 6}

| column | guess | blanks | placeholders | full-width | mojibake | spaces | top values | near-duplicate spellings |
|---|---|---|---|---|---|---|---|---|
| 학생ID | id | 0 | 0 | 0 | 0 | 0 | S24-001×1, S24-002×1, s24-003×1, S24-004×1, S24-099×1 |  |
| 날짜 | date | 0 | 0 | 0 | 0 | 0 | 2024-03-04×6 |  |
| 출결 | category | 0 | 0 | 0 | 0 | 1 | 출석×2, 지각×1, 결석×1, 출섭×1, 조퇴×1 | 출석/출섭 |
| 메모 | category | 3 | 0 | 0 | 0 | 0 | 버스 놓침 10분 늦음×1, 병결×1, 명단에 없음×1 |  |

### LLM layout read (openrouter:google/gemini-2.5-flash-lite), validated against the grid

- table `attendance_log`: header row(s) [1], data rows 2-7, columns: 학생ID→student_id:id, 날짜→date:date, 출결→attendance_status:category, 메모→memo:freetext
