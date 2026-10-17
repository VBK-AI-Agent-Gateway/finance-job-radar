# -*- coding: utf-8 -*-
"""抽取员:把官方列表页快照 -> 结构化岗位条目(正本 postings/{id}.yaml)。
第一阶段纯规则(HTML 结构各异,不猜字段,拿不到就写 null / unknown)。
- gov_list       : 政府/事业单位「公开招聘」列表页 -> 公告条目(标题/URL/发布日期)
- link_directory : 协会聚合页 -> 站内招聘公告 + 外部招聘入口(供发现员)
后续第二阶段:对详情页用 AI 抽取 单位/岗位/学历/经验/报名截止(见 docs/DESIGN.md)。
"""
import html as html_mod
import json, pathlib, re, sys, time
from urllib.parse import urljoin
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
POST = ROOT / "postings"
SNAP = ROOT / "snapshots"

TITLE_KW_DEFAULT = ("招聘",)            # 岗位公告的判定关键词(可按源覆盖 src.title_kw)
DETAIL_RE = re.compile(r"/\d{6,8}/")    # 详情页默认特征:URL 含日期目录(/202610/ 或 /20261015/)
UA_STRIP = re.compile(r"<[^>]+>")


def _today():
    return time.strftime("%Y-%m-%d")


def clean(s):
    s = UA_STRIP.sub(" ", s or "")
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def anchors(html):
    return [(h, clean(t)) for h, t in
            re.findall(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S | re.I)]


def date_from_href(href):
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", href)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"/(\d{4})(\d{2})/(?:[a-z])?(\d{4})(\d{2})(\d{2})_", href)
    if m:
        return f"{m.group(3)}-{m.group(4)}-{m.group(5)}"
    m = re.search(r"(\d{4})(\d{2})(\d{2})", href)
    if m and m.group(1) >= "2000":
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    return None


def pid_from_href(src_id, href):
    seg = href.rstrip("/").split("/")[-1]
    seg = re.sub(r"\.html?$", "", seg)
    return f"{src_id}:{seg}" if seg else None


def _evidence(src, url, excerpt):
    return [{"kind": "official_page", "url": url, "at": _today(), "excerpt": (excerpt or None)}]


def _title_kw(src):
    return tuple(src.get("title_kw") or TITLE_KW_DEFAULT)


def _is_detail(src, href):
    """详情页判定:排除导航/栏目/首页链接(默认要求 URL 含日期目录)。"""
    pat = src.get("detail_re")
    if pat:
        return bool(re.search(pat, href))
    return bool(DETAIL_RE.search(href))


def gov_list(src, html):
    """政府/事业单位公开招聘列表页 -> 公告条目。"""
    out, seen = [], set()
    kw = _title_kw(src)
    for href, title in anchors(html):
        if len(title) < 8 or not any(k in title for k in kw):
            continue
        if href.startswith(("javascript:", "#")) or href in (".", "./"):
            continue
        if not re.search(r"\.html?$", href) or not _is_detail(src, href):
            continue
        url = urljoin(src["url"], href)
        pid = pid_from_href(src["id"], href)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({
            "id": pid,
            "title": title,
            "url": url,
            "org": None,                 # 列表页无单位信息 -> unknown
            "category": src.get("category"),
            "region": src.get("region"),
            "publish_date": date_from_href(href),
            "deadline": None,
            "status": "declared",
            "evidence": _evidence(src, url, title),
            "last_verified": _today(),
        })
    return out


DIR_PORTAL_KW = ("招聘", "人才", "career", "job", "recruit", "campus", "intern")


def link_directory(src, html):
    """协会聚合页:站内招聘公告(条目) + 外部招聘入口(portals)。
    只把站内公告当 postings;外部入口返回在第二个返回值里(供发现员,不混入岗位正本)。"""
    postings, portals, seen = [], [], set()
    base = src["url"]
    for href, title in anchors(html):
        if href.startswith(("javascript:", "#")) or href in (".", "./", "../"):
            continue
        url = urljoin(base, href)
        internal_article = re.search(r"t?\d{8}_\d+\.html?$", href) and "sac.net.cn" in url
        if internal_article and any(k in title for k in _title_kw(src)) and len(title) >= 8:
            pid = pid_from_href(src["id"], href)
            if pid and pid not in seen:
                seen.add(pid)
                postings.append({
                    "id": pid, "title": title, "url": url, "org": None,
                    "category": src.get("category"), "region": src.get("region"),
                    "publish_date": date_from_href(href), "deadline": None,
                    "status": "declared",
                    "evidence": _evidence(src, url, title), "last_verified": _today(),
                })
        elif url.startswith("http") and "sac.net.cn" not in url and any(k in (title + href).lower() for k in DIR_PORTAL_KW):
            portals.append({"name": title, "url": url, "from": src["id"]})
    return postings, portals


EXTRACTORS = {"gov_list": gov_list, "link_directory": link_directory}


def load_postings(sid):
    p = POST / f"{sid}.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def upsert(src, postings, portals=None):
    """合并进正本:按 id 幂等;已存在保留 first_seen,更新 last_verified/evidence。"""
    doc = load_postings(src["id"])
    doc.setdefault("source", src["id"])
    doc["name"] = src.get("name")
    doc["homepage"] = src.get("url")
    doc["region"] = src.get("region")
    doc["category"] = src.get("category")
    doc["last_fetched"] = _today()
    existing = {p["id"]: p for p in doc.get("postings", [])}
    added = 0
    for p in postings:
        if p["id"] in existing:
            old = existing[p["id"]]
            old.update({k: p[k] for k in ("title", "url", "publish_date", "status", "evidence", "last_verified")})
        else:
            p["first_seen"] = _today()
            existing[p["id"]] = p
            added += 1
    doc["postings"] = sorted(existing.values(), key=lambda x: (x.get("publish_date") or ""), reverse=True)
    if portals is not None:
        doc["portals"] = portals
    POST.mkdir(exist_ok=True)
    (POST / f"{src['id']}.yaml").write_text(
        yaml.safe_dump(doc, allow_unicode=True, sort_keys=False), encoding="utf-8")
    return added, len(doc["postings"])


def run_extract():
    sources = (yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")) or {}).get("sources", [])
    total = 0
    for s in sources:
        parser = EXTRACTORS.get(s.get("parser"))
        if not parser:
            continue
        snap = SNAP / f"{s['id']}.html"
        if not snap.exists():
            print(f"  skip {s['id']}: no snapshot")
            continue
        html = snap.read_text(encoding="utf-8")
        portals = None
        res = parser(s, html)
        if isinstance(res, tuple):
            postings, portals = res
        else:
            postings = res
        added, count = upsert(s, postings, portals)
        total += len(postings)
        print(f"  extract {s['id']}: +{added} new, {count} total ({len(postings)} seen)")
    return total


def main(argv=None):
    print(f"extractor: registered={list(EXTRACTORS)}")
    n = run_extract()
    print(f"extractor: {n} posting(s) processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
