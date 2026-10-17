# -*- coding: utf-8 -*-
"""发布员:由正本 postings/*.yaml 生成
  docs/jobs.json   机器可读全量
  docs/feed.xml    RSS 2.0 订阅
  docs/index.html  网页(筛选/搜索)
  README.md        表格摘要
数据只有一份正本,四个产物都由它生成。
"""
import argparse, datetime, html, json, pathlib, time
import yaml

ROOT = pathlib.Path(__file__).resolve().parents[1]
POST = ROOT / "postings"
DOCS = ROOT / "docs"
REPO = "https://github.com/VBK-AI-Agent-Gateway/finance-job-radar"

DROP_STATUS = {"stale"}


def load_all():
    jobs, sources = [], []
    for fp in sorted(POST.glob("*.yaml")):
        doc = yaml.safe_load(fp.read_text(encoding="utf-8")) or {}
        src = {"source": doc.get("source") or fp.stem, "name": doc.get("name"),
               "homepage": doc.get("homepage"), "region": doc.get("region"),
               "category": doc.get("category"), "last_fetched": doc.get("last_fetched")}
        posts = [p for p in (doc.get("postings") or []) if p.get("status") not in DROP_STATUS]
        for p in posts:
            p["source"] = src["source"]
            jobs.append(p)
        src["count"] = len(posts)
        sources.append(src)
    jobs.sort(key=lambda x: (x.get("publish_date") or "", x.get("id") or ""), reverse=True)
    return sources, jobs


def _iso_now():
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())


def write_json(sources, jobs):
    (DOCS / "jobs.json").write_text(json.dumps(
        {"generated": _iso_now(), "count": len(jobs), "sources": sources, "jobs": jobs},
        ensure_ascii=False, indent=1), encoding="utf-8")


def _rfc822(d):
    try:
        dt = datetime.datetime.strptime(d, "%Y-%m-%d").replace(tzinfo=datetime.timezone.utc)
        return dt.strftime("%a, %d %b %Y %H:%M:%S +0000")
    except Exception:
        return datetime.datetime.now(datetime.timezone.utc).strftime("%a, %d %b %Y %H:%M:%S +0000")


def write_rss(jobs):
    items = []
    for j in jobs[:200]:
        items.append(
            "    <item>\n"
            f"      <title>{html.escape(j.get('title') or '')}</title>\n"
            f"      <link>{html.escape(j.get('url') or '')}</link>\n"
            f"      <guid isPermaLink=\"false\">{html.escape(j.get('id') or '')}</guid>\n"
            f"      <pubDate>{_rfc822(j.get('publish_date'))}</pubDate>\n"
            f"      <category>{html.escape(str(j.get('category') or ''))}</category>\n"
            "    </item>")
    xml = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<rss version="2.0"><channel>\n'
        "  <title>金融/事业单位 招聘情报</title>\n"
        f"  <link>{REPO}</link>\n"
        "  <description>每日公开渠道招聘公告汇总(事业单位/公务员/金融机构)</description>\n"
        f"  <lastBuildDate>{_rfc822(time.strftime('%Y-%m-%d', time.gmtime()))}</lastBuildDate>\n"
        + "\n".join(items) + "\n</channel></rss>\n")
    (DOCS / "feed.xml").write_text(xml, encoding="utf-8")


HTML_TMPL = """<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>金融/事业单位 招聘情报</title>
<style>
 body{{font-family:system-ui,-apple-system,"Microsoft YaHei",sans-serif;margin:0;background:#0f1115;color:#e6e6e6}}
 header{{padding:18px 22px;border-bottom:1px solid #23262d;position:sticky;top:0;background:#0f1115dd;backdrop-filter:blur(6px)}}
 h1{{font-size:18px;margin:0 0 6px}} .meta{{color:#8b93a1;font-size:12px}}
 .bar{{padding:14px 22px;display:flex;gap:10px;flex-wrap:wrap}}
 select,input{{background:#171a21;color:#e6e6e6;border:1px solid #2a2e37;border-radius:8px;padding:7px 10px;font-size:13px}}
 table{{width:100%;border-collapse:collapse;font-size:13px}}
 th,td{{text-align:left;padding:9px 12px;border-bottom:1px solid #1d2027;vertical-align:top}}
 th{{color:#8b93a1;font-weight:600;position:sticky;top:64px;background:#0f1115}}
 a{{color:#6cb6ff;text-decoration:none}} a:hover{{text-decoration:underline}}
 .tag{{display:inline-block;font-size:11px;padding:1px 7px;border-radius:999px;background:#1e2a3a;color:#9cc7ff}}
 .tag.公务员{{background:#2a1e2a;color:#ffb0d6}}
 .tag.社会招聘{{background:#1e2a24;color:#9be8b4}}
</style></head><body>
<header><h1>金融 / 事业单位 招聘情报</h1>
<div class="meta">正本 jobs.json · 共 {count} 条 · 生成 {gen} · <a href="feed.xml">RSS</a></div></header>
<div class="bar">
 <input id="q" placeholder="搜索单位 / 标题…" oninput="render()" style="min-width:240px">
 <select id="region" onchange="render()"><option value="">全部地区</option>{regions}</select>
 <select id="cat" onchange="render()"><option value="">全部类别</option>{cats}</select>
</div>
<table><thead><tr><th>发布</th><th>标题</th><th>类别</th><th>地区</th><th>来源</th></tr></thead>
<tbody id="tb"></tbody></table>
<script>
const JOBS={data};
function render(){{
 const q=(document.getElementById('q').value||'').toLowerCase();
 const rg=document.getElementById('region').value, ct=document.getElementById('cat').value;
 const rows=JOBS.filter(j=>(!rg||j.region===rg)&&(!ct||j.category===ct)&&
   (!q||((j.title||'')+(j.org||'')).toLowerCase().includes(q)));
 document.getElementById('tb').innerHTML=rows.map(j=>`<tr>
   <td>${{j.publish_date||''}}</td>
   <td><a href="${{j.url}}" target="_blank" rel="noopener">${{j.title||''}}</a></td>
   <td><span class="tag ${{j.category||''}}">${{j.category||'—'}}</span></td>
   <td>${{j.region||'—'}}</td><td>${{j.source||''}}</td></tr>`).join('');
}}
render();
</script></body></html>"""


def write_html(sources, jobs):
    regions = "".join(f'<option value="{r}">{r}</option>' for r in sorted({j.get("region") for j in jobs if j.get("region")}))
    cats = "".join(f'<option value="{c}">{c}</option>' for c in sorted({j.get("category") for j in jobs if j.get("category")}))
    (DOCS / "index.html").write_text(
        HTML_TMPL.format(count=len(jobs), gen=_iso_now(), regions=regions, cats=cats,
                         data=json.dumps(jobs, ensure_ascii=False)),
        encoding="utf-8")


def write_readme(sources, jobs):
    lines = ["# finance-job-radar", "",
             "金融 / 事业单位「公开招聘」情报汇聚智能体 — 只收公开官方渠道,每条带来源与验证时间。", "",
             "口径: 岗位 = 公开**招聘公告/岗位**(事业单位、公务员、金融机构社招);不含个人简历/联系方式。", "",
             f"共 {len(jobs)} 条,生成于 {_iso_now()}。", "",
             "| 发布 | 标题 | 类别 | 地区 | 来源 |", "| --- | --- | --- | --- | --- |"]
    for j in jobs[:80]:
        t = (j.get("title") or "").replace("|", "/")
        lines.append(f"| {j.get('publish_date') or ''} | [{t}]({j.get('url') or ''}) | "
                     f"{j.get('category') or ''} | {j.get('region') or ''} | {j.get('source') or ''} |")
    lines += ["", "数据正本: `postings/*.yaml`;机器可读: `docs/jobs.json`;订阅: `docs/feed.xml`。"]
    (ROOT / "README.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main(argv=None):
    ap = argparse.ArgumentParser(description="发布员")
    ap.add_argument("--notify", action="store_true", help="(占位)推送通知")
    ap.parse_args(argv)
    DOCS.mkdir(exist_ok=True)
    sources, jobs = load_all()
    write_json(sources, jobs)
    write_rss(jobs)
    write_html(sources, jobs)
    write_readme(sources, jobs)
    print(f"publisher: {len(sources)} sources, {len(jobs)} jobs -> docs/ + README.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
