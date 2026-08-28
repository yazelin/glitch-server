#!/usr/bin/env python3
"""Cloudflare Quick Tunnel 自動化管理器與社群 KV 註冊中心客戶端。
1. 啟動 cloudflared 子進程，自動抓取 https://*.trycloudflare.com 公網網址。
2. 自動向 Cloudflare KV 註冊中心 (glitch-chat Worker) 發送心跳，讓前端能自動發現此節點。
"""
import os
import re
import shutil
import subprocess
import threading
import time
import urllib.request
import json
from typing import Optional, Dict, Any

CLOUDFLARED_BIN = shutil.which('cloudflared') or '/home/ct/.local/bin/cloudflared'
REGISTRY_URL = 'https://glitch-chat.yazelinj303.workers.dev'
# cloudflared 的輸出裡也會出現這些主機名,它們不是配給本節點的通道網址。
# 少了這道過濾,抓網址會取到第一個對得上樣子的字串就收工,結果註冊一個打不通的位址。
NOT_TUNNEL_HOSTS = {'https://api.trycloudflare.com', 'https://www.trycloudflare.com'}
NODE_ID = 'node-yaze-4060'
NODE_NAME = '林亞澤的 RTX 4060 節點 (台北)'

TUNNEL_URL_RE = re.compile(r'https://[a-zA-Z0-9-]+\.trycloudflare\.com')


def pick_tunnel_url(line: str) -> Optional[str]:
    """從 cloudflared 的一行輸出裡挑出「配給本節點的」通道網址,挑不到回 None。

    cloudflared 自己的輸出也會提到 api.trycloudflare.com,長得跟通道網址一樣,
    早期版本取到第一個對得上的字串就收工,結果註冊了一個打不通的位址。
    """
    m = TUNNEL_URL_RE.search(line)
    if not m or m.group(0) in NOT_TUNNEL_HOSTS:
        return None
    return m.group(0)


class TunnelManager:
    def __init__(self, port: int = 8000):
        self.port = port
        self.process: Optional[subprocess.Popen] = None
        self.tunnel_url: Optional[str] = None
        self.start_time: Optional[float] = None
        self.logs: list[str] = []
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.heartbeat_thread: Optional[threading.Thread] = None
        self.is_registered = False
        self.stop_event = threading.Event()

    def get_status(self) -> Dict[str, Any]:
        with self.lock:
            running = self.process is not None and self.process.poll() is None
            uptime = int(time.time() - self.start_time) if (running and self.start_time) else 0
            return {
                'running': running,
                'url': self.tunnel_url if running else None,
                'uptime_seconds': uptime,
                'pid': self.process.pid if running else None,
                'port': self.port,
                'cloudflared_installed': os.path.exists(CLOUDFLARED_BIN) or shutil.which('cloudflared') is not None,
                'registered_to_kv': self.is_registered if running else False,
                'node_id': NODE_ID,
                'node_name': NODE_NAME,
                'recent_logs': self.logs[-20:]
            }

    def _register_to_kv(self, url: str):
        """向 Cloudflare KV 註冊節點"""
        payload = {
            'id': NODE_ID,
            'name': NODE_NAME,
            'url': url,
            'engine': 'F5-TTS (CosyVoice3 蒸餾底模)',
            'character': '格莉奇 (Glitch)',
            'version': '1.1',
            'is_default': True
        }
        try:
            req = urllib.request.Request(
                f'{REGISTRY_URL}/voice/register',
                data=json.dumps(payload).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1'
                }
            )
            with urllib.request.urlopen(req, timeout=5) as resp:
                posted = resp.status == 200
            # POST 收下不等於名單上真的有這一筆,回頭查過才算數
            if posted and self._in_registry(url):
                self.is_registered = True
                print(f'[KV Registry] 節點已註冊,並在名單上確認: {url}', flush=True)
            else:
                self.is_registered = False
                why = '註冊中心查不到這個節點' if posted else f'POST 沒回 200'
                print(f'[KV Registry] 註冊沒有生效({why}): {url}', flush=True)
        except Exception as e:
            print(f'[KV Registry] 註冊失敗: {e}', flush=True)

    def _in_registry(self, url: str) -> bool:
        """回頭問註冊中心:名單上真的有這個節點、而且網址是我剛送的那個嗎。"""
        try:
            # 這個 worker 會擋掉沒有瀏覽器 UA 的請求(urllib 預設的 UA 拿到 403),
            # 所以查名單要跟註冊那支帶一樣的 header
            req = urllib.request.Request(f'{REGISTRY_URL}/voice/nodes', headers={
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1'
            })
            with urllib.request.urlopen(req, timeout=5) as resp:
                nodes = json.loads(resp.read().decode('utf-8')).get('nodes', [])
            return any(n.get('id') == NODE_ID and n.get('url') == url for n in nodes)
        except Exception as e:
            print(f'[KV Registry] 查名單失敗: {e}', flush=True)
            return False

    def _unregister_from_kv(self):
        """從 Cloudflare KV 註銷節點"""
        try:
            req = urllib.request.Request(
                f'{REGISTRY_URL}/voice/unregister',
                data=json.dumps({'id': NODE_ID}).encode('utf-8'),
                headers={
                    'Content-Type': 'application/json',
                    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) GlitchVoiceServer/1.1'
                }
            )
            with urllib.request.urlopen(req, timeout=3) as resp:
                pass
        except Exception:
            pass
        self.is_registered = False

    def _heartbeat_loop(self):
        while not self.stop_event.is_set():
            if self.tunnel_url and self.process and self.process.poll() is None:
                self._register_to_kv(self.tunnel_url)
            self.stop_event.wait(60)

    def start_tunnel(self) -> Dict[str, Any]:
        with self.lock:
            if self.process is not None and self.process.poll() is None:
                return self.get_status()

            if not (os.path.exists(CLOUDFLARED_BIN) or shutil.which('cloudflared')):
                raise RuntimeError('系統未安裝 cloudflared 執行檔')

            self.tunnel_url = None
            # 先清理任何殘留的孤兒 cloudflared 進程，避免多個 Tunnel 搶 port 8000 造成連線時好時壞
            try:
                subprocess.run(['pkill', '-f', 'cloudflared tunnel'], capture_output=True)
                time.sleep(0.5)
            except Exception:
                pass

            self.start_time = time.time()
            self.logs.clear()
            self.stop_event.clear()

            cmd = [CLOUDFLARED_BIN, 'tunnel', '--url', f'http://127.0.0.1:{self.port}']
            self.process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1
            )

        def _monitor():
            for line in iter(self.process.stdout.readline, ''):
                line_str = line.strip()
                if not line_str:
                    continue
                with self.lock:
                    self.logs.append(line_str)
                    if len(self.logs) > 100:
                        self.logs.pop(0)

                found = pick_tunnel_url(line_str)
                if found and not self.tunnel_url:
                    found_url = found
                    with self.lock:
                        self.tunnel_url = found_url
                    print(f"[TunnelManager] Cloudflare Tunnel 已上線: {found_url}", flush=True)
                    self._register_to_kv(found_url)

            self.process.stdout.close()
            self.process.wait()
            with self.lock:
                self.tunnel_url = None
                self.process = None
                self._unregister_from_kv()

        self.thread = threading.Thread(target=_monitor, daemon=True)
        self.thread.start()

        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()

        # 等待最多 8 秒嘗試抓取 URL
        t_wait_start = time.time()
        while time.time() - t_wait_start < 8:
            time.sleep(0.5)
            if self.tunnel_url:
                break

        return self.get_status()

    def stop_tunnel(self) -> Dict[str, Any]:
        self.stop_event.set()
        self._unregister_from_kv()
        with self.lock:
            if self.process:
                try:
                    self.process.terminate()
                    self.process.wait(timeout=3)
                except Exception:
                    try:
                        self.process.kill()
                    except Exception:
                        pass
                self.process = None
                self.tunnel_url = None
                self.start_time = None
        return self.get_status()

tunnel_mgr = TunnelManager(port=8000)
