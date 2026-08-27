# glitch-server

**格莉奇（Glitch）AI 語音通話與聲學算力伺服器**。

為 [ai-brain-site](https://yazelin.github.io/ai-brain-site/)（格莉奇OS）及其他前端應用提供專屬的 **全雙工即時語音通話（In-Call Audio）**、**F5-TTS 格莉奇聲紋合成**、**台灣化口音校正** 與 **Cloudflare Tunnel 雲端安全穿透**。

```
瀏覽器前端 (ai-brain-site)
       │
       │ HTTPS (Barge-In 全雙工插話)
       ▼
Cloudflare Tunnel (https://*.trycloudflare.com)
       │
       ▼
FastAPI Server (@ localhost:8000)
       ├── 1. LLM 回覆 (格莉奇 4KB 記憶體人設)
       ├── 2. 台灣化字音校正 (taiwanize.py)
       ├── 3. F5-TTS 聲學引擎 (NFE=16, 常駐顯存 ~2.1GB)
       └── 4. Base64 音訊與表情標籤回傳 (laugh/sad/count/neutral)
```

---

## 🎯 核心功能

1. **格莉奇 100% 原音再現**：預載 `assets/glitch.wav` 聲紋特徵，還原 4KB 記憶體虛擬主播的俏皮少女嗓音。
2. **極速反應（NFE=16）**：推論速度提升 200%，15 字短句生成僅需 **~1 秒**，顯存平穩維持在 **~2.1 GB**。
3. **全雙工插話支援（Barge-In）**：通話期間格莉奇說話時，使用者可隨時開口插話，前端瞬間靜音並發起新請求。
4. **原生台灣國語校正（`taiwanize.py`）**：自動將簡中/大陸詞彙轉為正統台灣用語，並校正破音字與聲調（如垃圾➔勒瑟、我和你➔我汗你、微糖微冰➔為糖為冰）。
5. **Cloudflare Quick Tunnel**：一鍵生成合法公網 HTTPS 網址，徹底解決 GitHub Pages 混合內容（Mixed Content）限制。

---

## 🚀 快速開始

### 1. 啟動後端伺服器
```bash
cd ~/glitch-server
~/CosyVoice/.venv/bin/python server.py
```
伺服器將在 `http://127.0.0.1:8000` 啟動，並在開機時預先快取格莉奇聲紋。

### 2. 啟動 Cloudflare HTTPS 隧道
開另一個終端機視窗：
```bash
cd ~/glitch-server
bash tunnel.sh
```
終端機會輸出類似 `https://xxxx.trycloudflare.com` 的 HTTPS 網址。將此網址填入前端即可開始通話！

---

## 🔌 API 介面說明

### 1. `POST /api/glitch-call`（全雙工通話端點）

* **Request (JSON)**:
  ```json
  {
    "message": "格莉奇，你今天喝了什麼？",
    "history": [
      {"role": "user", "content": "你好"},
      {"role": "assistant", "content": "你好呀！我是格莉奇！"}
    ],
    "speed": 1.05,
    "nfe": 16
  }
  ```

* **Response (JSON)**:
  ```json
  {
    "request_id": "req-12345",
    "user_message": "格莉奇，你今天喝了什麼？",
    "reply_text": "今天喝了一杯微糖微冰的黑洞拿鐵喔！好耶！",
    "audio_url": "data:audio/wav;base64,UklGRi...",
    "duration": 2.15,
    "emotion": "laugh",
    "latency_ms": 1150
  }
  ```

---

## 📜 授權與維護

MIT © 林亞澤 (yazelin)
