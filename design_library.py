#!/usr/bin/env python3
"""本地设计稿工作台工具。"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import re
import shutil
import subprocess
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple


PACKAGE_TYPES = [
    "彩盒",
    "标签",
    "规格标签",
    "刀模图",
    "吊卡盒",
    "吸塑彩贴",
    "外箱",
    "说明卡",
    "信封包装",
]

PRODUCT_CATEGORIES = [
    "涂附",
    "砂轮",
    "钢丝刷",
    "金刚石工具",
    "其他",
]

CSV_FIELDS = [
    "original_path",
    "original_name",
    "new_name",
    "产品分类",
    "产品系列",
    "产品编码",
    "核心规格",
    "包装类型",
    "日期",
    "版本",
    "渠道",
    "状态",
    "设计图号",
    "客户",
    "备注",
    "file_hash",
    "duplicate_group",
    "thumbnail_path",
]

PACKAGE_HINTS = [
    ("规格标签", "规格标签"),
    ("刀模图", "刀模图"),
    ("信封包装", "信封包装"),
    ("吸塑彩贴", "吸塑彩贴"),
    ("外箱", "外箱"),
    ("吊卡", "吊卡盒"),
    ("吊卡装", "吊卡盒"),
    ("标签", "标签"),
    ("彩盒", "彩盒"),
    ("包装盒", "彩盒"),
    ("包装", "彩盒"),
]

STATUS_HINTS = [
    ("done", "DONE"),
    ("历史", "历史"),
]

CHANNEL_HINTS = [
    ("独立站", "独立站"),
    ("商超", "商超"),
    ("亚马逊", "亚马逊"),
]

PRODUCT_CODE_RE = re.compile(r"(?<![A-Z0-9])([A-Z]{1,4}\d{1,4}[A-Z]{0,3})(?![A-Z0-9])")
SPEC_PATTERNS = [
    re.compile(r"\d{2,4}mmx\d{2,4}mmx\d{2,4}mm", re.IGNORECASE),
    re.compile(r"\d{2,4}[Xx]\d{2,4}(?:[_&-]\d{2,4}[Xx]\d{2,4})?"),
    re.compile(r"\d{2,4}[Xx]\d{1,4}(?:m|mm|pcs)?", re.IGNORECASE),
    re.compile(r"\d{2,4}mm-\d{1,3}H", re.IGNORECASE),
    re.compile(r"\d{2,4}-\d{1,3}H", re.IGNORECASE),
    re.compile(r"\d{2,4}mmx\d{1,4}m", re.IGNORECASE),
    re.compile(r"\d{2,4}mm", re.IGNORECASE),
    re.compile(r"\d{1,3}H", re.IGNORECASE),
    re.compile(r"\d{1,4}PCS", re.IGNORECASE),
]
DATE_RE = re.compile(r"(20\d{6}|2\d{5})")
VERSION_RE = re.compile(r"(?<![A-Z0-9])(V\d+)(?![A-Z0-9])", re.IGNORECASE)
DESIGN_NO_RE = re.compile(r"(FPD\d{5,}|QCK\d{4,})", re.IGNORECASE)
DEFAULT_CATEGORY_CONFIG = {
    "default_category": "涂附",
    "force_all_category": "涂附",
    "source_overrides": {},
    "keyword_rules": [
        {"keyword": "砂轮", "category": "砂轮"},
        {"keyword": "切割片", "category": "砂轮"},
        {"keyword": "百叶片", "category": "砂轮"},
        {"keyword": "flap disc", "category": "砂轮"},
        {"keyword": "grinding wheel", "category": "砂轮"},
        {"keyword": "钢丝刷", "category": "钢丝刷"},
        {"keyword": "cup brush", "category": "钢丝刷"},
        {"keyword": "wheel brush", "category": "钢丝刷"},
        {"keyword": "wire brush", "category": "钢丝刷"},
        {"keyword": "金刚石", "category": "金刚石工具"},
        {"keyword": "diamond", "category": "金刚石工具"},
        {"keyword": "锯片", "category": "金刚石工具"},
        {"keyword": "磨片", "category": "金刚石工具"},
        {"keyword": "取芯钻", "category": "金刚石工具"},
    ],
}
DEFAULT_SERIES_CONFIG = {
    "series_overrides": {},
    "keyword_rules": [
        {"keyword": "V字卷", "series": "V字卷"},
        {"keyword": "手撕砂布卷", "series": "手撕砂布卷"},
        {"keyword": "STRIP", "series": "长条"},
        {"keyword": "手砂板", "series": "手砂板"},
        {"keyword": "快换碟", "series": "快换碟"},
        {"keyword": "QUICK-CHANG", "series": "快换碟"},
        {"keyword": "QUICK CHANG", "series": "快换碟"},
        {"keyword": "quick change", "series": "快换碟"},
        {"keyword": "拉绒片", "series": "拉绒片"},
        {"keyword": "海绵块", "series": "海绵块"},
        {"keyword": "Sponge Pad", "series": "海绵垫"},
        {"keyword": "Mesh Pad", "series": "网格垫"},
        {"keyword": "Spotfix", "series": "点修"},
        {"keyword": "spotcut", "series": "点修"},
        {"keyword": "点修", "series": "点修"},
        {"keyword": "钢纸磨片", "series": "钢纸磨片"},
        {"keyword": "规格标签", "series": "规格标签"},
        {"keyword": "标签", "series": "规格标签"},
        {"keyword": "外箱", "series": "外箱"},
        {"keyword": "吊卡", "series": "吊卡"},
        {"keyword": "FASTPLUS", "series": "FASTPLUS"},
        {"keyword": "SAMPLE BAG", "series": "样品包装"},
        {"keyword": "SAMPLE-PACK", "series": "样品包装"},
        {"keyword": "样品包装", "series": "样品包装"},
    ],
}


@dataclass
class Record:
    original_path: str
    original_name: str
    new_name: str
    product_category: str
    product_series: str
    product_code: str
    spec: str
    package_type: str
    date: str
    version: str
    channel: str
    status: str
    design_number: str
    customer: str
    notes: str
    file_hash: str
    duplicate_group: str
    thumbnail_path: str = ""

    def to_csv_row(self) -> Dict[str, str]:
        return {
            "original_path": self.original_path,
            "original_name": self.original_name,
            "new_name": self.new_name,
            "产品分类": self.product_category,
            "产品系列": self.product_series,
            "产品编码": self.product_code,
            "核心规格": self.spec,
            "包装类型": self.package_type,
            "日期": self.date,
            "版本": self.version,
            "渠道": self.channel,
            "状态": self.status,
            "设计图号": self.design_number,
            "客户": self.customer,
            "备注": self.notes,
            "file_hash": self.file_hash,
            "duplicate_group": self.duplicate_group,
            "thumbnail_path": self.thumbnail_path,
        }


def ensure_output_dirs(root: Path) -> None:
    for relative in [
        "data",
        "pdf/DONE",
        "pdf/进行中",
        "pdf/历史",
        "thumbnails",
        ]:
        (root / relative).mkdir(parents=True, exist_ok=True)


def reset_build_artifacts(root: Path) -> None:
    for relative in ["pdf", "thumbnails"]:
        target = root / relative
        if target.exists():
            shutil.rmtree(target)
    ensure_output_dirs(root)


def list_pdf_files(source: Path) -> List[Path]:
    return sorted(path for path in source.rglob("*.pdf") if path.is_file())


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            hasher.update(chunk)
    return hasher.hexdigest()


def clean_text(value: str) -> str:
    value = value.strip()
    value = value.replace("（", "(").replace("）", ")")
    value = re.sub(r"\s+", " ", value)
    return value


def sanitize_filename_part(value: str) -> str:
    value = clean_text(value)
    value = value.replace("/", "_").replace("\\", "_")
    value = value.replace("&", "_")
    value = re.sub(r"[?*:\"<>|]+", "", value)
    value = re.sub(r"\s+", "", value)
    value = re.sub(r"__+", "_", value)
    return value.strip("._-")


def config_path_for_script() -> Path:
    return Path(__file__).with_name("product_categories.json")


def series_config_path_for_script() -> Path:
    return Path(__file__).with_name("product_series_rules.json")


def ensure_category_config() -> Path:
    config_path = config_path_for_script()
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_CATEGORY_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return config_path


def ensure_series_config() -> Path:
    config_path = series_config_path_for_script()
    if not config_path.exists():
        config_path.write_text(
            json.dumps(DEFAULT_SERIES_CONFIG, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return config_path


def load_category_config() -> Dict[str, object]:
    config_path = ensure_category_config()
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def load_series_config() -> Dict[str, object]:
    config_path = ensure_series_config()
    with config_path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    return data


def category_rules_from_config(
    config: Dict[str, object]
) -> Tuple[str, str, Dict[str, str], List[Tuple[str, str]]]:
    default_category = str(config.get("default_category", "涂附"))
    force_all_category = str(config.get("force_all_category", "")).strip()
    source_overrides = {
        str(key): str(value)
        for key, value in dict(config.get("source_overrides", {})).items()
    }
    keyword_rules: List[Tuple[str, str]] = []
    for rule in list(config.get("keyword_rules", [])):
        if not isinstance(rule, dict):
            continue
        keyword = str(rule.get("keyword", "")).strip()
        category = str(rule.get("category", default_category)).strip()
        if keyword and category:
            keyword_rules.append((keyword, category))
    return default_category, force_all_category, source_overrides, keyword_rules


def detect_product_category(
    path_text: str,
    text: str,
    default_category: str,
    force_all_category: str,
    source_overrides: Dict[str, str],
    keyword_rules: Sequence[Tuple[str, str]],
) -> str:
    if force_all_category:
        return force_all_category
    normalized_path = path_text.replace("\\", "/")
    for prefix, category in source_overrides.items():
        cleaned_prefix = prefix.replace("\\", "/")
        if cleaned_prefix and normalized_path.startswith(cleaned_prefix):
            return category
    haystack = f"{path_text} {text}".lower()
    for keyword, category in keyword_rules:
        if keyword.lower() in haystack:
            return category
    return default_category


def detect_product_code(text: str) -> str:
    match = PRODUCT_CODE_RE.search(text.upper())
    if match:
        return match.group(1).upper()
    if "V字卷" in text:
        return "V字卷"
    if "手撕砂布卷" in text:
        return "手撕砂布卷"
    if "砂带" in text:
        return "砂带"
    if "无纺布" in text:
        return "无纺布"
    if "拉绒片" in text:
        return "拉绒片"
    if "金字塔" in text:
        return "金字塔"
    if "点修" in text:
        return "点修"
    if "快换碟" in text:
        return "快换碟"
    return "待补充"


def detect_product_series(path_text: str, text: str, product_code: str) -> str:
    series_config = load_series_config()
    text_haystack = f"{path_text} {text}".strip()
    lowered_text_haystack = text_haystack.lower()
    # Prefer coded product families when a stable code is present.
    if product_code and product_code != "待补充":
        return product_code
    # Handle a few high-value generic names before broader rules.
    if "双面海绵" in text_haystack or "4面海绵" in text_haystack or "海绵彩盒" in text_haystack:
        return "海绵块"
    if "砂纸卷彩贴" in text_haystack or "sandpaper roll sticker" in lowered_text_haystack:
        return "卷装标签"
    overrides = series_config.get("series_overrides", {})
    if isinstance(overrides, dict):
        normalized_path = path_text.replace("\\", "/")
        for prefix, series in overrides.items():
            if str(prefix).replace("\\", "/") and normalized_path.startswith(str(prefix).replace("\\", "/")):
                return str(series)
    keyword_rules = series_config.get("keyword_rules", [])
    if isinstance(keyword_rules, list):
        for rule in keyword_rules:
            if not isinstance(rule, dict):
                continue
            keyword = str(rule.get("keyword", "")).strip()
            series = str(rule.get("series", "")).strip()
            if keyword and series and keyword.lower() in lowered_text_haystack:
                return series
    for keyword in ["砂带", "无纺布", "金字塔", "缓冲垫", "长条", "卷装", "刀模图"]:
        if keyword in text_haystack:
            return keyword
    return "待补充"


def detect_spec(text: str) -> str:
    text = text.replace("'", "").replace('"', "")
    matches: List[str] = []
    for pattern in SPEC_PATTERNS:
        for match in pattern.findall(text):
            normalized = match.upper().replace(" ", "").replace("&", "_").replace("-", "-")
            if normalized not in matches:
                matches.append(normalized)
    if not matches:
        return "待补充"
    filtered: List[str] = []
    for match in matches:
        if re.fullmatch(r"\d{1,4}PCS", match):
            continue
        # Skip narrower fragments when a broader spec already exists.
        if any(match != other and match in other for other in matches):
            if re.fullmatch(r"\d{1,4}H", match) or re.fullmatch(r"\d{2,4}MM", match):
                continue
        filtered.append(match)
    if not filtered:
        filtered = [matches[0]]

    chosen: List[str] = []
    for match in filtered:
        if re.fullmatch(r"\d{2,4}(MM)?-\d{1,3}H", match):
            left, right = match.split("-", 1)
            chosen = [left, right]
            break
        chosen.append(match)
        if len(chosen) == 2:
            break

    cleaned = []
    for item in chosen:
        normalized = item.replace("MMX", "X").replace("MM", "")
        if normalized not in cleaned:
            cleaned.append(normalized)
    return "_".join(cleaned[:2]) if cleaned else "待补充"


def normalize_date(value: str) -> str:
    value = value.strip()
    if not value:
        return datetime.today().strftime("%Y%m%d")
    if re.fullmatch(r"20\d{6}", value):
        return value
    if re.fullmatch(r"2\d{5}", value):
        year = 2000 + int(value[:2])
        return f"{year:04d}{value[2:]}"
    return value


def detect_date(text: str, path: Path) -> str:
    for match in DATE_RE.findall(text):
        return normalize_date(match)
    return datetime.fromtimestamp(path.stat().st_mtime).strftime("%Y%m%d")


def detect_version(text: str) -> str:
    match = VERSION_RE.search(text)
    return match.group(1).upper() if match else "V1"


def detect_package_type(text: str) -> str:
    for keyword, mapped in PACKAGE_HINTS:
        if keyword.lower() in text.lower():
            return mapped
    if "彩卡" in text:
        return "说明卡"
    return "彩盒"


def detect_channel(path_text: str, file_text: str) -> str:
    haystack = f"{path_text} {file_text}"
    for keyword, mapped in CHANNEL_HINTS:
        if keyword in haystack:
            return mapped
    return "其他"


def detect_status(path_text: str) -> str:
    lowered = path_text.lower()
    for keyword, mapped in STATUS_HINTS:
        if keyword in lowered or keyword in path_text:
            return mapped
    return "进行中"


def detect_design_number(text: str) -> str:
    match = DESIGN_NO_RE.search(text)
    return match.group(1).upper() if match else ""


def build_notes(text: str, package_type: str) -> str:
    note_parts = []
    for marker in ["新款", "偏大", "高度不够", "宽度120mm正好", "通用", "混装", "单混", "粗粒度"]:
        if marker in text and marker not in note_parts:
            note_parts.append(marker)
    if "规格标签" in text and package_type != "规格标签":
        note_parts.append("含规格标签")
    return "；".join(note_parts)


def suggest_new_name(record: Record) -> str:
    parts = [
        sanitize_filename_part(record.product_code or "待补充"),
        sanitize_filename_part(record.spec or "待补充"),
        sanitize_filename_part(record.package_type or "待补充"),
        sanitize_filename_part(record.date or "待补充"),
        sanitize_filename_part(record.version or "V1"),
    ]
    return "-".join(part for part in parts if part) + ".pdf"


def make_duplicate_groups(hashes: Sequence[str]) -> Dict[str, str]:
    counts: Dict[str, int] = defaultdict(int)
    groups: Dict[str, str] = {}
    for file_hash in hashes:
        counts[file_hash] += 1
    group_index = 1
    for file_hash, count in counts.items():
        if count > 1:
            groups[file_hash] = f"DUP-{group_index:03d}"
            group_index += 1
    return groups


def scan_source(source: Path) -> List[Record]:
    pdf_files = list_pdf_files(source)
    hashes = [sha256_file(path) for path in pdf_files]
    duplicate_groups = make_duplicate_groups(hashes)
    config = load_category_config()
    default_category, force_all_category, source_overrides, keyword_rules = category_rules_from_config(config)
    records: List[Record] = []

    for path, file_hash in zip(pdf_files, hashes):
        original_name = path.name
        stem = clean_text(path.stem)
        path_text = str(path.relative_to(source))
        product_code = detect_product_code(f"{path_text} {stem}")
        package_type = detect_package_type(f"{path_text} {stem}")
        record = Record(
            original_path=str(path),
            original_name=original_name,
            new_name="",
            product_category=detect_product_category(
                path_text,
                stem,
                default_category,
                force_all_category,
                source_overrides,
                keyword_rules,
            ),
            product_series=detect_product_series(path_text, stem, product_code),
            product_code=product_code,
            spec=detect_spec(stem),
            package_type=package_type,
            date=detect_date(stem, path),
            version=detect_version(stem),
            channel=detect_channel(path_text, stem),
            status=detect_status(path_text),
            design_number=detect_design_number(stem),
            customer="",
            notes=build_notes(stem, package_type),
            file_hash=file_hash,
            duplicate_group=duplicate_groups.get(file_hash, ""),
        )
        record.new_name = suggest_new_name(record)
        records.append(record)
    return records


def scan_paths(source: Path, paths: Sequence[Path]) -> List[Record]:
    unique_paths = sorted({path.resolve() for path in paths if path.exists() and path.is_file()})
    hashes = [sha256_file(path) for path in unique_paths]
    duplicate_groups = make_duplicate_groups(hashes)
    config = load_category_config()
    default_category, force_all_category, source_overrides, keyword_rules = category_rules_from_config(config)
    records: List[Record] = []

    for path, file_hash in zip(unique_paths, hashes):
        original_name = path.name
        stem = clean_text(path.stem)
        path_text = str(path.relative_to(source))
        product_code = detect_product_code(f"{path_text} {stem}")
        package_type = detect_package_type(f"{path_text} {stem}")
        record = Record(
            original_path=str(path),
            original_name=original_name,
            new_name="",
            product_category=detect_product_category(
                path_text,
                stem,
                default_category,
                force_all_category,
                source_overrides,
                keyword_rules,
            ),
            product_series=detect_product_series(path_text, stem, product_code),
            product_code=product_code,
            spec=detect_spec(stem),
            package_type=package_type,
            date=detect_date(stem, path),
            version=detect_version(stem),
            channel=detect_channel(path_text, stem),
            status=detect_status(path_text),
            design_number=detect_design_number(stem),
            customer="",
            notes=build_notes(stem, package_type),
            file_hash=file_hash,
            duplicate_group=duplicate_groups.get(file_hash, ""),
        )
        record.new_name = suggest_new_name(record)
        records.append(record)
    return records


def write_csv(path: Path, rows: Iterable[Dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    row_list = list(rows)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(row_list)


def read_csv_records(path: Path) -> List[Record]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        records: List[Record] = []
        for row in reader:
            record = Record(
                original_path=row["original_path"],
                original_name=row["original_name"],
                new_name=row["new_name"],
                product_category=row.get("产品分类", "其他"),
                product_series=row.get("产品系列", ""),
                product_code=row["产品编码"],
                spec=row["核心规格"],
                package_type=row["包装类型"],
                date=row["日期"],
                version=row["版本"],
                channel=row["渠道"],
                status=row["状态"],
                design_number=row["设计图号"],
                customer=row["客户"],
                notes=row["备注"],
                file_hash=row["file_hash"],
                duplicate_group=row["duplicate_group"],
                thumbnail_path=row.get("thumbnail_path", ""),
            )
            if not record.product_series:
                record.product_series = detect_product_series(
                    record.original_path,
                    record.original_name,
                    record.product_code,
                )
            if not record.new_name:
                record.new_name = suggest_new_name(record)
            records.append(record)
    return records


def dedupe_destination_name(name: str, used_names: Dict[str, int]) -> str:
    if name not in used_names:
        used_names[name] = 1
        return name
    used_names[name] += 1
    stem, suffix = os.path.splitext(name)
    return f"{stem}-DUP{used_names[name]:02d}{suffix}"


def destination_for_status(root: Path, status: str, name: str) -> Path:
    normalized_status = status if status in {"DONE", "历史"} else "进行中"
    return root / "pdf" / normalized_status / name


def generate_thumbnail(pdf_path: Path, thumbnail_dir: Path, key: str) -> str:
    thumbnail_dir.mkdir(parents=True, exist_ok=True)
    prefix = thumbnail_dir / key
    command = [
        "pdftoppm",
        "-jpeg",
        "-f",
        "1",
        "-singlefile",
        "-scale-to",
        "420",
        str(pdf_path),
        str(prefix),
    ]
    try:
        subprocess.run(
            command,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=30,
        )
    except (subprocess.TimeoutExpired, subprocess.CalledProcessError):
        return ""
    return f"thumbnails/{key}.jpg"


def record_to_json(record: Record) -> Dict[str, str]:
    payload = record.to_csv_row()
    payload["pdf_path"] = f"pdf/{record.status if record.status in {'DONE', '历史'} else '进行中'}/{record.new_name}"
    return payload


def write_json(path: Path, records: Sequence[Record]) -> None:
    payload = [record_to_json(record) for record in records]
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2)


def build_html(records: Sequence[Record]) -> str:
    unique_series = sorted(
        {item.product_series for item in records if item.product_series and item.product_series != "待补充"}
    )
    stats = {
        "总文件数": len(records),
        "品类数": len({item.product_category for item in records}),
        "系列数": len(unique_series),
        "DONE": sum(1 for item in records if item.status == "DONE"),
        "进行中": sum(1 for item in records if item.status == "进行中"),
        "历史": sum(1 for item in records if item.status == "历史"),
        "重复副本": sum(1 for item in records if item.duplicate_group),
    }
    stat_html = "\n".join(
        f'<div class="stat"><div class="stat-value">{value}</div><div class="stat-label">{label}</div></div>'
        for label, value in stats.items()
    )
    package_options = "".join(f'<option value="{item}">{item}</option>' for item in PACKAGE_TYPES)
    category_options = "".join(f'<option value="{item}">{item}</option>' for item in PRODUCT_CATEGORIES)
    series_options = "".join(f'<option value="{item}">{item}</option>' for item in unique_series)
    return f"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>设计稿工作台</title>
  <style>
    :root {{
      --bg: #f4efe6;
      --panel: #fffaf2;
      --ink: #2e241c;
      --muted: #786a5d;
      --accent: #b14d1f;
      --accent-soft: #f3d9c8;
      --line: #e7d8c6;
      --shadow: 0 18px 40px rgba(76, 48, 27, 0.10);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      font-family: "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif;
      background:
        radial-gradient(circle at top left, #fff6e6 0, #fff6e6 18%, transparent 19%),
        linear-gradient(135deg, #f8f0e4 0%, #f4efe6 45%, #efe7da 100%);
      color: var(--ink);
    }}
    .page {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 32px 20px 56px;
    }}
    .hero {{
      background: linear-gradient(135deg, rgba(177,77,31,0.95), rgba(229,153,89,0.88));
      color: white;
      border-radius: 28px;
      padding: 28px;
      box-shadow: var(--shadow);
      position: relative;
    }}
    .hero h1 {{
      margin: 0 0 10px;
      font-size: 32px;
    }}
    .hero p {{
      margin: 0;
      color: rgba(255,255,255,0.9);
      max-width: 880px;
      line-height: 1.6;
    }}
    .stats {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
      gap: 12px;
      margin-top: 20px;
    }}
    .stat {{
      background: rgba(255,255,255,0.18);
      border: 1px solid rgba(255,255,255,0.18);
      border-radius: 18px;
      padding: 14px 16px;
      backdrop-filter: blur(10px);
    }}
    .stat-value {{
      font-size: 24px;
      font-weight: 700;
    }}
    .stat-label {{
      margin-top: 4px;
      font-size: 13px;
      color: rgba(255,255,255,0.85);
    }}
    .toolbar {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
      gap: 12px;
      padding: 22px;
      margin: 20px 0 26px;
      background: var(--panel);
      border-radius: 24px;
      box-shadow: var(--shadow);
    }}
    .toolbar label {{
      display: block;
      font-size: 13px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .toolbar input,
    .toolbar select {{
      width: 100%;
      padding: 12px 14px;
      border: 1px solid var(--line);
      border-radius: 14px;
      background: white;
      color: var(--ink);
      font-size: 14px;
    }}
    .series-overview {{
      margin: 0 0 24px;
      background: rgba(255,250,242,0.9);
      border-radius: 24px;
      box-shadow: var(--shadow);
      padding: 18px 20px;
    }}
    .series-overview h2 {{
      margin: 0 0 14px;
      font-size: 18px;
    }}
    .series-chips {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .series-chip {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 999px;
      padding: 8px 12px;
      font-size: 13px;
      cursor: pointer;
    }}
    .series-chip.active {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}
    .cards {{
      display: grid;
      gap: 16px;
    }}
    .card {{
      background: rgba(255,250,242,0.92);
      border: 1px solid var(--line);
      border-radius: 22px;
      overflow: hidden;
      box-shadow: var(--shadow);
      transform: translateY(18px);
      opacity: 0;
      animation: fadeUp 420ms ease forwards;
    }}
    .card.selected {{
      border-color: rgba(177,77,31,0.55);
      box-shadow: 0 20px 44px rgba(177,77,31,0.18);
      background: linear-gradient(180deg, rgba(255,250,242,0.98), rgba(255,244,236,0.98));
    }}
    .card.duplicate-candidate {{
      border-style: dashed;
    }}
    .card-row {{
      display: grid;
      grid-template-columns: 44px 240px minmax(320px, 1fr) minmax(320px, 420px);
      gap: 16px;
      align-items: start;
      padding: 16px;
    }}
    .select-cell {{
      display: flex;
      align-items: flex-start;
      justify-content: center;
      padding-top: 6px;
    }}
    .select-cell input {{
      width: 18px;
      height: 18px;
      accent-color: var(--accent);
      cursor: pointer;
    }}
    .thumb {{
      display: block;
      aspect-ratio: 4 / 3;
      background: linear-gradient(135deg, #f6e9d8, #ead9c7);
      overflow: hidden;
      border-radius: 16px;
    }}
    .thumb img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .body {{
      padding: 4px 0;
    }}
    .title {{
      font-size: 16px;
      font-weight: 700;
      line-height: 1.45;
      margin: 0 0 10px;
      word-break: break-word;
    }}
    .badges {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px;
      margin-bottom: 12px;
    }}
    .badge {{
      padding: 4px 10px;
      border-radius: 999px;
      background: var(--accent-soft);
      color: var(--accent);
      font-size: 12px;
      font-weight: 600;
    }}
    .badge-new {{
      background: #dff4e8;
      color: #1e7a46;
    }}
    .meta {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 8px 18px;
      font-size: 13px;
      color: var(--muted);
    }}
    .meta div {{
      min-width: 0;
      word-break: break-word;
    }}
    .meta strong {{
      color: var(--ink);
    }}
    .actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-top: 14px;
    }}
    .actions a,
    .actions button {{
      text-decoration: none;
      color: white;
      background: var(--accent);
      padding: 10px 12px;
      border-radius: 12px;
      font-size: 13px;
      border: none;
      cursor: pointer;
    }}
    .actions button.secondary {{
      background: white;
      color: var(--accent);
      border: 1px solid var(--line);
    }}
    .rename-panel {{
      padding: 14px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
    }}
    .rename-panel label {{
      display: block;
      font-size: 12px;
      color: var(--muted);
      margin-bottom: 6px;
    }}
    .rename-panel input {{
      width: 100%;
      padding: 10px 12px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: white;
      color: var(--ink);
      font-size: 13px;
    }}
    .rename-grid {{
      display: grid;
      grid-template-columns: repeat(2, minmax(0, 1fr));
      gap: 10px;
    }}
    .rename-field-full {{
      grid-column: 1 / -1;
    }}
    .rename-help {{
      margin-top: 8px;
      font-size: 12px;
      color: var(--muted);
      line-height: 1.5;
    }}
    .rename-status {{
      margin-top: 8px;
      font-size: 12px;
      color: var(--accent);
      font-weight: 600;
    }}
    .workspace-tools {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin: 18px 0 22px;
    }}
    .workspace-tools button {{
      border: 1px solid var(--line);
      background: white;
      color: var(--ink);
      border-radius: 999px;
      padding: 10px 14px;
      font-size: 13px;
      cursor: pointer;
      box-shadow: var(--shadow);
    }}
    .workspace-tools .primary {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}
    .workspace-note {{
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
    }}
    .workflow-note {{
      margin: 0 0 18px;
      padding: 14px 16px;
      border-radius: 16px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.7;
      box-shadow: var(--shadow);
    }}
    .workflow-note summary {{
      cursor: pointer;
      font-weight: 700;
      color: var(--ink);
      list-style: none;
    }}
    .workflow-note summary::-webkit-details-marker {{
      display: none;
    }}
    .workflow-note-content {{
      margin-top: 10px;
    }}
    .workflow-note strong {{
      color: var(--ink);
    }}
    .selection-summary {{
      margin: 0 0 18px;
      color: var(--muted);
      font-size: 13px;
    }}
    .autosave-status {{
      margin: 0 0 18px;
      padding: 10px 14px;
      border-radius: 14px;
      background: rgba(255,255,255,0.72);
      border: 1px solid var(--line);
      color: var(--muted);
      font-size: 13px;
      line-height: 1.6;
      box-shadow: var(--shadow);
    }}
    .autosave-status strong {{
      color: var(--ink);
    }}
    .action-bar {{
      position: sticky;
      bottom: 18px;
      z-index: 20;
      display: none;
      margin-top: 18px;
      padding: 14px 16px;
      border-radius: 18px;
      background: rgba(46, 36, 28, 0.92);
      color: white;
      box-shadow: 0 18px 40px rgba(46, 36, 28, 0.28);
      backdrop-filter: blur(12px);
    }}
    .action-bar.visible {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
    }}
    .action-bar-text {{
      font-size: 14px;
      line-height: 1.6;
      color: rgba(255,255,255,0.92);
    }}
    .action-bar-actions {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
    }}
    .action-bar-actions button {{
      border: 1px solid rgba(255,255,255,0.18);
      background: rgba(255,255,255,0.12);
      color: white;
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 13px;
      cursor: pointer;
    }}
    .action-bar-actions .danger {{
      background: #c85a26;
      border-color: #c85a26;
    }}
    .empty {{
      display: none;
      margin-top: 18px;
      padding: 32px;
      border-radius: 20px;
      background: rgba(255,250,242,0.9);
      text-align: center;
      color: var(--muted);
      box-shadow: var(--shadow);
    }}
    @keyframes fadeUp {{
      to {{
        transform: translateY(0);
        opacity: 1;
      }}
    }}
    @media (max-width: 640px) {{
      .page {{ padding: 18px 14px 40px; }}
      .hero {{ border-radius: 22px; padding: 22px; position: static; }}
      .hero h1 {{ font-size: 24px; }}
      .rename-grid {{ grid-template-columns: 1fr; }}
      .card-row {{ grid-template-columns: 1fr; }}
      .select-cell {{ justify-content: flex-start; padding-top: 0; }}
      .action-bar.visible {{ flex-direction: column; align-items: stretch; }}
      .meta {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 1120px) {{
      .card-row {{
        grid-template-columns: 44px 220px minmax(280px, 1fr);
      }}
      .rename-panel {{
        grid-column: 1 / -1;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="hero">
      <h1>设计稿工作台</h1>
      <p>集中查看各产品线历史设计稿，支持按产品分类、产品编码、包装类型、日期、渠道和状态筛选。当前默认分类为涂附、砂轮、钢丝刷、金刚石工具和其他。</p>
      <div class="stats">{stat_html}</div>
    </section>

    <section class="toolbar">
      <div>
        <label for="search">搜索</label>
        <input id="search" type="search" placeholder="文件名 / 产品分类 / 产品编码 / 备注">
      </div>
      <div>
        <label for="productCategory">产品分类</label>
        <select id="productCategory">
          <option value="">全部</option>
          {category_options}
        </select>
      </div>
      <div>
        <label for="productSeries">产品系列</label>
        <input id="productSeries" list="productSeriesList" type="search" placeholder="如 B15 / BT77 / V字卷">
        <datalist id="productSeriesList">
          {series_options}
        </datalist>
      </div>
      <div>
        <label for="packageType">包装类型</label>
        <select id="packageType">
          <option value="">全部</option>
          {package_options}
        </select>
      </div>
      <div>
        <label for="channel">渠道</label>
        <select id="channel">
          <option value="">全部</option>
          <option value="独立站">独立站</option>
          <option value="商超">商超</option>
          <option value="亚马逊">亚马逊</option>
          <option value="其他">其他</option>
        </select>
      </div>
      <div>
        <label for="status">状态</label>
        <select id="status">
          <option value="">全部</option>
          <option value="DONE">DONE</option>
          <option value="进行中">进行中</option>
          <option value="历史">历史</option>
        </select>
      </div>
      <div>
        <label for="date">日期</label>
        <input id="date" type="search" placeholder="YYYYMMDD">
      </div>
      <div>
        <label for="onlySelected">仅看已选</label>
        <select id="onlySelected">
          <option value="">全部</option>
          <option value="selected">仅看已选</option>
        </select>
      </div>
      <div>
        <label for="duplicateMode">重复筛选</label>
        <select id="duplicateMode">
          <option value="">全部</option>
          <option value="hash">仅看内容重复</option>
          <option value="name">仅看名称疑似重复</option>
        </select>
      </div>
      <div>
        <label for="recentSync">同步批次</label>
        <select id="recentSync">
          <option value="">全部</option>
          <option value="recent">仅看本次新增</option>
        </select>
      </div>
    </section>

    <section class="series-overview">
      <h2>系列概览</h2>
      <div id="seriesChips" class="series-chips"></div>
    </section>

    <section class="workspace-tools">
      <button id="selectVisible" type="button">全选当前筛选结果</button>
      <button id="selectDuplicateRemainders" type="button">每组保留1个，其余全选</button>
      <button id="clearSelected" type="button">清空当前选择</button>
      <button id="deleteSelectedRows" type="button">删除所选（先确认）</button>
      <button id="deleteVisibleRows" type="button">删除当前筛选结果（先确认）</button>
      <button id="exportRenameDrafts" type="button" class="primary">导出改名清单 CSV</button>
      <button id="exportSelectedRows" type="button">导出所选清单 CSV</button>
      <button id="exportDeleteList" type="button">导出删除清单 CSV</button>
      <button id="clearRenameDrafts" type="button">清空本地改名草稿</button>
    </section>
    <p class="workspace-note">你现在可以先按 4 个字段整理名称：产品分类、货号、产品规格、装盒片数。网页会自动拼出计划名称，并保存在当前浏览器。你也可以先批量筛选、多选，再导出所选清单或删除清单，后面我们再统一同步到本地文件名和正式台账。</p>
    <details class="workflow-note">
      <summary>推荐操作流程</summary>
      <div class="workflow-note-content">
        改名后先点“导出改名清单 CSV”，再双击桌面的“应用最新改名清单.command”。
        删除时先选中记录，再点“删除所选（先确认）”或“删除当前筛选结果（先确认）”，导出删除清单后，双击桌面的“应用最新删除清单.command”。
      </div>
    </details>
    <div id="autosaveStatus" class="autosave-status"><strong>草稿状态：</strong>尚未产生新的本地草稿</div>
    <p id="selectionSummary" class="selection-summary"></p>
    <section id="actionBar" class="action-bar">
      <div id="actionBarText" class="action-bar-text"></div>
      <div class="action-bar-actions">
        <button id="actionBarExportSelected" type="button">导出所选清单</button>
        <button id="actionBarExportRename" type="button">导出改名清单</button>
        <button id="actionBarDeleteSelected" type="button" class="danger">删除所选</button>
      </div>
    </section>

    <section id="cards" class="cards"></section>
    <section id="empty" class="empty">没有符合条件的设计稿。</section>
  </div>

  <script id="design-data" type="application/json">{json.dumps([record_to_json(record) for record in records], ensure_ascii=False)}</script>
  <script>
    function main() {{
      const raw = document.getElementById('design-data').textContent;
      const records = JSON.parse(raw);
      const cards = document.getElementById('cards');
      const empty = document.getElementById('empty');
      const seriesChips = document.getElementById('seriesChips');
      const exportRenameDrafts = document.getElementById('exportRenameDrafts');
      const exportSelectedRows = document.getElementById('exportSelectedRows');
      const exportDeleteList = document.getElementById('exportDeleteList');
      const selectVisible = document.getElementById('selectVisible');
      const selectDuplicateRemainders = document.getElementById('selectDuplicateRemainders');
      const clearSelected = document.getElementById('clearSelected');
      const deleteSelectedRows = document.getElementById('deleteSelectedRows');
      const deleteVisibleRows = document.getElementById('deleteVisibleRows');
      const clearRenameDrafts = document.getElementById('clearRenameDrafts');
      const selectionSummary = document.getElementById('selectionSummary');
      const autosaveStatus = document.getElementById('autosaveStatus');
      const actionBar = document.getElementById('actionBar');
      const actionBarText = document.getElementById('actionBarText');
      const actionBarExportSelected = document.getElementById('actionBarExportSelected');
      const actionBarExportRename = document.getElementById('actionBarExportRename');
      const actionBarDeleteSelected = document.getElementById('actionBarDeleteSelected');
      const renameDraftStorageKey = 'design-workbench-rename-drafts-v1';
      const selectedStorageKey = 'design-workbench-selected-v1';
      const autosaveTimeKey = 'design-workbench-last-save-v1';
      const filters = {{
        search: document.getElementById('search'),
        productCategory: document.getElementById('productCategory'),
        productSeries: document.getElementById('productSeries'),
        packageType: document.getElementById('packageType'),
        channel: document.getElementById('channel'),
        status: document.getElementById('status'),
        date: document.getElementById('date'),
        onlySelected: document.getElementById('onlySelected'),
        duplicateMode: document.getElementById('duplicateMode'),
        recentSync: document.getElementById('recentSync'),
      }};
      const recentSyncedPaths = new Set([
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_1.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_2.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_3.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_4.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_5.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_6.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_7.pdf',
        '/Users/zhanghan/Desktop/涂覆包装-设计稿/1-5涂附-卷装/涂附-砂带-待补充-20260506-V1_8.pdf',
      ]);
      const renameDrafts = loadRenameDrafts();
      const selectedRecords = loadSelectedRecords();
      const seriesCounts = records.reduce((acc, record) => {{
        const key = record["产品系列"] || '待补充';
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }}, {{}});
      const fileHashCounts = records.reduce((acc, record) => {{
        const key = (record.file_hash || '').trim();
        if (!key) return acc;
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }}, {{}});

      function normalizeDuplicateName(value) {{
        return String(value || '')
          .replace(/\.pdf$/i, '')
          .replace(/20\d{{6}}/g, '')
          .replace(/v\d+/ig, '')
          .replace(/[()\[\]（）]/g, '')
          .replace(/[_\-\s]+/g, '')
          .toLowerCase()
          .trim();
      }}

      const nameDuplicateCounts = records.reduce((acc, record) => {{
        const key = normalizeDuplicateName(record.original_name || record.new_name || '');
        if (!key) return acc;
        acc[key] = (acc[key] || 0) + 1;
        return acc;
      }}, {{}});

      function escapeCsvCell(value) {{
        const text = String(value ?? '');
        if (/[",\\n]/.test(text)) {{
          return `"${{text.replace(/"/g, '""')}}"`;
        }}
        return text;
      }}

      function getRecordKey(record) {{
        return record.file_hash || record.original_path || record.new_name;
      }}

      function loadRenameDrafts() {{
        try {{
          const rawDrafts = window.localStorage.getItem(renameDraftStorageKey);
          const parsed = rawDrafts ? JSON.parse(rawDrafts) : {{}};
          return parsed && typeof parsed === 'object' ? parsed : {{}};
        }} catch (error) {{
          return {{}};
        }}
      }}

      function loadSelectedRecords() {{
        try {{
          const rawSelected = window.localStorage.getItem(selectedStorageKey);
          const parsed = rawSelected ? JSON.parse(rawSelected) : [];
          return Array.isArray(parsed) ? new Set(parsed) : new Set();
        }} catch (error) {{
          return new Set();
        }}
      }}

      function saveRenameDrafts() {{
        window.localStorage.setItem(renameDraftStorageKey, JSON.stringify(renameDrafts));
        markAutosaved();
      }}

      function saveSelectedRecords() {{
        window.localStorage.setItem(selectedStorageKey, JSON.stringify(Array.from(selectedRecords)));
        markAutosaved();
      }}

      function markAutosaved() {{
        const stamp = new Date().toISOString();
        window.localStorage.setItem(autosaveTimeKey, stamp);
        updateAutosaveStatus();
      }}

      function updateAutosaveStatus() {{
        const stamp = window.localStorage.getItem(autosaveTimeKey);
        const draftCount = Object.keys(renameDrafts).length;
        const selectedCount = selectedRecords.size;
        if (!stamp && draftCount === 0 && selectedCount === 0) {{
          autosaveStatus.innerHTML = '<strong>草稿状态：</strong>尚未产生新的本地草稿';
          return;
        }}
        const date = stamp ? new Date(stamp) : null;
        const localTime = date && !Number.isNaN(date.getTime())
          ? `${{date.getFullYear()}}-${{String(date.getMonth() + 1).padStart(2, '0')}}-${{String(date.getDate()).padStart(2, '0')}} ${{String(date.getHours()).padStart(2, '0')}}:${{String(date.getMinutes()).padStart(2, '0')}}:${{String(date.getSeconds()).padStart(2, '0')}}`
          : '未知时间';
        autosaveStatus.innerHTML = `<strong>草稿已自动保存</strong>：最后保存于 ${{localTime}}；当前改名草稿 ${{draftCount}} 条，已选记录 ${{selectedCount}} 条。`;
      }}

      function detectBoxCount(record) {{
        const text = [record.new_name, record.original_name, record["核心规格"]].join(' ');
        const match = String(text).match(/(\d+)\s*PCS/i);
        return match ? `${{match[1]}}PCS` : '';
      }}

      function detectLogo(record) {{
        const text = [record.new_name, record.original_name, record["备注"]].join(' ').toUpperCase();
        for (const keyword of ['FASTPLUS', 'MATTLUX', 'NACUT', 'DEERFOS', 'SUNMIGHT']) {{
          if (text.includes(keyword)) return keyword;
        }}
        return '';
      }}

      function defaultDraftFields(record) {{
        return {{
          category_detail: [record["产品分类"], record["产品系列"]].filter(Boolean).join('-'),
          spec_detail: record["核心规格"] || '',
          box_count: detectBoxCount(record),
          item_no: record["设计图号"] || '',
        }};
      }}

      function draftFields(record) {{
        const stored = renameDrafts[getRecordKey(record)];
        const defaults = defaultDraftFields(record);
        if (!stored) return defaults;
        if (typeof stored === 'string') {{
          return {{
            ...defaults,
            planned_name_override: stored,
          }};
        }}
        return {{
          ...defaults,
          ...stored,
        }};
      }}

      function buildPlannedName(record) {{
        const fields = draftFields(record);
        if (fields.planned_name_override) {{
          return fields.planned_name_override;
        }}
        const parts = [
          fields.category_detail,
          fields.item_no,
          fields.spec_detail,
          fields.box_count,
          record["日期"] || '',
          record["版本"] || '',
        ]
          .map((item) => String(item || '').trim())
          .filter(Boolean);
        return parts.length ? `${{parts.join('-')}}.pdf` : (record.new_name || '');
      }}

      function plannedName(record) {{
        return buildPlannedName(record);
      }}

      function getDuplicateModeKey(record, mode) {{
        if (mode === 'hash') {{
          const key = (record.file_hash || '').trim();
          return fileHashCounts[key] > 1 ? key : '';
        }}
        if (mode === 'name') {{
          const key = normalizeDuplicateName(record.original_name || record.new_name || '');
          return nameDuplicateCounts[key] > 1 ? key : '';
        }}
        return '';
      }}

      function saveDraftField(record, fieldName, value) {{
        const key = getRecordKey(record);
        const nextDraft = {{
          ...defaultDraftFields(record),
          ...draftFields(record),
          [fieldName]: value.trim(),
        }};
        delete nextDraft.planned_name_override;
        const generated = [
          nextDraft.category_detail,
          nextDraft.item_no,
          nextDraft.spec_detail,
          nextDraft.box_count,
        ].map((item) => String(item || '').trim());
        const defaultValues = defaultDraftFields(record);
        const unchanged = (
          nextDraft.category_detail === defaultValues.category_detail &&
          nextDraft.item_no === defaultValues.item_no &&
          nextDraft.spec_detail === defaultValues.spec_detail &&
          nextDraft.box_count === defaultValues.box_count
        );
        if (unchanged) {{
          delete renameDrafts[key];
        }} else {{
          renameDrafts[key] = nextDraft;
        }}
        saveRenameDrafts();
      }}

      function matches(record) {{
        const search = filters.search.value.trim().toLowerCase();
        const productCategory = filters.productCategory.value;
        const productSeries = filters.productSeries.value.trim().toLowerCase();
        const packageType = filters.packageType.value;
        const channel = filters.channel.value;
        const status = filters.status.value;
        const date = filters.date.value.trim();
        const onlySelected = filters.onlySelected.value;
        const duplicateMode = filters.duplicateMode.value;
        const recentSync = filters.recentSync.value;

        if (productCategory && record["产品分类"] !== productCategory) return false;
        if (productSeries && (record["产品系列"] || '').toLowerCase() !== productSeries) return false;
        if (packageType && record["包装类型"] !== packageType) return false;
        if (channel && record["渠道"] !== channel) return false;
        if (status && record["状态"] !== status) return false;
        if (date && !String(record["日期"] || '').includes(date)) return false;
        if (onlySelected === 'selected' && !selectedRecords.has(getRecordKey(record))) return false;
        if (duplicateMode && !getDuplicateModeKey(record, duplicateMode)) return false;
        if (recentSync === 'recent' && !recentSyncedPaths.has(record.original_path)) return false;
        if (!search) return true;

        const fields = [
          record.new_name,
          record["产品分类"],
          record["产品系列"],
          record["产品编码"],
          record["核心规格"],
          record["包装类型"],
          record["设计图号"],
          record["客户"],
          record["备注"],
          record.original_name,
        ].join(' ').toLowerCase();
        return fields.includes(search);
      }}

      function badge(text) {{
        return `<span class="badge">${{text || '未填写'}}</span>`;
      }}

      function newBadge(text) {{
        return `<span class="badge badge-new">${{text}}</span>`;
      }}

      function renderSeriesChips() {{
        const current = filters.productSeries.value.trim();
        const chips = Object.entries(seriesCounts)
          .sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0], 'zh-CN'))
          .map(([series, count]) => `
            <button
              type="button"
              class="series-chip ${{current === series ? 'active' : ''}}"
              data-series="${{series}}"
            >${{series}} (${{count}})</button>
          `)
          .join('');
        seriesChips.innerHTML = `<button type="button" class="series-chip ${{current === '' ? 'active' : ''}}" data-series="">全部</button>${{chips}}`;
        seriesChips.querySelectorAll('[data-series]').forEach((button) => {{
          button.addEventListener('click', () => {{
            filters.productSeries.value = button.getAttribute('data-series') || '';
            render();
          }});
        }});
      }}

      function exportRows(rows, filenamePrefix) {{
        const header = [
          'original_path',
          'original_name',
          'current_new_name',
          'planned_new_name',
          'draft_category_detail',
          'draft_item_no',
          'draft_spec_detail',
          'draft_box_count',
          'product_category',
          'product_series',
          'product_code',
          'spec',
          'package_type',
          'date',
          'version',
          'status',
          'file_hash',
        ];
        const lines = [header.join(',')];
        rows.forEach((row) => {{
          lines.push(header.map((key) => escapeCsvCell(row[key])).join(','));
        }});
        const csv = "\\ufeff" + lines.join('\\n');
        const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const now = new Date();
        const stamp = [
          now.getFullYear(),
          String(now.getMonth() + 1).padStart(2, '0'),
          String(now.getDate()).padStart(2, '0'),
          String(now.getHours()).padStart(2, '0'),
          String(now.getMinutes()).padStart(2, '0'),
        ].join('');
        link.href = url;
        link.download = `${{filenamePrefix}}_${{stamp}}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
      }}

      function deleteRows(rows, label) {{
        if (!rows.length) {{
          window.alert(`没有可删除的记录：${{label}}`);
          return;
        }}
        const names = rows.slice(0, 8).map((row) => row.current_new_name || row.original_name).join('\\n');
        const more = rows.length > 8 ? `\\n... 另有 ${{rows.length - 8}} 条` : '';
        const ok = window.confirm(`确认删除${{label}}吗？\\n\\n共 ${{rows.length}} 条\\n\\n${{names}}${{more}}\\n\\n删除后会从原始目录和工作台中移除。`);
        if (!ok) return;
        const header = [
          'original_path',
          'original_name',
          'current_new_name',
          'planned_new_name',
          'draft_category_detail',
          'draft_item_no',
          'draft_spec_detail',
          'draft_box_count',
          'product_category',
          'product_series',
          'product_code',
          'spec',
          'package_type',
          'date',
          'version',
          'status',
          'file_hash',
        ];
        const lines = [header.join(',')];
        rows.forEach((row) => {{
          lines.push(header.map((key) => escapeCsvCell(row[key])).join(','));
        }});
        const csv = "\\ufeff" + lines.join('\\n');
        const blob = new Blob([csv], {{ type: 'text/csv;charset=utf-8;' }});
        const url = URL.createObjectURL(blob);
        const link = document.createElement('a');
        const now = new Date();
        const stamp = [
          now.getFullYear(),
          String(now.getMonth() + 1).padStart(2, '0'),
          String(now.getDate()).padStart(2, '0'),
          String(now.getHours()).padStart(2, '0'),
          String(now.getMinutes()).padStart(2, '0'),
        ].join('');
        link.href = url;
        link.download = `delete_list_${{stamp}}.csv`;
        document.body.appendChild(link);
        link.click();
        document.body.removeChild(link);
        URL.revokeObjectURL(url);
        window.alert('已导出删除清单 CSV。请把这份 CSV 发给我，或在终端执行 apply-delete-list 正式删除。');
      }}

      function render() {{
        const visible = records
          .filter(matches)
          .slice()
          .sort((a, b) => {{
            const aRecent = recentSyncedPaths.has(a.original_path) ? 1 : 0;
            const bRecent = recentSyncedPaths.has(b.original_path) ? 1 : 0;
            if (aRecent !== bRecent) return bRecent - aRecent;
            const aDate = String(a["日期"] || '');
            const bDate = String(b["日期"] || '');
            if (aDate !== bDate) return bDate.localeCompare(aDate, 'zh-CN');
            return String(a.new_name || '').localeCompare(String(b.new_name || ''), 'zh-CN');
          }});
        const hashDuplicateRows = records.filter((record) => getDuplicateModeKey(record, 'hash')).length;
        const nameDuplicateRows = records.filter((record) => getDuplicateModeKey(record, 'name')).length;
        selectionSummary.textContent = `当前共 ${{records.length}} 条，筛选结果 ${{visible.length}} 条，已选择 ${{selectedRecords.size}} 条；内容重复候选 ${{hashDuplicateRows}} 条，名称疑似重复 ${{nameDuplicateRows}} 条。`;
        updateAutosaveStatus();
        if (selectedRecords.size > 0) {{
          actionBar.classList.add('visible');
          actionBarText.textContent = `已选中 ${{selectedRecords.size}} 条。现在可以导出所选清单、导出改名清单，或继续删除所选记录。`;
        }} else {{
          actionBar.classList.remove('visible');
          actionBarText.textContent = '';
        }}
        cards.innerHTML = visible.map((record, index) => `
          <article class="card ${{selectedRecords.has(getRecordKey(record)) ? 'selected' : ''}} ${{getDuplicateModeKey(record, 'hash') || getDuplicateModeKey(record, 'name') ? 'duplicate-candidate' : ''}}" style="animation-delay:${{index * 20}}ms">
            <div class="card-row">
              <div class="select-cell">
                <input type="checkbox" data-select-row="${{index}}" ${{selectedRecords.has(getRecordKey(record)) ? 'checked' : ''}}>
              </div>
              <a class="thumb" href="./${{record.pdf_path}}" target="_blank" rel="noreferrer">
                <img src="./${{record.thumbnail_path}}" alt="${{record.new_name}}">
              </a>
              <div class="body">
                <h2 class="title">${{record.new_name}}</h2>
                <div class="badges">
                  ${{recentSyncedPaths.has(record.original_path) ? newBadge('本次新增') : ''}}
                  ${{badge(record["产品分类"])}}
                  ${{badge(record["产品系列"])}}
                  ${{badge(record["包装类型"])}}
                  ${{badge(record["渠道"])}}
                  ${{badge(record["状态"])}}
                  ${{getDuplicateModeKey(record, 'hash') ? badge('内容重复候选') : ''}}
                  ${{getDuplicateModeKey(record, 'name') ? badge('名称疑似重复') : ''}}
                </div>
                <div class="meta">
                  <div><strong>产品分类：</strong>${{record["产品分类"] || ''}}</div>
                  <div><strong>产品系列：</strong>${{record["产品系列"] || ''}}</div>
                  <div><strong>产品编码：</strong>${{record["产品编码"] || ''}}</div>
                  <div><strong>核心规格：</strong>${{record["核心规格"] || ''}}</div>
                  <div><strong>日期：</strong>${{record["日期"] || ''}}</div>
                  <div><strong>版本：</strong>${{record["版本"] || ''}}</div>
                  <div><strong>设计图号：</strong>${{record["设计图号"] || ''}}</div>
                  <div><strong>客户：</strong>${{record["客户"] || ''}}</div>
                  <div><strong>备注：</strong>${{record["备注"] || ''}}</div>
                  <div><strong>原文件：</strong>${{record.original_name}}</div>
                  <div><strong>重复组：</strong>${{record.duplicate_group || '无'}}</div>
                </div>
                <div class="actions">
                  <a href="./${{record.pdf_path}}" target="_blank" rel="noreferrer">打开 PDF</a>
                  <button type="button" class="secondary" data-copy-name="${{index}}">复制当前名称</button>
                </div>
              </div>
              <div class="rename-panel">
                <div class="rename-grid">
                  <div class="rename-field-full">
                    <label for="rename-category-${{index}}">产品分类</label>
                    <input id="rename-category-${{index}}" data-rename-field="category_detail" data-rename-input="${{index}}" type="text" value="${{draftFields(record).category_detail.replace(/"/g, '&quot;')}}" placeholder="例如：涂附-拉绒片">
                  </div>
                  <div>
                    <label for="rename-itemno-${{index}}">货号</label>
                    <input id="rename-itemno-${{index}}" data-rename-field="item_no" data-rename-input="${{index}}" type="text" value="${{draftFields(record).item_no.replace(/"/g, '&quot;')}}" placeholder="例如：FPD10005">
                  </div>
                  <div>
                    <label for="rename-spec-${{index}}">产品规格</label>
                    <input id="rename-spec-${{index}}" data-rename-field="spec_detail" data-rename-input="${{index}}" type="text" value="${{draftFields(record).spec_detail.replace(/"/g, '&quot;')}}" placeholder="例如：150mm+15孔">
                  </div>
                  <div>
                    <label for="rename-count-${{index}}">装盒片数</label>
                    <input id="rename-count-${{index}}" data-rename-field="box_count" data-rename-input="${{index}}" type="text" value="${{draftFields(record).box_count.replace(/"/g, '&quot;')}}" placeholder="例如：50PCS">
                  </div>
                </div>
                <div class="rename-help">计划名称预览：<strong data-rename-preview="${{index}}">${{plannedName(record)}}</strong></div>
                <div class="rename-help">当前正式名称：${{record.new_name}}</div>
                <div class="rename-status" data-rename-status="${{index}}">${{plannedName(record) !== record.new_name ? '已修改，等待导出' : '未修改'}}</div>
              </div>
            </div>
          </article>
        `).join('');
        empty.style.display = visible.length ? 'none' : 'block';
        renderSeriesChips();

        cards.querySelectorAll('[data-rename-input]').forEach((input) => {{
          input.addEventListener('input', (event) => {{
            const recordIndex = Number(event.target.getAttribute('data-rename-input'));
            const fieldName = event.target.getAttribute('data-rename-field');
            const currentRecord = visible[recordIndex];
            if (!currentRecord || !fieldName) return;
            saveDraftField(currentRecord, fieldName, event.target.value);
            const previewNode = cards.querySelector(`[data-rename-preview="${{recordIndex}}"]`);
            const statusNode = cards.querySelector(`[data-rename-status="${{recordIndex}}"]`);
            if (previewNode) {{
              previewNode.textContent = plannedName(currentRecord);
            }}
            if (statusNode) {{
              statusNode.textContent = plannedName(currentRecord) !== currentRecord.new_name ? '已修改，等待导出' : '未修改';
            }}
          }});
        }});

        cards.querySelectorAll('[data-copy-name]').forEach((button) => {{
          button.addEventListener('click', async () => {{
            const recordIndex = Number(button.getAttribute('data-copy-name'));
            const currentRecord = visible[recordIndex];
            if (!currentRecord) return;
            try {{
              await navigator.clipboard.writeText(currentRecord.new_name || '');
              button.textContent = '已复制';
              window.setTimeout(() => {{
                button.textContent = '复制当前名称';
              }}, 1000);
            }} catch (error) {{
              button.textContent = '复制失败';
              window.setTimeout(() => {{
                button.textContent = '复制当前名称';
              }}, 1200);
            }}
          }});
        }});

        cards.querySelectorAll('[data-select-row]').forEach((checkbox) => {{
          checkbox.addEventListener('change', (event) => {{
            const recordIndex = Number(event.target.getAttribute('data-select-row'));
            const currentRecord = visible[recordIndex];
            if (!currentRecord) return;
            const key = getRecordKey(currentRecord);
            if (event.target.checked) {{
              selectedRecords.add(key);
            }} else {{
              selectedRecords.delete(key);
            }}
            saveSelectedRecords();
            const hashDuplicateRows = records.filter((record) => getDuplicateModeKey(record, 'hash')).length;
            const nameDuplicateRows = records.filter((record) => getDuplicateModeKey(record, 'name')).length;
            selectionSummary.textContent = `当前共 ${{records.length}} 条，筛选结果 ${{visible.length}} 条，已选择 ${{selectedRecords.size}} 条；内容重复候选 ${{hashDuplicateRows}} 条，名称疑似重复 ${{nameDuplicateRows}} 条。`;
          }});
        }});
      }}

      exportRenameDrafts.addEventListener('click', () => {{
        const changed = records
          .map((record) => {{
            const draftName = plannedName(record).trim();
            return {{
              original_path: record.original_path,
              original_name: record.original_name,
              current_new_name: record.new_name,
              planned_new_name: draftName,
              draft_category_detail: draftFields(record).category_detail || '',
              draft_item_no: draftFields(record).item_no || '',
              draft_spec_detail: draftFields(record).spec_detail || '',
              draft_box_count: draftFields(record).box_count || '',
              product_category: record["产品分类"] || '',
              product_series: record["产品系列"] || '',
              product_code: record["产品编码"] || '',
              spec: record["核心规格"] || '',
              package_type: record["包装类型"] || '',
              date: record["日期"] || '',
              version: record["版本"] || '',
              status: record["状态"] || '',
              file_hash: record.file_hash || '',
            }};
          }})
          .filter((row) => row.planned_new_name && row.planned_new_name !== row.current_new_name);

        exportRows(changed, 'rename_drafts');
      }});

      actionBarExportRename.addEventListener('click', () => {{
        exportRenameDrafts.click();
      }});

      exportSelectedRows.addEventListener('click', () => {{
        const selected = records
          .filter((record) => selectedRecords.has(getRecordKey(record)))
          .map((record) => ({{
            original_path: record.original_path,
            original_name: record.original_name,
            current_new_name: record.new_name,
            planned_new_name: plannedName(record).trim(),
            draft_category_detail: draftFields(record).category_detail || '',
            draft_item_no: draftFields(record).item_no || '',
            draft_spec_detail: draftFields(record).spec_detail || '',
            draft_box_count: draftFields(record).box_count || '',
            product_category: record["产品分类"] || '',
            product_series: record["产品系列"] || '',
            product_code: record["产品编码"] || '',
            spec: record["核心规格"] || '',
            package_type: record["包装类型"] || '',
            date: record["日期"] || '',
            version: record["版本"] || '',
            status: record["状态"] || '',
            file_hash: record.file_hash || '',
          }}));
        exportRows(selected, 'selected_records');
      }});

      actionBarExportSelected.addEventListener('click', () => {{
        exportSelectedRows.click();
      }});

      exportDeleteList.addEventListener('click', () => {{
        const selected = records
          .filter((record) => selectedRecords.has(getRecordKey(record)))
          .map((record) => ({{
            original_path: record.original_path,
            original_name: record.original_name,
            current_new_name: record.new_name,
            planned_new_name: plannedName(record).trim(),
            draft_category_detail: draftFields(record).category_detail || '',
            draft_item_no: draftFields(record).item_no || '',
            draft_spec_detail: draftFields(record).spec_detail || '',
            draft_box_count: draftFields(record).box_count || '',
            product_category: record["产品分类"] || '',
            product_series: record["产品系列"] || '',
            product_code: record["产品编码"] || '',
            spec: record["核心规格"] || '',
            package_type: record["包装类型"] || '',
            date: record["日期"] || '',
            version: record["版本"] || '',
            status: record["状态"] || '',
            file_hash: record.file_hash || '',
          }}));
        exportRows(selected, 'delete_list');
      }});

      selectVisible.addEventListener('click', () => {{
        const visible = records.filter(matches);
        visible.forEach((record) => selectedRecords.add(getRecordKey(record)));
        saveSelectedRecords();
        render();
      }});

      selectDuplicateRemainders.addEventListener('click', () => {{
        const visible = records.filter(matches);
        const mode = filters.duplicateMode.value || 'name';
        const grouped = new Map();
        visible.forEach((record) => {{
          const key = getDuplicateModeKey(record, mode);
          if (!key) return;
          if (!grouped.has(key)) grouped.set(key, []);
          grouped.get(key).push(record);
        }});
        grouped.forEach((items) => {{
          items.slice(1).forEach((record) => selectedRecords.add(getRecordKey(record)));
        }});
        saveSelectedRecords();
        render();
      }});

      clearSelected.addEventListener('click', () => {{
        selectedRecords.clear();
        saveSelectedRecords();
        render();
      }});

      deleteSelectedRows.addEventListener('click', () => {{
        const selected = records
          .filter((record) => selectedRecords.has(getRecordKey(record)))
          .map((record) => ({{
            original_path: record.original_path,
            original_name: record.original_name,
            current_new_name: record.new_name,
            planned_new_name: plannedName(record).trim(),
            draft_category_detail: draftFields(record).category_detail || '',
            draft_item_no: draftFields(record).item_no || '',
            draft_spec_detail: draftFields(record).spec_detail || '',
            draft_box_count: draftFields(record).box_count || '',
            product_category: record["产品分类"] || '',
            product_series: record["产品系列"] || '',
            product_code: record["产品编码"] || '',
            spec: record["核心规格"] || '',
            package_type: record["包装类型"] || '',
            date: record["日期"] || '',
            version: record["版本"] || '',
            status: record["状态"] || '',
            file_hash: record.file_hash || '',
          }}));
        deleteRows(selected, '所选记录');
      }});

      actionBarDeleteSelected.addEventListener('click', () => {{
        deleteSelectedRows.click();
      }});

      deleteVisibleRows.addEventListener('click', () => {{
        const visible = records
          .filter(matches)
          .map((record) => ({{
            original_path: record.original_path,
            original_name: record.original_name,
            current_new_name: record.new_name,
            planned_new_name: plannedName(record).trim(),
            draft_category_detail: draftFields(record).category_detail || '',
            draft_item_no: draftFields(record).item_no || '',
            draft_spec_detail: draftFields(record).spec_detail || '',
            draft_box_count: draftFields(record).box_count || '',
            product_category: record["产品分类"] || '',
            product_series: record["产品系列"] || '',
            product_code: record["产品编码"] || '',
            spec: record["核心规格"] || '',
            package_type: record["包装类型"] || '',
            date: record["日期"] || '',
            version: record["版本"] || '',
            status: record["状态"] || '',
            file_hash: record.file_hash || '',
          }}));
        deleteRows(visible, '当前筛选结果');
      }});

      clearRenameDrafts.addEventListener('click', () => {{
        if (!window.confirm('确认清空当前浏览器里保存的改名草稿吗？')) return;
        Object.keys(renameDrafts).forEach((key) => delete renameDrafts[key]);
        saveRenameDrafts();
        render();
      }});

      Object.values(filters).forEach((element) => {{
        element.addEventListener('input', render);
        element.addEventListener('change', render);
      }});

      render();
    }}

    try {{
      main();
    }} catch (error) {{
      const cards = document.getElementById('cards');
      cards.innerHTML = `<article class="card"><div class="body"><h2 class="title">数据加载失败</h2><div class="meta"><div>${{error.message}}</div></div></article>`;
    }}
  </script>
</body>
</html>
"""


def write_html(path: Path, records: Sequence[Record]) -> None:
    path.write_text(build_html(records), encoding="utf-8")


def backup_file(path: Path, backup_dir: Path) -> Optional[Path]:
    if not path.exists():
        return None
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    backup_path = backup_dir / f"{path.stem}-{stamp}{path.suffix}"
    shutil.copy2(path, backup_path)
    return backup_path


def command_apply_renames(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    rename_csv = Path(args.rename_csv).expanduser().resolve()
    preview_path = output / "data" / "rename_preview.csv"
    if not preview_path.exists():
        raise FileNotFoundError(f"未找到预览清单: {preview_path}")
    if not rename_csv.exists():
        raise FileNotFoundError(f"未找到改名清单: {rename_csv}")

    records = read_csv_records(preview_path)
    backup_dir = output / "data" / "backups"
    backup_file(preview_path, backup_dir)

    by_hash: Dict[str, Record] = {}
    by_original_path: Dict[str, Record] = {}
    for record in records:
        if record.file_hash:
            by_hash[record.file_hash] = record
        by_original_path[record.original_path] = record

    updated = 0
    skipped = 0
    seen_names: Dict[str, str] = {}
    with rename_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            planned_new_name = clean_text(row.get("planned_new_name", ""))
            if not planned_new_name:
                skipped += 1
                continue
            record = None
            file_hash = clean_text(row.get("file_hash", ""))
            original_path = clean_text(row.get("original_path", ""))
            if file_hash and file_hash in by_hash:
                record = by_hash[file_hash]
            elif original_path and original_path in by_original_path:
                record = by_original_path[original_path]
            if record is None:
                skipped += 1
                continue
            if not planned_new_name.lower().endswith(".pdf"):
                planned_new_name = f"{planned_new_name}.pdf"
            planned_new_name = sanitize_filename_part(planned_new_name[:-4]) + ".pdf"
            if planned_new_name in seen_names and seen_names[planned_new_name] != record.original_path:
                raise ValueError(f"改名清单中存在重复目标名称: {planned_new_name}")
            seen_names[planned_new_name] = record.original_path
            if record.new_name != planned_new_name:
                record.new_name = planned_new_name
                updated += 1

    write_csv(preview_path, [record.to_csv_row() for record in records])
    build_args = argparse.Namespace(output=str(output))
    command_build(build_args)
    print(f"已应用改名草稿: {rename_csv}")
    print(f"更新数量: {updated}")
    print(f"跳过数量: {skipped}")


def command_apply_delete_list(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    delete_csv = Path(args.delete_csv).expanduser().resolve()
    preview_path = output / "data" / "rename_preview.csv"
    if not preview_path.exists():
      raise FileNotFoundError(f"未找到预览清单: {preview_path}")
    if not delete_csv.exists():
      raise FileNotFoundError(f"未找到删除清单: {delete_csv}")

    backup_dir = output / "data" / "backups"
    backup_file(preview_path, backup_dir)

    records = read_csv_records(preview_path)
    delete_hashes = set()
    delete_paths = set()
    with delete_csv.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        for row in reader:
            file_hash = clean_text(row.get("file_hash", ""))
            original_path = clean_text(row.get("original_path", ""))
            if file_hash:
                delete_hashes.add(file_hash)
            if original_path:
                delete_paths.add(original_path)

    kept_records: List[Record] = []
    deleted_records: List[Record] = []
    for record in records:
        if (record.file_hash and record.file_hash in delete_hashes) or record.original_path in delete_paths:
            deleted_records.append(record)
        else:
            kept_records.append(record)

    delete_log_rows: List[Dict[str, str]] = []
    for record in deleted_records:
        source_path = Path(record.original_path)
        existed = source_path.exists()
        deleted = False
        error = ""
        if existed:
            try:
                source_path.unlink()
                deleted = True
            except Exception as exc:
                error = str(exc)
        delete_log_rows.append({
            "original_path": record.original_path,
            "original_name": record.original_name,
            "new_name": record.new_name,
            "file_hash": record.file_hash,
            "existed": "Y" if existed else "N",
            "deleted": "Y" if deleted else "N",
            "error": error,
        })

    write_csv(preview_path, [record.to_csv_row() for record in kept_records])
    delete_log_path = output / "data" / "deleted_from_selection.csv"
    with delete_log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=["original_path", "original_name", "new_name", "file_hash", "existed", "deleted", "error"],
        )
        writer.writeheader()
        writer.writerows(delete_log_rows)

    build_args = argparse.Namespace(output=str(output))
    command_build(build_args)
    print(f"已应用删除清单: {delete_csv}")
    print(f"删除数量: {len(deleted_records)}")
    print(f"保留数量: {len(kept_records)}")
    print(f"删除记录: {delete_log_path}")
    if not deleted_records:
        print("提示: 这份删除清单没有命中新文件，可能这些文件之前已经删除过了。本次主要执行了工作台重建与台账同步。")


def command_sync_source_updates(args: argparse.Namespace) -> None:
    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    preview_path = output / "data" / "rename_preview.csv"
    if not preview_path.exists():
        raise FileNotFoundError(f"未找到预览清单: {preview_path}")

    existing_records = read_csv_records(preview_path)
    existing_paths = {record.original_path for record in existing_records}
    source_files = list_pdf_files(source)
    new_files = [path for path in source_files if str(path) not in existing_paths]

    if not new_files:
        print("未发现新增设计稿，工作台无需同步。")
        return

    backup_dir = output / "data" / "backups"
    backup_file(preview_path, backup_dir)

    new_records = scan_paths(source, new_files)
    merged_records = existing_records + new_records
    write_csv(preview_path, [record.to_csv_row() for record in merged_records])

    build_args = argparse.Namespace(output=str(output))
    command_build(build_args)
    print(f"已同步新增设计稿: {len(new_records)}")
    for record in new_records:
        print(record.original_path)


def command_sync_source_names(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    preview_path = output / "data" / "rename_preview.csv"
    index_path = output / "data" / "design_index.csv"
    if not preview_path.exists():
        raise FileNotFoundError(f"未找到预览清单: {preview_path}")
    if not index_path.exists():
        raise FileNotFoundError(f"未找到正式台账: {index_path}")

    preview_records = read_csv_records(preview_path)
    index_records = read_csv_records(index_path)
    if len(preview_records) != len(index_records):
        raise ValueError("rename_preview.csv 与 design_index.csv 条数不一致，停止同步原始文件名。")

    backup_dir = output / "data" / "backups"
    backup_file(preview_path, backup_dir)
    backup_file(index_path, backup_dir)

    rename_pairs: List[Tuple[Path, Path]] = []
    updated_preview_by_old_path: Dict[str, Tuple[str, str]] = {}

    for record in preview_records:
        source_path = Path(record.original_path)
        if not source_path.exists():
            continue
        target_path = source_path.with_name(record.new_name)
        if target_path == source_path:
            updated_preview_by_old_path[str(source_path)] = (str(source_path), source_path.name)
            continue
        if target_path.exists():
            try:
                same_file = source_path.samefile(target_path)
            except FileNotFoundError:
                same_file = False
            if not same_file:
                raise FileExistsError(f"目标文件已存在，无法同步原始名称: {target_path}")
        rename_pairs.append((source_path, target_path))
        updated_preview_by_old_path[str(source_path)] = (str(target_path), target_path.name)

    rename_log_rows: List[Dict[str, str]] = []
    renamed_count = 0
    for source_path, target_path in rename_pairs:
        if source_path.name.lower() == target_path.name.lower():
            temp_path = source_path.with_name(f"__codex_tmp__{source_path.name}")
            while temp_path.exists():
                temp_path = source_path.with_name(f"__codex_tmp__{datetime.now().strftime('%H%M%S%f')}_{source_path.name}")
            source_path.rename(temp_path)
            temp_path.rename(target_path)
        else:
            source_path.rename(target_path)
        renamed_count += 1
        rename_log_rows.append({
            "old_path": str(source_path),
            "new_path": str(target_path),
            "new_name": target_path.name,
        })

    for record in preview_records:
        updated = updated_preview_by_old_path.get(record.original_path)
        if updated:
            record.original_path, record.original_name = updated

    index_by_hash_and_name: Dict[Tuple[str, str], Record] = {
        (record.file_hash, record.new_name): record for record in index_records
    }
    for preview_record in preview_records:
        match = index_by_hash_and_name.get((preview_record.file_hash, preview_record.new_name))
        if match:
            match.original_path = preview_record.original_path
            match.original_name = preview_record.original_name

    write_csv(preview_path, [record.to_csv_row() for record in preview_records])
    write_csv(index_path, [record.to_csv_row() for record in index_records])
    write_json(output / "data" / "design_index.json", index_records)
    write_html(output / "index.html", index_records)

    rename_log_path = output / "data" / "source_rename_log.csv"
    with rename_log_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["old_path", "new_path", "new_name"])
        writer.writeheader()
        writer.writerows(rename_log_rows)

    print(f"已同步原始文件名: {output}")
    print(f"重命名数量: {renamed_count}")
    print(f"记录文件: {rename_log_path}")


def command_scan(args: argparse.Namespace) -> None:
    source = Path(args.source).expanduser().resolve()
    output = Path(args.output).expanduser().resolve()
    ensure_output_dirs(output)
    records = scan_source(source)
    preview_path = output / "data" / "rename_preview.csv"
    write_csv(preview_path, [record.to_csv_row() for record in records])
    print(f"已生成预览清单: {preview_path}")
    print(f"共扫描 PDF: {len(records)}")


def command_build(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    ensure_output_dirs(output)
    reset_build_artifacts(output)
    preview_path = output / "data" / "rename_preview.csv"
    records = read_csv_records(preview_path)
    used_names: Dict[str, int] = {}
    built_records: List[Record] = []

    for record in records:
        source_path = Path(record.original_path)
        proposed_name = record.new_name or suggest_new_name(record)
        destination_name = dedupe_destination_name(proposed_name, used_names)
        record.new_name = destination_name
        destination = destination_for_status(output, record.status, destination_name)
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source_path, destination)
        thumbnail_key = hashlib.md5(destination_name.encode("utf-8")).hexdigest()
        record.thumbnail_path = generate_thumbnail(destination, output / "thumbnails", thumbnail_key)
        built_records.append(record)

    write_csv(output / "data" / "design_index.csv", [record.to_csv_row() for record in built_records])
    write_json(output / "data" / "design_index.json", built_records)
    write_html(output / "index.html", built_records)
    print(f"已完成建库: {output}")
    print(f"共复制 PDF: {len(built_records)}")


def append_record_to_index(index_path: Path, record: Record) -> List[Record]:
    records = read_csv_records(index_path) if index_path.exists() else []
    records.append(record)
    return records


def command_add(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    ensure_output_dirs(output)
    source_file = Path(args.file).expanduser().resolve()
    file_hash = sha256_file(source_file)
    record = Record(
        original_path=str(source_file),
        original_name=source_file.name,
        new_name="",
        product_category=args.product_category,
        product_series=args.product_series or detect_product_series(str(source_file), source_file.stem, args.product_code),
        product_code=args.product_code,
        spec=args.spec,
        package_type=args.package_type,
        date=normalize_date(args.date),
        version=args.version.upper(),
        channel=args.channel,
        status=args.status,
        design_number=args.design_number or "",
        customer=args.customer or "",
        notes=args.notes or "",
        file_hash=file_hash,
        duplicate_group="",
    )
    record.new_name = suggest_new_name(record)
    destination = destination_for_status(output, record.status, record.new_name)
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source_file, destination)
    thumbnail_key = hashlib.md5(record.new_name.encode("utf-8")).hexdigest()
    record.thumbnail_path = generate_thumbnail(destination, output / "thumbnails", thumbnail_key)

    index_path = output / "data" / "design_index.csv"
    records = append_record_to_index(index_path, record)
    write_csv(index_path, [item.to_csv_row() for item in records])
    write_json(output / "data" / "design_index.json", records)
    write_html(output / "index.html", records)
    print(f"已新增设计稿: {destination}")


def command_site(args: argparse.Namespace) -> None:
    output = Path(args.output).expanduser().resolve()
    index_path = output / "data" / "design_index.csv"
    records = read_csv_records(index_path)
    write_json(output / "data" / "design_index.json", records)
    write_html(output / "index.html", records)
    print(f"已重建网页: {output / 'index.html'}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="设计稿工作台工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    scan_parser = subparsers.add_parser("scan", help="扫描原始设计稿并生成预览 CSV")
    scan_parser.add_argument("--source", required=True, help="原始设计稿目录")
    scan_parser.add_argument("--output", required=True, help="资料库输出目录")
    scan_parser.set_defaults(func=command_scan)

    build_parser_cmd = subparsers.add_parser("build", help="根据 rename_preview.csv 建立资料库")
    build_parser_cmd.add_argument("--output", required=True, help="资料库输出目录")
    build_parser_cmd.set_defaults(func=command_build)

    add_parser = subparsers.add_parser("add", help="新增单个设计稿到资料库")
    add_parser.add_argument("--output", required=True, help="资料库输出目录")
    add_parser.add_argument("--file", required=True, help="待加入的 PDF 文件")
    add_parser.add_argument("--product-category", required=True, choices=PRODUCT_CATEGORIES, help="产品分类")
    add_parser.add_argument("--product-series", help="产品系列，如 B15、BT77、V字卷")
    add_parser.add_argument("--product-code", required=True, help="产品编码")
    add_parser.add_argument("--spec", required=True, help="核心规格")
    add_parser.add_argument("--package-type", required=True, choices=PACKAGE_TYPES, help="包装类型")
    add_parser.add_argument("--date", required=True, help="日期，支持 YYYYMMDD 或 YYMMDD")
    add_parser.add_argument("--version", required=True, help="版本，如 V1")
    add_parser.add_argument("--channel", default="其他", help="渠道")
    add_parser.add_argument("--status", default="进行中", help="状态")
    add_parser.add_argument("--design-number", help="设计图号")
    add_parser.add_argument("--customer", help="客户")
    add_parser.add_argument("--notes", help="备注")
    add_parser.set_defaults(func=command_add)

    site_parser = subparsers.add_parser("site", help="根据 design_index.csv 重建网页与 JSON")
    site_parser.add_argument("--output", required=True, help="资料库输出目录")
    site_parser.set_defaults(func=command_site)

    apply_renames_parser = subparsers.add_parser("apply-renames", help="应用网页导出的改名清单并重建设计稿工作台")
    apply_renames_parser.add_argument("--output", required=True, help="资料库输出目录")
    apply_renames_parser.add_argument("--rename-csv", required=True, help="网页导出的改名清单 CSV")
    apply_renames_parser.set_defaults(func=command_apply_renames)

    apply_delete_parser = subparsers.add_parser("apply-delete-list", help="应用网页导出的删除清单并重建设计稿工作台")
    apply_delete_parser.add_argument("--output", required=True, help="资料库输出目录")
    apply_delete_parser.add_argument("--delete-csv", required=True, help="网页导出的删除清单 CSV")
    apply_delete_parser.set_defaults(func=command_apply_delete_list)

    sync_updates_parser = subparsers.add_parser("sync-source-updates", help="将原始设计稿目录中的新增 PDF 增量同步到工作台")
    sync_updates_parser.add_argument("--source", required=True, help="原始设计稿目录")
    sync_updates_parser.add_argument("--output", required=True, help="资料库输出目录")
    sync_updates_parser.set_defaults(func=command_sync_source_updates)

    sync_source_parser = subparsers.add_parser("sync-source-names", help="将原始设计稿目录文件名同步为当前工作台正式名称")
    sync_source_parser.add_argument("--output", required=True, help="资料库输出目录")
    sync_source_parser.set_defaults(func=command_sync_source_names)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
