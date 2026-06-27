#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
scrape.py — 競品定價儀表板 爬蟲(方案 A:規格自動抓 + 價格人工)

做什麼:
- 讀 targets.json,對 site=rapoo 且有 url 的品項抓「規格」(尺寸/重量/連接等)
- 讀現有 data.json,**只更新規格欄位,完整保留人工維護的 price / sell / image**
- 抓失敗時保留舊值(優雅降級),不會把既有資料清空
- 合理性檢查:規格是否抓到、價格是否還沒填 → 決定 draft 旗標
- site=manual 或 url 留空者:跳過抓取,原樣保留

不做什麼:
- 不抓價格(價格一律人工填 data.json)
- 不繞過反爬/驗證碼;會看 robots.txt,單次請求+間隔(README 安全界線第 3 條)

用法:
    python scrape.py            # 正常跑,寫回 data.json
    python scrape.py --dry-run  # 只印結果,不寫檔
"""
import json
import re
import sys
import time
import argparse
import datetime
import urllib.robotparser as robotparser
from pathlib import Path
from urllib.parse import urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

# Windows 主控台預設 cp950,強制 UTF-8 輸出避免 emoji/中文崩潰
try:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
except Exception:
    pass

ROOT = Path(__file__).resolve().parent.parent
TARGETS = ROOT / "scraper" / "targets.json"
DATA = ROOT / "data.json"

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/120.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept-Language": "zh-CN,zh;q=0.9"}
TIMEOUT = (15, 45)          # (連線, 讀取) — 中國站可能慢
RETRIES = 3
POLITE_DELAY = 1.5          # 每次請求間隔(秒)

# 規格欄位以外都視為「人工維護」,爬蟲不可覆蓋
HUMAN_FIELDS = ("price", "sell", "image")

# 規格細項欄位:滑鼠/鍵盤各自不同。每個欄位 = (顯示欄名, [雷柏頁面可能的標籤別名])
# 前端依各品類的 spec_fields 動態長出對照表欄位。
SPEC_SCHEMA = {
    "mouse": [
        ("连接方式",   ["连接方式", "传输方式"]),
        ("分辨率DPI",  ["分辨率", "灵敏度", "最高DPI", "DPI"]),
        ("传感器",     ["工作方式", "传感器", "引擎"]),
        ("手感",       ["手感类型", "手感"]),
        ("滚轮",       ["滚轮方向", "滚轮"]),
        ("颜色",       ["产品颜色", "颜色"]),
    ],
    "kb": [
        ("连接方式",   ["连接方式", "传输方式"]),
        ("按键数",     ["按键数", "键数"]),
        ("按键类型",   ["按键类型", "轴体"]),
        ("按键行程",   ["按键行程"]),
        ("按键寿命",   ["按键寿命"]),
        ("供电续航",   ["续航时长", "供电模式", "供电方式", "工作电压", "电池"]),
    ],
}


def spec_fields_of(cat_key):
    return [canon for canon, _ in SPEC_SCHEMA.get(cat_key, [])]


def build_specs_detail(cat_key, pairs):
    """依品類 schema,從雷柏配對挑出細項欄位;找不到填 '—'。"""
    detail = {}
    for canon, aliases in SPEC_SCHEMA.get(cat_key, []):
        val = ""
        for a in aliases:
            if pairs.get(a):
                val = pairs[a]
                break
        detail[canon] = val or "—"
    return detail


def norm_price(v):
    """把人工填的價格清成純數字:去掉 ¥ ￥ 逗號 空白。整數存 int,否則 float。
    空值/無法解析回 None。讓使用者誤填 '¥172' 隔天排程能自癒。"""
    if v is None or isinstance(v, (int, float)):
        return v
    s = re.sub(r"[¥￥,\s]", "", str(v))
    if s == "":
        return None
    try:
        f = float(s)
        return int(f) if f == int(f) else f
    except ValueError:
        return None


# ---------- robots ----------
_robots_cache: dict = {}

def robots_allows(url: str) -> bool:
    """檢查 robots.txt 是否允許抓此 url(抓不到 robots 時保守放行,但記錄)。"""
    p = urlsplit(url)
    base = f"{p.scheme}://{p.netloc}"
    if base not in _robots_cache:
        rp = robotparser.RobotFileParser()
        rp.set_url(urlunsplit((p.scheme, p.netloc, "/robots.txt", "", "")))
        try:
            rp.read()
        except Exception:
            rp = None  # 讀不到 robots,視為未限制
        _robots_cache[base] = rp
    rp = _robots_cache[base]
    if rp is None:
        return True
    return rp.can_fetch(UA, url)


# ---------- 抓取 ----------
def fetch(url: str) -> str | None:
    for attempt in range(1, RETRIES + 1):
        try:
            r = requests.get(url, headers=HEADERS, timeout=TIMEOUT, allow_redirects=True)
            if r.status_code == 200 and len(r.content) > 3000:
                r.encoding = r.apparent_encoding or "utf-8"
                return r.text
            print(f"      try{attempt}: HTTP {r.status_code} ({len(r.content)}B)")
        except Exception as e:
            print(f"      try{attempt}: {type(e).__name__}: {e}")
        time.sleep(2)
    return None


# ---------- 各站 extract() ----------
def extract_rapoo(html: str) -> dict:
    """
    雷柏官網規格結構:
        <ul class="params"><li>
            <p><span>产品尺寸</span><span>125*81*47mm</span></p>
            <p><span>产品重量</span><span>约101g（...）</span></p>
            <p><span>连接方式</span><span>蓝牙5.0、无线2.4G、有线</span></p> ...
    回傳 {size, weight, pairs}:size/weight 為字串,pairs 為頁面上所有「標籤:值」配對
    (供 build_specs_detail() 依品類挑出細項欄位)。
    """
    soup = BeautifulSoup(html, "lxml")
    pairs: dict[str, str] = {}
    for ul in soup.select("ul.params"):
        for p in ul.find_all("p"):
            spans = p.find_all("span")
            if len(spans) >= 2:
                key = spans[0].get_text(strip=True)
                val = spans[1].get_text(" ", strip=True)
                if key and val and key not in pairs:
                    pairs[key] = val

    return {
        "size": pairs.get("产品尺寸", ""),
        "weight": pairs.get("产品重量", ""),
        "pairs": pairs,
    }


EXTRACTORS = {"rapoo": extract_rapoo}


# ---------- 主流程 ----------
def load_json(path: Path, default):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except Exception as e:
            print(f"⚠ 讀 {path.name} 失敗,當作空白:{e}")
    return default


def find_existing(old_data: dict, cat_key: str, brand: str, model: str) -> dict:
    """從舊 data.json 找對應品項(brand+model),用來保留人工欄位/降級。"""
    cat = (old_data.get("categories") or {}).get(cat_key) or {}
    for it in cat.get("items", []):
        if it.get("brand") == brand and it.get("model") == model:
            return it
    return {}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry-run", action="store_true", help="只印結果,不寫 data.json")
    args = ap.parse_args()

    targets = load_json(TARGETS, {})
    old_data = load_json(DATA, {})

    out = {
        "updated_at": datetime.date.today().isoformat(),
        "currency": "CNY",
        "draft": False,
        "categories": {},
    }

    total = scraped_ok = scrape_fail = manual = no_price = 0

    for cat_key, cat in targets.items():
        if cat_key.startswith("_"):
            continue
        items_out = []
        for it in cat.get("items", []):
            total += 1
            brand, model = it.get("brand", ""), it.get("model", "")
            site, url = it.get("site", ""), it.get("url", "")
            prev = find_existing(old_data, cat_key, brand, model)

            # 基底:沿用舊值(降級的根本),保留人工欄位
            row = {
                "brand": brand,
                "model": model,
                "price": norm_price(prev.get("price")),
                "size": prev.get("size", "—"),
                "weight": prev.get("weight", "—"),
                "specs_detail": prev.get("specs_detail", {}),
                "sell": prev.get("sell", ""),
                "image": prev.get("image", ""),
                "source_url": url or prev.get("source_url", ""),
            }

            name = f"{brand} {model}"
            if site in EXTRACTORS and url:
                if not robots_allows(url):
                    print(f"  ⛔ {name}: robots.txt 不允許,跳過抓取(保留舊值)")
                    scrape_fail += 1
                else:
                    print(f"  ⟳ {name}: 抓取規格 …")
                    html = fetch(url)
                    if html:
                        try:
                            spec = EXTRACTORS[site](html)
                            # 合理性檢查:至少要有尺寸或重量,否則視為解析失敗→降級
                            if spec.get("size") or spec.get("weight"):
                                if spec.get("size"):
                                    row["size"] = spec["size"]
                                if spec.get("weight"):
                                    row["weight"] = spec["weight"]
                                row["specs_detail"] = build_specs_detail(cat_key, spec["pairs"])
                                scraped_ok += 1
                                print(f"      ✓ size={row['size']} weight={row['weight']} "
                                      f"specs={row['specs_detail']}")
                            else:
                                scrape_fail += 1
                                print(f"      ✗ 解析不到規格,保留舊值")
                        except Exception as e:
                            scrape_fail += 1
                            print(f"      ✗ extract 例外:{e},保留舊值")
                    else:
                        scrape_fail += 1
                        print(f"      ✗ 抓取失敗,保留舊值")
                    time.sleep(POLITE_DELAY)
            else:
                manual += 1
                print(f"  ✎ {name}: 人工維護(site={site or '空'}),不抓取")

            if row["price"] in (None, "", 0):
                no_price += 1

            items_out.append(row)

        out["categories"][cat_key] = {
            "label": cat.get("label", cat_key),
            "spec_fields": spec_fields_of(cat_key),
            "items": items_out,
        }

    # draft 判定:有任何抓取失敗或缺價格 → 標 draft 提醒前端
    out["draft"] = bool(scrape_fail > 0 or no_price > 0)

    print("\n" + "=" * 60)
    print(f"品項共 {total}:規格抓成功 {scraped_ok} · 抓失敗/降級 {scrape_fail} · 人工 {manual}")
    print(f"尚未填價格 {no_price} 項 → draft = {out['draft']}")
    if no_price:
        print("→ 價格為人工維護:請在 data.json 對應品項填 price(純數字,CNY)。")
    print("=" * 60)

    if args.dry_run:
        print("\n[--dry-run] 不寫檔。預覽:")
        print(json.dumps(out, ensure_ascii=False, indent=2)[:1500], "…")
    else:
        DATA.write_text(json.dumps(out, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(f"\n已寫回 {DATA}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
