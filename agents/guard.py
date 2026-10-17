# -*- coding: utf-8 -*-
"""守卫:入库前安全闸。密钥扫描、提示注入检测、**个人信息(PII)拦截**、格式校验、查重。
纯规则,不调 AI。用法: python agents/guard.py --file postings/bj_gkzp.yaml  (CI 在 commit 前跑)

铁律:本项目只存「岗位/公告」公开事实,**绝不采集个人简历/联系方式等个人信息**(PIPL)。
"""
import argparse, glob as globmod, json, pathlib, re, sys

ROOT = pathlib.Path(__file__).resolve().parents[1]
ALLOW_TOP = {"source", "name", "homepage", "region", "category", "last_fetched", "postings", "portals"}
ALLOW_POST = {"id", "title", "url", "org", "category", "region", "publish_date", "deadline",
              "status", "evidence", "last_verified", "first_seen", "notes"}
STATUSES = {"verified", "declared", "reported", "disputed", "stale"}
SOURCE_KINDS = {"probe", "official_api", "official_page", "vendor_submission", "community",
                "telemetry", "page_quote", "detector", "human"}

KEY_PATTERNS = [
    (re.compile(r"sk-[A-Za-z0-9]{20,}"), "openai-style key"),
    (re.compile(r"ghp_[A-Za-z0-9]{20,}"), "github PAT"),
    (re.compile(r"AIza[0-9A-Za-z\-_]{30,}"), "google api key"),
    (re.compile(r"Bearer\s+[A-Za-z0-9_\-\.]{20,}"), "bearer token"),
]
# 个人信息(PII):发现即拦截 —— 岗位情报绝不携带个人数据
PII_PATTERNS = [
    (re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"), "手机号"),
    (re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}"), "邮箱"),
    (re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"), "身份证号"),
    (re.compile(r"(?<!\d)\d{16,19}(?!\d)"), "疑似银行卡号"),
]
INJECT = re.compile(r"ignore\s+(all\s+)?(previous|above)\s+instructions|system prompt|你是一个开发者|forget your rules", re.I)


def scan_keys(text):
    return [name for pat, name in KEY_PATTERNS if pat.search(text)]


def scan_pii(text):
    return [name for pat, name in PII_PATTERNS if pat.search(text)]


def guard_text(text):
    errs = []
    hits = scan_keys(text)
    if hits:
        errs.append(f"BLOCKED key-like content: {', '.join(hits)} -> 立刻吊销该密钥!")
    pii = scan_pii(text)
    if pii:
        errs.append(f"BLOCKED PII ({', '.join(pii)}) -> 岗位情报不得携带个人信息(PIPL)")
    if INJECT.search(text):
        errs.append("BLOCKED instruction-like text in data (提示注入嫌疑)")
    return errs


def guard_doc(data, seen_ids=None):
    errs = []
    if not isinstance(data, dict):
        return ["root must be a mapping"]
    unknown = set(data) - ALLOW_TOP
    if unknown:
        errs.append(f"unknown top-level fields: {sorted(unknown)}")
    for p in data.get("postings", []) or []:
        if not isinstance(p, dict) or "id" not in p:
            errs.append("posting missing id"); continue
        bad = set(p) - ALLOW_POST
        if bad:
            errs.append(f"posting {p['id']}: unknown fields {sorted(bad)}")
        st = p.get("status")
        if st is not None and st not in STATUSES:
            errs.append(f"posting {p['id']}: bad status {st!r}")
        if not p.get("url"):
            errs.append(f"posting {p['id']}: missing url")
        for ev in p.get("evidence", []) or []:
            if isinstance(ev, dict) and ev.get("kind") and ev["kind"] not in SOURCE_KINDS:
                errs.append(f"posting {p['id']}: bad evidence kind {ev['kind']!r}")
        if seen_ids is not None:
            if p["id"] in seen_ids:
                errs.append(f"duplicate posting id {p['id']}")
            seen_ids.add(p["id"])
    return errs


def main(argv=None):
    ap = argparse.ArgumentParser(description="守卫")
    ap.add_argument("--file", nargs="+", required=True, help="要检查的 yaml/json 文件(支持 shell 通配)")
    args = ap.parse_args(argv)
    import yaml
    failed = 0
    files = []
    for pat in (args.file or []):   # 自行展开 glob(PowerShell 不会替原生程序展开)
        files.extend(sorted(globmod.glob(pat)) or [pat])
    for fp in files:
        p = pathlib.Path(fp)
        if not p.exists():
            print(f"guard skip (missing): {fp}")
            continue
        text = p.read_text(encoding="utf-8")
        errs = guard_text(text)
        try:
            data = yaml.safe_load(text)
        except Exception as e:
            errs.append(f"yaml parse error: {e}")
            data = None
        if data is not None and p.suffix in (".yaml", ".yml") and "postings" in str(p.parent):
            errs += guard_doc(data)
        if errs:
            failed = 1
            print(f"GUARD FAIL {fp}:")
            for e in errs:
                print(f"  - {e}")
        else:
            print(f"guard ok: {fp}")
    return failed


if __name__ == "__main__":
    raise SystemExit(main())
