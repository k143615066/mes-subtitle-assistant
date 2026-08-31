#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
中文润色模块

提供中文字幕润色、MES术语优化功能，保持原始时间轴不变。
"""

import os
import re
import time
import requests

from .srt_parser import SRTEntry, build_srt


def build_polish_prompt(glossary_text: str) -> str:
    """
    构建中文润色用的system prompt。

    参数:
        glossary_text: 术语表文本

    返回:
        str: 完整的system prompt
    """
    prompt = (
        "你是一个专业的制造业MES系统视频字幕润色专家。\n"
        "\n"
        "润色要求：\n"
        "1. 修正错别字、听写遗漏、病句和明显不准确的表述，使内容准确。\n"
        "2. 删除不承载事实信息的口头填充词、重复表达和无意义连接词，"
        "例如‘嗯、啊、呃、这个、那个、就是、然后’；删除会影响语气、逻辑或营销重点时必须保留。\n"
        "3. 修正MES系统相关专业术语，确保术语准确。\n"
        "4. 保持原意、事实、数字、产品名称和营销重点，不得编造或遗漏关键信息。\n"
        "5. 保持自然的中文视频解说风格，确保上下文逻辑连贯。\n"
        "6. 每条字幕只改写文本，不得合并、拆分、增删字幕条目，也不得修改时间轴。\n"
        "\n"
    )

    if glossary_text:
        prompt += (
            "以下是MES系统专业术语对照表，请确保术语使用正确：\n"
            f"{glossary_text}\n"
            "\n"
        )

    prompt += (
        "请润色以下中文字幕，保持SRT格式，只输出润色结果，不要添加任何解释。\n"
        "注意：请保持原始时间轴完全不变！\n"
    )

    return prompt


def polish_batch(api_key: str, api_base: str, model: str,
                 system_prompt: str, srt_content: str,
                 retry: int = 3, temperature: float = 0.3,
                 timeout: int = 120) -> str:
    """
    调用AI接口润色字幕。

    参数:
        api_key: API密钥
        api_base: API基础URL
        model: 模型名称
        system_prompt: system prompt
        srt_content: 待润色的SRT文本
        retry: 最大重试次数
        temperature: 温度参数
        timeout: 请求超时时间（秒）

    返回:
        str: 润色后的SRT文本
    """
    url = f"{api_base.rstrip('/')}/chat/completions"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}",
    }
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": srt_content},
        ],
        "temperature": temperature,
    }

    last_error = None
    for attempt in range(1, retry + 1):
        try:
            resp = requests.post(url, headers=headers, json=payload, timeout=timeout)
            resp.raise_for_status()
            result = resp.json()

            polished = result["choices"][0]["message"]["content"]
            return polished.strip()

        except requests.exceptions.Timeout:
            last_error = "请求超时"
            print(f"  [重试 {attempt}/{retry}] 请求超时，正在重试...")
        except requests.exceptions.HTTPError as e:
            last_error = f"HTTP错误: {e.response.status_code} - {e.response.text[:200]}"
            print(f"  [重试 {attempt}/{retry}] {last_error}")
        except requests.exceptions.ConnectionError:
            last_error = "连接失败"
            print(f"  [重试 {attempt}/{retry}] 连接失败，正在重试...")
        except (KeyError, IndexError) as e:
            last_error = f"响应解析失败: {e}"
            print(f"  [重试 {attempt}/{retry}] {last_error}")
        except Exception as e:
            last_error = f"未知错误: {e}"
            print(f"  [重试 {attempt}/{retry}] {last_error}")

        if attempt < retry:
            wait_time = min(2 ** attempt, 30)
            time.sleep(wait_time)

    raise RuntimeError(f"润色失败（已重试{retry}次）: {last_error}")


def parse_polished_srt(srt_text: str) -> list:
    """
    解析AI返回的润色结果SRT文本，提取润色后的文本行。

    参数:
        srt_text: AI返回的SRT格式文本

    返回:
        list[str]: 润色后的文本列表（按序号顺序）
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


def polish_srt_entries(entries: list, api_key: str, api_base: str,
                       model: str, glossary_text: str = "",
                       batch_size: int = 20, temperature: float = 0.3) -> list:
    """
    批量润色SRTEntry列表，保持原始时间轴不变。

    参数:
        entries: SRTEntry字幕条目列表
        api_key: API密钥
        api_base: API基础URL
        model: 模型名称
        glossary_text: 术语表文本
        batch_size: 每批字幕条数
        temperature: 温度参数

    返回:
        list[SRTEntry]: 润色后的字幕条目列表（时间轴保持不变）
    """
    system_prompt = build_polish_prompt(glossary_text)

    total = len(entries)
    polished_entries = []
    failed_batches = []

    num_batches = (total + batch_size - 1) // batch_size

    print(f"[信息] 开始中文润色，共 {num_batches} 批，每批最多 {batch_size} 条")
    print(f"[信息] 使用模型: {model}")
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

        all_for_polish = context_before + batch_entries + context_after
        srt_content = build_srt(all_for_polish)

        context_before_count = len(context_before)

        progress = (start / total) * 100
        print(
            f"[进度] {progress:5.1f}% | "
            f"正在润色第 {start + 1}-{end} 条 "
            f"(批次 {batch_idx + 1}/{num_batches})...",
            end="",
            flush=True,
        )

        try:
            polished_srt = polish_batch(
                api_key=api_key,
                api_base=api_base,
                model=model,
                system_prompt=system_prompt,
                srt_content=srt_content,
                retry=3,
                temperature=temperature,
            )

            all_polished_texts = parse_polished_srt(polished_srt)

            batch_polished_texts = all_polished_texts[
                context_before_count:context_before_count + len(batch_entries)
            ]

            if len(batch_polished_texts) != len(batch_entries):
                print(
                    f"\n  [警告] 润色结果条数不匹配 "
                    f"(期望 {len(batch_entries)} 条，得到 {len(batch_polished_texts)} 条)"
                )
                if len(batch_polished_texts) > len(batch_entries):
                    batch_polished_texts = batch_polished_texts[:len(batch_entries)]
                else:
                    while len(batch_polished_texts) < len(batch_entries):
                        batch_polished_texts.append("")

            for i, entry in enumerate(batch_entries):
                polished_text = (
                    batch_polished_texts[i]
                    if i < len(batch_polished_texts) and batch_polished_texts[i]
                    else entry.text
                )
                polished_entries.append(SRTEntry(
                    index=entry.index,
                    start_time=entry.start_time,
                    end_time=entry.end_time,
                    text=polished_text,
                ))

            print(" 完成")

        except RuntimeError as e:
            print(f"\n  [错误] {e}")
            failed_batches.append({
                "batch": batch_idx + 1,
                "range": f"{start + 1}-{end}",
                "error": str(e),
            })
            polished_entries.extend(batch_entries)

    print()

    if failed_batches:
        print(f"[警告] 共有 {len(failed_batches)} 批润色失败，已保留原文：")
        for fb in failed_batches:
            print(f"  - 批次 {fb['batch']} (第 {fb['range']} 条): {fb['error']}")

    return polished_entries
