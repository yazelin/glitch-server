#!/usr/bin/env python3
"""格莉奇語音通話與 AI 算力伺服器 (Glitch Voice Server)。
提供 F5-TTS 格莉奇聲紋合成、台灣化前處理、LLM 問答與全雙工打斷支援。
"""
import base64
import json
import os
import subprocess
import time
import urllib.request
from typing import List, Optional
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, Response
from pydantic import BaseModel

import socket
from engine import GlitchTTSEngine
from persona import GLITCH_SYSTEM_PROMPT, detect_emotion
from taiwanize import taiwanize_text
from tunnel import tunnel_mgr

def find_available_port(start_port: int = 8000, max_attempts: int = 50) -> int:
    """自動探測可用埠號，若 8000 被佔用則依序遞增 (8001, 8002...)"""
    for p in range(start_port, start_port + max_attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("0.0.0.0", p))
                return p
            except OSError:
                continue
    return start_port

ACTIVE_PORT = find_available_port(int(os.environ.get("PORT", "8000")))
tunnel_mgr.port = ACTIVE_PORT

app = FastAPI(title="Glitch Voice Server", description="格莉奇 AI 語音通話與聲學算力核心")

# 開放所有跨域存取 (允許 GitHub Pages 與本機端點)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    # 規範上 "*" 不能搭 credentials，瀏覽器會直接擋掉；前端本來就沒帶 cookie
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 初始化 F5-TTS 聲學引擎（顯存常駐 ~2.1GB，NFE=12 極速模式）
DEFAULT_NFE = 12
engine = GlitchTTSEngine(nfe_default=DEFAULT_NFE)

class LLMConfigManager:
    def __init__(self):
        self.backend = "llmshare"
        self.model = "deepseek-v4-flash:0731"
        self.groq_api_key = os.environ.get("GROQ_API_KEY", "")
        self.local_url = "http://127.0.0.1:11434/v1"
        self.community_node_url = ""
        self.lock = threading.Lock()

    def get_config(self):
        with self.lock:
            return {
                "backend": self.backend,
                "model": self.model,
                "has_groq_key": bool(self.groq_api_key),
                "local_url": self.local_url,
                "community_node_url": self.community_node_url,
                "available_backends": [
                    {
                        "id": "llmshare",
                        "name": "llmshare (本機 CLI • 免金鑰)",
                        "default_model": "deepseek-v4-flash:0731",
                        "desc": "本機極速直連，超低延遲回答"
                    },
                    {
                        "id": "groq",
                        "name": "Groq Cloud (極速雲端 API)",
                        "default_model": "llama-3.3-70b-versatile",
                        "desc": "雲端高智慧大腦，回覆生動細膩"
                    },
                    {
                        "id": "local",
                        "name": "Local Endpoint (本機 Ollama / vLLM)",
                        "default_model": "qwen2.5:7b",
                        "desc": "私有在地端大模型推理"
                    },
                    {
                        "id": "community",
                        "name": "Community Node Mesh (社群推論大腦)",
                        "default_model": "default",
                        "desc": "連接其他社群開源節點的共享推理算力"
                    }
                ]
            }

    def update_config(self, backend=None, model=None, groq_api_key=None, local_url=None, community_node_url=None):
        with self.lock:
            if backend:
                self.backend = backend
            if model is not None:
                self.model = model
            if groq_api_key is not None:
                self.groq_api_key = groq_api_key
            if local_url is not None:
                self.local_url = local_url
            if community_node_url is not None:
                self.community_node_url = community_node_url
        return self.get_config()

llm_mgr = LLMConfigManager()

class ChatHistoryItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class GlitchCallRequest(BaseModel):
    message: str
    history: Optional[List[ChatHistoryItem]] = []
    request_id: Optional[str] = None
    engine: Optional[str] = None
    speed: Optional[float] = 1.0
    nfe: Optional[int] = 12
    backend: Optional[str] = None
    model: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    engine: Optional[str] = None
    speed: Optional[float] = 1.0
    nfe: Optional[int] = 12
    return_base64: Optional[bool] = False

class SelectEngineRequest(BaseModel):
    engine: str

class UpdateLLMConfigRequest(BaseModel):
    backend: Optional[str] = None
    model: Optional[str] = None
    groq_api_key: Optional[str] = None
    local_url: Optional[str] = None
    community_node_url: Optional[str] = None

class TestLLMRequest(BaseModel):
    message: str
    backend: Optional[str] = None
    model: Optional[str] = None


def call_llm(message: str, history: Optional[List[ChatHistoryItem]] = None, backend: Optional[str] = None, model: Optional[str] = None) -> str:
    """調用 LLM 生成格莉奇的回覆"""
    cfg = llm_mgr.get_config()
    active_backend = backend or cfg["backend"]
    target_model = model or cfg["model"]

    sys_prompt = GLITCH_SYSTEM_PROMPT
    past_dialogue = ""
    if history:
        turns = [f"{'你' if h.role=='assistant' else '我'}：{h.content}" for h in history[-6:]]
        past_dialogue = "\n".join(turns) + "\n"

    raw = ""
    if active_backend == "llmshare":
        user_prompt = (
            f"{sys_prompt}\n"
            f"【對話歷史】\n{past_dialogue}"
            f"我：{message}\n"
            f"格莉奇（簡短自然口語回答）："
        )
        try:
            r = subprocess.run(
                ["llmshare", "raw", target_model or "deepseek-v4-flash:0731", user_prompt],
                capture_output=True,
                text=True,
                timeout=15
            )
            raw = r.stdout if r.returncode == 0 else "欸嘿，我的 4KB 記憶體剛才當機了一下！"
        except Exception as e:
            raw = f"記憶體讀取超時囉：{e}"

    elif active_backend == "groq":
        key = llm_mgr.groq_api_key or os.environ.get("GROQ_API_KEY")
        if not key:
            return "未設定 GROQ_API_KEY，請在控制台填入金鑰。"
        payload = json.dumps({
            "model": target_model or "llama-3.3-70b-versatile",
            "messages": [
                {"role": "system", "content": GLITCH_SYSTEM_PROMPT},
                *[{"role": h.role, "content": h.content} for h in (history or [])[-6:]],
                {"role": "user", "content": message}
            ],
            "max_tokens": 150
        })
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            payload.encode(),
            {
                "Authorization": f"Bearer {key}",
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raw = f"Groq 連線異常：{e}"

    elif active_backend == "community":
        node_url = (cfg.get("community_node_url") or "").rstrip("/")
        if not node_url:
            # 主動向 KV 註冊中心查詢全網在線的社群大腦節點 (Auto-Discovery)
            try:
                req_disc = urllib.request.Request(
                    "https://glitch-chat.yazelinj303.workers.dev/voice/nodes",
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1"}
                )
                with urllib.request.urlopen(req_disc, timeout=4) as resp_d:
                    d_nodes = json.load(resp_d).get("nodes", [])
                    if d_nodes:
                        node_url = d_nodes[0].get("url", "").rstrip("/")
            except Exception:
                pass

        if not node_url:
            return "全網尚未發現任何在線的社群大腦節點，請確認節點在線狀態。"

        endpoint = node_url if node_url.endswith("/chat/completions") else f"{node_url}/v1/chat/completions"
        payload = json.dumps({
            "model": target_model or "default",
            "messages": [
                {"role": "system", "content": GLITCH_SYSTEM_PROMPT},
                *[{"role": h.role, "content": h.content} for h in (history or [])[-6:]],
                {"role": "user", "content": message}
            ],
            "max_tokens": 150
        })
        req = urllib.request.Request(
            endpoint,
            payload.encode(),
            {
                "Content-Type": "application/json",
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1"
            }
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raw = f"社群大腦節點連線異常：{e}"

    else:
        # local endpoint (Ollama / vLLM / llama.cpp)
        local_base = (cfg.get("local_url") or "http://127.0.0.1:11434/v1").rstrip("/")
        endpoint = local_base if local_base.endswith("/chat/completions") else f"{local_base}/chat/completions"
        payload = json.dumps({
            "model": target_model or "qwen2.5:7b",
            "messages": [
                {"role": "system", "content": GLITCH_SYSTEM_PROMPT},
                *[{"role": h.role, "content": h.content} for h in (history or [])[-6:]],
                {"role": "user", "content": message}
            ],
            "max_tokens": 150
        })
        req = urllib.request.Request(
            endpoint,
            payload.encode(),
            {"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=12) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raw = f"地端模型連線異常：{e}"

    cleaned = " ".join(raw.strip().split())
    for prefix in ["格莉奇：", "格莉奇:", "Glitch:", "Glitch："]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned or "好耶！我有聽到你說話喔！"


@app.get("/api/llm/config")
def get_llm_config():
    return llm_mgr.get_config()


@app.post("/api/llm/config")
def update_llm_config(req: UpdateLLMConfigRequest):
    return llm_mgr.update_config(
        backend=req.backend,
        model=req.model,
        groq_api_key=req.groq_api_key,
        local_url=req.local_url,
        community_node_url=req.community_node_url
    )


@app.post("/api/llm/test")
def test_llm_endpoint(req: TestLLMRequest):
    t0 = time.time()
    reply = call_llm(message=req.message, backend=req.backend, model=req.model)
    elapsed_ms = int((time.time() - t0) * 1000)
    cfg = llm_mgr.get_config()
    return {
        "user_message": req.message,
        "reply": reply,
        "backend": req.backend or cfg["backend"],
        "model": req.model or cfg["model"],
        "latency_ms": elapsed_ms
    }


@app.on_event("startup")
def on_startup():
    try:
        tunnel_mgr.start_tunnel()
    except Exception as e:
        print(f"[Startup] Tunnel 自動啟動略過: {e}")

@app.on_event("shutdown")
def on_shutdown():
    try:
        tunnel_mgr.stop_tunnel()
    except Exception:
        pass


@app.get("/", response_class=HTMLResponse)
def index_dashboard():
    """格莉奇語音核心控制台 UI"""
    dashboard_path = os.path.join(os.path.dirname(__file__), "dashboard.html")
    if os.path.exists(dashboard_path):
        with open(dashboard_path, "r", encoding="utf-8") as f:
            return HTMLResponse(content=f.read())
    return HTMLResponse(content="<h1>格莉奇語音伺服器運行中 (Port 8000)</h1>")


@app.get("/api/tunnel/status")
def get_tunnel_status():
    return tunnel_mgr.get_status()


@app.post("/api/tunnel/start")
def start_tunnel():
    return tunnel_mgr.start_tunnel()


@app.post("/api/tunnel/stop")
def stop_tunnel():
    return tunnel_mgr.stop_tunnel()


@app.get("/api/engine/active")
def get_active_engine():
    return {
        "active_engine": engine.active_engine,
        "available_engines": [
            {
                "id": "f5_distilled",
                "name": "F5-TTS (CosyVoice3 蒸餾底模)",
                "desc": "極速超低延遲 (~1.2s, RTF=0.25) • 顯存佔用低"
            },
            {
                "id": "cosyvoice_native",
                "name": "CosyVoice 3 (原生 Instruct 0.5B)",
                "desc": "極致細膩少女聲線與自然呼吸感 • 視覺小說正典音質"
            }
        ]
    }


@app.post("/api/engine/select")
def select_engine(req: SelectEngineRequest):
    act = engine.set_engine(req.engine)
    return {"status": "ok", "active_engine": act}


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "glitch-voice-server",
        "port": ACTIVE_PORT,
        "active_engine": engine.active_engine,
        "tts_engine": f"{engine.active_engine} (NFE={DEFAULT_NFE})",
        "character": "格莉奇 (Glitch)",
        "memory": "4KB",
    }


@app.post("/api/tts")
def tts_endpoint(req: TTSRequest):
    """純文字語音合成端點"""
    if not req.text.strip():
        raise HTTPException(status_code=400, detail="文字不得為空")

    speech_text = taiwanize_text(req.text, for_speech=True)
    display_text = taiwanize_text(req.text, for_speech=False)

    wav_bytes, duration, sr = engine.synthesize_wav_bytes(
        text=speech_text,
        engine_name=req.engine,
        speed=req.speed,
        nfe=req.nfe
    )

    if req.return_base64:
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        return {
            "text": display_text,
            "speech_text": speech_text,
            "engine": req.engine or engine.active_engine,
            "audio_base64": f"data:audio/wav;base64,{b64}",
            "duration": duration,
            "sample_rate": sr
        }

    return Response(content=wav_bytes, media_type="audio/wav")


@app.post("/api/glitch-call")
def glitch_call_endpoint(req: GlitchCallRequest):
    """格莉奇語音通話全雙工端點（文字問答 ＋ 台灣化 ＋ 格莉奇聲紋合成 ＋ 表情判定）"""
    t_start = time.time()
    user_msg = req.message.strip()
    if not user_msg:
        raise HTTPException(status_code=400, detail="提問內容不得為空")

    # 1. LLM 產生回應
    raw_reply = call_llm(
        message=user_msg,
        history=req.history,
        backend=req.backend,
        model=req.model
    )

    # 2. 台灣化處理（顯示 vs 發音）
    reply_display = taiwanize_text(raw_reply, for_speech=False)
    reply_speech = taiwanize_text(raw_reply, for_speech=True)

    # 3. 表情推論
    emotion = detect_emotion(reply_display)

    # 4. 聲學合成 (F5-TTS 蒸餾 或 原生 CosyVoice3)
    try:
        wav_bytes, duration, sr = engine.synthesize_wav_bytes(
            text=reply_speech,
            engine_name=req.engine,
            speed=req.speed,
            nfe=req.nfe
        )
    except Exception as e:
        # 寧可回 500 讓前端顯示錯誤，也不要回一個解不開的 data URL 讓人以為是喇叭壞了
        raise HTTPException(status_code=500, detail=f"語音合成失敗：{e}")

    # 5. 打包 Base64 Audio URL
    b64_audio = base64.b64encode(wav_bytes).decode("ascii")
    audio_data_url = f"data:audio/wav;base64,{b64_audio}"

    total_elapsed = time.time() - t_start
    print(f"[GlitchCall] 完成通話輪次 | 總耗時={total_elapsed:.2f}s | 表情={emotion} | 回應: {reply_display}")

    return {
        "request_id": req.request_id,
        "user_message": user_msg,
        "reply_text": reply_display,
        "audio_url": audio_data_url,
        "duration": duration,
        "emotion": emotion,
        "latency_ms": int(total_elapsed * 1000)
    }


if __name__ == "__main__":
    import uvicorn
    print(f"啟動格莉奇語音伺服器 @ http://127.0.0.1:{ACTIVE_PORT} ...")
    uvicorn.run(app, host="0.0.0.0", port=ACTIVE_PORT)
