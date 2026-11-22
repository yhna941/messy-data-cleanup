#!/usr/bin/env python3
"""Download one public data.go.kr file dataset the way the site's own download button does.

usage: datagokr_fetch.py PUBLIC_DATA_PK OUT_FILE

Flow (from the page's script_fileDetail.js / script_cmmFunction.js): page -> fn_fileDataDown(pk, uddi)
-> /tcs/dss/selectFileDataDownload.do -> /cmm/cmm/check-limit.json -> /cmm/cmm/fileDownload.do.
If the site asks for a captcha (needCaptcha), stop: download it by hand in a browser.
The server needs TLS 1.2 and is flaky, so every step retries.
"""
import json
import os
import re
import subprocess
import sys
import time
import urllib.parse

pk, out = sys.argv[1], sys.argv[2]
page = f"https://www.data.go.kr/data/{pk}/fileData.do"
jar = f"/tmp/datagokr_{pk}.cookies"
base = ["curl", "-s", "--tlsv1.2", "--tls-max", "1.2", "-A", "Mozilla/5.0 (X11; Linux x86_64) Chrome/120",
        "-b", jar, "-c", jar, "-e", page]


def get(args, timeout=40, tries=6):
    for i in range(tries):
        p = subprocess.run(base + ["--max-time", str(timeout)] + args, capture_output=True)
        if p.stdout:
            return p.stdout
        time.sleep(3 + 2 * i)
    raise SystemExit(f"no response after {tries} tries: {args[-1]}")


html = get([page]).decode("utf-8", "replace")
m = re.search(r"fn_fileDataDown\('(\d+)', '(uddi:[^']+)'", html)
if not m:
    raise SystemExit("download button not found on " + page)
info = json.loads(get(["-d", f"publicDataDetailPk={m.group(2)}&publicDataPk={pk}&atchFileId=&fileDetailSn=1&publicDataTyCode=PR0051",
                       "https://www.data.go.kr/tcs/dss/selectFileDataDownload.do"]))
if not info.get("status"):
    raise SystemExit(f"download refused: {info.get('error')}")
fid, sn = info["atchFileId"], info["fileDetailSn"]
lim = json.loads(get(["-d", f"atchFileId={fid}&fileDetailSn={sn}", "https://www.data.go.kr/cmm/cmm/check-limit.json"]))
if lim.get("needCaptcha"):
    raise SystemExit(f"data.go.kr wants a captcha for {pk}: download it by hand from {page}")
name = info["dataSetFileDetailInfo"].get("dataNm", pk)
url = f"https://www.data.go.kr/cmm/cmm/fileDownload.do?atchFileId={fid}&fileDetailSn={sn}&dataNm={urllib.parse.quote(name)}"
for i in range(6):
    subprocess.run(base + ["-L", "--max-time", "1800", "-o", out, url])
    if os.path.exists(out) and os.path.getsize(out) > 0:
        break
    time.sleep(5)
else:
    raise SystemExit("empty download")
print(f"{pk} {name} -> {out}")
