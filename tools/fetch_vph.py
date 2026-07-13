#!/usr/bin/env python3
"""VPH（Views Per Hour・1時間あたり再生数）収集 — vidIQのVPH相当を自作で再現する。

仕組み:
  毎時、全チャンネルのRSSから各動画の累計再生数をスナップショットし
  data/vph_log.json に追記（直近7日分だけ保持）。
  直近スナップショットとの差分から VPH = 増分再生数 ÷ 経過時間 を計算し
  data/vph.json に書き出す（ベンチ分析の⚡VPHタブが読む）。

vidIQのVPHは「今1時間あたり何回再生されているか」（視聴速度）。
公開直後はVPHが大きくなりがちなので、UIで公開48時間以内は⚠表示する。

GitHub Actionsで毎時実行（.github/workflows/vph.yml）。
チャンネルは fetch_bench_titles.py の CHANNELS を共用。
"""
import json
import datetime
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from fetch_bench_titles import CHANNELS, NS

BASE = Path(__file__).resolve().parent.parent / "data"
LOG = BASE / "vph_log.json"
OUT = BASE / "vph.json"
KEEP_DAYS = 7          # スナップショット保持期間
MIN_WINDOW_MIN = 50    # VPH計算に使う最小の経過時間（分）


def fetch_views(channel_id):
    """RSSから {video_id: {views, title, published(フルISO)}} を取得"""
    url = f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        root = ET.fromstring(r.read())
    out = {}
    for e in root.findall("a:entry", NS):
        stats = e.find("media:group/media:community/media:statistics", NS)
        vid = e.findtext("yt:videoId", "", NS)
        out[vid] = {
            "views": int(stats.get("views", "0")) if stats is not None else 0,
            "title": e.findtext("a:title", "", NS),
            "published": e.findtext("a:published", "", NS),
        }
    return out


def main():
    now = datetime.datetime.now(datetime.timezone.utc)

    # ① 今回スナップショット
    views, meta = {}, {}
    for ch in CHANNELS:
        for vid, v in fetch_views(ch["channel_id"]).items():
            views[vid] = v["views"]
            meta[vid] = {"title": v["title"], "published": v["published"],
                         "ch": ch["name"], "role": ch["role"]}

    # ② ログへ追記（7日より古いものは捨てる）
    log = json.load(open(LOG)) if LOG.exists() else {"snaps": []}
    cutoff = (now - datetime.timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    snaps = [s for s in log["snaps"] if s["ts"] >= cutoff]
    snaps.append({"ts": now.isoformat(timespec="seconds"), "views": views})
    json.dump({"snaps": snaps}, open(LOG, "w"), ensure_ascii=False)

    # ③ VPH計算: 最新と「MIN_WINDOW_MIN分以上前で最も新しい」スナップショットを比較
    latest = snaps[-1]
    base = None
    for s in reversed(snaps[:-1]):
        dt = (datetime.datetime.fromisoformat(latest["ts"])
              - datetime.datetime.fromisoformat(s["ts"])).total_seconds() / 60
        if dt >= MIN_WINDOW_MIN:
            base = s
            break
    vph = {}
    if base:
        hours = (datetime.datetime.fromisoformat(latest["ts"])
                 - datetime.datetime.fromisoformat(base["ts"])).total_seconds() / 3600
        for vid, v_now in latest["views"].items():
            if vid not in base["views"] or vid not in meta:
                continue  # 新登場動画は次回から（公開直後の異常値も避ける）
            delta = v_now - base["views"][vid]
            vph[vid] = {
                "vph": round(max(0, delta) / hours, 1),
                "window_h": round(hours, 2),
                "views": v_now,
                **meta[vid],
            }

    jst = now.astimezone(datetime.timezone(datetime.timedelta(hours=9)))
    json.dump({"updated": jst.isoformat(timespec="seconds"),
               "snap_count": len(snaps), "vph": vph},
              open(OUT, "w"), ensure_ascii=False)
    print(f"snapshot {len(views)}本 / VPH算出 {len(vph)}本"
          + (f"（窓 {vph[next(iter(vph))]['window_h']}h）" if vph else "（初回はスナップショットのみ）"))


if __name__ == "__main__":
    main()
