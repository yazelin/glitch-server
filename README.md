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
| **`llmshare`** (預設) | `gemma4:31b` | 本機 CLI 調用、免 API Key。選型理由見下方 |
| **`groq`** | `openai/gpt-oss-120b` | 雲端極速推論 API（需在控制台填入 `GROQ_API_KEY`）。選型理由見下方 |
| **`local`** | `qwen2.5:7b` | 本機私有端點（預設 `http://127.0.0.1:11434/v1`，相容 Ollama / vLLM） |
| **`community`** | `default` | **社群節點推論大腦**：自動從 Cloudflare KV 探索在線大腦節點，共享社群推理算力 |

### 預設模型是怎麼挑的

判準只有三個：**延遲**（語音通話要即時）、**回覆長度落在人設要求的 15 到 30 字**、**不吐簡體字或 `<think>`**。全部用本 repo 的格莉奇人設加對話歷史實測，2026-09-02。

**llmshare**（22 個模型全掃過，取前四名重跑三題）：

| 模型 | 中位延遲 | 三題字數 |
| :--- | ---: | :--- |
| **`gemma4:31b`** | **1.49s** | 20 / 18 / 20 |
| `deepseek-v4-flash:0731`（舊預設） | 1.80s | 15 / 12 / 17 |
| `gpt-oss:120b` | 2.27s | 21 / 17 / 15 |
| `deepseek-v4-pro:preview` | 2.54s | 21 / 21 / 21 |

`gemma4:31b` 又快又答得出角色梗（問 4KB 那題它自己講出「守則本的第一頁」）。`glm-5.3-flash` 品質更好但中位 8.53 秒，語音通話會卡，適合非即時用途。

**llmshare 是共用閘道，延遲抖動很大**：同一個模型在兩輪量測裡出現過 4.35s 與 1.80s。單跑一次的數字不能當結論。

順手掃到的地雷：`minimax-m3` 會把 `<think>` 吐進正文、`gpt-oss:20b` 回簡體字、`nemotron-3-ultra` 會插 emoji（TTS 唸不出來）。

**Groq**：

| 模型 | 延遲 | 字數 | 問題 |
| :--- | ---: | :--- | :--- |
| **`openai/gpt-oss-120b`** | 0.75–1.38s | 18–23 | 偶爾回空字串 |
| `qwen/qwen3.8-27b` | 0.42s | 8–9 | **不遵守字數指令**，加強語氣也拉不動，逼長會吐殘句與中國用詞 |
| `groq/compound-mini` | — | — | 不理會 `max_tokens`（設 150 回 512），輸入膨脹到 1112 |

原本的預設 `llama-3.3-70b-versatile` **已經從 Groq 下架**，呼叫會回 `The model does not exist or you do not have access to it`。

`MAX_REPLY_TOKENS` 從 150 拉到 800 是配套：gpt-oss 是推理型模型，token 先花在 reasoning 上，150 的上限下實測 **0/3 有回話**，`content` 一律空字串。

人設維持字數限制、不改成句數限制：實測把「15 到 30 個字」換成「講滿三句」之後，deepseek 變 70 字、glm 變 59 字、gpt-oss 變 93 字，語音要唸二十幾秒。

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
* 按一下開啟 `ai-brain-site` 並自動套用伺服器網址。
* 切換 `F5-TTS` / `CosyVoice 3` 雙語音引擎。
* 切換 `llmshare` / `Groq` / `Local` / `Community` 四大推論大腦並即時測試 Q&A。
* 檢視系統事件日誌與聲學延遲指標。

---

## 音色（聲紋參考音）

一個音色 = `assets/` 底下一組同名的 `.wav` 與 `.txt`。**丟兩個檔進去就多一個音色**，不用改 code。

```
assets/glitch.wav      assets/glitch.txt        ← 預設，格莉奇
assets/輕柔女孩.wav     assets/輕柔女孩.txt
```

`.txt` 是那段 wav 的**逐字稿，必須一字不差**。F5 靠它對齊聲紋，寫錯的話聲線跟咬字會一起飄，而且不會報錯，只會愈聽愈不像。

參考音建議 24000 Hz、單聲道、7 到 10 秒、乾淨無背景音。取樣率跟底模的 `target_sample_rate` 對齊，餵別的 F5 會自己重採樣，但先對齊比較不會出事。

指定方式有兩種，兩種都吃 `assets/` 掃出來的 id：

* 單次請求：`/api/tts` 或 `/api/glitch-call` 帶 `"voice": "<id>"`
* 換掉預設：`POST /api/voice/select`，或在控制台的下拉選單選

CosyVoice 的預設音色沿用 `glitch-vn/voice-ref/glitch.wav`（那支比較乾淨），其他音色一律用 `assets/` 裡的。

## 節點金鑰（誰能連這台）

**預設完全開放**，跟以前一樣，舊節點升上來不會壞。設了金鑰才開始擋。

```bash
# 方式一:環境變數(優先,控制台改不動)
GLITCH_NODE_KEY=你的金鑰 python server.py

# 方式二:控制台的 NODE ACCESS KEY 欄位,寫進 ~/.config/glitch-voice/node-key (0600)
```

呼叫端帶 `X-Glitch-Key: 你的金鑰`，或 `Authorization: Bearer 你的金鑰`。

| 路徑 | 設了金鑰之後 |
| :--- | :--- |
| `/health`、`/api/voices` | 仍然公開 |
| 其餘全部（含控制台 `/`、`/api/tts`、`/api/glitch-call`、LLM 設定、Tunnel 開關） | 要金鑰 |

`/health` 與 `/api/voices` 留著公開是有原因的：KV 節點清單上的節點要有人驗得出還活著，全鎖等於退出節點網格。

**本機直連（127.0.0.1）永遠放行**，不然第一次設密碼會沒有入口（控制台自己也在保護範圍內）。判斷「本機」不是只看來源 IP。cloudflared 是打到 `127.0.0.1`，從外面進來的請求來源 IP 也是本機。所以要同時滿足「來源是 loopback」而且「沒有任何 proxy 轉發標頭」（`X-Forwarded-For` / `CF-Connecting-IP` / `CF-Ray` / `X-Real-IP`）。這條實測過：同一支端點本機直連 200、經 Tunnel 進來 401。

### 連別人的節點

這台當呼叫端去打別人的節點時，會自己找對方的金鑰：

```bash
curl -X POST http://127.0.0.1:8000/api/node/peers \
  -H 'Content-Type: application/json' \
  -d '{"node_url":"https://對方.trycloudflare.com","key":"對方給的金鑰"}'
```

存在 `~/.config/glitch-voice/peer-keys.json`（0600）。**查不到就當對方是開放的直接打**，所以沒設密碼的節點照樣連得上。

節點註冊時會多送一個 `requires_key` 欄位讓呼叫端在打之前就知道該不該帶金鑰。**註冊中心 Worker 目前會把這個欄位丟掉**（那是另一個 repo），所以現階段呼叫端還是得吃一次 401 才知道。

## API 規格

### 1. `POST /api/glitch-call` (全雙工通話)
```json
{
  "message": "格莉奇，你今天喝了什麼？",
  "engine": "f5_distilled",
  "voice": "glitch",
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
### 4. `GET /api/voices` & `POST /api/voice/select` (音色切換)
### 5. `GET /api/llm/config` & `POST /api/llm/config` (LLM 大腦配置)
### 6. `POST /api/llm/test` (LLM 大腦沙盒測試)
### 7. `GET /api/tunnel/status` (通道狀態)
### 8. `GET /api/node/key` & `POST /api/node/key` (本節點金鑰)
### 9. `GET /api/node/peers` & `POST /api/node/peers` (別人節點的金鑰)

## 授權

程式碼 **MIT**（見 `LICENSE`）。**`assets/` 裡的角色語音素材是 CC BY-NC 4.0**
（見 `assets/LICENSE`）：可以自由使用、改作、散布，須標示出處，不可商用，
商業使用含角色授權要先問過林亞澤。
角色（格莉奇、黑洞先生）的設定正典在
[ai-brain-site](https://github.com/yazelin/ai-brain-site) 的 `persona.json`。
