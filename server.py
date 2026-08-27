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
from fastapi.responses import Response
from pydantic import BaseModel

from engine import GlitchTTSEngine
from persona import GLITCH_SYSTEM_PROMPT, detect_emotion
from taiwanize import taiwanize_text

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

DEFAULT_MODEL = {
    "llmshare": "deepseek-v4-flash:0731",
    "groq": "openai/gpt-oss-120b",
    "local": "qwen3.5-4b",
}

class ChatHistoryItem(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class GlitchCallRequest(BaseModel):
    message: str
    history: Optional[List[ChatHistoryItem]] = []
    request_id: Optional[str] = None
    speed: Optional[float] = 0.92
    nfe: Optional[int] = 12
    backend: Optional[str] = "llmshare"
    model: Optional[str] = None

class TTSRequest(BaseModel):
    text: str
    speed: Optional[float] = 0.92
    nfe: Optional[int] = 12
    return_base64: Optional[bool] = False


def call_llm(message: str, history: List[ChatHistoryItem], backend: str, model: str) -> str:
    """調用 LLM 生成格莉奇的回覆"""
    sys_prompt = GLITCH_SYSTEM_PROMPT
    past_dialogue = ""
    if history:
        turns = [f"{'你' if h.role=='assistant' else '我'}：{h.content}" for h in history[-6:]]
        past_dialogue = "\n".join(turns) + "\n"

    user_prompt = (
        f"{sys_prompt}\n"
        f"【對話歷史】\n{past_dialogue}"
        f"我：{message}\n"
        f"格莉奇（簡短自然口語回答）："
    )

    target_model = model or DEFAULT_MODEL.get(backend, DEFAULT_MODEL["llmshare"])

    if backend == "llmshare":
        try:
            r = subprocess.run(
                ["llmshare", "raw", target_model, user_prompt],
                capture_output=True,
                text=True,
                timeout=15
            )
            raw = r.stdout if r.returncode == 0 else f"欸嘿，我的 4KB 記憶體剛才當機了一下！"
        except Exception as e:
            raw = f"記憶體讀取超時囉：{e}"
    elif backend == "groq":
        key = os.environ.get("GROQ_API_KEY")
        if not key:
            return "未設定 GROQ_API_KEY"
        payload = json.dumps({
            "model": target_model,
            "messages": [
                {"role": "system", "content": GLITCH_SYSTEM_PROMPT},
                *[{"role": h.role, "content": h.content} for h in history[-6:]],
                {"role": "user", "content": message}
            ],
            "max_tokens": 150
        })
        req = urllib.request.Request(
            "https://api.groq.com/openai/v1/chat/completions",
            payload.encode(),
            {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raw = f"Groq 連線異常：{e}"
    else:
        # local
        payload = json.dumps({
            "model": target_model,
            "messages": [
                {"role": "system", "content": GLITCH_SYSTEM_PROMPT},
                *[{"role": h.role, "content": h.content} for h in history[-6:]],
                {"role": "user", "content": message}
            ],
            "max_tokens": 150
        })
        req = urllib.request.Request(
            "http://127.0.0.1:8080/v1/chat/completions",
            payload.encode(),
            {"Content-Type": "application/json"}
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                data = json.load(resp)
            raw = data["choices"][0]["message"].get("content") or ""
        except Exception as e:
            raw = f"在地端模型異常：{e}"

    cleaned = " ".join(raw.strip().split())
    # 避免 LLM 自帶角色前綴
    for prefix in ["格莉奇：", "格莉奇:", "Glitch:", "Glitch："]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):].strip()
    return cleaned or "好耶！我有聽到你說話喔！"


@app.get("/health")
def health_check():
    return {
        "status": "ok",
        "service": "glitch-voice-server",
        "tts_engine": f"F5-TTS (Base, NFE={DEFAULT_NFE})",
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
        speed=req.speed,
        nfe=req.nfe
    )

    if req.return_base64:
        b64 = base64.b64encode(wav_bytes).decode("ascii")
        return {
            "text": display_text,
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

    # 4. F5-TTS 聲學合成
    try:
        wav_bytes, duration, sr = engine.synthesize_wav_bytes(
            text=reply_speech,
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
    print("啟動格莉奇語音伺服器 @ http://127.0.0.1:8000 ...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
