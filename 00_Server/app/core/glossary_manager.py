"""Read and update the project-managed MES glossary Markdown file."""

import os
import re
import tempfile
import base64
from typing import Dict, List


GLOSSARY_HEADERS = ["序号", "中文术语", "推荐英文", "缩写/别名", "所属模块", "备注说明"]


def _clean_cell(value) -> str:
    return str(value or "").replace("\n", " ").replace("\r", " ").replace("|", "/").strip()


def _split_row(line: str) -> List[str]:
    return [cell.strip() for cell in line.strip().strip("|").split("|")]


def _is_separator(line: str) -> bool:
    cells = _split_row(line)
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "-") for cell in cells)


def _make_id(category: str, term: str) -> str:
    value = f"{category}\x00{term}".encode("utf-8")
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


class GlossaryManager:
    """Preserve glossary prose while editing only Markdown terminology tables."""

    def __init__(self, path: str):
        self.path = path

    def _read_lines(self) -> List[str]:
        with open(self.path, "r", encoding="utf-8") as handle:
            return handle.read().splitlines()

    def _parse(self) -> List[Dict]:
        lines = self._read_lines()
        tables = []
        category = "未分类"
        position = 0
        while position < len(lines):
            line = lines[position].strip()
            if line.startswith("## "):
                category = line[3:].strip()
            if not line.startswith("|"):
                position += 1
                continue

            header = _split_row(line)
            if "中文术语" not in header or "推荐英文" not in header:
                position += 1
                continue
            if position + 1 >= len(lines) or not _is_separator(lines[position + 1]):
                position += 1
                continue

            end = position + 2
            rows = []
            while end < len(lines) and lines[end].strip().startswith("|"):
                if not _is_separator(lines[end]):
                    cells = _split_row(lines[end])
                    row = {name: cells[index] if index < len(cells) else "" for index, name in enumerate(header)}
                    term = row.get("中文术语", "").strip()
                    translation = row.get("推荐英文", "").strip()
                    if term and translation:
                        rows.append({
                            "id": _make_id(category, term),
                            "category": category,
                            "term": term,
                            "translation": translation,
                            "alias": row.get("缩写/别名", ""),
                            "module": row.get("所属模块", ""),
                            "notes": row.get("备注说明", ""),
                        })
                end += 1
            tables.append({
                "category": category,
                "start": position,
                "end": end,
                "header": header,
                "rows": rows,
            })
            position = end
        return tables

    def list_terms(self) -> Dict:
        tables = self._parse()
        terms = [term for table in tables for term in table["rows"]]
        return {
            "terms": terms,
            "categories": [table["category"] for table in tables],
            "count": len(terms),
        }

    def _write(self, tables: List[Dict]) -> None:
        original = self._read_lines()
        replacements = {table["start"]: table for table in tables}
        result = []
        position = 0
        while position < len(original):
            table = replacements.get(position)
            if not table:
                result.append(original[position])
                position += 1
                continue

            header = table["header"]
            result.append("| " + " | ".join(header) + " |")
            result.append("| " + " | ".join(["---"] * len(header)) + " |")
            for index, term in enumerate(table["rows"], start=1):
                values = {
                    "序号": str(index),
                    "中文术语": _clean_cell(term["term"]),
                    "推荐英文": _clean_cell(term["translation"]),
                    "缩写/别名": _clean_cell(term.get("alias")),
                    "所属模块": _clean_cell(term.get("module")),
                    "备注说明": _clean_cell(term.get("notes")),
                }
                result.append("| " + " | ".join(values.get(name, "") for name in header) + " |")
            position = table["end"]

        directory = os.path.dirname(self.path)
        descriptor, temp_path = tempfile.mkstemp(prefix="glossary_", suffix=".md", dir=directory, text=True)
        try:
            with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as handle:
                handle.write("\n".join(result) + "\n")
            os.replace(temp_path, self.path)
        except Exception:
            if os.path.exists(temp_path):
                os.unlink(temp_path)
            raise

    def save_term(self, payload: Dict) -> Dict:
        category = _clean_cell(payload.get("category"))
        term = _clean_cell(payload.get("term"))
        translation = _clean_cell(payload.get("translation"))
        if not category or not term or not translation:
            raise ValueError("分类、中文术语和推荐英文不能为空")

        tables = self._parse()
        target = next((table for table in tables if table["category"] == category), None)
        if not target:
            raise ValueError("请选择已有术语分类")

        original_id = payload.get("id", "")
        match = None
        for table in tables:
            for item in table["rows"]:
                if item["id"] == original_id:
                    match = (table, item)
                    break
            if match:
                break

        if match:
            source_table, source_item = match
            if source_item["term"] != term and any(item["term"] == term for item in target["rows"]):
                raise ValueError("该分类中已有相同中文术语")
            source_table["rows"].remove(source_item)
        elif any(item["term"] == term for item in target["rows"]):
            raise ValueError("该分类中已有相同中文术语")

        saved = {
            "id": _make_id(category, term),
            "category": category,
            "term": term,
            "translation": translation,
            "alias": _clean_cell(payload.get("alias")),
            "module": _clean_cell(payload.get("module")),
            "notes": _clean_cell(payload.get("notes")),
        }
        target["rows"].append(saved)
        self._write(tables)
        return saved

    def delete_term(self, term_id: str) -> None:
        tables = self._parse()
        for table in tables:
            for item in table["rows"]:
                if item["id"] == term_id:
                    table["rows"].remove(item)
                    self._write(tables)
                    return
        raise ValueError("未找到该术语")
