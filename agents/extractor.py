# -*- coding: utf-8 -*-
"""抽取员:官方列表页快照 -> 结构化岗位条目(正本 postings/{id}.yaml),并按 config/filters.yaml 判定是否在范围内。
第一阶段纯规则(不猜字段,拿不到写 null)。解析器:
- anchors_list  : 通用列表页(银行/国企/事业单位栏目)按 title_kw + 日期
- gov_list      : 政府/事业单位「公开招聘」列表页(详情页 URL 含日期目录)
- link_directory: 协会聚合页(站内公告 + 外部入口,供发现员)
"""
import datetime, hashlib, html as html_mod, json, pathlib, re, sys, time
from urllib.parse import urljoin
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
POST = ROOT / "postings"
SNAP = ROOT / "snapshots"

TITLE_KW_DEFAULT = ("招聘",)
DETAIL_RE = re.compile(r"/\d{6,8}/")
UA_STRIP = re.compile(r"<[^>]+>")


def _today():
    return time.strftime("%Y-%m-%d")


def _base(src):
    return src.get("url") or (src.get("urls") or [""])[0]


def clean(s):
    s = UA_STRIP.sub(" ", s or "")
    s = html_mod.unescape(s)
    return re.sub(r"\s+", " ", s).strip()


def anchors(html):
    return [(m.group(1), clean(m.group(2)), m.start(), m.end()) for m in
            re.finditer(r'<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', html, flags=re.S | re.I)]


def date_in_block(html, start, end):
    """日期常挂在标题同一条目(<li>)内、<a> 前后的 <span> 里。优先在当前 <li> 块内找,
    否则退回锚点后/前的小窗口。"""
    ls = html.rfind("<li", 0, start)
    le = html.find("</li>", end)
    if ls != -1 and le != -1 and 0 < le - ls < 2000:
        d = date_from_text(html[ls:le])
        if d:
            return d
    for seg in (html[end:end + 200], html[max(0, start - 200):start]):
        d = date_from_text(seg)
        if d:
            return d
    return None


def _iso(y, mo, d):
    y, mo, d = int(y), int(mo), int(d)
    if not (2000 <= y <= 2100 and 1 <= mo <= 12 and 1 <= d <= 31):
        return None
    return f"{y:04d}-{mo:02d}-{d:02d}"


def date_from_href(href):
    m = re.search(r"/(\d{4})(\d{2})(\d{2})/", href)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3))
    m = re.search(r"/(\d{4})(\d{2})/(?:[a-z])?(\d{4})(\d{2})(\d{2})_", href)
    if m:
        return _iso(m.group(3), m.group(4), m.group(5))
    m = re.search(r"/(\d{4})(\d{2})(\d{2})[^\d]", href)
    if m:
        return _iso(m.group(1), m.group(2), m.group(3))
    return None


def date_from_text(s):
    s = s or ""
    for m in re.finditer(r"(\d{4}|\d{2})\s*[.\-/年]\s*(\d{1,2})\s*[.\-/月]\s*(\d{1,2})", s):
        d = _iso(int(m.group(1)) if len(m.group(1)) == 4 else 2000 + int(m.group(1)),
                 m.group(2), m.group(3))
        if d:
            return d
    m = re.search(r"\[\s*(\d{1,2})[-/.]\s*(\d{1,2})\s*\]\s*$", s)
    if m:
        return _iso(time.strftime("%Y"), m.group(1), m.group(2))
    return None


def clean_title(s):
    s = re.sub(r"\s*\[\s*\d{1,2}[-/.]\s*\d{1,2}\s*\]\s*$", "", s)
    s = re.sub(r"\s*\d{4}\s*[.\-/]\s*\d{1,2}\s*[.\-/]\s*\d{1,2}\s*$", "", s)
    return s.strip()


def pid_from_href(src_id, href):
    seg = href.rstrip("/").split("/")[-1]
    seg = re.sub(r"\.html?$", "", seg)
    seg = re.sub(r"[^0-9A-Za-z_\-.]+", "_", seg)[:60].strip("_")
    return f"{src_id}:{seg}" if seg else None


def _pid(src_id, href, url):
    pid = pid_from_href(src_id, href)
    if not pid or len(pid) < len(src_id) + 2 or "jsp" in pid:
        pid = f"{src_id}:h{hashlib.md5(url.encode('utf-8')).hexdigest()[:10]}"
    return pid


def _evidence(src, url, excerpt):
    return [{"kind": "official_page", "url": url, "at": _today(), "excerpt": (excerpt or None)}]


def _title_kw(src):
    return tuple(src.get("title_kw") or TITLE_KW_DEFAULT)


def _is_detail(src, href):
    pat = src.get("detail_re")
    if pat:
        return bool(re.search(pat, href))
    return bool(DETAIL_RE.search(href))


# ── 解析器 ────────────────────────────────────────────
def anchors_list(src, html):
    """通用列表页:标题命中 title_kw、有可抓 URL 的条目。"""
    out, seen = [], set()
    kw = _title_kw(src)
    for href, raw, astart, aend in anchors(html):
        href = real_href(href)
        if href.startswith(("javascript:", "#", "mailto:")) or href in (".", "./", "../", ""):
            continue
        if not any(k in raw for k in kw):
            continue
        title = clean_title(raw)
        if len(title) < 8:
            continue
        url = urljoin(_base(src), href)
        if not url.startswith("http"):
            continue
        pid = _pid(src["id"], href, url)
        if pid in seen:
            continue
        seen.add(pid)
        out.append({
            "id": pid, "title": title, "url": url, "org": None,
            "category": src.get("category"), "region": src.get("region"),
            "publish_date": date_from_text(raw) or date_in_block(html, astart, aend) or date_from_href(href),
            "deadline": None, "status": "declared",
            "evidence": _evidence(src, url, title), "last_verified": _today(),
        })
    return out


def gov_list(src, html):
    """政府/事业单位公开招聘列表页:详情页 URL 含日期目录。"""
    out, seen = [], set()
    kw = _title_kw(src)
    for href, title, astart, aend in anchors(html):
        if len(title) < 8 or not any(k in title for k in kw):
            continue
        if href.startswith(("javascript:", "#")) or href in (".", "./"):
            continue
        if not re.search(r"\.html?$", href) or not _is_detail(src, href):
            continue
        url = urljoin(_base(src), href)
        pid = pid_from_href(src["id"], href)
        if not pid or pid in seen:
            continue
        seen.add(pid)
        out.append({
            "id": pid, "title": title, "url": url, "org": None,
            "category": src.get("category"), "region": src.get("region"),
            "publish_date": date_in_block(html, astart, aend) or date_from_href(href), "deadline": None,
            "status": "declared", "evidence": _evidence(src, url, title),
            "last_verified": _today(),
        })
    return out


DIR_PORTAL_KW = ("招聘", "人才", "career", "job", "recruit", "campus", "intern")


def link_directory(src, html):
    """协会聚合页:站内公告(返回 postings) + 外部入口(返回 portals)。"""
    postings, portals, seen = [], [], set()
    base = _base(src)
    for href, title, astart, aend in anchors(html):
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
                    "status": "declared", "evidence": _evidence(src, url, title),
                    "last_verified": _today(),
                })
        elif url.startswith("http") and "sac.net.cn" not in url and \
                any(k in (title + href).lower() for k in DIR_PORTAL_KW):
            portals.append({"name": title, "url": url, "from": src["id"]})
    return postings, portals


def json_api(src, text):
    """JSON 接口列表:按 json_path 取数组,映射字段 id/title/url/date(用于 SPA 站点的后端接口)。"""
    try:
        data = json.loads(text)
    except Exception:
        return []
    rows = data if isinstance(data, list) else (data.get(src.get("json_path") or "zp") or [])
    tmpl = src.get("detail_tmpl") or ""
    out, seen = [], set()
    for row in rows:
        if not isinstance(row, dict):
            continue
        title = clean(row.get("title") or row.get("name") or "")
        did = row.get("d") if row.get("d") is not None else row.get("id")
        if not title or did is None:
            continue
        url = urljoin(_base(src), tmpl.format(id=did)) if tmpl else _base(src)
        pid = f"{src['id']}:{did}"
        if pid in seen:
            continue
        seen.add(pid)
        raw = str(row.get("time") or row.get("date") or "")
        out.append({
            "id": pid, "title": title, "url": url, "org": row.get("org"),
            "category": src.get("category"), "region": src.get("region"),
            "publish_date": raw[:10] if re.match(r"\d{4}-\d{2}-\d{2}", raw) else None,
            "deadline": None, "status": "declared",
            "evidence": _evidence(src, url, title), "last_verified": _today(),
        })
    return out


GOX_RE = re.compile(r"'(/[^']+\.html?)'")


def real_href(href):
    """把 javascript:goxxinfo(...) 里内嵌的真实路径还原成可抓 URL(人事网),否则原样返回。"""
    if href.startswith("javascript:goxxinfo"):
        m = GOX_RE.search(href)
        if m:
            return m.group(1)
    return href


EXTRACTORS = {"anchors_list": anchors_list, "gov_list": gov_list,
              "link_directory": link_directory, "json_api": json_api}


# ── 范围过滤(口径见 config/filters.yaml) ──────────────
def load_filters():
    p = ROOT / "config" / "filters.yaml"
    return yaml.safe_load(p.read_text(encoding="utf-8")) or {} if p.exists() else {}


def qualify(posting, src, filters):
    """-> (in_scope, reason, entity, domain_tags)"""
    reg = filters.get("region") or {}
    region_kw, region_ex = reg.get("include") or [], reg.get("exclude") or []
    dom = filters.get("domain") or {}
    rules = filters.get("rules") or {}
    entity = src.get("entity") or "institution"
    title = posting.get("title") or ""
    text = f"{title} {posting.get('org') or ''}"
    if any(k in title for k in (filters.get("exclude_title") or [])):
        return False, "非岗位(过程/结果公示)", entity, []
    region_kw = src.get("region_kw") or region_kw   # 源级覆盖(如全国性银行只看四川/成都分行)
    has_inc, has_exc = any(k in text for k in region_kw), any(k in text for k in region_ex)
    region_ok = has_inc or (src.get("default_region") in ("成都", "大成都") and not has_exc)
    tags = [t for t, kws in (("金融", dom.get("finance") or []), ("后勤", dom.get("logistics") or []))
            if any(k in text for k in kws)]
    need_domain = bool((rules.get(entity) or {}).get("domain_required"))
    domain_ok = (not need_domain) or bool(tags)
    if not region_ok:
        return False, "非大成都", entity, tags
    if not domain_ok:
        return False, "国企未命中金融/后勤", entity, tags
    rec = filters.get("recency") or {}
    max_age, pd_ = rec.get("max_age_days"), posting.get("publish_date")
    if max_age and pd_:
        try:
            if (datetime.date.today() - datetime.date.fromisoformat(pd_)).days > int(max_age):
                return False, f"过旧(>{max_age}天)", entity, tags
        except ValueError:
            pass
    dl = posting.get("deadline")
    if rec.get("drop_expired", True) and dl:
        try:
            if datetime.date.fromisoformat(dl) < datetime.date.today():
                return False, "已过期(超过截止日)", entity, tags
        except ValueError:
            pass
    return True, f"命中[{'/'.join(tags) if tags else entity}]", entity, tags


# ── 正本读写 ──────────────────────────────────────────
def load_postings(sid):
    p = POST / f"{sid}.yaml"
    if p.exists():
        return yaml.safe_load(p.read_text(encoding="utf-8")) or {}
    return {}


def upsert(src, postings, portals=None, filters=None):
    """合并进正本:按 id 幂等;每条打上 entity / in_scope / scope_reason / domain。"""
    if filters is None:
        filters = load_filters()
    doc = load_postings(src["id"])
    doc["source"] = src["id"]
    doc["name"] = src.get("name")
    doc["homepage"] = _base(src)
    doc["entity"] = src.get("entity")
    doc["region"] = src.get("region")
    doc["category"] = src.get("category")
    doc["last_fetched"] = _today()
    existing = {p["id"]: p for p in doc.get("postings", [])}
    added = 0
    for p in postings:
        scope, reason, entity, tags = qualify(p, src, filters)
        p["entity"], p["in_scope"], p["scope_reason"], p["domain"] = entity, scope, reason, tags
        if p["id"] in existing:
            existing[p["id"]].update(p)
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
    in_scope = sum(1 for p in doc["postings"] if p.get("in_scope"))
    return added, len(doc["postings"]), in_scope


def _snapshots(sid):
    files = sorted(SNAP.glob(f"{sid}.html")) + sorted(SNAP.glob(f"{sid}.json")) + \
            sorted(SNAP.glob(f"{sid}__*.html")) + sorted(SNAP.glob(f"{sid}__*.json"))
    return files


def run_extract():
    srcs = (yaml.safe_load((ROOT / "config" / "sources.yaml").read_text(encoding="utf-8")) or {}).get("sources", [])
    filters = load_filters()
    total = 0
    for s in srcs:
        parser = EXTRACTORS.get(s.get("parser"))
        if not parser:
            continue
        snaps = _snapshots(s["id"])
        if not snaps:
            print(f"  skip {s['id']}: no snapshot")
            continue
        postings, portals, seen_ids = [], None, set()
        for fp in snaps:
            html = fp.read_text(encoding="utf-8")
            res = parser(s, html)
            got, p = (res if isinstance(res, tuple) else (res, None))
            for item in got:
                if item["id"] not in seen_ids:
                    seen_ids.add(item["id"])
                    postings.append(item)
            if p is not None:
                portals = (portals or []) + p
        added, count, in_scope = upsert(s, postings, portals, filters)
        total += len(postings)
        print(f"  extract {s['id']}: +{added} new, {count} total, {in_scope} in_scope ({len(snaps)} page(s))")
    return total


def main(argv=None):
    print(f"extractor: registered={list(EXTRACTORS)}")
    n = run_extract()
    print(f"extractor: {n} posting(s) processed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
