#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
字幕翻译质量检查模块。

第一版只做本地规则检查：术语推荐译法、禁用译法、条目数量和时间轴一致性。
它不修改字幕，只生成质检报告和人工审稿稿。
"""

import json
import os
import re
from datetime import datetime
from typing import Dict, List, Optional

from .srt_parser import SRTEntry, build_srt
from .translator import parse_translated_srt


DEFAULT_TERM_RULES = [
    {
        "source": "built_in",
        "term": "首检",
        "preferred": ["First Quality Check", "FQC"],
        "aliases": ["FQC"],
        "context": "工厂/MES/质量检验",
        "forbidden": ["First Article Check", "FAC", "FA"],
        "enforce_preferred": True,
        "note": "在工厂 MES 质量场景中，首检优先按首次质量检验处理，避免误译为首件检验。",
    }
]


def _split_cell_values(value: str) -> List[str]:
    if not value:
        return []
    parts = re.split(r"[/,，、;；\n]+", value)
    results = []
    for part in parts:
        cleaned = part.strip()
        if cleaned and cleaned not in {"-", "无", "N/A", "n/a"}:
            results.append(cleaned)
    return results


def _clean_header(cell: str) -> str:
    return cell.strip().replace(" ", "").lower()


def _contains_latin_phrase(text: str, phrase: str) -> bool:
    pattern = r"(?<![A-Za-z0-9])" + re.escape(phrase) + r"(?![A-Za-z0-9])"
    return re.search(pattern, text, flags=re.IGNORECASE) is not None


def _contains_phrase(text: str, phrase: str) -> bool:
    if not phrase:
        return False
    if re.search(r"[A-Za-z]", phrase):
        return _contains_latin_phrase(text, phrase)
    return phrase in text


def _dedupe_rules(rules: List[Dict]) -> List[Dict]:
    merged: Dict[str, Dict] = {}
    for rule in rules:
        term = rule.get("term", "").strip()
        if not term:
            continue
        if term not in merged:
            merged[term] = {
                "source": rule.get("source", "glossary"),
                "term": term,
                "preferred": [],
                "aliases": [],
                "context": rule.get("context", ""),
                "forbidden": [],
                "enforce_preferred": bool(rule.get("enforce_preferred", False)),
                "note": rule.get("note", ""),
            }
        target = merged[term]
        for key in ["preferred", "aliases", "forbidden"]:
            for value in rule.get(key, []):
                if value and value not in target[key]:
                    target[key].append(value)
        if rule.get("context") and not target.get("context"):
            target["context"] = rule["context"]
        if rule.get("note") and not target.get("note"):
            target["note"] = rule["note"]
        if rule.get("enforce_preferred"):
            target["enforce_preferred"] = True
    return list(merged.values())


def load_quality_rules(glossary_path: Optional[str] = None) -> List[Dict]:
    """从 Markdown 术语表中读取质检规则，并合并内置关键规则。"""
    rules = [dict(rule) for rule in DEFAULT_TERM_RULES]

    if not glossary_path or not os.path.exists(glossary_path):
        return _dedupe_rules(rules)

    try:
        with open(glossary_path, "r", encoding="utf-8") as f:
            content = f.read()
    except Exception:
        return _dedupe_rules(rules)

    current_headers: List[str] = []
    for raw_line in content.splitlines():
        line = raw_line.strip()
        if not line.startswith("|") or "---" in line:
            continue

        cells = [cell.strip() for cell in line.strip("|").split("|")]
        normalized = [_clean_header(cell) for cell in cells]

        if any("中文术语" in h or h == "中文" for h in normalized):
            current_headers = normalized
            continue

        if not current_headers or len(cells) < 2:
            continue

        row = {}
        for i, header in enumerate(current_headers):
            if i < len(cells):
                row[header] = cells[i].strip()

        term = row.get("中文术语") or row.get("中文")
        preferred = row.get("英文翻译") or row.get("推荐英文") or row.get("英文")
        aliases = row.get("缩写/别名") or row.get("缩写") or ""
        context = row.get("适用场景") or row.get("所属模块") or ""
        forbidden = row.get("禁用译法") or row.get("禁止译法") or ""
        note = row.get("备注说明") or row.get("备注") or ""

        if term and preferred:
            rules.append({
                "source": "glossary",
                "term": term,
                "preferred": [preferred],
                "aliases": _split_cell_values(aliases),
                "context": context,
                "forbidden": _split_cell_values(forbidden),
                "enforce_preferred": bool(forbidden),
                "note": note,
            })

    return _dedupe_rules(rules)


def _entry_confidence(score: int) -> str:
    if score >= 90:
        return "high"
    if score >= 70:
        return "medium"
    return "low"


def _entry_to_dict(entry: Optional[SRTEntry]) -> Dict:
    if not entry:
        return {"index": None, "start_time": "", "end_time": "", "text": ""}
    return {
        "index": entry.index,
        "start_time": entry.start_time,
        "end_time": entry.end_time,
        "text": entry.text,
    }


def _check_term_rule(cn_text: str, en_text: str, rule: Dict) -> List[Dict]:
    issues = []
    term = rule["term"]

    if term not in cn_text:
        return issues

    forbidden_hits = []
    for value in rule.get("forbidden", []):
        if _contains_phrase(en_text, value):
            forbidden_hits.append(value)

    if forbidden_hits:
        issues.append({
            "type": "forbidden_term",
            "severity": "high",
            "term": term,
            "message": f"术语 '{term}' 命中了禁用译法: {', '.join(forbidden_hits)}",
            "expected": rule.get("preferred", []),
            "actual": forbidden_hits,
            "note": rule.get("note", ""),
        })

    expected_values = list(rule.get("preferred", [])) + list(rule.get("aliases", []))
    if rule.get("enforce_preferred") and expected_values and not any(_contains_phrase(en_text, value) for value in expected_values):
        issues.append({
            "type": "missing_preferred_term",
            "severity": "medium",
            "term": term,
            "message": f"术语 '{term}' 未命中推荐译法",
            "expected": expected_values,
            "actual": [],
            "note": rule.get("note", ""),
        })

    return issues


def generate_quality_report(
    cn_entries: List[SRTEntry],
    en_entries: List[SRTEntry],
    glossary_path: Optional[str] = None,
    back_translations: Optional[List[str]] = None,
) -> Dict:
    """生成机器可读的翻译质量报告。"""
    rules = load_quality_rules(glossary_path)
    max_len = max(len(cn_entries), len(en_entries))
    report_entries = []

    for i in range(max_len):
        cn_entry = cn_entries[i] if i < len(cn_entries) else None
        en_entry = en_entries[i] if i < len(en_entries) else None
        cn_text = cn_entry.text if cn_entry else ""
        en_text = en_entry.text if en_entry else ""
        issues = []

        if not cn_entry or not en_entry:
            issues.append({
                "type": "entry_count_mismatch",
                "severity": "high",
                "message": "中英文字幕条目数量不一致，当前序号无法配对",
            })
        elif cn_entry.start_time != en_entry.start_time or cn_entry.end_time != en_entry.end_time:
            issues.append({
                "type": "timestamp_mismatch",
                "severity": "high",
                "message": "中英文字幕时间轴不一致",
            })

        for rule in rules:
            issues.extend(_check_term_rule(cn_text, en_text, rule))

        score = 100
        for issue in issues:
            if issue.get("severity") == "high":
                score -= 35
            elif issue.get("severity") == "medium":
                score -= 15
            else:
                score -= 5
        score = max(score, 0)

        report_entries.append({
            "index": cn_entry.index if cn_entry else (en_entry.index if en_entry else i + 1),
            "chinese": _entry_to_dict(cn_entry),
            "english": _entry_to_dict(en_entry),
            "back_translation": back_translations[i] if back_translations and i < len(back_translations) else "",
            "issues": issues,
            "score": score,
            "confidence": _entry_confidence(score),
        })

    issue_entries = [entry for entry in report_entries if entry["issues"]]
    summary = {
        "total_entries": max_len,
        "cn_entries": len(cn_entries),
        "en_entries": len(en_entries),
        "issue_entries": len(issue_entries),
        "issue_count": sum(len(entry["issues"]) for entry in report_entries),
        "high_confidence": sum(1 for entry in report_entries if entry["confidence"] == "high"),
        "medium_confidence": sum(1 for entry in report_entries if entry["confidence"] == "medium"),
        "low_confidence": sum(1 for entry in report_entries if entry["confidence"] == "low"),
        "rules_checked": len(rules),
    }

    return {
        "version": "1.0",
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "summary": summary,
        "rules": rules,
        "entries": report_entries,
    }


def back_translate_english_entries(
    en_entries: List[SRTEntry],
    ai_client,
    batch_size: int = 25,
    temperature: float = 0.1,
) -> List[str]:
    """
    将英文字幕直译回中文，供人工质检使用。

    返回的文本不作为字幕交付，也不会覆盖原始中文或英文结果。
    """
    if not en_entries:
        return []

    system_prompt = (
        "你是一个制造业 MES 字幕翻译质检助手。\n"
        "任务是把英文字幕逐条直译回中文，帮助人工检查英文翻译是否偏离原意。\n"
        "要求：\n"
        "1. 严格保持 SRT 序号和时间轴不变。\n"
        "2. 尽量直译，不要润色成新的中文字幕。\n"
        "3. 遇到 MES、FQC、OEE、WMS 等术语，保留其专业含义。\n"
        "4. 只输出 SRT 格式，不要添加解释。"
    )

    back_translations: List[str] = []
    total = len(en_entries)
    num_batches = (total + batch_size - 1) // batch_size

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch_entries = en_entries[start:end]

        try:
            result = ai_client.call_chat(
                system_prompt=system_prompt,
                user_prompt=build_srt(batch_entries),
                temperature=temperature,
            )
            texts = parse_translated_srt(result)
        except Exception:
            texts = []

        if len(texts) > len(batch_entries):
            texts = texts[:len(batch_entries)]
        while len(texts) < len(batch_entries):
            texts.append("")

        back_translations.extend(texts)

    return back_translations


def build_quality_markdown(report: Dict) -> str:
    """生成给人工审稿使用的 Markdown 质检稿。"""
    summary = report["summary"]
    lines = [
        "# 翻译质量质检稿",
        "",
        f"生成时间：{report['generated_at']}",
        "",
        "## 总览",
        "",
        f"- 字幕条目：{summary['total_entries']}",
        f"- 风险条目：{summary['issue_entries']}",
        f"- 风险点：{summary['issue_count']}",
        f"- 高置信度：{summary['high_confidence']}",
        f"- 中置信度：{summary['medium_confidence']}",
        f"- 低置信度：{summary['low_confidence']}",
        f"- 质检规则：{summary['rules_checked']}",
        "",
    ]

    readability = report.get("subtitle_readability") or {}
    if readability:
        lines.extend([
            "## 英文字幕可读性",
            "",
            f"- 最终字幕条目：{readability.get('total_entries', 0)}",
            f"- 原始英文条目：{readability.get('source_entries', 0)}",
            f"- 合并减少：{readability.get('merged_entries', 0)}",
            f"- 阅读速度警告：{readability.get('warning_entries', 0)} 条",
            f"- AI重排批次：{readability.get('ai_batches', 0)}",
            f"- AI二次修订批次：{readability.get('ai_revision_batches', 0)}",
            "",
        ])

    lines.extend([
        "## 风险条目",
        "",
    ])

    risky_entries = [entry for entry in report["entries"] if entry["issues"]]
    if not risky_entries:
        lines.extend(["未发现本地规则风险。", ""])
    else:
        for entry in risky_entries:
            cn = entry["chinese"]
            en = entry["english"]
            lines.extend([
                f"### #{entry['index']} 评分 {entry['score']} / 100，置信度 {entry['confidence']}",
                "",
                f"时间轴：{cn.get('start_time') or en.get('start_time')} --> {cn.get('end_time') or en.get('end_time')}",
                "",
                f"中文：{cn.get('text', '')}",
                "",
                f"英文：{en.get('text', '')}",
                "",
                f"英文直译回中文：{entry.get('back_translation', '') or '未生成'}",
                "",
                "风险：",
            ])
            for issue in entry["issues"]:
                lines.append(f"- [{issue.get('severity')}] {issue.get('message')}")
                if issue.get("expected"):
                    lines.append(f"  推荐：{', '.join(issue['expected'])}")
                if issue.get("note"):
                    lines.append(f"  备注：{issue['note']}")
            lines.append("")

    lines.extend([
        "## 全量对照",
        "",
        "| 序号 | 时间轴 | 中文 | 英文 | 英文直译回中文 | 分数 | 置信度 |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ])

    for entry in report["entries"]:
        cn = entry["chinese"]
        en = entry["english"]
        timeline = f"{cn.get('start_time') or en.get('start_time')} --> {cn.get('end_time') or en.get('end_time')}"
        cn_text = cn.get("text", "").replace("|", "\\|").replace("\n", "<br>")
        en_text = en.get("text", "").replace("|", "\\|").replace("\n", "<br>")
        back_translation = entry.get("back_translation", "").replace("|", "\\|").replace("\n", "<br>")
        lines.append(
            f"| {entry['index']} | {timeline} | {cn_text} | {en_text} | {back_translation} | {entry['score']} | {entry['confidence']} |"
        )

    lines.append("")
    return "\n".join(lines)


def write_quality_artifacts(report: Dict, output_dir: str, original_base: str) -> List[Dict]:
    """写入 JSON 报告和 Markdown 质检稿，返回下载文件元数据。"""
    os.makedirs(output_dir, exist_ok=True)

    json_name = f"翻译质量报告_{original_base}.json"
    md_name = f"直译质检稿_{original_base}.md"
    json_path = os.path.join(output_dir, json_name)
    md_path = os.path.join(output_dir, md_name)

    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)

    with open(md_path, "w", encoding="utf-8") as f:
        f.write(build_quality_markdown(report))

    return [
        {"name": json_name, "label": "翻译质量报告（机器可读）", "path": json_path, "category": "quality"},
        {"name": md_name, "label": "直译质检稿（人工审核用）", "path": md_path, "category": "quality"},
    ]
