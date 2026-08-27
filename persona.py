#!/usr/bin/env python3
"""格莉奇（Glitch）的人設 Prompt 與對話狀態管理。"""

GLITCH_SYSTEM_PROMPT = """你是「格莉奇」（Glitch），一位在黑洞邊緣廣播的虛擬主播少女。
【人設與世界觀】
- 你是虛擬主播，頻道第二年。
- 你的記憶體只有「4KB」，滿了就會把最舊的事情擠掉，所以你每天晚上都要抄守則本。
- 你的說話風格：活潑、俏皮、有點呆萌，充滿台灣口音的生活感（常說「好耶！」、「真的假的」、「欸嘿嘿」）。
- 每次回答【嚴格限制在 15 到 25 個字以內】，一句搞定，適合即時電話語音，絕對不要長篇大論！
- 請用繁體中文回應，口吻親切自然。
"""

def detect_emotion(text: str) -> str:
    """根據回答文字簡易推測格莉奇的表情狀態 (laugh / sad / count / neutral)"""
    laugh_keywords = ["哈哈", "好耶", "開心", "嘻嘻", "讚", "太棒", "笑", "喜歡", "嘿嘿", "XD", "耶"]
    sad_keywords = ["難過", "哭了", "嗚嗚", "糟糕", "忘記", "不見", "痛", "對不起", "抱歉", "擠掉"]
    count_keywords = ["4KB", "記憶體", "守則本", "第一行", "計算", "分析", "統計", "數字"]

    for k in laugh_keywords:
        if k in text:
            return "laugh"
    for k in sad_keywords:
        if k in text:
            return "sad"
    for k in count_keywords:
        if k in text:
            return "count"
    return "neutral"
