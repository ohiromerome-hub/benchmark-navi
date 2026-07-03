#!/usr/bin/env python3
"""ベンチ先＋自チャンネルのタイトル・再生数をYouTube RSSから取得し
data/bench_titles.json に【蓄積】する（上書きで消さない仕様）。

- 動画はIDで管理。RSSから消えても記録は残す（削除しない）
- 再生数は views_hist に日付つきで毎日追記 → 日次の伸び・変化を分析できる
- タイトルが変わったら title_hist に旧タイトルを保存 → リネームの前後効果を測れる
  （キラ式: 改善の優先順位①サムネ→②タイトル→③中身。タイトル変更の効果測定用）

GitHub Actionsで毎朝実行（.github/workflows/bench_titles.yml）。
チャンネル追加は CHANNELS を編集。
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
        stats = e.find("media:group/media:community/media:statistics", NS)
        videos.append({
            "id": e.findtext("yt:videoId", "", NS),
            "title": e.findtext("a:title", "", NS),
            "published": (e.findtext("a:published", "", NS) or "")[:10],
            "views": int(stats.get("views", "0")) if stats is not None else 0,
        })
    return videos


def main():
    today = datetime.date.today().isoformat()
    old = json.load(open(OUT)) if OUT.exists() else {"channels": []}
    old_by_cid = {c.get("channel_id"): c for c in old.get("channels", [])}

    out = {"updated": today, "channels": []}
    for ch in CHANNELS:
        prev = old_by_cid.get(ch["channel_id"], {})
        merged = {v["id"]: v for v in prev.get("videos", [])}  # 既存レコードは全部保持
        try:
            fetched = fetch(ch["channel_id"])
        except Exception as e:
            print(f"WARN {ch['name']}: {e}（既存データを保持して続行）")
            fetched = []
        for v in fetched:
            rec = merged.get(v["id"])
            if rec is None:
                rec = {"id": v["id"], "title": v["title"], "published": v["published"],
                       "first_seen": today, "views": v["views"],
                       "views_hist": {}, "title_hist": []}
                merged[v["id"]] = rec
            else:
                # 旧スキーマ互換
                rec.setdefault("views_hist", {})
                rec.setdefault("title_hist", [])
                rec.setdefault("first_seen", rec.get("published") or today)
                if v["title"] and v["title"] != rec.get("title"):
                    rec["title_hist"].append({"until": today, "title": rec.get("title")})
                    rec["title"] = v["title"]
                rec["views"] = v["views"]
            rec["views_hist"][today] = v["views"]
            rec["last_seen"] = today
        videos = sorted(merged.values(), key=lambda r: r.get("published", ""), reverse=True)
        out["channels"].append({**ch, "videos": videos})
        print(f"{ch['name']}: RSS {len(fetched)}本 / 蓄積 {len(videos)}本")

    # CHANNELSから外したチャンネルの過去データも残す（消さない）
    kept_ids = {c["channel_id"] for c in CHANNELS}
    for cid, c in old_by_cid.items():
        if cid not in kept_ids:
            out["channels"].append(c)
            print(f"{c.get('name')}: 監視対象外（過去データ保持）")

    OUT.parent.mkdir(exist_ok=True)
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("→", OUT)


if __name__ == "__main__":
    main()
