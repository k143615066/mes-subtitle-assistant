#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
SRT 解析与生成模块

提供SRT字幕文件的解析、生成功能，以及SRTEntry数据类和时间解析辅助函数。
"""

import re
from dataclasses import dataclass
from datetime import datetime


@dataclass
class SRTEntry:
    """SRT字幕条目数据类"""
    index: int
    start_time: str
    end_time: str
    text: str

    @property
    def duration_ms(self) -> int:
        """计算字幕持续时间（毫秒）"""
        start = parse_time(self.start_time)
        end = parse_time(self.end_time)
        delta = end - start
        return int(delta.total_seconds() * 1000)

    @property
    def char_count(self) -> int:
        """计算字幕文本字符数"""
        return len(self.text.replace("\n", ""))

    def to_dict(self) -> dict:
        """转换为字典格式（兼容旧接口）"""
        return {
            "index": self.index,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "text": self.text,
        }

    @classmethod
    def from_dict(cls, d: dict) -> "SRTEntry":
        """从字典创建SRTEntry"""
        return cls(
            index=d["index"],
            start_time=d["start_time"],
            end_time=d["end_time"],
            text=d["text"],
        )


def parse_time(time_str: str) -> datetime:
    """
    解析SRT时间字符串为datetime对象。

    支持格式: HH:MM:SS,mmm 或 HH:MM:SS.mmm

    参数:
        time_str: SRT时间字符串

    返回:
        datetime: 解析后的datetime对象
    """
    time_str = time_str.strip().replace(",", ".")
    return datetime.strptime(time_str, "%H:%M:%S.%f")


def format_time(dt: datetime) -> str:
    """
    将datetime对象格式化为SRT时间字符串。

    输出格式: HH:MM:SS,mmm

    参数:
        dt: datetime对象

    返回:
        str: SRT格式的时间字符串
    """
    return dt.strftime("%H:%M:%S,%f")[:-3]


def parse_srt(file_path: str) -> list:
    """
    解析SRT字幕文件，提取所有字幕条目。

    参数:
        file_path: SRT文件路径

    返回:
        list[SRTEntry]: 字幕条目列表
    """
    with open(file_path, "r", encoding="utf-8-sig") as f:
        content = f.read()

    content = content.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", content.strip())

    entries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 2:
            continue

        index_line = lines[0].strip()
        try:
            index = int(index_line)
        except ValueError:
            match = re.match(r"(\d+)", index_line)
            if match:
                index = int(match.group(1))
            else:
                continue

        time_line = lines[1].strip()
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})",
            time_line,
        )
        if not time_match:
            continue

        start_time = time_match.group(1)
        end_time = time_match.group(2)

        text_lines = lines[2:]
        text = "\n".join(text_lines)

        entries.append(SRTEntry(
            index=index,
            start_time=start_time,
            end_time=end_time,
            text=text,
        ))

    return entries


def parse_srt_from_text(srt_text: str) -> list:
    srt_text = srt_text.replace("\r\n", "\n").replace("\r", "\n")
    blocks = re.split(r"\n\s*\n", srt_text.strip())

    entries = []
    for block in blocks:
        block = block.strip()
        if not block:
            continue

        lines = block.split("\n")
        if len(lines) < 2:
            continue

        index_line = lines[0].strip()
        try:
            index = int(index_line)
        except ValueError:
            match = re.match(r"(\d+)", index_line)
            if match:
                index = int(match.group(1))
            else:
                continue

        time_line = lines[1].strip()
        time_match = re.match(
            r"(\d{2}:\d{2}:\d{2}[,.]\d{3})\s*-->\s*(\d{2}:\d{2}:\d{2}[,.]\d{3})",
            time_line,
        )
        if not time_match:
            continue

        start_time = time_match.group(1)
        end_time = time_match.group(2)

        text_lines = lines[2:]
        text = "\n".join(text_lines)

        entries.append(SRTEntry(
            index=index,
            start_time=start_time,
            end_time=end_time,
            text=text,
        ))

    return entries


def build_srt(entries: list) -> str:
    """
    根据字幕条目列表生成SRT格式文本。

    支持SRTEntry对象和字典格式。

    参数:
        entries: 字幕条目列表

    返回:
        str: SRT格式文本
    """
    blocks = []
    for entry in entries:
        if isinstance(entry, SRTEntry):
            index = entry.index
            start_time = entry.start_time
            end_time = entry.end_time
            text = entry.text
        else:
            index = entry["index"]
            start_time = entry["start_time"]
            end_time = entry["end_time"]
            text = entry["text"]

        block = f"{index}\n"
        block += f"{start_time} --> {end_time}\n"
        block += f"{text}\n"
        blocks.append(block)

    return "\n".join(blocks)
