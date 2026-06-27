#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
probe.py — 可達性診斷器(對 targets.json 裡有填 url 的品項各做一次禮貌請求)

用途:在「直接撈得到嗎」這個問題上給出 ✅/🟡/❌ 判定。
- ✅ 綠:HTTP 200 且抓回頁面夠大(像真的內容,不是攔截頁)
- 🟡 黃:能連但異常(轉址到首頁/驗證頁、內容過小、偶爾逾時)
- ❌ 紅:連不上(逾時/連線重設/DNS 失敗)

設計重點:
- 單次請求、看 robots.txt(README 安全界線第 3 條:不繞過反爬)
- 跑在哪台機器,就測那台的 IP。GitHub Actions 上跑 = 測 GitHub 美國 IP(這才是正式判定)
- 不寫任何檔案、不改 data.json,純診斷
"""
import json
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests

# Windows 主控台預設 cp950,吃不下 emoji/UTF-8,強制改 UTF-8 輸出
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
CONNECT_TIMEOUT = 8
READ_TIMEOUT = 15
MIN_OK_BYTES = 3000  # 小於此值多半是攔截頁/空殼

TARGETS = Path(__file__).with_name("targets.json")


def robots_url(url: str) -> str:
    p = urlsplit(url)
    return urlunsplit((p.scheme, p.netloc, "/robots.txt", "", ""))


def probe_one(session: requests.Session, url: str) -> dict:
    r = {"url": url, "code": None, "time": None, "bytes": None,
         "redirects": None, "final": None, "verdict": "❌", "note": ""}
    try:
        t0 = time.monotonic()
        resp = session.get(url, headers=HEADERS, allow_redirects=True,
                           timeout=(CONNECT_TIMEOUT, READ_TIMEOUT))
        r["time"] = round(time.monotonic() - t0, 2)
        r["code"] = resp.status_code
        r["bytes"] = len(resp.content)
        r["redirects"] = len(resp.history)
        r["final"] = resp.url
        if resp.status_code == 200 and r["bytes"] >= MIN_OK_BYTES:
            # 轉址跨網域(像被丟到首頁/登入頁)算可疑
            if urlsplit(resp.url).netloc != urlsplit(url).netloc:
                r["verdict"], r["note"] = "🟡", "轉址到其他網域(疑似攔截/首頁)"
            else:
                r["verdict"], r["note"] = "✅", "正常"
        elif resp.status_code == 200:
            r["verdict"], r["note"] = "🟡", f"內容過小({r['bytes']}B),疑似攔截頁"
        else:
            r["verdict"], r["note"] = "🟡", f"HTTP {resp.status_code}"
    except requests.exceptions.ConnectTimeout:
        r["note"] = "連線逾時"
    except requests.exceptions.ReadTimeout:
        r["note"] = "讀取逾時"
    except requests.exceptions.ConnectionError as e:
        r["note"] = f"連線失敗:{type(e).__name__}"
    except Exception as e:
        r["note"] = f"{type(e).__name__}: {e}"
    return r


def main() -> int:
    data = json.loads(TARGETS.read_text(encoding="utf-8"))
    jobs = []
    for cat_key, cat in data.items():
        if cat_key.startswith("_"):
            continue
        for it in cat.get("items", []):
            if it.get("url"):
                jobs.append((cat_key, it["brand"], it["model"], it["url"]))

    if not jobs:
        print("targets.json 裡沒有任何已填 url 的品項,無可探測。")
        return 1

    session = requests.Session()
    print(f"探測 {len(jobs)} 個已填網址的品項…\n")
    print(f"{'判定':<4} {'品項':<28} {'CODE':<5} {'TIME':<6} {'BYTES':<9} 備註")
    print("-" * 100)

    checked_robots = set()
    results = []
    for cat_key, brand, model, url in jobs:
        host = urlsplit(url).netloc
        # 每個網域查一次 robots
        if host not in checked_robots:
            checked_robots.add(host)
            rb = probe_one(session, robots_url(url))
            print(f"{'robots':<4} {host:<28} {str(rb['code']):<5} "
                  f"{str(rb['time']):<6} {str(rb['bytes']):<9} {rb['note']}")
        res = probe_one(session, url)
        results.append(res)
        name = f"{brand} {model}"
        print(f"{res['verdict']:<4} {name[:28]:<28} {str(res['code']):<5} "
              f"{str(res['time']):<6} {str(res['bytes']):<9} {res['note']}")
        time.sleep(1)  # 禮貌:每次請求間隔

    ok = sum(1 for r in results if r["verdict"] == "✅")
    warn = sum(1 for r in results if r["verdict"] == "🟡")
    bad = sum(1 for r in results if r["verdict"] == "❌")
    print("-" * 100)
    print(f"總結:✅ {ok}  🟡 {warn}  ❌ {bad}  （共 {len(results)} 項)")
    if bad == len(results):
        print("→ 全紅:這台機器的 IP 撈不到目標站。若在 GitHub Actions 上得此結果,改走方案 B(自架 Runner)。")
    elif ok == 0:
        print("→ 無一全綠:可達性不穩,建議方案 B 或改人工維護。")
    else:
        print("→ 有綠燈:這台機器可走方案 A(直接爬)。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
