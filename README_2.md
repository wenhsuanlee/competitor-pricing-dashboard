# README — 競品定價儀表板(交接說明)

> 這份文件給接手的人或 Claude Code 看。**請先讀完這份,再動手。**
> 目標:做一個會自動更新的競品定價儀表板,電腦版為主、相容手機,目標市場為中國(人民幣)。
> 管理這個專案的人沒有工程背景,請把這點放在心上:能自動、能降級、出錯要看得懂。

---

## 30 秒看懂這個專案

- **看資料**:`index.html` 是 dashboard,開啟時讀同目錄的 `data.json`,畫成卡片 / 對照表 / 價格長條圖三種視圖,可切換滑鼠 / 鍵盤兩個品類。
- **產資料**:`scraper/scrape.py` 每天抓一次競品的官方售價與規格,寫回 `data.json`;`.github/workflows/update-data.yml` 用 GitHub Actions 排程跑它,並自動 commit 回 repo。
- **核心原則**:**「爬資料」和「看資料」分開**,靠 `data.json` 串接、各自獨立。前端永遠只讀現成的 `data.json`,不在瀏覽器裡爬(會被 CORS 擋、也不符合自動更新)。

---

## 檔案結構

```
.
├─ index.html                  # 前端 dashboard(讀 data.json;含讀不到時的內建範例後備)
├─ data.json                   # 資料檔(爬蟲的輸出、前端的輸入)
├─ .github/workflows/
│  ├─ update-data.yml          # 正式:排程+手動觸發,跑爬蟲、自動寫回 data.json
│  └─ scrape.yml               # 診斷:probe 探測「撈不撈得到」(可保留)
├─ scraper/
│  ├─ scrape.py                # 正式爬蟲(★ extract() 待定稿)
│  ├─ probe.py                 # 診斷探測器(單次請求,報告可達性)
│  ├─ targets.json             # 爬蟲設定:14 個品項的品類/品牌/型號/來源網址
│  └─ requirements.txt         # requests, beautifulsoup4
└─ docs(若有保留)
   ├─ 競品分析Dashboard_開發流程_v3.md   # 整體流程與決策脈絡(很值得先看)
   ├─ gh操作清單.md                       # 用 gh 把整套跑起來的逐行清單
   ├─ 實測包說明.md                       # probe 怎麼跑、怎麼看判定
   └─ data填寫指南.md                     # 人工維護 data.json 的白話指南
```

---

## 現況:已完成 vs 待辦

**已完成**
- 前端三視圖、品類切換、排序、KPI、手機相容,並改成讀外部 `data.json`(含 draft / 讀不到 的狀態提示)。
- `data.json` 結構(契約)已定,並用範例值預填、標為 `draft: true`。
- GitHub Actions:排程 + 手動觸發 + 用內建 `GITHUB_TOKEN` 自動 commit 回 repo,皆已寫好。
- probe 診斷器:能回報 GitHub 國外 IP 撈不撈得到目標站。
- 合理性檢查、robots 檢查、優雅降級(抓失敗保留舊值)都已內建。

**待辦(接手的重點)**
1. **跑 probe 確認可達性**:GitHub 的伺服器 IP 在國外,撈中國站撈不撈得到要實測。判定 ✅ 才走方案 A(直接在 Actions 爬);🟡/❌ 要退方案 B(自架 Runner,用正常 IP)。
2. **★ 定稿 `scraper/scrape.py` 的 `extract()`**:目前是暫行版(正規表達式猜價格,正確率有限)。**必須先看實際抓回來的 `raw.html`,才能寫出精準的 CSS 選擇器。** 這是目前唯一卡住的技術點。
3. **填 `scraper/targets.json` 的 `url`**:每個品項填它的來源頁(官網或 ZOL/PConline 詳情頁,一頁對一型號最好解析)。留空的會被跳過。
4. 部署到 GitHub Pages(公開前先確認下方法律/商業風險)。

---

## 給 Claude Code 的起手式

建議直接這樣請它做(它在本機可以跑指令、看輸出,正好補上「看真實頁面」這段):

> 先讀 repo 裡的 README、`實測包說明.md`、`gh操作清單.md` 了解現況。
> 然後:(1) 用 `gh` 跑一次 probe,確認能不能撈到 `targets.json` 裡某個 ZOL 頁;
> (2) 把抓回的 `raw.html` 打開,定位價格 / 尺寸 / 重量 / 規格的實際節點;
> (3) 把 `scrape.py` 的 `extract()` 改成精準選擇器,跑一次驗證輸出對不對;
> (4) 用合理性檢查確認沒有空值 / 離譜價格,再讓 workflow 寫回 `data.json`。

「跑 → 看 raw.html → 改 extract() → 再跑驗證」這個循環在本機做最快,這正是搬到 Claude Code 的主要理由。

---

## data.json 資料契約(改前端或爬蟲都要遵守)

```jsonc
{
  "updated_at": "2026-06-27",   // 最後更新日期
  "currency": "CNY",
  "draft": true,                // true=有品項抓失敗/未核實,前端會跳黃色提醒
  "categories": {
    "mouse": { "label": "辦公滑鼠", "items": [ /* ... */ ] },
    "kb":    { "label": "辦公鍵盤", "items": [ /* ... */ ] }
  }
}
```
每個 item:
```jsonc
{
  "brand": "羅技 Logitech",   // 文字;爬蟲靠 brand+model 對應品項,要與 targets.json 完全一致
  "model": "MX Master 3S",
  "price": 749,               // 純數字,不要 ¥ 或逗號
  "size": "125×84×51 mm",     // 文字,沒有填 "—"
  "weight": "141 g",
  "specs": "無線 / 藍牙雙模 · 8000 DPI",
  "sell": "...",              // 賣點:自行改寫,勿整段照抄官網(著作權)
  "image": "",                // 圖片網址,留空顯示佔位圖示
  "source_url": ""            // 備查用
}
```

---

## 安全與合規界線(請務必沿用,不要為了方便繞過)

1. **鑰匙不交給 AI**:自動寫回 `data.json` 用的是 GitHub Actions **內建、用完即丟的 `GITHUB_TOKEN`**,不需要任何人產生或交出 token。Claude Code 操作 git/`gh` 時,用的是**你本機已登入的憑證**,憑證不離開你的環境。執行有風險的指令前讓使用者確認。
2. **public repo 不放任何密鑰**;需要時放 repo 的 Secrets,不寫進程式或前端。
3. **不繞過反爬 / 驗證碼**:只做禮貌的單次請求、看 robots.txt。某站若擋機器人,正解是換你有權使用的正常 IP、或該欄位改人工,**不是破解它**。
4. **公開發布前評估法律/商業風險**:系統性抓取、公開展示競品定價,在中國涉及服務條款與相關法規,且會被對手看到你在監控誰。要內部限定就別開 Pages。詳見 v3 流程第 2 步。(非法律意見,商業用途請找法務確認。)
5. **賣點等文案**:自行改寫摘要,不要整段複製官網文字。

---

## 維護的現實(別忽略)

目標網站一改版,`extract()` 就會抓不到——這是長期成本,不是做完一勞永逸。
所以:失敗通知、合理性檢查(已內建)、以及 `draft` 旗標的黃色提醒要持續看著。
排程是 UTC(每天 01:00 UTC = 台灣 09:00),且 repo 連續 60 天沒提交排程會被自動停用。
