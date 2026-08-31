#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""English subtitle reflow and readability analysis.

The translation API keeps one English entry per source entry. This module
groups those fragments into readable English subtitle units and records the
reading-speed metrics used to review the result.
"""

import json
import re
from typing import Dict, List, Optional, Tuple

from .srt_parser import SRTEntry, build_srt, format_time, parse_time
from .translator import parse_translated_srt


SENTENCE_END_RE = re.compile(r"[.!?。！？；;]\s*$")
CLAUSE_END_RE = re.compile(r"[,，、:]\s*$")
CONTINUATION_START_RE = re.compile(
    r"^(and|or|but|so|because|if|when|while|which|that|to|of|for|in|on|with|as)\b",
    re.IGNORECASE,
)


def word_count(text: str) -> int:
    return len(re.findall(r"\b[\w']+\b", text or ""))


def reading_speed(text: str, duration_ms: int) -> float:
    seconds = max(duration_ms / 1000.0, 0.001)
    return word_count(text) / seconds


def _clean_text(text: str) -> str:
    text = re.sub(r"\s+", " ", (text or "").replace("\n", " ")).strip()
    text = re.sub(r"\s+([,.;:!?])", r"\1", text)
    text = re.sub(r"([,.;:!?])(?!\s|$)", r"\1 ", text)
    return text.strip()


def _group_by_rules(entries: List[SRTEntry]) -> List[List[int]]:
    """Fallback grouping used when the AI response is unavailable or invalid."""
    if not entries:
        return []

    groups: List[List[int]] = []
    current: List[int] = []
    for position, entry in enumerate(entries):
        current.append(position)
        duration_ms = parse_time(entry.end_time) - parse_time(entries[current[0]].start_time)
        english = _clean_text(entry.text)
        chinese = (entry.text or "").strip()
        source_ends = bool(SENTENCE_END_RE.search(chinese))
        english_ends = bool(SENTENCE_END_RE.search(english))
        clause_ends = bool(CLAUSE_END_RE.search(chinese)) or bool(CLAUSE_END_RE.search(english))

        next_text = _clean_text(entries[position + 1].text) if position + 1 < len(entries) else ""
        next_continues = bool(CONTINUATION_START_RE.search(next_text))
        should_close = (
            len(current) >= 4
            or duration_ms.total_seconds() >= 7
            or (source_ends or english_ends) and not next_continues
        )
        if should_close:
            groups.append(current)
            current = []
        elif not clause_ends and len(current) >= 2 and next_text and not next_continues:
            # A complete fragment without punctuation is a reasonable boundary.
            groups.append(current)
            current = []

    if current:
        groups.append(current)
    return groups


def _parse_ai_groups(raw: str, count: int) -> Optional[List[Dict]]:
    """Parse and strictly validate the AI's partition of a batch."""
    text = (raw or "").strip()
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1).strip()
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return None

    groups = payload.get("groups") if isinstance(payload, dict) else payload
    if not isinstance(groups, list) or not groups:
        return None

    normalized = []
    covered = []
    for group in groups:
        if not isinstance(group, dict):
            return None
        positions = group.get("source_positions") or group.get("source_indices")
        value = group.get("text") or group.get("english")
        if not isinstance(positions, list) or not positions or not isinstance(value, str):
            return None
        try:
            positions = [int(position) for position in positions]
        except (TypeError, ValueError):
            return None
        if any(position < 1 or position > count for position in positions):
            return None
        if positions != list(range(positions[0], positions[-1] + 1)):
            return None
        covered.extend(positions)
        normalized.append({"source_positions": positions, "text": _clean_text(value)})

    if covered != list(range(1, count + 1)) or any(not group["text"] for group in normalized):
        return None
    return normalized


def _build_prompt(
    batch_cn: List[SRTEntry],
    batch_en: List[SRTEntry],
    glossary_text: str,
    max_chars_per_line: int,
    warning_wps: float,
    hard_wps: float,
    revision_note: str = "",
) -> Tuple[str, str]:
    system = (
        "你是制造业 MES 视频的英文字幕编辑。\n"
        "任务是把机器翻译产生的英文碎片重排为易读字幕。\n"
        "规则：\n"
        "1. 相邻且属于同一句话的片段必须合并，不要保留孤立的从句、介词短语或逗号短语。\n"
        "2. 保留中文原意和 MES/SMT 专业术语，不添加原文没有的信息。\n"
        f"3. 英文要自然、简洁，目标不超过 {warning_wps} words/sec，绝对不要超过 {hard_wps} words/sec。\n"
        "4. 每个输出组只能由连续的 source_positions 组成，必须覆盖所有输入位置且不能遗漏、重复。\n"
        "5. 一般一个完整句子一个组；长句应按语义拆成多个相邻组。\n"
        f"6. 每组最多两行，每行最多约 {max_chars_per_line} 个英文字符，即单组尽量不超过 {max_chars_per_line * 2} 个字符。\n"
        "7. 不要输出以逗号结尾的孤立短语，也不要输出不完整语法片段。\n"
        "8. 只输出 JSON，不要 Markdown，不要解释。格式："
        '{"groups":[{"source_positions":[1,2],"text":"Complete English sentence."}]}\n'
    )
    if glossary_text:
        system += "术语表（优先采用）：\n" + glossary_text + "\n"

    rows = []
    for position, (cn, en) in enumerate(zip(batch_cn, batch_en), start=1):
        rows.append({
            "source_position": position,
            "duration_seconds": round(en.duration_ms / 1000.0, 3),
            "chinese": cn.text,
            "english_fragment": en.text,
        })
    user = json.dumps(rows, ensure_ascii=False, indent=2)
    if revision_note:
        user += "\n\n上一版未通过字幕约束，请完整重做。具体问题：\n" + revision_note
    return system, user


def _group_violations(
    groups: List[Dict],
    entries: List[SRTEntry],
    max_chars_per_line: int,
    hard_wps: float,
) -> List[str]:
    violations = []
    for number, group in enumerate(groups, start=1):
        positions = group["source_positions"]
        first = entries[positions[0] - 1]
        last = entries[positions[-1] - 1]
        duration_ms = int((parse_time(last.end_time) - parse_time(first.start_time)).total_seconds() * 1000)
        text = _clean_text(group["text"])
        wps = reading_speed(text, duration_ms)
        if len(text) > max_chars_per_line * 2:
            violations.append(
                f"第 {number} 组有 {len(text)} 个字符，超过两行建议上限 {max_chars_per_line * 2}"
            )
        if wps > hard_wps:
            violations.append(
                f"第 {number} 组阅读速度 {wps:.2f} words/sec，超过硬上限 {hard_wps}"
            )
        if re.search(r"[,，:]\s*$", text):
            violations.append(f"第 {number} 组以逗号或冒号结尾，是不完整片段")
    return violations


def _entry_from_group(group: Dict, cn_entries: List[SRTEntry], en_entries: List[SRTEntry], index: int) -> SRTEntry:
    positions = group["source_positions"]
    first = en_entries[positions[0] - 1]
    last = en_entries[positions[-1] - 1]
    return SRTEntry(
        index=index,
        start_time=first.start_time,
        end_time=last.end_time,
        text=group["text"],
    )


def _wrap_text(text: str, max_chars: int) -> str:
    words = text.split()
    if not words:
        return ""
    if len(" ".join(words)) <= max_chars:
        return " ".join(words)

    best_split = 1
    best_score = float("inf")
    for split in range(1, len(words)):
        first = " ".join(words[:split])
        second = " ".join(words[split:])
        overflow = max(0, len(first) - max_chars) + max(0, len(second) - max_chars)
        balance = abs(len(first) - len(second))
        score = overflow * 100 + balance
        if score < best_score:
            best_score = score
            best_split = split
    return " ".join(words[:best_split]) + "\n" + " ".join(words[best_split:])


def reflow_english_subtitles(
    cn_entries: List[SRTEntry],
    en_entries: List[SRTEntry],
    ai_client=None,
    glossary_text: str = "",
    batch_size: int = 40,
    max_chars_per_line: int = 42,
    warning_wps: float = 3.5,
    hard_wps: float = 4.0,
    min_duration_ms: int = 1200,
    timeout: int = 60,
    max_retries: int = 1,
    revise_batches: bool = False,
    progress_callback=None,
) -> Tuple[List[SRTEntry], List[List[int]], Dict]:
    """Return optimized English entries, source mappings, and metrics."""
    if len(cn_entries) != len(en_entries):
        raise ValueError("Chinese and English entry counts must match before reflow")
    if not en_entries:
        return [], [], {"total_entries": 0, "warning_entries": 0, "ai_batches": 0, "fallback_batches": 0}

    output: List[SRTEntry] = []
    mappings: List[List[int]] = []
    ai_batches = 0
    ai_revision_batches = 0
    fallback_batches = 0

    total_batches = (len(en_entries) + max(1, batch_size) - 1) // max(1, batch_size)
    for batch_number, start in enumerate(range(0, len(en_entries), max(1, batch_size)), start=1):
        end = min(start + max(1, batch_size), len(en_entries))
        batch_cn = cn_entries[start:end]
        batch_en = en_entries[start:end]
        groups = None
        if progress_callback:
            progress_callback(batch_number, total_batches, "开始 AI 可读性优化")
        if ai_client is not None and getattr(ai_client, "api_key", ""):
            system, user = _build_prompt(
                batch_cn,
                batch_en,
                glossary_text,
                max_chars_per_line,
                warning_wps,
                hard_wps,
            )
            try:
                groups = _parse_ai_groups(
                    ai_client.call_chat(
                        system,
                        user,
                        temperature=0.15,
                        timeout=timeout,
                        max_retries=max_retries,
                    ),
                    len(batch_en),
                )
                if groups:
                    ai_batches += 1
                    violations = _group_violations(groups, batch_en, max_chars_per_line, hard_wps)
                    if violations and revise_batches:
                        revision_system, revision_user = _build_prompt(
                            batch_cn,
                            batch_en,
                            glossary_text,
                            max_chars_per_line,
                            warning_wps,
                            hard_wps,
                            revision_note="\n".join(f"- {item}" for item in violations),
                        )
                        revised = _parse_ai_groups(
                            ai_client.call_chat(
                                revision_system,
                                revision_user,
                                temperature=0.1,
                                timeout=timeout,
                                max_retries=max_retries,
                            ),
                            len(batch_en),
                        )
                        if revised:
                            revised_violations = _group_violations(
                                revised, batch_en, max_chars_per_line, hard_wps
                            )
                            if len(revised_violations) <= len(violations):
                                groups = revised
                            ai_revision_batches += 1
            except Exception:
                groups = None
        if not groups:
            fallback_batches += 1
            if progress_callback:
                progress_callback(batch_number, total_batches, "AI 未响应，使用本地规则合并")
            groups = [
                {"source_positions": [position + 1 for position in positions],
                 "text": _clean_text(" ".join(batch_en[position].text for position in positions))}
                for positions in _group_by_rules(batch_en)
            ]

        if progress_callback:
            progress_callback(batch_number, total_batches, "完成")

        for group in groups:
            absolute_positions = [start + position - 1 for position in group["source_positions"]]
            absolute_group = {"source_positions": [position + 1 for position in absolute_positions], "text": group["text"]}
            entry = _entry_from_group(absolute_group, cn_entries, en_entries, len(output) + 1)
            entry.text = _wrap_text(entry.text, max_chars_per_line)
            output.append(entry)
            mappings.append(absolute_positions)

    metrics = []
    warning_entries = 0
    for entry, source_positions in zip(output, mappings):
        wps = reading_speed(entry.text, entry.duration_ms)
        flags = []
        if entry.duration_ms < min_duration_ms:
            flags.append("short_duration")
        if wps > warning_wps:
            flags.append("fast_reading")
        if wps > hard_wps:
            flags.append("over_hard_limit")
        if flags:
            warning_entries += 1
        metrics.append({
            "index": entry.index,
            "source_positions": [position + 1 for position in source_positions],
            "duration_seconds": round(entry.duration_ms / 1000.0, 3),
            "word_count": word_count(entry.text),
            "words_per_second": round(wps, 2),
            "flags": flags,
        })

    return output, mappings, {
        "total_entries": len(output),
        "source_entries": len(en_entries),
        "merged_entries": max(0, len(en_entries) - len(output)),
        "warning_entries": warning_entries,
        "warning_wps": warning_wps,
        "hard_wps": hard_wps,
        "ai_batches": ai_batches,
        "ai_revision_batches": ai_revision_batches,
        "fallback_batches": fallback_batches,
        "entries": metrics,
    }


def build_grouped_source_entries(entries: List[SRTEntry], mappings: List[List[int]]) -> List[SRTEntry]:
    """Build Chinese entries with the same grouping as optimized English."""
    grouped = []
    for index, positions in enumerate(mappings, start=1):
        first = entries[positions[0]]
        last = entries[positions[-1]]
        grouped.append(SRTEntry(
            index=index,
            start_time=first.start_time,
            end_time=last.end_time,
            text=_clean_text(" ".join(entries[position].text for position in positions)),
        ))
    return grouped


def compare_subtitle_files(system_entries: List[SRTEntry], manual_entries: List[SRTEntry]) -> Dict:
    """Compare two SRT versions by timeline overlap for offline review."""
    records = []
    for manual in manual_entries:
        manual_start = parse_time(manual.start_time)
        manual_end = parse_time(manual.end_time)
        overlaps = []
        for system in system_entries:
            system_start = parse_time(system.start_time)
            system_end = parse_time(system.end_time)
            if system_start < manual_end and system_end > manual_start:
                overlaps.append(system)
        records.append({
            "manual_index": manual.index,
            "manual_text": manual.text,
            "manual_word_count": word_count(manual.text),
            "manual_words_per_second": round(reading_speed(manual.text, manual.duration_ms), 2),
            "system_indices": [entry.index for entry in overlaps],
            "system_text": " ".join(entry.text for entry in overlaps),
            "system_word_count": word_count(" ".join(entry.text for entry in overlaps)),
        })
    return {
        "manual_entries": len(manual_entries),
        "system_entries": len(system_entries),
        "merged_entry_reduction": len(system_entries) - len(manual_entries),
        "records": records,
    }


def build_comparison_markdown(report: Dict) -> str:
    lines = [
        "# 英文字幕版本对比报告",
        "",
        f"系统条目：{report['system_entries']}",
        f"手改条目：{report['manual_entries']}",
        f"条目减少：{report['merged_entry_reduction']}",
        "",
        "| 手改序号 | 对应系统序号 | 手改英文 | 手改词速 |",
        "| --- | --- | --- | --- |",
    ]
    for record in report["records"]:
        text = record["manual_text"].replace("|", "\\|").replace("\n", "<br>")
        lines.append(
            f"| {record['manual_index']} | {', '.join(map(str, record['system_indices']))} | "
            f"{text} | {record['manual_words_per_second']} wps |"
        )
    return "\n".join(lines) + "\n"
