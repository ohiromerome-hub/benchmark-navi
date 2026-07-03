#!/usr/bin/env python3
"""ベンチ先の「勢い上位」動画からコメントを取得し data/bench_comments.json に蓄積する。
視聴者が何を求めているか（利用シーン・要望・感想）の分析材料。

- APIキー不要（yt-dlpのコメント抽出）
- 対象: 各ベンチchの勢い上位 TOP_N 本（勢い=累計再生÷公開日数）
- 蓄積型: 動画IDごとにマージ・消えない。コメントは人気順上位 MAX_C 件
- 実行: python3 tools/fetch_comments.py（GitHub Actionsでは週次）
"""
import json
import datetime
import subprocess
import sys
from pathlib import Path

TOP_N = 5      # 各chの対象動画数
MAX_C = 60     # 動画あたり保存コメント数

BASE = Path(__file__).resolve().parent.parent
TITLES = BASE / "data" / "bench_titles.json"
OUT = BASE / "data" / "bench_comments.json"
YTDLP = sys.argv[1] if len(sys.argv) > 1 else "yt-dlp"


def momentum(v, today):
    days = max(1, (datetime.date.fromisoformat(today) -
                   datetime.date.fromisoformat(v["published"])).days)
    return v.get("views", 0) / days


def fetch_comments(video_id):
    """yt-dlpでコメント取得（上位のみ・音声等はDLしない）"""
    cmd = [YTDLP, "--skip-download", "--write-comments",
           "--extractor-args", f"youtube:comment_sort=top;max_comments={MAX_C},all,0",
           "--no-warnings", "-o", "%(id)s", "--paths", "/tmp/yt_comments",
           f"https://www.youtube.com/watch?v={video_id}"]
    subprocess.run(cmd, capture_output=True, timeout=180)
    info = Path(f"/tmp/yt_comments/{video_id}.info.json")
    if not info.exists():
        return []
    d = json.load(open(info))
    info.unlink()
    out = []
    for c in (d.get("comments") or []):
        if c.get("author_is_uploader"):  # 投稿者自身の宣伝コメは視聴者の声でないため除外
            continue
        out.append({"t": (c.get("text") or "")[:300],
                    "likes": c.get("like_count") or 0})
        if len(out) >= MAX_C:
            break
    return out


def main():
    titles = json.load(open(TITLES))
    today = titles.get("updated") or datetime.date.today().isoformat()
    old = json.load(open(OUT)) if OUT.exists() else {"videos": {}}
    out = {"updated": datetime.date.today().isoformat(), "videos": old.get("videos", {})}
    Path("/tmp/yt_comments").mkdir(exist_ok=True)
    for ch in titles["channels"]:
        if ch.get("role") != "bench":
            continue
        vids = sorted(ch["videos"], key=lambda v: momentum(v, today), reverse=True)[:TOP_N]
        for v in vids:
            try:
                comments = fetch_comments(v["id"])
            except Exception as e:
                print(f"WARN {v['id']}: {e}")
                comments = None
            rec = out["videos"].get(v["id"], {})
            out["videos"][v["id"]] = {
                "ch": ch["name"], "title": v["title"], "published": v["published"],
                "views": v.get("views", 0),
                "comments": comments if comments else rec.get("comments", []),
                "fetched": datetime.date.today().isoformat() if comments else rec.get("fetched"),
            }
            print(f"{ch['name']} {v['id']}: {len(out['videos'][v['id']]['comments'])}件")
    json.dump(out, open(OUT, "w"), ensure_ascii=False, indent=1)
    print("→", OUT, f"（計{len(out['videos'])}動画）")


if __name__ == "__main__":
    main()
