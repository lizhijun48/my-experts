#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
高项论文机械检查器 —— 供「高项论文评分」Skill 调用。
只做可量化的机械检查（字数 / 摘要 / 结构 / 绩效域命中），
定性打分由 agent 结合 rubric.md 完成。
用法:
  python score_essay.py <论文文件.md>
  cat essay.md | python score_essay.py
"""
import sys, re, json

PERFORMANCE_DOMAINS = {
    "利益相关者": ["利益相关者", "干系人", "stakeholder"],
    "团队": ["团队", "成员", "协作"],
    "开发方法和生命周期": ["开发方法", "生命周期", "敏捷", "瀑布", "迭代"],
    "规划": ["规划", "计划", "wbs", "范围", "进度"],
    "项目工作": ["项目工作", "执行", "监控", "变更"],
    "交付": ["交付", "成果", "验收", "价值"],
    "度量": ["度量", "度量指标", "kpi", "评估"],
    "不确定性": ["不确定性", "风险", "应对", "突发", "未知"],
}


def analyze(text: str) -> dict:
    chars = len(re.sub(r"\s", "", text))
    has_abstract = bool(re.search(r"(摘要|提要)", text))
    paras = [p for p in re.split(r"\n\s*\n", text) if p.strip()]
    domain_hits = {}
    for dom, kws in PERFORMANCE_DOMAINS.items():
        domain_hits[dom] = sum(1 for kw in kws if kw.lower() in text.lower())
    covered = sum(1 for v in domain_hits.values() if v > 0)
    # 子题目回应检测（常见提示词）
    subq = len(re.findall(r"(第[一二三]个?问题|问题[一二三]|要求[一二三]|子题)", text))
    return {
        "char_count": chars,
        "has_abstract": has_abstract,
        "paragraph_count": len(paras),
        "domain_hits": domain_hits,
        "domains_covered": covered,
        "subquestion_markers": subq,
    }


def main():
    if len(sys.argv) > 1:
        with open(sys.argv[1], encoding="utf-8") as f:
            text = f.read()
    else:
        text = sys.stdin.read()

    res = analyze(text)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    verdict = []
    if res["char_count"] < 2000:
        verdict.append(f"⚠️ 字数偏少（{res['char_count']} 字），建议补足至 2000–2500 字")
    else:
        verdict.append(f"✅ 字数达标（{res['char_count']} 字）")
    verdict.append("✅ 有摘要" if res["has_abstract"] else "⚠️ 未检测到摘要，建议补 200–300 字摘要")
    verdict.append(f"📊 绩效域命中 {res['domains_covered']}/8 个")
    if res["subquestion_markers"] == 0:
        verdict.append("⚠️ 未检测到子题目回应标记，确认是否覆盖全部子要求")
    print("\n[机械检查]\n" + "\n".join("- " + v for v in verdict))


if __name__ == "__main__":
    main()
