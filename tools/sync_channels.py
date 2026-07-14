#!/usr/bin/env python3
"""ジャンル＆手本ハブ（Firestore）のベンチ先を data/channels.json へ同期する。

流れ:
  1. アプリがsaveCloud時に public_channels/main へ {name,url} 一覧をミラー書き込み
     （Firestoreルールに public_channels の公開読み取りを追加しておく＝SETUP.md参照）
  2. このスクリプトがREST（apiKeyのみ・無認証）で読み取り
  3. チャンネルURL（@handle等）をHTMLフェッチで channelId(UC…) に解決
     （解決結果は channels.json にキャッシュされ再解決しない）
  4. data/channels.json を出力 → fetch_bench_titles.py / fetch_vph.py が読む

Firestoreが読めない（ルール未設定・オフライン等）場合は既存channels.jsonを
維持して正常終了する（グレースフル・フォールバック）。
"""
import json
import re
import urllib.request
from pathlib import Path

PROJECT_ID = "molten-reach-496513-c6"
API_KEY = "AIzaSyB-Jk2D7rszFv0DJs-EsheeijZYdFql1fM"  # Webアプリ公開キー（index.htmlと同一・秘密ではない）
DOC_URL = (f"https://firestore.googleapis.com/v1/projects/{PROJECT_ID}"
           f"/databases/(default)/documents/public_channels/main?key={API_KEY}")

OUT = Path(__file__).resolve().parent.parent / "data" / "channels.json"

OWN = {"name": "Dive365", "role": "own", "channel_id": "UCLPixAVIYE5xZGMCC-WZXDw"}
# ハブが空・未設定でも従来の4chは維持する（フォールバック兼最低ライン）
DEFAULT_BENCH = [
    {"name": "Flow365", "role": "bench", "channel_id": "UCzKizPkhLBGaTK5_y2s0yJw"},
    {"name": "Mind365", "role": "bench", "channel_id": "UCpKf7HR_SAc5XJ1YD8rdluQ"},
    {"name": "Focus Music 365", "role": "bench", "channel_id": "UCCcsYfuXbm_R3AgAMw7FZsg"},
]


def fetch_hub_channels():
    """public_channels/main → [{name,url}]。読めなければNone"""
    try:
        with urllib.request.urlopen(DOC_URL, timeout=30) as r:
            doc = json.loads(r.read())
        arr = doc.get("fields", {}).get("channels", {}).get("arrayValue", {}).get("values", [])
        out = []
        for v in arr:
            f = v.get("mapValue", {}).get("fields", {})
            out.append({"name": f.get("name", {}).get("stringValue", ""),
                        "url": f.get("url", {}).get("stringValue", "")})
        return out
    except Exception as e:
        print(f"Firestore読み取り不可（ルール未設定 or オフライン）: {str(e)[:80]}")
        return None


def resolve_channel_id(url):
    """チャンネルURL（@handle / /channel/UC… / /c/…）→ UC… を解決"""
    m = re.search(r"(UC[0-9A-Za-z_-]{22})", url)
    if m:
        return m.group(1)
    if not url.startswith("http"):
        url = "https://www.youtube.com/" + url.lstrip("/")
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        html = urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "ignore")
        m = re.search(r'"channelId":"(UC[0-9A-Za-z_-]{22})"', html)
        return m.group(1) if m else None
    except Exception as e:
        print(f"channelId解決失敗 {url}: {str(e)[:80]}")
        return None


def main():
    existing = []
    if OUT.exists():
        try:
            existing = json.load(open(OUT))
        except Exception:
            existing = []
    cache = {c.get("url"): c["channel_id"] for c in existing
             if c.get("url") and c.get("channel_id")}

    hub = fetch_hub_channels()
    if hub is None:
        if not OUT.exists():  # 初回はフォールバックを書いておく
            json.dump([OWN] + DEFAULT_BENCH, open(OUT, "w"), ensure_ascii=False, indent=1)
            print(f"フォールバックで初期化: {len(DEFAULT_BENCH) + 1}ch")
        else:
            print("既存channels.jsonを維持")
        return

    channels, seen = [OWN], {OWN["channel_id"]}
    for b in hub:
        if not b["url"]:
            continue
        cid = cache.get(b["url"]) or resolve_channel_id(b["url"])
        if not cid or cid in seen:
            continue
        channels.append({"name": b["name"] or cid, "role": "bench",
                         "channel_id": cid, "url": b["url"]})
        seen.add(cid)
    for d in DEFAULT_BENCH:  # ハブ未登録でも従来chは残す
        if d["channel_id"] not in seen:
            channels.append(d)
            seen.add(d["channel_id"])

    json.dump(channels, open(OUT, "w"), ensure_ascii=False, indent=1)
    print(f"channels.json更新: bench {len(channels) - 1}ch（ハブ{len(hub)}件から）")


if __name__ == "__main__":
    main()
