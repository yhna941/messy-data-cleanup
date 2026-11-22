#!/usr/bin/env python3
"""Combine NYC DOF annualized rolling-sales workbooks (one borough per file) into one multi-sheet workbook.

usage: combine_nyc_sales.py OUT.xlsx IN1.xlsx IN2.xlsx ...
Sheets are named '<year> <Borough>'. Cell values and number formats are copied as-is (title rows,
notes and the blank row under the header stay), so the result is as messy as the originals.
"""
import sys
from pathlib import Path

import openpyxl
from openpyxl.cell import WriteOnlyCell

out, ins = Path(sys.argv[1]), [Path(p) for p in sys.argv[2:]]
wb = openpyxl.Workbook(write_only=True)
for p in ins:
    src = openpyxl.load_workbook(p, read_only=True)
    for ws in src.worksheets:
        dst = wb.create_sheet(f"{p.stem.split('_')[0]} {ws.title}"[:31])
        for row in ws.iter_rows():
            cells = []
            for c in row:
                w = WriteOnlyCell(dst, value=c.value)
                if c.value is not None and c.number_format != "General":
                    w.number_format = c.number_format
                cells.append(w)
            dst.append(cells)
wb.save(out)
print(out, out.stat().st_size)
