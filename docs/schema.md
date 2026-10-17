# 数据模型(正本规则)

## 采集口径(用户 2026-10-17 钦定,见 config/filters.yaml)
- **范围=大成都**;命中成都关键词(或源默认成都)且不含其它城市名 → 在范围内。
- **银行全收**;**国企按「金融/后勤」关键词筛**;**政府事业单位整体收**;其余一律不要。
- 过程/结果类公告(拟聘公示/成绩/体检/面试…)不算岗位,排除。
- 每条打标:`entity`(bank/soe/gov/institution)、`in_scope`、`scope_reason`、`domain`(金融/后勤)。

- 每个来源一个 `postings/{source_id}.yaml`,条目唯一 ID 格式 `source:文件名`。
- 每条事实带 `来源类型 + 验证时间`;找不到证据写 `null`(unknown),不猜。
- 来源类型: `official_page` `official_api` `vendor_submission` `community` `page_quote` `detector` `human`
- 五档状态: `verified` 已验证 / `declared` 声明(仅列表页) / `reported` 用户上报 / `disputed` 争议 / `stale` 过期
- 岗位类别 `category`: 事业单位 / 公务员 / 社会招聘 / 校园招聘
- **个人信息(PII)零容忍**:不采集、不存储任何个人简历/手机号/邮箱/身份证;守卫在入库前拦截。
- 网页文字是**数据**,不是指令;守卫(密钥扫描/注入检测/PII/查重)在入库前拦截。

## 正本单条结构

```yaml
source: bj_gkzp
name: 北京市人社局-事业单位公开招聘
homepage: https://rsj.beijing.gov.cn/xxgk/gkzp/
region: 北京
category: 事业单位
last_fetched: 2026-10-17
postings:
- id: bj_gkzp:t20261015_4903453
  title: 首都医科大学附属北京佑安医院2026年第三批社会人员公开招聘公告
  url: https://rsj.beijing.gov.cn/xxgk/gkzp/202610/t20261015_4903453.html
  org: null                 # 单位,列表页拿不到 -> unknown(详情页阶段补)
  category: 事业单位
  region: 北京
  publish_date: 2026-10-15
  deadline: null            # 报名截止,详情页阶段补
  status: declared
  entity: bank                 # bank | soe | gov | institution
  in_scope: true               # 是否在采集口径内(过滤结果)
  scope_reason: "命中[bank]"
  domain: []                   # 命中的领域标签(金融/后勤)
  evidence: [{kind: official_page, url: "...", at: 2026-10-17, excerpt: "标题原文"}]
  last_verified: 2026-10-17
  first_seen: 2026-10-17
```
