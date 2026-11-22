#!/usr/bin/env bash
# Download the public real-world datasets used by realworld/bench.py and lay them out as
#   $RW_DATA/<set>/<subset>/<file>   (default RW_DATA=data/rw, raw downloads in data/raw)
# Nothing here is committed (data/ is gitignored). ~430 MB on disk.
set -euo pipefail
cd "$(dirname "$0")/.."
RAW=${RW_RAW:-data/raw}; RW=${RW_DATA:-data/rw}; HERE=$(pwd)
mkdir -p "$RAW" "$RW"
get() { [ -s "$RAW/$1" ] || curl -sSL -A "Mozilla/5.0" --retry 3 --max-time "${3:-1800}" -o "$RAW/$1" "$2"; echo "$1 $(stat -c%s "$RAW/$1") bytes"; }

# 1. NYC 311 service requests, 1,000,000 rows x 14 columns (Socrata erm2-nwe9)
get nyc311_1m.csv 'https://data.cityofnewyork.us/resource/erm2-nwe9.csv?$select=unique_key,created_date,closed_date,agency,complaint_type,descriptor,location_type,incident_zip,incident_address,city,borough,status,latitude,longitude&$where=created_date>%272024-01-01%27&$order=unique_key&$limit=1000000'
# 2. 국민연금 가입 사업장 내역 (data.go.kr 15083277), cp949 CSV ~590k rows
[ -s "$RAW/nps_workplaces.csv" ] || python3 scripts/datagokr_fetch.py 15083277 "$RAW/nps_workplaces.csv"
# 3. NYC DOF annualized rolling sales 2022-2023, 10 borough workbooks -> one 10-sheet workbook
for y in 2022 2023; do for b in manhattan bronx brooklyn queens staten_island; do
  get "${y}_$b.xlsx" "https://www.nyc.gov/assets/finance/downloads/pdf/rolling_sales/annualized-sales/$y/${y}_$b.xlsx" 300; done; done
[ -s "$RAW/nyc_rolling_sales_2022_2023.xlsx" ] || python3 scripts/combine_nyc_sales.py "$RAW/nyc_rolling_sales_2022_2023.xlsx" \
  $(for y in 2022 2023; do for b in manhattan bronx brooklyn queens staten_island; do echo "$RAW/${y}_$b.xlsx"; done; done)
# 4. 국민건강보험공단 시군구별 국가건강검진 (data.go.kr 15149732): a zip of 3 workbooks
if [ ! -s "$RAW/nhis_1.xlsx" ]; then
  [ -s "$RAW/nhis_checkup.zip" ] || python3 scripts/datagokr_fetch.py 15149732 "$RAW/nhis_checkup.zip"
  python3 - "$RAW" <<'PY'
import sys, zipfile
raw = sys.argv[1]
for i, info in enumerate(zipfile.ZipFile(f"{raw}/nhis_checkup.zip").infolist(), 1):
    open(f"{raw}/nhis_{i}.xlsx", "wb").write(zipfile.ZipFile(f"{raw}/nhis_checkup.zip").read(info))
PY
fi
# 5. US Census county population estimates 2020-2023
get co-est2023-pop.xlsx https://www2.census.gov/programs-surveys/popest/tables/2020-2023/counties/totals/co-est2023-pop.xlsx
# 6. Powerhouse Museum collection (Programming Historian OpenRefine lesson)
get phm-collection.tsv https://programminghistorian.org/assets/cleaning-data-with-openrefine/phm-collection.tsv

# layout + head subsets for the scaling curve
A="$HERE/$RAW"
python3 - "$A" "$RW" <<'PY'
import csv, collections, openpyxl, sys
raw, rw = sys.argv[1], sys.argv[2]
names = {'1': 'MANHATTAN', '2': 'BRONX', '3': 'BROOKLYN', '4': 'QUEENS', '5': 'STATEN ISLAND'}
z = collections.defaultdict(collections.Counter)
for ws in openpyxl.load_workbook(f"{raw}/nyc_rolling_sales_2022_2023.xlsx", read_only=True).worksheets:
    for r in ws.iter_rows(min_row=9, values_only=True):
        if r[10] and r[0] in names:
            z[int(r[10])][names[r[0]]] += 1
with open(f"{raw}/zips.csv", "w", newline="") as f:
    w = csv.writer(f); w.writerow(["zip", "borough"])
    for k in sorted(z):
        if k: w.writerow([f"{k:05d}", z[k].most_common(1)[0][0]])
PY
lnk() { mkdir -p "$RW/$1"; ln -sf "$A/$2" "$RW/$1/${3:-$2}"; }
for n in 1000 10000 100000 300000; do
  mkdir -p "$RW/nyc311/n$n" "$RW/nps/n$n"
  head -$((n+1)) "$A/nyc311_1m.csv" > "$RW/nyc311/n$n/sr.csv"; ln -sf "$A/zips.csv" "$RW/nyc311/n$n/zips.csv"
  head -$((n+1)) "$A/nps_workplaces.csv" > "$RW/nps/n$n/nps.csv"
done
lnk nyc311/n1000000 nyc311_1m.csv sr.csv; ln -sf "$A/zips.csv" "$RW/nyc311/n1000000/zips.csv"
lnk nps/full nps_workplaces.csv nps.csv
lnk nycsales/full nyc_rolling_sales_2022_2023.xlsx
for i in 1 2 3; do lnk nhis/full nhis_$i.xlsx; done
lnk census/full co-est2023-pop.xlsx
lnk phm/full phm-collection.tsv
mkdir -p "$RW/nps_naive"; ln -sfn "$(cd "$RW/nps/n10000" && pwd)" "$RW/nps_naive/n10000"   # same rows, codes typed as numbers
echo "layout ready in $RW"
