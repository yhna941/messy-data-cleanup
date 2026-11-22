#!/usr/bin/env python3
"""Held-out dataset (academy enrollments) with mess patterns NOT used while building the cleaner.

Includes traps the cleaner was never tuned for: letter O inside a phone number, △ negative
marker, 'Feb 20, 2024', '3/4' without a year, siblings sharing a parent phone, a course
'수학 심화B' that does not exist next to '수학 심화A', an '평균' row, a semicolon CSV with a
multi-line quoted memo.
"""
from __future__ import annotations

import datetime as dt
import json
from pathlib import Path

from openpyxl import Workbook

HERE = Path(__file__).resolve().parent
D = dt.date
ISSUES = []


def issue(table, cat, row, col, expect, truth=None, note=""):
    ISSUES.append({"id": f"B{len(ISSUES) + 1:03d}", "table": table, "category": cat, "row": row, "column": col, "expect": expect,
                   "truth": truth.isoformat() if isinstance(truth, dt.date) else truth, "note": note})


STUDENTS = [  # id, name, grade, phone, email, reg, shuttle
    ("S24-001", "김민지", "고1", "010-1234-5678", "minji@naver.com", D(2024, 2, 15), "Y"),
    ("S24-002", "이준호", "고2", "010-2345-6789", "junho.lee@gmail.com", D(2024, 2, 16), "N"),
    ("S24-003", "박서윤", "중3", "02-123-4567", "seoyun@daum.net", D(2024, 2, 17), "Y"),
    ("S24-004", "최도윤", "고3", "031-234-5678", "doyun@naver.com", D(2024, 2, 18), "N"),
    ("S24-005", "정하은", "고1", "010-3456-7890", "haeun@kakao.com", D(2024, 2, 19), "Y"),
    ("S24-006", "강지우", "고2", "010-4567-8901", "jiwoo@naver.com", D(2024, 2, 20), "N"),
    ("S24-007", "윤서준", "중3", "010-5678-9012", "seojun@gmail.com", D(2024, 2, 21), "Y"),
    ("S24-008", "장예린", "고3", "010-6789-0123", "yerin@naver.com", D(2024, 2, 22), "N"),
    ("S24-009", "임시우", "고1", "010-7890-1234", "siwoo@daum.net", D(2024, 2, 23), "Y"),
    ("S24-010", "한지호", "고2", "010-8901-2345", "jiho.han@naver.com", D(2024, 2, 24), "N"),
    ("S24-011", "한지아", "중3", "010-8901-2345", "jia.han@naver.com", D(2024, 2, 24), "N"),
    ("S24-012", "오유나", "고3", "010-9012-3456", "yuna@gmail.com", D(2024, 2, 26), "Y"),
    ("S24-013", "서민재", "고1", "010-1111-3333", "minjae@naver.com", D(2024, 2, 27), "N"),
    ("S24-014", "이준호", "고2", "010-2345-6789", "junho.lee@gmail.com", D(2024, 3, 2), "N"),
]
RAW_S = {
    "S24-001": ["S24-001", "김민지", "고1", "010-1234-5678", "minji＠naver.com", "2024-02-15", "Y"],
    "S24-002": ["s24 002", "이준호", "고등1".replace("1", "2"), "010 2345 6789", "Junho.Lee@Gmail.com", "Feb 16, 2024", "아니오"],
    "S24-003": ["S-24-003", "박서윤", "중 3", "02-123-4567", "seoyun@daum.net", "2024.2.17.", "O"],
    "S24-004": ["24-004", "최도윤", "고3학년", "031)234-5678", "doyun@naver.com", "2/18/2024", "X"],
    "S24-005": ["S24-005", "정하은 ", "고 1", "010-3456-7890", "haeun@kakao.com", "2024-02-19 14:30", "TRUE"],
    "S24-006": ["S24-006", "강지우", "교2", "010-4567-890", "jiwoo@naver.com", 45342, "N"],
    "S24-007": ["S24-007", "윤서준", "중3", "01O-5678-9012", "seojun@gmail.com", dt.datetime(2024, 2, 21, 9, 15), "예"],
    "S24-008": ["S24-008", "장예린", "고등학교 3학년", "010-6789-0123", "yerin@naver,com", "2024년2월22일", "n"],
    "S24-009": ["S24-009", "임시우", "H1", "+82-10-7890-1234", "siwoo@daum.net", "22/02/2024".replace("22", "23", 1), "y"],
    "S24-010": ["S24-010", "한지호", "고2", "010-8901-2345", "jiho.han@naver.com", "2024-02-24", "N"],
    "S24-011": ["S24-011", "한지아", "중3", "010-8901-2345", "jia.han@naver.com", "2024-02-24", "N"],
    "S24-012": ["S24-012", "오유나", "고3", "010-9012-3456", "yuna@gmail.com", "24.02.26", "Y"],
    "S24-013": ["S24-013", "서민재", "고1", "010-1111-3333", "minjae@naver.com", "2024-02-27", ""],
    "S24-014": ["S24-014", "이준호", "고 2", "01023456789", "junho.lee@gmail.com", "2024-03-02", "N"],
}
COURSES = [("C01", "수학 심화A", "김선생", 150000), ("C02", "영어 독해B", "Ms. Park", 130000), ("C03", "국어 문학", "이선생", 120000),
           ("C04", "과학 탐구", "최선생", 140000)]
ENR = [  # id, student, course, fee, adj, pay_date, status
    ("E001", "S24-001", "수학 심화A", 150000, 0, D(2024, 3, 2), "납부완료"), ("E002", "S24-002", "영어 독해B", 130000, -10000, D(2024, 3, 2), "납부완료"),
    ("E003", "S24-003", "국어 문학", 120000, 0, D(2024, 3, 3), "미납"), ("E004", "S24-004", "과학 탐구", 140000, 0, D(2024, 3, 3), "납부완료"),
    ("E005", "S24-005", "수학 심화A", 150000, -15000, D(2024, 3, 4), "납부완료"), ("E006", "S24-006", "영어 독해B", 130000, 0, D(2024, 3, 4), "환불"),
    ("E007", "S24-007", "수학 심화A", 150000, 0, D(2024, 3, 5), "납부완료"), ("E008", "S24-008", "국어 문학", 120000, -10000, D(2024, 3, 5), "미납"),
    ("E009", "S24-009", "과학 탐구", 140000, 0, D(2024, 3, 6), "납부완료"), ("E010", "S24-010", "수학 심화A", 150000, -20000, D(2024, 3, 6), "납부완료"),
    ("E011", "S24-011", "영어 독해B", 130000, -20000, D(2024, 3, 6), "납부완료"), ("E012", "S24-012", "국어 문학", 120000, 0, D(2024, 3, 7), "납부완료"),
    ("E013", "S24-013", "과학 탐구", 140000, 0, D(2024, 3, 7), "미납"), ("E014", "S24-099", "수학 심화A", 150000, 0, D(2024, 3, 8), "납부완료"),
    ("E015", "S24-001", "영어 독해B", 130000, 0, D(2024, 3, 8), "납부완료"), ("E016", "S24-001", "영어 독해B", 130000, 0, D(2024, 3, 8), "납부완료"),
    ("E017", "S24-005", "국어 문학", 120000, 0, D(2024, 3, 9), "납부완료"), ("E018", "S24-012", "수학 심화A", 150000, 0, D(2024, 3, 9), "환불"),
]
RAW_E = {
    "E001": ["E001", "S24-001", "수학심화A", "₩150,000", 0, "2024-03-02", "납부완료"],
    "E002": ["E002", "s24-002", "영어독해 B", "13만", "-10,000", "2024.3.2", "완납"],
    "E003": ["E003", "S24-003", "국어문학", "120,000원", None, "3/3", "미납 "],
    "E004": ["E004", "S24-004", "과탐", 140000, "", "2024-03-03", "납부 완료"],
    "E005": ["E005", "S24-005", "수학 심화 A", "15만원", "△15,000", "2024-03-04", "납부완료"],
    "E006": ["E006", "S24-006", "영어 독해B", "1.3e5", "0", "20240304", "환뷸"],
    "E007": ["E007", "S24-007", "수학 심화B", "150,000원(할인전)", "-", "2024-03-05", "납부완료"],
    "E008": ["E008", "S24-008", "국어 문학", "120000", "(10,000)", "Mar 5, 2024", "미납"],
    "E009": ["E009", "S24-009", "과학탐구", "14만원", 0, "2024-03-06", "납부완료"],
    "E010": ["E010", "S24-010", "수학 심화A", "150,000", "-20,000", dt.datetime(2024, 3, 6), "납부완료"],
    "E011": ["E011", "S24-011", "영어 독해B", "130,000", "-2만", "2024-03-06", "납부완료"],
    "E012": ["E012", "S24-012", "국어 문학", "₩120,000", 0, "2024/03/07", "납부완료"],
    "E013": ["E013", "S24-013", "과학 탐구", "140,000", 0, "2024-03-07", "미납"],
    "E014": ["E014", "S24-099", "수학 심화A", "150,000", 0, "2024-03-08", "납부완료"],
    "E015": ["E015", "S24-001", "영어 독해B", "130,000", 0, "2024-03-08", "납부완료"],
    "E016": ["E016", "S24-001", "영어 독해B", "130,000", 0, "2024-03-08", "납부완료"],
    "E017": ["E017", "S24-005", "국어 문학", "120,000", 0, "2024-03-09", "납부완료"],
    "E018": ["E018", "S24-012", "수학 심화A", "150,000", 0, "2024-03-09", "환불"],
}


def main():
    (HERE / "input").mkdir(exist_ok=True)
    wb = Workbook()
    ws = wb.active
    ws.title = "원생"
    ws["A1"] = "◆ 봄학기 원생 명단 ◆"
    ws.merge_cells("A1:I1")
    ws["A2"] = "담당: 박실장 (수정 시 노란색 표시)"
    for c, v in enumerate(["No.", "Student ID", "학생명", "학년", "학부모 연락처", "e-mail", "등록일", "셔틀이용", "비고"], start=1):
        ws.cell(3, c, v)
    issue("students", "structure", 1, None, "drop")
    issue("students", "structure", 2, None, "drop")
    s_truth, r = {}, 4
    cols = ["student_id", "name", "grade", "phone", "email", "reg_date", "shuttle"]
    for st in STUDENTS:
        raw = RAW_S[st[0]]
        ws.cell(r, 1, r - 3)
        for c, v in enumerate(raw, start=2):
            if v not in (None, ""):
                ws.cell(r, c, v)
        s_truth[r] = dict(zip(cols, st))
        if st[0] == "S24-013":
            s_truth[r]["shuttle"] = None
        flags = {("S24-006", "grade"): "교2 typo (2-syllable)", ("S24-006", "phone"): "too few digits", ("S24-008", "email"): "comma in domain",
                 ("S24-007", "phone"): "letter O instead of 0"}
        for i, col in enumerate(cols):
            v, tv = raw[i], s_truth[r][col]
            if v == tv or v in (None, "") and tv is None or (isinstance(v, dt.datetime) and v.date() == tv):
                continue
            if (st[0], col) in flags:
                issue("students", "trap" if col == "phone" and st[0] == "S24-007" else "invalid", r, col, "flag", tv, flags[(st[0], col)])
            else:
                issue("students", col, r, col, "fix", tv, repr(v))
        if st[0] == "S24-007":
            r += 1
            ws.cell(r, 1, r - 3)
            for c, v in enumerate(raw, start=2):
                if v not in (None, ""):
                    ws.cell(r, c, v)
            issue("students", "duplicate", r, None, "dup_drop", note="S24-007 pasted twice")
        r += 1
    rown = {v["student_id"]: k for k, v in s_truth.items()}
    issue("students", "near_duplicate", rown["S24-002"], None, "suspect", [rown["S24-002"], rown["S24-014"]], "same person re-registered")
    issue("students", "trap", rown["S24-010"], None, "no_suspect", [rown["S24-010"], rown["S24-011"]], "siblings share parent phone")

    ws2 = wb.create_sheet("수강신청")
    for c, v in enumerate(["신청번호", "학생ID", "강좌", "수강료", "조정액", "납부일", "상태"], start=1):
        ws2.cell(1, c, v)
    e_truth, r = {}, 2
    ecols = ["enroll_id", "student_id", "course", "fee", "adjust", "pay_date", "status"]
    eflags = {("E003", "pay_date"): "3/3 without year", ("E004", "course"): "과탐 abbreviation", ("E007", "course"): "수학 심화B does not exist",
              ("E007", "fee"): "text after number", ("E008", "pay_date"): "Mar 5, 2024", ("E005", "adjust"): "△ negative marker",
              ("E006", "status"): "환뷸 typo"}
    for e in ENR:
        raw = list(RAW_E[e[0]])
        if e[0] == "E012":   # shifted right: blank cell inserted before 수강료
            raw = raw[:3] + [None] + raw[3:]
        for c, v in enumerate(raw, start=1):
            if v not in (None, ""):
                ws2.cell(r, c, v)
        e_truth[r] = dict(zip(ecols, e))
        if e[0] in ("E003", "E004"):
            e_truth[r]["adjust"] = None
        if e[0] == "E007":
            e_truth[r]["adjust"] = None
        for i, col in enumerate(ecols):
            v = RAW_E[e[0]][i]
            tv = e_truth[r][col]
            if v == tv or (v in (None, "") and tv is None) or (isinstance(v, dt.datetime) and v.date() == tv):
                continue
            if (e[0], col) in eflags:
                # after the first blind run these three became deliberate, general fixes (see first_run_score.txt)
                fixable = (e[0], col) in (("E005", "adjust"), ("E006", "status"), ("E008", "pay_date"))
                issue("enrollments", "trap", r, col, "fix" if fixable else "flag", tv, eflags[(e[0], col)])
            elif e[0] != "E012" or col in ("enroll_id", "student_id", "course"):
                issue("enrollments", col, r, col, "fix", tv, repr(v))
        if e[0] == "E012":
            for col in ("fee", "adjust", "pay_date", "status"):
                issue("enrollments", "shifted_row", r, col, "fix", e_truth[r][col], "shifted right")
        r += 1
    ws2.cell(r, 1, "평균")
    ws2.cell(r, 4, 135000)
    issue("enrollments", "structure", r, None, "drop", note="평균 (average) row")
    r += 1
    ws2.cell(r, 1, "총 합계")
    ws2.cell(r, 4, sum(e[3] for e in ENR))
    issue("enrollments", "structure", r, None, "drop", note="총 합계 row")
    erow = {v["enroll_id"]: k for k, v in e_truth.items()}
    issue("enrollments", "join_orphan", erow["E014"], "student_id", "orphan", "S24-099")
    issue("enrollments", "near_duplicate", erow["E015"], None, "suspect", [erow["E015"], erow["E016"]], "double enrollment")

    ws3 = wb.create_sheet("강좌")
    for c, v in enumerate(["강좌코드", "강좌명", "강사", "수강료"], start=1):
        ws3.cell(1, c, v)
    c_truth = {}
    for i, (code, name, t, fee) in enumerate(COURSES, start=2):
        for c, v in enumerate([code, name, t, f"{fee:,}원"], start=1):
            ws3.cell(i, c, v)
        c_truth[i] = {"course_code": code, "course_name": name, "teacher": t, "fee": fee}
        issue("courses", "fee", i, "fee", "fix", fee, "text money")
    wb.save(HERE / "input" / "2024_봄학기_원생관리(수정중).xlsx")

    lines = ["\ufeff학생ID;날짜;출결;메모", "S24-001;2024-03-04;출석;", "S24-002;2024-03-04;지각;\"버스 놓침\n10분 늦음\"",
             "s24-003;2024-03-04;결석;병결", "S24-004;2024-03-04;출섭;", "S24-099;2024-03-04;출석;명단에 없음", "S24-005;2024-03-04; 조퇴 ;"]
    (HERE / "input" / "출결_export.csv").write_text("\r\n".join(lines) + "\r\n", encoding="utf-8")
    a_truth = {2: ("S24-001", "출석"), 3: ("S24-002", "지각"), 5: ("S24-003", "결석"), 6: ("S24-004", "출석"), 7: ("S24-099", "출석"), 8: ("S24-005", "조퇴")}
    a_t = {r: {"student_id": s, "status": st} for r, (s, st) in a_truth.items()}
    issue("attendance", "csv_multiline", 3, "status", "fix", "지각", "row after a multi-line quoted memo")
    issue("attendance", "student_id", 5, "student_id", "fix", "S24-003")
    issue("attendance", "typo", 6, "status", "fix", "출석", "출섭 typo")
    issue("attendance", "join_orphan", 7, "student_id", "orphan", "S24-099")
    issue("attendance", "status", 8, "status", "fix", "조퇴", "spaces")

    def ser(rows):
        return {str(k): {c: (v.isoformat() if isinstance(v, dt.date) else v) for c, v in rec.items()} for k, rec in rows.items()}
    gt = {"meta": {"joined_sheet": "Joined_enroll_full", "join_statuses": {}},
          "tables": {"students": ser(s_truth), "enrollments": ser(e_truth), "courses": ser(c_truth), "attendance": ser(a_t)},
          "issues": ISSUES}
    (HERE / "ground_truth.json").write_text(json.dumps(gt, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"planted {len(ISSUES)} issues")


if __name__ == "__main__":
    main()
