#!/usr/bin/env python3
"""F5-TTS 格莉奇專屬聲學推論引擎（預載聲紋、NFE=16、顯存常駐 ~2.1GB）。"""
import io
import time
from pathlib import Path
import soundfile as sf
import torch

HERE = Path(__file__).resolve().parent
ASSETS = HERE / "assets"
DEFAULT_WAV = ASSETS / "glitch.wav"
DEFAULT_TXT = ASSETS / "glitch.txt"

class GlitchTTSEngine:
    def __init__(self, nfe_default: int = 16):
        self.nfe_default = nfe_default
        self.ref_wav = str(DEFAULT_WAV)
        self.ref_text = DEFAULT_TXT.read_text(encoding="utf-8").strip() if DEFAULT_TXT.exists() else ""
        self.f5 = None
        self._load_model()

    def _load_model(self):
        print(f"[GlitchTTSEngine] 正在載入 F5-TTS 模型 (預設 NFE={self.nfe_default})...", flush=True)
        t0 = time.time()
        from f5_tts.api import F5TTS
        self.f5 = F5TTS()
        print(f"[GlitchTTSEngine] F5-TTS 載入完成！耗時 {time.time()-t0:.2f}s", flush=True)
        print(f"[GlitchTTSEngine] 預設聲紋：{self.ref_wav}")
        print(f"[GlitchTTSEngine] 參考文字：{self.ref_text[:30]}...")

        # 🚀 伺服器開機主動預熱 GPU 顯存與 CUDA JIT (消除首次通話的冷啟動延遲)
        print(f"[GlitchTTSEngine] 正在進行 GPU 聲學預熱 (Warmup)...", flush=True)
        t_w = time.time()
        try:
            self.f5.infer(
                ref_file=self.ref_wav,
                ref_text=self.ref_text,
                gen_text="連線就緒",
                nfe_step=self.nfe_default,
                show_info=lambda x: None
            )
            print(f"[GlitchTTSEngine] GPU 預熱完成（{time.time()-t_w:.2f}s），後續所有通話將達極速！", flush=True)
        except Exception as e:
            print(f"[GlitchTTSEngine] 預熱略過: {e}", flush=True)

    def synthesize_wav_bytes(self, text: str, speed: float = 1.05, nfe: int = None) -> tuple[bytes, float, int]:
        """合成語音並回傳 (wav_bytes, duration_secs, sample_rate)"""
        nfe_step = nfe or self.nfe_default
        t0 = time.time()
        wav_out, sr, _ = self.f5.infer(
            ref_file=self.ref_wav,
            ref_text=self.ref_text,
            gen_text=text,
            speed=speed,
            nfe_step=nfe_step,
            show_info=lambda x: None
        )
        duration = len(wav_out) / sr
        buf = io.BytesIO()
        sf.write(buf, wav_out, sr, format="WAV")
        wav_bytes = buf.getvalue()
        elapsed = time.time() - t0
        print(f"[TTS] 合成「{text[:20]}...」 | NFE={nfe_step} | 耗時={elapsed:.2f}s | 音訊長={duration:.2f}s (RTF={elapsed/duration:.2f})")
        return wav_bytes, duration, sr
