First 200 rows of two of the real-world sets, so the contracts can be run without downloading ~430 MB:

    python3 skill/messy-data-cleanup/scripts/clean_pipeline.py --contract realworld/nps/contract.yaml --input-dir realworld/sample/nps --out /tmp/nps_sample
    python3 skill/messy-data-cleanup/scripts/clean_pipeline.py --contract realworld/nyc311/contract.yaml --input-dir realworld/sample/nyc311 --out /tmp/nyc311_sample

- `nps/nps.csv`: 국민연금공단 국민연금 가입 사업장 내역 (data.go.kr 15083277), original cp949 bytes.
- `nyc311/sr.csv`: NYC 311 service requests (data.cityofnewyork.us erm2-nwe9), 14 columns. `zips.csv`: ZIP -> borough derived from the NYC DOF rolling sales files.

The full data comes from `scripts/fetch_realworld.sh`.
