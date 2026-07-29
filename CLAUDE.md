# CLAUDE.md — 鍵鼠競品study 專案說明

> Claude Code 開啟此專案時請先讀完這份文件，再開始任何操作。

---

## 專案一句話

ASUS 內部的「鍵鼠競品 study」儀表板，追蹤中國市場矮軸鍵盤 × 垂直滑鼠的競品定價與規格，部署在 GitHub Pages，資料每日由 GitHub Actions 自動更新。

- 線上網址：https://wenhsuanlee.github.io/competitor-pricing-dashboard/
- GitHub Repo：https://github.com/wenhsuanlee/competitor-pricing-dashboard（public）
- 主要維護人：diana_lee@asus.com（無工程背景，請說白話）

---

## 檔案結構

```
.
├─ index.html               # 前端 dashboard（單頁，原生 JS，無框架）
├─ data.json                # 資料檔（爬蟲輸出＋人工維護）
├─ images/                  # 本機托管產品圖
├─ scraper/
│  ├─ scrape.py             # 爬蟲主程式
│  ├─ targets.json          # 爬蟲品項清單（brand/model/site/url）
│  └─ requirements.txt
└─ .github/workflows/
   └─ update-data.yml       # 每日 01:00 UTC 排程 + 手動觸發
```

---

## 現有品項

### 矮軸鍵盤（10 款）
| 品牌 | 型號 | 價格(CNY) | site |
|------|------|-----------|------|
| 珂芝 KZZI | i75青春版 | 299 | manual |
| Keychron | J9 Ultra | 339 | manual |
| 洛斐 Lofree | 小順青春版 | 399 | shopify |
| AKKO | Air 01 | 399 | manual |
| NuPhy | Node75 | 469 | manual |
| AESCO | A83 Air | 699 | manual |
| 洛斐 Lofree | 小順 FLOW2 | 699 | shopify |
| NuPhy | Air96 V2 | 749 | manual |
| NuPhy | Kick75 | 799 | manual |
| MelGeek | O2 Mac版 | 899 | shopify |

### 垂直滑鼠（7 款）
| 品牌 | 型號 | 價格(CNY) | site |
|------|------|-----------|------|
| 多彩 Delux | M618AIR GX | 69 | manual |
| 雷柏 Rapoo | MV20 | 79 | manual |
| 多彩 Delux | M618XU | 99 | manual |
| 綠聯 UGREEN | MU008 | 119 | manual |
| B.O.W 航世 | MD190L mini | 159 | manual |
| 英菲克 INPHIC | X9 Pro | 129 | manual |
| 羅技 Logitech | Lift | 599 | manual |

---

## 爬蟲架構（重要決策，不要反覆問）

- **方案 A 已確認可行**：GitHub Actions 美國 IP 可直接抓 rapoo.cn，不需自架 Runner。
- **雷柏 rapoo.cn** 是目前唯一可靜態解析的官網（`ul.params > p > span` 結構）。
- **Shopify 品牌**（洛斐 Lofree、MelGeek）：用 `{url}.json` Shopify API 取圖片，價格固定為 CNY 人工填（`update_price: false`），因國際官網以 USD 定價。
- **NuPhy**：Cloudflare 擋 `.json` API，改 `site=manual`。
- **ZOL/PConline**：台灣 IP 不穩，已排除作為自動來源。
- **價格一律人工維護**，爬蟲只更新規格與圖片，絕不蓋掉人工填的 price。
- `find_existing(old_data, cat_key, brand, model)` 是降級核心：抓失敗時保留舊值。若新增品項前尚未在 data.json 建立記錄，Actions 跑一次就會清空 → **新增品項務必先手動在 data.json 建好記錄，再推 targets.json**。

---

## 前端功能（index.html）

- 三視圖：卡片 / 對照表 / 價格長條圖
- 散點圖子視圖：DPI×價格(滑鼠) / 按鍵數×價格(鍵盤) / 象限圖(規格分×價格) / 重量×續航
- 篩選：品類切換、品牌多選、價位帶、連接模式
- 手動觸發 GitHub Actions 的「更新資料」按鈕（PAT 存 localStorage，不寫進程式）
- `draft: true` 時顯示黃色警告橫幅
- 純原生 JS，無外部框架，SVG 圖表，無需 build

---

## 本機環境

- Python：`C:\Users\Diana_Lee\AppData\Local\Programs\Python\Python312\python.exe`（PATH 未更新，需完整路徑）
- 跑 Python 前：`$env:PYTHONUTF8=1`（否則中文/emoji 在 cp950 主控台崩潰）
- Git push 走 HTTPS，Windows Credential Manager 有快取（不需重新登入）
- `.claude/settings.json` 設定 `bypassPermissions`（全放行，已確認）

---

## data.json 欄位契約

```jsonc
{
  "updated_at": "YYYY-MM-DD",
  "currency": "CNY",
  "draft": false,          // true = 有品項缺價格或抓失敗，前端顯示黃色警告
  "categories": {
    "kb": {
      "label": "矮軸鍵盤",
      "spec_fields": ["连接方式","按键数","按键类型","按键行程","按键寿命","供电续航"],
      "items": [{ /* 見下 */ }]
    },
    "mouse": {
      "label": "垂直滑鼠",
      "spec_fields": ["连接方式","分辨率DPI","传感器","手感","滚轮","颜色","手型","供电方式"],
      "items": [{ /* 見下 */ }]
    }
  }
}
```

每個 item：
```jsonc
{
  "brand": "品牌",        // 與 targets.json 完全一致，爬蟲靠此對應
  "model": "型號",
  "price": 399,          // 純數字，CNY，人工填，爬蟲不蓋
  "size": "mm",
  "weight": "g",
  "specs_detail": {},    // 依品類 spec_fields 填
  "sell": "",            // 賣點文案，自行改寫勿抄官網
  "image": "",           // 本機 images/ 相對路徑，或 Shopify CDN URL
  "source_url": "",
  "rating": null,
  "reviews": null,
  "launched": "2025"
}
```

---

## GitHub Actions 注意事項

- workflow 檔案是透過 GitHub 網頁介面手動建立的（本機 `git push` 時 token 缺 `workflow` scope）。
- 排程：每日 UTC 01:00（台灣時間 09:00）。連續 60 天無 commit 排程會被 GitHub 自動停用。
- 使用內建 `GITHUB_TOKEN`（用完即丟），無需另外產生或儲存。
- 手動觸發需要帶 `workflow` scope 的 PAT，存在瀏覽器 localStorage（鍵名 `gh_pat`），不寫進程式。

---

## 安全與合規界線（請務必沿用）

1. **鑰匙不交給 AI**：`GITHUB_TOKEN` 由 Actions 自動注入，Claude Code 使用本機已登入憑證，憑證不離開本機。
2. **public repo 不放任何密鑰**；需要時放 repo Secrets。
3. **不繞過反爬/驗證碼**：禮貌的單次請求、遵守 robots.txt，擋了就改 `site=manual`。
4. **賣點文案**：自行改寫摘要，不整段複製官網。
5. 這是全網公開的 repo，使用者已知競品可能看到監控清單。

---

## 常見操作備忘

### 新增品項（安全步驟）
1. 先在 `data.json` 手動新增該品項記錄（含圖片、規格、價格）
2. commit & push data.json
3. 再新增/更新 `targets.json`
4. commit & push targets.json
> ⚠️ 順序反了，Actions 一跑就會把新品項清空（find_existing 找不到舊值 → 全部空白）

### 補回遺失資料
若 Actions 跑過後資料被清空，用 scratchpad 裡的 restore 腳本模式：直接對 data.json patch 對應欄位，不用重跑爬蟲。

### 執行爬蟲（本機測試）
```powershell
$env:PYTHONUTF8="1"
& "C:\Users\Diana_Lee\AppData\Local\Programs\Python\Python312\python.exe" scraper/scrape.py --dry-run
```

### git push 被拒（remote 有新 commit）
```powershell
git pull --rebase
git push
```
