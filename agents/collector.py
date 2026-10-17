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
UA = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                    "(KHTML, like Gecko) Chrome/124.0 Safari/537.36",
      "Accept-Language": "zh-CN,zh;q=0.9"}


def source_urls(src):
    return src.get("urls") or [src["url"]]


def load_sources():
    with open(ROOT / "config/sources.yaml", encoding="utf-8") as f:
        return yaml.safe_load(f)["sources"]


def requests_for(src):
    """-> 列表 [(url, method, data)];支持 API 分页参数注入(page_param/pages)。"""
    pp, n = src.get("page_param"), int(src.get("pages") or 0)
    body = dict(src.get("body") or {})
    if pp and n:
        return [(src["url"], src.get("method", "GET"), {**body, pp: i}) for i in range(1, n + 1)]
    return [(u, src.get("method", "GET"), body) for u in source_urls(src)]


def fetch(src, url, method="GET", data=None):
    """-> (ok, kind 'json'|'html', payload)"""
    try:
        r = (requests.post(url, headers=UA, data=data, timeout=25)
             if str(method).upper() == "POST" else requests.get(url, headers=UA, timeout=25))
        if r.status_code != 200:
            return False, None, f"HTTP {r.status_code}"
        ctype = r.headers.get("content-type", "")
        if src["type"] == "official_api" or ctype.startswith("application/json"):
            return True, "json", r.json()
        r.encoding = r.apparent_encoding or "utf-8"
        return True, "html", r.text
    except Exception as e:  # 网络/解析失败都算采集失败,保留旧快照
        return False, None, str(e)[:200]


def snap_path(sid, index, kind):
    ext = "json" if kind == "json" else "html"
    return SNAP / (f"{sid}.{ext}" if index == 0 else f"{sid}__{index}.{ext}")


def digest(payload):
    if not isinstance(payload, str):
        payload = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def collect_one(src, changed_events):
    sid = src["id"]
    meta = SNAP / f"{sid}.meta.json"
    old_hash = None
    if meta.exists():
        old_hash = json.loads(meta.read_text(encoding="utf-8")).get("hash")
    reqs, parts, errors, urls = requests_for(src), [], [], []
    for i, (url, method, data) in enumerate(reqs):
        urls.append(url)
        ok, kind, payload = fetch(src, url, method, data)
        if not ok:
            errors.append({"url": url, "error": payload})
            continue
        snap_path(sid, i, kind).write_text(
            json.dumps(payload, ensure_ascii=False, indent=1) if kind == "json" else payload,
            encoding="utf-8")
        parts.append(payload if isinstance(payload, str) else json.dumps(payload, ensure_ascii=False, sort_keys=True))
    if not parts:
        return {"id": sid, "ok": False, "error": "; ".join(e["error"] for e in errors)}
    new_hash = digest("\u0000".join(parts))
    changed = old_hash is not None and old_hash != new_hash
    meta.write_text(json.dumps({"id": sid, "urls": urls, "type": src["type"],
                                "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                "hash": new_hash, "errors": errors}, ensure_ascii=False, indent=1), encoding="utf-8")
    if changed:
        changed_events.append({"id": sid, "urls": urls, "type": src["type"],
                               "old_hash": old_hash, "new_hash": new_hash})
    return {"id": sid, "ok": True, "changed": bool(changed), "pages": len(parts)}


def main(argv=None):
    ap = argparse.ArgumentParser(description="采集员")
    ap.add_argument("--dry-run", action="store_true", help="只打印,不写快照")
    args = ap.parse_args(argv)
    if args.dry_run:
        for s in load_sources():
            print(f"[dry-run] would fetch {s['id']} {source_urls(s)}")
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
