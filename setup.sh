#!/usr/bin/env bash
# glitch-server 環境依賴檢查與快速啟動腳本
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PYTHON="${HOME}/CosyVoice/.venv/bin/python"

echo "=== 檢查格莉奇伺服器環境 ==="

if [ ! -f "$PYTHON" ]; then
  echo "❌ 找不到 Python 虛擬環境: $PYTHON"
  exit 1
fi

echo "✅ Python 環境就緒: $($PYTHON --version)"

# 檢查模型與音訊資產
if [ ! -f "$HERE/assets/glitch.wav" ]; then
  echo "❌ 缺少格莉奇參考音檔: $HERE/assets/glitch.wav"
  exit 1
fi
echo "✅ 格莉奇參考音檔就緒 ($(stat -c%s "$HERE/assets/glitch.wav") bytes)"

echo ""
echo "=== 啟動方式 ==="
echo "1. 啟動後端 API 伺服器 (預設 8000 Port):"
echo "   $PYTHON server.py"
echo ""
echo "2. 在另一個終端機啟動 Cloudflare Tunnel (取得 HTTPS 網址):"
echo "   bash tunnel.sh"
echo "========================="
