#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI翻译模块（Step 2）

提供AI接口调用、翻译批处理、术语表加载和system prompt构建功能。
"""

import os
import re

from .srt_parser import SRTEntry, build_srt


def build_system_prompt(glossary_text: str, prompts: dict = None) -> str:
    """
    构建翻译用的system prompt。

    参数:
        glossary_text: 术语表文本（已格式化）
        prompts: prompt模板字典（可选，若提供则使用模板构建）

    返回:
        str: 完整的system prompt
    """
    if prompts and "translation" in prompts:
        prompt = prompts["translation"]["system"]
    else:
        prompt = (
            "你是一个专业的制造业MES系统视频字幕翻译专家。\n"
            "\n"
            "翻译要求：\n"
            "1. 准确翻译MES系统相关专业术语\n"
            "2. 保持口语化解说风格，自然流畅\n"
            "3. 翻译要简洁，适合字幕显示（每条字幕尽量简短）\n"
            "4. 保持前后文一致性\n"
        )

    if glossary_text:
        glossary_header = ""
        if prompts and "glossary_header" in prompts:
            glossary_header = prompts["glossary_header"]
        else:
            glossary_header = "以下是MES系统专业术语对照表，请严格按照此表翻译："

        prompt += (
            "\n"
            f"{glossary_header}\n"
            f"{glossary_text}\n"
        )

    user_instruction = ""
    if prompts and "translation" in prompts and "user" in prompts["translation"]:
        user_instruction = prompts["translation"]["user"]
    else:
        user_instruction = "请将以下中文字幕翻译为英文，保持SRT格式，只输出翻译结果，不要添加任何解释。"

    prompt += f"\n{user_instruction}"

    return prompt


def parse_translated_srt(srt_text: str) -> list:
    """
    解析AI返回的翻译结果SRT文本，提取翻译后的文本行。

    参数:
        srt_text: AI返回的SRT格式文本

    返回:
        list[str]: 翻译后的文本列表（按序号顺序）
    """
    srt_text = srt_text.replace("\r\n", "\n").replace("\r", "\n")

    blocks = re.split(r"\n\s*\n", srt_text.strip())
    texts = []

    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 2:
            continue

        text_start = 2
        if text_start < len(lines):
            text = "\n".join(lines[text_start:])
            texts.append(text)

    return texts


def load_glossary_from_md(md_path: str) -> str:
    """
    从Markdown文件中读取MES术语对照表。

    参数:
        md_path: Markdown文件路径

    返回:
        str: 格式化的术语表字符串，用于注入system prompt
    """
    if not os.path.exists(md_path):
        return None

    try:
        with open(md_path, "r", encoding="utf-8") as f:
            content = f.read()

        terms = []
        for line in content.split("\n"):
            line = line.strip()
            if not line.startswith("|"):
                continue
            if "---" in line:
                continue

            cells = [cell.strip() for cell in line.split("|")]
            cells = [c for c in cells if c]

            if len(cells) < 2:
                continue

            if "中文术语" in cells and (
                "英文翻译" in cells or "推荐英文" in cells
            ):
                continue

            cn_term = None
            en_term = None

            for i, cell in enumerate(cells):
                if cell in ["序号", "中文术语", "英文翻译", "缩写/别名", "所属模块", "备注说明"]:
                    continue
                if cn_term is None and any("\u4e00" <= c <= "\u9fff" for c in cell):
                    cn_term = cell
                elif en_term is None and any(c.isalpha() for c in cell):
                    en_term = cell

            if cn_term is None and len(cells) >= 3:
                cn_term = cells[1] if len(cells) > 1 else None
                en_term = cells[2] if len(cells) > 2 else None

            if cn_term and en_term:
                cn_str = str(cn_term).strip()
                en_str = str(en_term).strip()
                if cn_str not in ["中文术语", "", "-"] and en_str not in ["英文翻译", "", "-"]:
                    if any("\u4e00" <= c <= "\u9fff" for c in cn_str):
                        terms.append(f"  {cn_str} → {en_str}")

        if not terms:
            return None

        glossary_text = "\n".join(terms)
        print(f"[信息] 已从Markdown加载 {len(terms)} 条术语")
        return glossary_text

    except Exception as e:
        print(f"[警告] 读取Markdown术语表失败: {e}")
        return None


def load_glossary(path: str) -> str:
    """Load the project-managed Markdown glossary for prompt injection."""
    if not os.path.exists(path):
        print(f"[警告] 术语表文件不存在: {path}")
        return ""

    if path.lower().endswith(".md"):
        result = load_glossary_from_md(path)
        if result:
            return result
        print("[警告] 无法从Markdown解析术语表")
        return ""

    print("[警告] 术语表必须为 Markdown 文件")
    return ""


def translate_srt_entries(entries: list, ai_client, glossary_text: str = "",
                          batch_size: int = 25, prompts: dict = None,
                          temperature: float = 0.3) -> list:
    """
    批量翻译SRTEntry列表。

    参数:
        entries: SRTEntry字幕条目列表
        ai_client: AI客户端实例
        glossary_text: 术语表文本
        batch_size: 每批字幕条数
        prompts: prompt模板字典
        temperature: 温度参数

    返回:
        list[SRTEntry]: 翻译后的字幕条目列表
    """
    system_prompt = build_system_prompt(glossary_text, prompts)

    total = len(entries)
    translated_entries = []
    failed_batches = []

    num_batches = (total + batch_size - 1) // batch_size

    print(f"[信息] 开始翻译，共 {num_batches} 批，每批最多 {batch_size} 条")
    print(f"[信息] 使用模型: {ai_client.model}")
    print(f"[信息] API地址: {ai_client.api_base}")
    print()

    for batch_idx in range(num_batches):
        start = batch_idx * batch_size
        end = min(start + batch_size, total)
        batch_entries = entries[start:end]

        context_before = []
        context_after = []

        if batch_idx > 0:
            prev_start = max(0, start - 2)
            context_before = entries[prev_start:start]

        if batch_idx < num_batches - 1:
            next_end = min(total, end + 2)
            context_after = entries[end:next_end]

        all_for_translation = context_before + batch_entries + context_after
        srt_content = build_srt(all_for_translation)

        context_before_count = len(context_before)

        progress = (start / total) * 100
        print(
            f"[进度] {progress:5.1f}% | "
            f"正在翻译第 {start + 1}-{end} 条 "
            f"(批次 {batch_idx + 1}/{num_batches})...",
            end="",
            flush=True,
        )

        try:
            translated_srt = ai_client.call_chat(
                system_prompt=system_prompt,
                user_prompt=srt_content,
                temperature=temperature,
            )

            all_translated_texts = parse_translated_srt(translated_srt)

            batch_translated_texts = all_translated_texts[
                context_before_count:context_before_count + len(batch_entries)
            ]

            if len(batch_translated_texts) != len(batch_entries):
                print(
                    f"\n  [警告] 翻译结果条数不匹配 "
                    f"(期望 {len(batch_entries)} 条，得到 {len(batch_translated_texts)} 条)"
                )
                if len(batch_translated_texts) > len(batch_entries):
                    batch_translated_texts = batch_translated_texts[:len(batch_entries)]
                else:
                    while len(batch_translated_texts) < len(batch_entries):
                        batch_translated_texts.append("")

            for i, entry in enumerate(batch_entries):
                translated_text = (
                    batch_translated_texts[i]
                    if i < len(batch_translated_texts) and batch_translated_texts[i]
                    else entry.text
                )
                translated_entries.append(SRTEntry(
                    index=entry.index,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    text=translated_text,
                ))

            print(" 完成")

        except RuntimeError as e:
            print(f"\n  [错误] {e}")
            failed_batches.append({
                "batch": batch_idx + 1,
                "range": f"{start + 1}-{end}",
                "error": str(e),
            })
            translated_entries.extend(batch_entries)

    print()

    if failed_batches:
        print(f"[警告] 共有 {len(failed_batches)} 批翻译失败，已保留原文：")
        for fb in failed_batches:
            print(f"  - 批次 {fb['batch']} (第 {fb['range']} 条): {fb['error']}")

    return translated_entries
