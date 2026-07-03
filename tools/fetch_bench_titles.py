#!/usr/bin/env python3
"""ベンチ先＋自チャンネルの最新動画タイトルをYouTube RSSから取得し
data/bench_titles.json を更新する（APIキー不要）。
GitHub Actionsで毎日実行（.github/workflows/bench_titles.yml）。
チャンネルの追加・変更はこのファイルの CHANNELS を編集。
"""
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

CHANNELS = [
    {"name": "Flow365", "role": "bench", "channel_id": "UCzKizPkhLBGaTK5_y2s0yJw"},
    {"name": "Dive365", "role": "own", "channel_id": "UCLPixAVIYE5xZGMCC-WZXDw"},
]

NS = {
    "a": "http://www.w3.org/2005/Atom",
    "media": "http://search.yahoo.com/mrss/",
    "yt": "http://www.youtube.com/xml/schemas/2015",
}
OUT = Path(__file__).resolve().parent.parent / "data" / "bench_titles.json"


def fetch(channel_id):
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    videos = []
    for e in root.findall("a:entry", NS):
        title = e.findtext("a:title", "", NS)
        vid = e.findtext("yt:videoId", "", NS)
        pub = (e.findtext("a:published", "", NS) or "")[:10]
        stats = e.find("media:group/media:community/media:statistics", NS)
        views = int(stats.get("views", "0")) if stats is not None else 0
        videos.append({"id": vid, "title": title, "published": pub, "views": views})
    return videos


def main():
    out = {"updated": datetime.date.today().isoformat(), "channels": []}
    for ch in CHANNELS:
        try:
            videos = fetch(ch["channel_id"])
        except Exception as e:
            print(f"WARN {ch['name']}: {e}")
            videos = []
        out["channels"].append({**ch, "videos": videos})
        print(f"{ch['name']}: {len(videos)}本")
    OUT.parent.mkdir(exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("→", OUT)


if __name__ == "__main__":
    main()
