# 🎙️ glitch-server (格莉奇 AI 語音通話與多服務聲學算力伺服器)

**[ai-brain-site (格莉奇OS)](https://yazelin.github.io/ai-brain-site/) 專屬的開源分散式語音/算力節點。**

提供 **全雙工即時語音通話 (In-Call Audio)**、**雙核心 TTS 聲學推論 (F5-TTS 337M 蒸餾底模 + CosyVoice 3 原生 0.5B)**、**雙軌台灣化音準替身系統**、**內建專業廣播控制台** 以及 **Cloudflare KV 自動心跳註冊**。

---

## 🌟 核心架構與功能亮點

```
瀏覽器前端 (ai-brain-site / OBS / Client)
       │
       │ HTTPS / WSS 全雙工通話
       ▼
Cloudflare Edge Tunnel (自動穿透 HTTPS) ── 自動心跳 ──> Cloudflare KV 註冊中心
       │                                              (glitch-chat.yazelinj303.workers.dev)
       ▼
FastAPI 核心伺服器 (@ localhost:8000 智慧動態順延)
       ├── 1. 雙引擎 TTS 推論核心 (F5-TTS Base 337M / CosyVoice 3 0.5B)
       ├── 2. 雙軌字音校正系統 (taiwanize.py：螢幕字幕軌 vs 聲學發音軌)
       ├── 3. 格莉奇大腦與人設推理 (LLM + 表情標籤自動判定)
       ├── 4. 內建專業錄音室廣播控制台 (Studio Broadcast Console @ GET /)
       └── 5. 分散式多服務節點網格 (Voice, LLM, Video, Reaction, Vision)
```

---

## 🎛️ 雙核心 TTS 聲學推論引擎

| 引擎名稱 | 參數量 | 延遲 (RTF) | 顯存佔用 | 特色與適用場景 |
| :--- | :--- | :--- | :--- | :--- |
| **`F5-TTS Base`** (預設) | **337 M (0.34B)** | **~1.2s (RTF=0.25)** | **~2.1 GB** | 極低延遲、高吞吐、最適合即時語音電話對話 |
| **`CosyVoice 3`** (原生) | **500 M (0.50B)** | **~3.5s (RTF=0.85)** | **~3.8 GB** | 視覺小說正典音質、極致細膩少女聲線與呼吸感、支援情感指令 |

---

## 🇹🇼 雙軌台灣化與音準替身系統 (`taiwanize.py`)

為了同時保證 **「螢幕字幕字形正確」** 與 **「TTS 聲學模型發音標準」**，系統全面採用雙軌替換：

1. **`for_speech=False` (螢幕字幕軌)**：
   * 簡繁與兩岸詞彙轉換（例如：`視頻` ➔ `影片`、`服務器` ➔ `伺服器`、`代碼` ➔ `程式碼`）。
   * 保持正典字形（例如：`第一頁有七行`、`林亞澤`、`零失誤`）。
2. **`for_speech=True` (聲學發音軌)**：
   * 自動套用《讀音替身表》修正大陸聲學模型破音字與兩岸聲調差異（例如：`七行` ➔ `七航`、`亞澤` ➔ 台灣輕柔三聲 `雅澤`、`垃圾` ➔ `勒瑟`、`我和` ➔ `我汗`、`微糖` ➔ `為糖`）。

---

## 📡 分散式多服務節點矩陣 (Service Mesh)

本伺服器支援向 Cloudflare KV 自動註冊為社群節點，未來可自由擴展以下五大服務模組：

* **`voice`**：文字轉語音、聲紋克隆（F5-TTS / CosyVoice3）
* **`llm`**：角色大腦對話（Ollama / vLLM / DeepSeek）
* **`reaction`**：直播彈幕即時反應、情緒表情判定、動作觸發
* **`video`**：Live2D 動態立繪視訊流、即時口型同步（MuseTalk / LivePortrait）
* **`vision`**：即時生草圖、角色插畫生成（ComfyUI / SDXL / Flux）

---

## 🚀 快速啟動

### 1. 啟動語音伺服器與控制台
```bash
cd ~/glitch-server
~/CosyVoice/.venv/bin/python server.py
```

### 2. 開啟工程控制台
瀏覽器直接打開：
👉 **`http://127.0.0.1:8000`**（若 8000 被佔用會自動順延至 8001, 8002...）

在控制台中即可：
* 監控 Cloudflare Tunnel 公網網址與在線狀態。
* 一鍵開啟 `ai-brain-site` 並自動套用伺服器網址。
* 切換 `F5-TTS` / `CosyVoice 3` 雙引擎並即時試聽台詞發音。
* 檢視系統事件日誌與聲學延遲指標。

---

## 🔌 API 規格

### 1. `POST /api/glitch-call` (全雙工通話)
```json
{
  "message": "格莉奇，你今天喝了什麼？",
  "engine": "f5_distilled",
  "speed": 1.0,
  "nfe": 12
}
```
* **Response**:
  ```json
  {
    "request_id": "...",
    "reply_text": "今天喝了一杯黑洞冰美式，超有精神的呢！",
    "audio_url": "data:audio/wav;base64,...",
    "duration": 2.8,
    "emotion": "happy",
    "latency_ms": 1150
  }
  ```

### 2. `POST /api/tts` (純文字合成)
### 3. `GET /api/engine/active` & `POST /api/engine/select` (引擎切換)
### 4. `GET /api/tunnel/status` (通道狀態)
