# -*- coding: utf-8 -*-
"""采集员:抓官方列表页/接口 -> snapshots/{id}.html|json,对比出变化事件。
纯代码,不调 AI,不读任何密钥。单个源失败不阻断(降级为保留上次快照)。
"""
import argparse, hashlib, json, pathlib, sys, time
import requests, yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
SNAP = ROOT / "snapshots"
RUNS = ROOT / "runs"
REPO = "https://github.com/VBK-AI-Agent-Gateway/finance-job-radar"
UA = {"User-Agent": f"finance-job-radar/0 (+{REPO})"}


def load_sources():
    with open(ROOT / "config/sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def fetch(src):
    """-> (ok, kind 'json'|'html', payload)"""
    try:
        r = requests.get(src["url"], headers=UA, timeout=25)
        if r.status_code != 200:
            return False, None, f"HTTP {r.status_code}"
        ctype = r.headers.get("content-type", "")
        if src["type"] == "official_api" or ctype.startswith("application/json"):
            return True, "json", r.json()
        r.encoding = r.apparent_encoding or "utf-8"
        return True, "html", r.text
    except Exception as e:  # 网络/解析失败都算采集失败,保留旧快照
        return False, None, str(e)[:200]


def snap_path(sid, kind):
    return SNAP / (f"{sid}.json" if kind == "json" else f"{sid}.html")


def digest(payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_one(src, changed_events):
    sid = src["id"]
    ok, kind, payload = fetch(src)
    if not ok:
        return {"id": sid, "ok": False, "error": payload}
    pj = snap_path(sid, kind)
    old_hash = None
    meta = SNAP / f"{sid}.meta.json"
    if meta.exists():
        old_hash = json.loads(meta.read_text(encoding="utf-8")).get("hash")
    new_hash = digest(payload)
    changed = old_hash is not None and old_hash != new_hash
    if kind == "json":
        pj.write_text(json.dumps(payload, ensure_ascii=False, indent=1), encoding="utf-8")
    else:
        pj.write_text(payload, encoding="utf-8")
    meta.write_text(json.dumps({"id": sid, "url": src["url"], "type": src["type"],
                                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "hash": new_hash}, ensure_ascii=False, indent=1), encoding="utf-8")
    if changed:
        changed_events.append({"id": sid, "url": src["url"], "type": src["type"],
                               "old_hash": old_hash, "new_hash": new_hash})
    return {"id": sid, "ok": True, "changed": bool(changed)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="采集员")
    ap.add_argument("--dry-run", action="store_true", help="只打印,不写快照")
    args = ap.parse_args(argv)
    if args.dry_run:
        for s in load_sources():
            print(f"[dry-run] would fetch {s['id']} {s['url']}")
        return 0
    SNAP.mkdir(exist_ok=True); RUNS.mkdir(exist_ok=True)
    events, results = [], []
    for s in load_sources():
        results.append(collect_one(s, events))
    report = {"agent": "collector", "at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
              "results": results, "changes": events}
    (RUNS / f"collector-{time.strftime('%Y-%m-%dT%H%M')}.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    (ROOT / "state.changes.json").write_text(json.dumps(events, ensure_ascii=False, indent=1), encoding="utf-8")
    fails = [r for r in results if not r["ok"]]
    print(f"collector: {len(results)} sources, {len(events)} changed, {len(fails)} failed")
    for f in fails:
        print(f"  FAIL {f['id']}: {f['error']}", file=sys.stderr)
    return 0  # 单源失败不阻断


if __name__ == "__main__":
    raise SystemExit(main())
