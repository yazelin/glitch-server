# glitch-voice-server (格莉奇 AI 語音通話與多服務聲學算力伺服器)

**[ai-brain-site (格莉奇OS)](https://yazelin.github.io/ai-brain-site/) 專屬的開源分散式語音/算力節點。**

提供 **全雙工即時語音通話 (In-Call Audio)**、**雙核心 TTS 聲學推論 (F5-TTS v1 Base 337M + CosyVoice 3 原生 0.5B)**、**多後端 LLM 大腦管理（支援社群節點大腦連線）**、**雙軌台灣化音準替身系統**、**內建專業廣播控制台** 以及 **Cloudflare KV 自動心跳註冊**。

---

## 核心架構與功能亮點

```
瀏覽器前端 (ai-brain-site / OBS / Client)
       │
       │ HTTPS / WSS 全雙工通話
       ▼
Cloudflare Edge Tunnel (自動穿透 HTTPS) ── 自動心跳 ──> Cloudflare KV 註冊中心
       │                                              (glitch-chat.yazelinj303.workers.dev)
       ▼
FastAPI 核心伺服器 (@ localhost:8000 智慧動態順延)
       ├── 1. 雙引擎 TTS 推論核心 (F5-TTS v1 Base 337M / CosyVoice 3 0.5B)
       ├── 2. 雙軌字音校正系統 (taiwanize.py：螢幕字幕軌 vs 聲學發音軌)
       ├── 3. 格莉奇大腦與人設推理 (LLM + 表情標籤自動判定)
       ├── 4. 內建專業錄音室廣播控制台 (Studio Broadcast Console @ GET /)
       └── 5. 分散式多服務節點網格 (Voice, LLM, Video, Reaction, Vision)
```

---

## 雙核心 TTS 聲學推論引擎

| 引擎名稱 | 參數量 | 延遲 (RTF) | 顯存佔用 | 特色與適用場景 |
| :--- | :--- | :--- | :--- | :--- |
| **`F5-TTS v1 Base`** (預設) | **337 M (0.34B)** | **~0.9s (RTF=0.20)** | **~1.0 GB** | 極低延遲、高吞吐、最適合即時語音電話對話 |
| **`CosyVoice 3`** (原生) | **500 M (0.50B)** | **~3.4s (RTF=0.78)** | **~4.8 GB** | 視覺小說正典音質、極致細膩少女聲線與呼吸感、支援情感指令 |

RTF（Real-Time Factor）＝ 合成耗時 ÷ 產出音訊長度，**低於 1 才追得上即時對話**。

量測條件：RTX 4060 Laptop 8GB、F5 用 `NFE=12`、6.12 秒參考音、23 字輸入、各跑 3 次取中位數。

| 輸入長度 | F5 耗時 / RTF | CosyVoice 3 耗時 / RTF |
| :--- | :--- | :--- |
| 3 字（音長 ~1–2s） | 0.66s / 0.33 | 1.56s / **1.50** |
| 23 字（音長 ~4.4s） | 0.92s / 0.20 | 3.41s / 0.78 |
| 66 字（音長 ~13s） | 1.79s / 0.13 | 7.47s / 0.59 |

* **RTF 跟輸入長度高度相關**，短句被固定開銷吃掉，別把單一數字當常數看。
* **CosyVoice 3 的短句 RTF 是 1.50，超過即時**，即時通話請用 F5，CosyVoice 3 留給可以等的正典錄音。
* F5 若改用官方預設 `NFE=32`，同樣三檔是 0.87 / 0.52 / 0.36，約 2.7 倍慢。
* 顯存為推論穩態的 nvidia-smi 程序峰值；torch 自報 allocated 分別是 0.70 / 3.24 GiB。
* 模型載入：F5 約 **6 秒**、CosyVoice 3 約 **18–23 秒**（熱切換引擎時使用者會等到這段）。
  把 page cache 踢掉重測，F5 變 7.8 秒、CosyVoice 3 仍是 20.7 秒 — 讀碟不是瓶頸。
  曾觀察到一次 CosyVoice 3 載入 88 秒，之後重現不出來，原因未定案。
* **合成時間不受 page cache 影響**，權重載完就常駐顯存。但每個 process 的第 1 次合成都比較貴：
  F5 是 1.24s（穩態 0.92s），**CosyVoice 3 是 8.71s（穩態 3.0–3.4s），多 5.5 秒**。
  `_load_f5()` 載入後有一次預熱合成把這段吃掉，`_load_cosyvoice()` 目前沒有。
* CosyVoice 3 底層是 LLM 取樣，**同一句話每次產出的音長都不同**（實測 4.00–4.84s），RTF 只能看區間；
  F5 是 flow matching，五次跑出來都是 4.70s 分毫不差。
* 兩顆同時常駐約 5.8 GB，8 GB 卡塞得下但不寬。

---

## 雙軌台灣化與音準替身系統 (`taiwanize.py`)

為了同時保證 **「螢幕字幕字形正確」** 與 **「TTS 聲學模型發音標準」**，系統全面採用雙軌替換：

1. **`for_speech=False` (螢幕字幕軌)**：
   * 簡繁與兩岸詞彙轉換（例如：`視頻` → `影片`、`服務器` → `伺服器`、`代碼` → `程式碼`）。
   * 保持正典字形（例如：`第一頁有七行`、`林亞澤`、`零失誤`）。
2. **`for_speech=True` (聲學發音軌)**：
   * 自動套用《讀音替身表》修正大陸聲學模型破音字與兩岸聲調差異（例如：`七行` → `七航`、`亞澤` → 台灣輕柔三聲 `雅澤`、`垃圾` → `勒瑟`、`我和` → `我汗`、`微糖` → `為糖`）。

---

## 多後端 LLM 大腦管理與社群節點連線 (LLM Reasoning Backends)

伺服器內建靈活的大腦推論後端管理器，可直接在控制台熱切換或透過 API 指定：

| 後端類型 (`backend`) | 預設模型 (`model`) | 連線方式與特色 |
| :--- | :--- | :--- |
| **`llmshare`** (預設) | `deepseek-v4-flash:0731` | 本機 CLI 調用，毫秒級極速回應、免 API Key、零網路依賴 |
| **`groq`** | `llama-3.3-70b-versatile` | 雲端極速推論 API，回覆細膩生動（需在控制台填入 `GROQ_API_KEY`） |
| **`local`** | `qwen2.5:7b` | 本機私有端點（預設 `http://127.0.0.1:11434/v1`，相容 Ollama / vLLM） |
| **`community`** | `default` | **社群節點推論大腦**：自動從 Cloudflare KV 探索在線大腦節點，共享社群推理算力 |

---

## 分散式多服務節點矩陣 (Service Mesh)

本伺服器支援向 Cloudflare KV 自動註冊為社群節點，未來可自由擴展以下五大服務模組：

* **`voice`**：文字轉語音、聲紋克隆（F5-TTS / CosyVoice3）
* **`llm`**：角色大腦對話（Ollama / vLLM / DeepSeek）
* **`reaction`**：直播彈幕即時反應、情緒表情判定、動作觸發
* **`video`**：Live2D 動態立繪視訊流、即時口型同步（MuseTalk / LivePortrait）
* **`vision`**：即時生草圖、角色插畫生成（ComfyUI / SDXL / Flux）

---

## 環境與相依

本機是借共用 venv `~/voice-venv`（實體在 `~/CosyVoice/.venv`，另有 f5-voice-loop、voice-loop、cosy-narrator、glitch-vn 一起用）。

**換機器 / 別人要跑**，先跑體檢，缺什麼它會一次印出來：

```bash
bash setup.sh
```

要自己建一份獨立環境（會多吃約 4.4G）：

```bash
python3.10 -m venv .venv
.venv/bin/pip install -r requirements.txt   # torch 的 CUDA index 見檔內註解
GLITCH_PYTHON=$PWD/.venv/bin/python bash setup.sh
```

非 pip 的相依：`cloudflared`（tunnel）、`ollama` 或 `llmshare`（LLM 後端，擇一）。
F5-TTS 模型第一次啟動會自己下載到 `~/.cache/huggingface`（約 1.3G）。

注意：切到 CosyVoice 引擎時 `engine.py` 會 `sys.path` 指向 `~/CosyVoice` 本體，
所以那個資料夾也是執行期相依，不只是 venv 借住。

## 快速啟動

### 1. 啟動語音伺服器與控制台
```bash
cd ~/glitch-voice-server
~/voice-venv/bin/python server.py
```

### 2. 開啟工程控制台
瀏覽器直接打開：
**`http://127.0.0.1:8000`**（若 8000 被佔用會自動順延至 8001, 8002...）

在控制台中即可：
* 監控 Cloudflare Tunnel 公網網址與在線狀態。
* 一鍵開啟 `ai-brain-site` 並自動套用伺服器網址。
* 切換 `F5-TTS` / `CosyVoice 3` 雙語音引擎。
* 切換 `llmshare` / `Groq` / `Local` / `Community` 四大推論大腦並即時測試 Q&A。
* 檢視系統事件日誌與聲學延遲指標。

---

## API 規格

### 1. `POST /api/glitch-call` (全雙工通話)
```json
{
  "message": "格莉奇，你今天喝了什麼？",
  "engine": "f5_distilled",
  "backend": "llmshare",
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

### 2. `POST /api/tts` (純文字語音合成)
### 3. `GET /api/engine/active` & `POST /api/engine/select` (語音引擎切換)
### 4. `GET /api/llm/config` & `POST /api/llm/config` (LLM 大腦配置)
### 5. `POST /api/llm/test` (LLM 大腦沙盒測試)
### 6. `GET /api/tunnel/status` (通道狀態)
