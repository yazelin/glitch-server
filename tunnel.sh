#!/usr/bin/env bash
# 一鍵啟動 Cloudflare Quick Tunnel，將本機 8000 連接埠映射至公網 HTTPS
set -euo pipefail

echo "========================================================"
echo "  🚀 啟動格莉奇 Cloudflare HTTPS 安全隧道通道"
echo "  將本地 http://127.0.0.1:8000 映射至雲端 HTTPS 端點"
echo "========================================================"

if ! command -v cloudflared &>/dev/null; then
  echo "找不到 cloudflared，正在自動安裝..."
  mkdir -p "$HOME/.local/bin"
  curl -fsSL -o "$HOME/.local/bin/cloudflared" https://github.com/cloudflare/cloudflared/releases/latest/download/cloudflared-linux-amd64
  chmod +x "$HOME/.local/bin/cloudflared"
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "正在建立隧道連線... (請複製產生的 https://*.trycloudflare.com 網址填入 ai-brain-site)"
cloudflared tunnel --url http://127.0.0.1:8000
