#!/usr/bin/env python3
"""VPH（Views Per Hour・1時間あたり再生数）収集 — vidIQのVPH相当を自作で再現する。

仕組み:
  毎時、全チャンネルのRSSから各動画の累計再生数をスナップショットし
  data/vph_log.json に追記（直近7日分だけ保持）。
  VPH = 約24時間前のスナップショットとの増分 ÷ 経過時間（vidIQと同スケール）。
  bench_titles.json の views_hist（毎朝6:30の日次記録）も擬似スナップショット
  として使うので、初回から24時間窓のVPHが出せる。

なぜ24時間窓か（2026-07-14 vidIQ実測との突き合わせで確認）:
  YouTubeの公開再生数はバッチ更新（動画によって数時間〜1日凍結）のため、
  1時間窓では増分が0か尖った値になり使いものにならない。
  24時間窓ならvidIQ表示と±10〜20%で一致する（動きのある動画で検証:
  自作11.4 vs vidIQ12.8 / 自作50.2 vs vidIQ47.8）。
  カウンター凍結中の動画は vidIQ側も自作側も計測タイミング次第でズレる。
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
KEEP_DAYS = 7            # スナップショット保持期間
TARGET_WINDOW_H = 24     # VPH計算の目標窓（vidIQと同スケール）
MIN_WINDOW_H = 6         # これ未満の窓では計算しない（バッチ更新ノイズ対策）


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


def pseudo_snaps_from_titles(cutoff):
    """毎朝6:30(JST)の日次記録 views_hist を擬似スナップショットに変換する。
    fetch_bench_titles.py は UTCの date.today() をキーにするので、
    実行時刻はそのUTC日付の21:30頃＝キー日付+21:30Z とみなす"""
    path = BASE / "bench_titles.json"
    if not path.exists():
        return []
    bt = json.load(open(path))
    by_date = {}
    for ch in bt.get("channels", []):
        for v in ch.get("videos", []):
            for d, val in (v.get("views_hist") or {}).items():
                by_date.setdefault(d, {})[v["id"]] = val
    out = []
    for d, views in by_date.items():
        ts = f"{d}T21:30:00+00:00"
        if ts >= cutoff:
            out.append({"ts": ts, "views": views})
    return out


def main():
    now = datetime.datetime.now(datetime.timezone.utc)

    # ① 今回スナップショット（一時的な5xxはリトライ→ダメならそのchだけスキップ）
    import time
    views, meta = {}, {}
    for ch in CHANNELS:
        for attempt in range(3):
            try:
                fetched = fetch_views(ch["channel_id"])
                break
            except Exception as e:
                print(f"RSS失敗 {ch['name']}（{attempt + 1}/3）: {str(e)[:80]}")
                time.sleep(10 * (attempt + 1))
        else:
            continue
        for vid, v in fetched.items():
            views[vid] = v["views"]
            meta[vid] = {"title": v["title"], "published": v["published"],
                         "ch": ch["name"], "role": ch["role"]}
    if not views:
        raise SystemExit("全チャンネルのRSS取得に失敗（スナップショットなし・前回データ維持）")

    # ② ログへ追記（7日より古いものは捨てる）
    log = json.load(open(LOG)) if LOG.exists() else {"snaps": []}
    cutoff = (now - datetime.timedelta(days=KEEP_DAYS)).isoformat(timespec="seconds")
    snaps = [s for s in log["snaps"] if s["ts"] >= cutoff]
    snaps.append({"ts": now.isoformat(timespec="seconds"), "views": views})
    json.dump({"snaps": snaps}, open(LOG, "w"), ensure_ascii=False)

    # ③ VPH計算: 「約24時間前」に最も近いスナップショットと比較（6時間未満の窓は使わない）
    #    毎朝6:30の日次記録（bench_titles.jsonのviews_hist）も擬似スナップショットとして使う
    pool = snaps[:-1] + pseudo_snaps_from_titles(cutoff)
    latest = snaps[-1]
    t_latest = datetime.datetime.fromisoformat(latest["ts"])
    cands = []  # (経過時間h, views辞書)
    for s in pool:
        h = (t_latest - datetime.datetime.fromisoformat(s["ts"])).total_seconds() / 3600
        if h >= MIN_WINDOW_H:
            cands.append((h, s["views"]))
    vph = {}
    for vid, v_now in latest["views"].items():
        if vid not in meta:
            continue
        # この動画を含み、目標24時間に最も近い基準スナップショットを選ぶ
        # （新着動画は公開6時間後から計測開始＝公開直後の異常値も避ける）
        avail = [(h, vs[vid]) for h, vs in cands if vid in vs]
        if not avail:
            continue
        hours, v_base = min(avail, key=lambda x: abs(x[0] - TARGET_WINDOW_H))
        vph[vid] = {
            "vph": round(max(0, v_now - v_base) / hours, 1),
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
