"""跑法:python3 test_tunnel.py

只測不需要網路的那半:從 cloudflared 的輸出挑通道網址。
會回頭查註冊中心的 _in_registry 需要網路,不放在這裡。
"""
from tunnel import pick_tunnel_url

CASES = [
    # cloudflared 自己提到的 api 主機,不是配給節點的網址
    ("INF Requesting new quick Tunnel on trycloudflare.com... https://api.trycloudflare.com/tunnel", None),
    ("INF |  https://tvs-enquiries-watch-assessing.trycloudflare.com  |",
     "https://tvs-enquiries-watch-assessing.trycloudflare.com"),
    ("INF 這行沒有網址", None),
    ("WRN https://www.trycloudflare.com 也不是", None),
]

if __name__ == "__main__":
    bad = 0
    for line, want in CASES:
        got = pick_tunnel_url(line)
        ok = got == want
        bad += not ok
        print(f"{'ok  ' if ok else 'FAIL'} {got!r:60} <- {line[:52]}")
    print(f"\n{len(CASES)-bad}/{len(CASES)} 通過")
    raise SystemExit(1 if bad else 0)
