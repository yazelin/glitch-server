#!/usr/bin/env python3
"""格莉奇多引擎聲學推論核心 (Dual-Engine TTS Core)。
支援：
1. F5-TTS v1 Base (官方 Emilia 中英底模)：極速超低延遲 (~1.2s, RTF=0.25)。
2. CosyVoice 3 (原生 Instruct 0.5B)：極致細膩少女聲線與自然呼吸感。
"""
import io
import os
import sys
import threading
import time
from pathlib import Path
from typing import Optional, Tuple, Literal

import numpy as np
import soundfile as sf
import torch

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
DEFAULT_WAV = ASSETS / "glitch.wav"
DEFAULT_TXT = ASSETS / "glitch.txt"

COSY_DIR = Path("/home/ct/CosyVoice")
COSY_MODEL_DIR = COSY_DIR / "pretrained_models/Fun-CosyVoice3-0.5B"
COSY_REF_WAV = Path("/home/ct/glitch-vn/voice-ref/glitch.wav")
COSY_INSTRUCT = "You are a helpful assistant. 用台灣腔的中文說，用甜美、活潑、自然的少女語氣說<|endofprompt|>"

class GlitchTTSEngine:
    def __init__(self, nfe_default: int = 12, default_engine: str = "f5_distilled"):
        self.nfe_default = nfe_default
        self.active_engine = default_engine
        self.active_voice = DEFAULT_WAV.stem
        self.ref_wav, self.ref_text = self._voice_ref(self.active_voice)
        
        self.f5 = None
        self.cosyvoice = None
        self._lock = threading.Lock()
        
        # 預載 F5-TTS v1 Base 底模
        self._load_f5()

    # 音色 = assets/ 底下一組同名的 .wav 與 .txt。.txt 是那段 wav 的逐字稿,
    # F5 靠它對齊聲紋,寫錯聲線跟咬字會一起飄。
    def voices(self) -> list:
        return sorted(p.stem for p in ASSETS.glob("*.wav") if p.with_suffix(".txt").exists())

    def _voice_ref(self, voice_id: str) -> Tuple[str, str]:
        wav = ASSETS / f"{voice_id}.wav"
        txt = ASSETS / f"{voice_id}.txt"
        if not wav.exists() or not txt.exists():
            raise ValueError(f"找不到音色 {voice_id}(需要 assets/{voice_id}.wav 與 .txt)")
        return str(wav), txt.read_text(encoding="utf-8").strip()

    def set_voice(self, voice_id: str) -> str:
        with self._lock:
            self.ref_wav, self.ref_text = self._voice_ref(voice_id)
            self.active_voice = voice_id
            return self.active_voice

    def _load_f5(self):
        if self.f5 is not None:
            return
        print(f"[GlitchTTSEngine] 正在載入 F5-TTS 模型 (預設 NFE={self.nfe_default})...", flush=True)
        t0 = time.time()
        from f5_tts.api import F5TTS
        self.f5 = F5TTS()
        print(f"[GlitchTTSEngine] F5-TTS 載入完成！耗時 {time.time()-t0:.2f}s", flush=True)
        
        # 預熱
        try:
            self.f5.infer(
                ref_file=self.ref_wav,
                ref_text=self.ref_text,
                gen_text="連線就緒",
                nfe_step=self.nfe_default,
                show_info=lambda x: None
            )
        except Exception:
            pass

    def _load_cosyvoice(self):
        if self.cosyvoice is not None:
            return
        print(f"[GlitchTTSEngine] 正在載入 CosyVoice 3 (0.5B Instruct) 模型...", flush=True)
        t0 = time.time()
        sys.path.insert(0, str(COSY_DIR))
        sys.path.insert(0, str(COSY_DIR / "third_party/Matcha-TTS"))
        from cosyvoice.cli.cosyvoice import AutoModel
        self.cosyvoice = AutoModel(model_dir=str(COSY_MODEL_DIR))
        print(f"[GlitchTTSEngine] CosyVoice 3 載入完成！耗時 {time.time()-t0:.2f}s", flush=True)

        # 預熱：第一次合成比穩態貴約 5.5s（8.71s vs 3.0-3.4s），先在這裡吃掉
        try:
            ref = str(COSY_REF_WAV) if COSY_REF_WAV.exists() else self.ref_wav
            list(self.cosyvoice.inference_instruct2(
                "連線就緒", COSY_INSTRUCT, ref, stream=False, speed=1.0))
        except Exception:
            pass

    def set_engine(self, engine_name: str) -> str:
        with self._lock:
            if engine_name in ["cosyvoice_native", "cosyvoice"]:
                self.active_engine = "cosyvoice_native"
                self._load_cosyvoice()
            else:
                self.active_engine = "f5_distilled"
                self._load_f5()
            return self.active_engine

    def synthesize_wav_bytes(
        self,
        text: str,
        engine_name: Optional[str] = None,
        speed: float = 1.0,
        nfe: Optional[int] = None,
        voice: Optional[str] = None
    ) -> Tuple[bytes, float, int]:
        target_engine = engine_name or self.active_engine
        target_voice = voice or self.active_voice
        ref_wav, ref_text = self._voice_ref(target_voice)
        t0 = time.time()

        with self._lock:
            if target_engine in ["cosyvoice_native", "cosyvoice"]:
                self._load_cosyvoice()
                if target_voice == DEFAULT_WAV.stem and COSY_REF_WAV.exists():
                    ref_wav = str(COSY_REF_WAV)   # 預設音色沿用 glitch-vn 那支較乾淨的參考音
                gen = self.cosyvoice.inference_instruct2(
                    text,
                    COSY_INSTRUCT,
                    ref_wav,
                    stream=False,
                    speed=speed
                )
                pieces = [r["tts_speech"] for r in gen]
                if not pieces:
                    raise RuntimeError("CosyVoice3 回傳空音訊")
                tensor_out = torch.cat(pieces, dim=1)
                wav_out = tensor_out.squeeze().cpu().numpy()
                sr = self.cosyvoice.sample_rate
            else:
                self._load_f5()
                nfe_step = nfe or self.nfe_default
                wav_out, sr, _ = self.f5.infer(
                    ref_file=ref_wav,
                    ref_text=ref_text,
                    gen_text=text,
                    speed=speed,
                    nfe_step=nfe_step,
                    show_info=lambda x: None
                )
                if wav_out is None or len(wav_out) == 0:
                    raise RuntimeError("F5-TTS 回傳空音訊")

        wav_out = np.asarray(wav_out, dtype=np.float32)
        peak = float(np.max(np.abs(wav_out)))
        if peak > 0:
            wav_out = wav_out * (0.891 / peak)

        duration = len(wav_out) / sr
        buf = io.BytesIO()
        sf.write(buf, wav_out, sr, format="WAV", subtype="PCM_16")
        wav_bytes = buf.getvalue()
        if len(wav_bytes) < 44 or wav_bytes[:4] != b"RIFF":
            raise RuntimeError("合成結果不是合法的 WAV")

        elapsed = time.time() - t0
        print(f"[TTS][{target_engine}/{target_voice}] 「{text[:20]}...」 | 耗時={elapsed:.2f}s | 音訊長={duration:.2f}s (RTF={elapsed/duration:.2f})")
        return wav_bytes, duration, sr
