#!/usr/bin/env bash
# glitch-voice-server 環境依賴檢查與快速啟動腳本
# 缺什麼就印什麼，不要讓人跑到一半才撞 ImportError
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# 這台機器是借 CosyVoice 的 venv（F5-TTS 也裝在那裡）。換機器就設 GLITCH_PYTHON。
PYTHON="${GLITCH_PYTHON:-${HOME}/voice-venv/bin/python}"
FAIL=0

echo "=== 檢查格莉奇伺服器環境 ==="

if [ ! -x "$PYTHON" ]; then
  echo "❌ 找不到 Python: $PYTHON"
  echo "   設 GLITCH_PYTHON 指到你的 python，或自己建一個："
  echo "   python3.10 -m venv .venv && .venv/bin/pip install -r $HERE/requirements.txt"
  exit 1
fi
echo "✅ Python: $($PYTHON --version) ($PYTHON)"

# 逐一 import，缺的一次全印出來
MISSING=$("$PYTHON" - <<'PY'
import importlib.util as u
need = ["torch","torchaudio","f5_tts","fastapi","uvicorn","pydantic","numpy","soundfile"]
print(" ".join(m for m in need if u.find_spec(m) is None))
PY
)
if [ -n "$MISSING" ]; then
  echo "❌ 缺套件: $MISSING"
  echo "   $PYTHON -m pip install -r $HERE/requirements.txt   （torch 的 CUDA index 見檔內註解）"
  FAIL=1
else
  echo "✅ Python 套件齊全 ($("$PYTHON" -c 'import torch;print("torch",torch.__version__,"cuda" if torch.cuda.is_available() else "cpu")'))"
fi

if [ ! -f "$HERE/assets/glitch.wav" ]; then
  echo "❌ 缺少格莉奇參考音檔: $HERE/assets/glitch.wav"
  FAIL=1
else
  echo "✅ 格莉奇參考音檔就緒 ($(stat -c%s "$HERE/assets/glitch.wav") bytes)"
fi

# 非 pip 的相依，缺了只是某些功能不能用，不擋啟動
command -v cloudflared >/dev/null 2>&1 || [ -x "$HOME/.local/bin/cloudflared" ] \
  && echo "✅ cloudflared 就緒（對外 HTTPS 網址）" \
  || echo "⚠️  沒有 cloudflared：tunnel 功能不能用，本機直連還是可以"
curl -sf -m 2 http://127.0.0.1:11434/api/tags >/dev/null 2>&1 \
  && echo "✅ ollama 在跑（LLM 後端預設打它）" \
  || echo "⚠️  ollama 沒在跑：LLM 要改用 groq 或 llmshare 後端"
command -v llmshare >/dev/null 2>&1 \
  && echo "✅ llmshare 就緒（選用的 LLM 後端）" \
  || echo "⚠️  沒有 llmshare（選用，不影響 TTS）"

[ -d "$HOME/.cache/huggingface/hub/models--SWivid--F5-TTS" ] \
  && echo "✅ F5-TTS 模型已快取" \
  || echo "⚠️  F5-TTS 模型還沒下載，第一次啟動會自己抓約 1.3G"

echo ""
if [ "$FAIL" -ne 0 ]; then
  echo "=== 上面有 ❌，先補齊再啟動 ==="
  exit 1
fi

echo "=== 啟動方式 ==="
echo "1. 啟動後端 API 伺服器 (預設 8000 Port，被佔用會自動往上找):"
echo "   $PYTHON server.py"
echo ""
echo "2. Cloudflare Tunnel 由 server.py 自己拉起，要手動另開的話:"
echo "   bash tunnel.sh"
echo "========================="
