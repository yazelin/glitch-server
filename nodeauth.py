#!/usr/bin/env python3
"""節點金鑰:沒設 = 完全開放(跟以前一樣),設了就擋。

放行的只有 /health 與 /api/voices —— 少了這兩個,KV 清單上的節點沒人驗得出活著。

本機直連放行,不然第一次設密碼會沒有入口(控制台自己也在保護範圍內)。
判斷「本機」不能只看來源 IP:cloudflared 是打到 127.0.0.1,從外面進來的請求
來源 IP 也是 127.0.0.1。所以要同時滿足「來源是 loopback」而且「沒有任何
proxy 轉發標頭」。
"""
import os
from pathlib import Path

KEY_FILE = Path.home() / ".config/glitch-voice/node-key"
HEADER = "x-glitch-key"
OPEN_PATHS = {"/health", "/api/voices"}
_FORWARD_HEADERS = ("x-forwarded-for", "cf-connecting-ip", "cf-ray", "x-real-ip")


def node_key() -> str:
    """環境變數優先,其次是設定檔。都沒有就是空字串 = 開放。"""
    env = (os.environ.get("GLITCH_NODE_KEY") or "").strip()
    if env:
        return env
    if KEY_FILE.exists():
        return KEY_FILE.read_text(encoding="utf-8").strip()
    return ""


def set_node_key(new_key: str) -> bool:
    """寫進設定檔。空字串 = 拿掉密碼。回傳「現在有沒有密碼」。"""
    KEY_FILE.parent.mkdir(parents=True, exist_ok=True)
    new_key = (new_key or "").strip()
    if new_key:
        KEY_FILE.write_text(new_key, encoding="utf-8")
        KEY_FILE.chmod(0o600)
    elif KEY_FILE.exists():
        KEY_FILE.unlink()
    return bool(node_key())


def is_direct_local(request) -> bool:
    if any(h in request.headers for h in _FORWARD_HEADERS):
        return False
    host = getattr(request.client, "host", "") or ""
    return host in ("127.0.0.1", "::1", "localhost")


def request_is_allowed(request) -> bool:
    key = node_key()
    if not key:
        return True
    if request.url.path in OPEN_PATHS:
        return True
    if is_direct_local(request):
        return True
    supplied = request.headers.get(HEADER) or ""
    if not supplied:
        auth = request.headers.get("authorization") or ""
        if auth.lower().startswith("bearer "):
            supplied = auth[7:]
    return supplied.strip() == key


# ---- 當呼叫端:記別人節點的金鑰 ----
# 對方沒設密碼就不用帶,查不到就當對方是開放的直接打。
PEER_FILE = Path.home() / ".config/glitch-voice/peer-keys.json"


def _load_peers() -> dict:
    if not PEER_FILE.exists():
        return {}
    try:
        import json
        return json.loads(PEER_FILE.read_text(encoding="utf-8"))
    except Exception:
        return {}


def peer_key(node_url: str) -> str:
    """用網址找金鑰。網址結尾的斜線不算數。"""
    peers = _load_peers()
    return (peers.get((node_url or "").rstrip("/")) or "").strip()


def set_peer_key(node_url: str, key: str) -> int:
    import json
    peers = _load_peers()
    node_url = (node_url or "").rstrip("/")
    if key:
        peers[node_url] = key
    else:
        peers.pop(node_url, None)
    PEER_FILE.parent.mkdir(parents=True, exist_ok=True)
    PEER_FILE.write_text(json.dumps(peers, ensure_ascii=False, indent=2), encoding="utf-8")
    PEER_FILE.chmod(0o600)
    return len(peers)


def peer_headers(node_url: str) -> dict:
    k = peer_key(node_url)
    return {HEADER: k} if k else {}
