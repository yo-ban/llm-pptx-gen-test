import re

def sanitize_filename(filename: str) -> str:
    """ファイル名をWindowsおよびLinuxで有効な名前に変換する。"""
    # まずはLinuxの有効な名前に変換
    sanitized = re.sub(r'[^\w\-_.]', '', filename)
    # 次にWindowsの有効な名前に変換
    sanitized = re.sub(r'[<>:"/\\|?*]', '', sanitized)
    return sanitized

