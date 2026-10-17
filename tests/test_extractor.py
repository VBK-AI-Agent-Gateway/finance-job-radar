# -*- coding: utf-8 -*-
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "agents"))
import extractor as ex

SAMPLE = """
<html><body>
<nav><a href="./">事业单位公开招聘</a><a href="javascript:void(0);">搜索</a></nav>
<ul>
<li><a href="./202610/t20261015_4903453.html">首都医科大学附属北京佑安医院2026年第三批社会人员公开招聘公告</a></li>
<li><a href="./202610/t20261014_4901622.html">首都医科大学附属北京康复医院2026年第三批公开招聘工作人员公告</a></li>
<li><a href="./xxgk/tzgg/202610/t20261009_4894652.html">关于中国银行系统升级期间社保卡业务调整的公告</a></li>
<li><a href="./">首页</a></li>
</ul></body></html>
"""

SRC = {"id": "bj_gkzp", "url": "https://rsj.beijing.gov.cn/xxgk/gkzp/",
       "region": "北京", "category": "事业单位"}


def test_gov_list_extracts_only_recruitment():
    posts = ex.gov_list(SRC, SAMPLE)
    titles = [p["title"] for p in posts]
    assert len(posts) == 2, titles
    assert all("招聘" in t for t in titles)
    assert all(p["category"] == "事业单位" and p["region"] == "北京" for p in posts)
    ids = {p["id"] for p in posts}
    assert "bj_gkzp:t20261015_4903453" in ids


def test_publish_date_from_href():
    assert ex.date_from_href("./202610/t20261015_4903453.html") == "2026-10-15"
    assert ex.date_from_href("/tgsgg_17341/20261015/t0035_1444213.html") == "2026-10-15"
    assert ex.date_from_href("https://x.com/a/b.html") is None


def test_upsert_idempotent(tmp_path, monkeypatch):
    monkeypatch.setattr(ex, "POST", tmp_path)
    posts = ex.gov_list(SRC, SAMPLE)
    a1, c1 = ex.upsert(SRC, posts)
    a2, c2 = ex.upsert(SRC, posts)
    assert a1 == 2 and a2 == 0 and c1 == c2 == 2
