from __future__ import annotations

from pathlib import Path
from typing import Iterable
from xml.etree import ElementTree
from zipfile import ZipFile

from .models import StandardClause, StandardTable

XML_NS = {
    "main": "http://schemas.openxmlformats.org/spreadsheetml/2006/main",
    "rel": "http://schemas.openxmlformats.org/officeDocument/2006/relationships",
    "pkgrel": "http://schemas.openxmlformats.org/package/2006/relationships",
}

ITEM_HEADER_KEYWORDS = ("检测项目", "项目名称", "内容/检测项目", "内容/项目名称")


def load_workbook_clauses(path: str | Path, group: str = "国内标准") -> list[StandardClause]:
    clauses: list[StandardClause] = []
    for sheet_name, rows in _iter_workbook_rows(path):
        table, header_columns = _rows_to_table(sheet_name, rows, group)
        if table is None:
            continue
        clauses.extend(_table_to_clauses(table, header_columns))
    return clauses


def load_workbook_tables(path: str | Path, group: str = "国内标准") -> list[StandardTable]:
    tables: list[StandardTable] = []
    for sheet_name, rows in _iter_workbook_rows(path):
        table, _ = _rows_to_table(sheet_name, rows, group)
        if table is not None:
            tables.append(table)
    return tables


def _iter_workbook_rows(path: str | Path) -> Iterable[tuple[str, list[tuple[int, dict[int, str]]]]]:
    workbook_path = Path(path)
    with ZipFile(workbook_path) as archive:
        shared_strings = _read_shared_strings(archive)
        sheets = _read_sheet_paths(archive)
        for sheet_name, sheet_path in sheets:
            if sheet_name.startswith("WpsReserved"):
                continue
            yield sheet_name, _read_sheet_rows(archive, sheet_path, shared_strings)


def _read_shared_strings(archive: ZipFile) -> list[str]:
    if "xl/sharedStrings.xml" not in archive.namelist():
        return []
    root = ElementTree.fromstring(archive.read("xl/sharedStrings.xml"))
    values: list[str] = []
    for item in root.findall("main:si", XML_NS):
        parts = [node.text or "" for node in item.findall(".//main:t", XML_NS)]
        values.append("".join(parts))
    return values


def _read_sheet_paths(archive: ZipFile) -> list[tuple[str, str]]:
    workbook = ElementTree.fromstring(archive.read("xl/workbook.xml"))
    rels = ElementTree.fromstring(archive.read("xl/_rels/workbook.xml.rels"))
    rel_targets = {
        rel.attrib["Id"]: _normalize_xl_path(rel.attrib["Target"])
        for rel in rels.findall("pkgrel:Relationship", XML_NS)
    }

    sheets: list[tuple[str, str]] = []
    for sheet in workbook.findall("main:sheets/main:sheet", XML_NS):
        rel_id = sheet.attrib[f"{{{XML_NS['rel']}}}id"]
        sheets.append((sheet.attrib["name"], rel_targets[rel_id]))
    return sheets


def _normalize_xl_path(target: str) -> str:
    target = target.lstrip("/")
    if target.startswith("xl/"):
        return target
    return f"xl/{target}"


def _read_sheet_rows(
    archive: ZipFile, sheet_path: str, shared_strings: list[str]
) -> list[tuple[int, dict[int, str]]]:
    root = ElementTree.fromstring(archive.read(sheet_path))
    rows: list[tuple[int, dict[int, str]]] = []
    for row in root.findall(".//main:sheetData/main:row", XML_NS):
        row_number = int(row.attrib["r"])
        values: dict[int, str] = {}
        for cell in row.findall("main:c", XML_NS):
            coordinate = cell.attrib.get("r", "")
            column = _column_index_from_cell(coordinate)
            text = _cell_text(cell, shared_strings)
            if text:
                values[column] = text
        rows.append((row_number, values))
    return rows


def _cell_text(cell: ElementTree.Element, shared_strings: list[str]) -> str:
    cell_type = cell.attrib.get("t")
    if cell_type == "inlineStr":
        return _clean_text("".join(node.text or "" for node in cell.findall(".//main:t", XML_NS)))

    value = cell.find("main:v", XML_NS)
    if value is None or value.text is None:
        return ""

    raw = value.text
    if cell_type == "s":
        index = int(raw)
        return _clean_text(shared_strings[index] if index < len(shared_strings) else "")
    return _clean_text(raw)


def _rows_to_table(
    sheet_name: str,
    rows: Iterable[tuple[int, dict[int, str]]],
    group: str,
) -> tuple[StandardTable | None, dict[str, int]]:
    materialized = list(rows)
    header_index = _find_header_index(materialized)
    if header_index is None:
        return None, {}

    _, header = materialized[header_index]
    item_col = _find_item_column(header)
    if item_col is None:
        return None, {}

    header_columns = {
        _display_header(value, group): column
        for column, value in sorted(header.items())
        if value
    }
    base_columns = [
        _display_header(value, group)
        for column, value in sorted(header.items())
        if value and column <= item_col
    ]
    standard_columns = [
        _display_header(value, group)
        for column, value in sorted(header.items())
        if value and column > item_col and not _skip_standard_column(value, group)
    ]

    if not base_columns or not standard_columns:
        return None, {}

    title = _table_title(sheet_name, materialized, header_index)
    table_rows = _data_rows(materialized[header_index + 1 :], header, base_columns, standard_columns, group)
    return (
        StandardTable(
            material=sheet_name,
            title=title,
            group=group,
            base_columns=base_columns,
            standard_columns=standard_columns,
            rows=table_rows,
        ),
        header_columns,
    )


def _find_header_index(rows: list[tuple[int, dict[int, str]]]) -> int | None:
    for index, (_, row) in enumerate(rows):
        values = list(row.values())
        if len(values) >= 2 and any(_is_item_header(value) for value in values):
            return index
    return None


def _find_item_column(header: dict[int, str]) -> int | None:
    for column, value in sorted(header.items()):
        if _is_item_header(value):
            return column
    return None


def _is_item_header(value: str) -> bool:
    return any(keyword in value for keyword in ITEM_HEADER_KEYWORDS)


def _display_header(value: str, group: str) -> str:
    if group == "国内标准" and ("检测项目" in value or "项目名称" in value):
        return "检测项目"
    return value


def _skip_standard_column(value: str, group: str) -> bool:
    return group == "国内标准" and value == "备注"


def _table_title(sheet_name: str, rows: list[tuple[int, dict[int, str]]], header_index: int) -> str:
    for _, row in rows[:header_index]:
        first_value = next((value for _, value in sorted(row.items()) if value), "")
        if first_value:
            return first_value
    return f"{sheet_name}技术要求"


def _data_rows(
    rows: Iterable[tuple[int, dict[int, str]]],
    header: dict[int, str],
    base_columns: list[str],
    standard_columns: list[str],
    group: str,
) -> list[dict[str, str | int]]:
    table_rows: list[dict[str, str | int]] = []
    header_by_column = {column: _display_header(value, group) for column, value in header.items()}
    current_base_values = {column: "" for column in base_columns}

    for row_number, row in rows:
        if not any(row.get(column_number, "") for column_number in header):
            continue

        display_row: dict[str, str | int] = {"source_row": row_number}
        for column_number, column_name in sorted(header_by_column.items()):
            if column_name not in base_columns and column_name not in standard_columns:
                continue
            value = row.get(column_number, "")
            if column_name in base_columns:
                if column_name != "序号" and value:
                    current_base_values[column_name] = value
                elif column_name != "序号" and not value:
                    value = current_base_values[column_name]
                display_row[column_name] = _coerce_cell_value(value)
            else:
                display_row[column_name] = value

        item_column = "检测项目" if "检测项目" in base_columns else "项目名称"
        if not str(display_row.get(item_column, "")).strip():
            continue
        table_rows.append(display_row)

    return table_rows


def _table_to_clauses(table: StandardTable, header_columns: dict[str, int]) -> list[StandardClause]:
    clauses: list[StandardClause] = []
    item_column = "检测项目" if "检测项目" in table.base_columns else "项目名称"
    product_column = _product_column(table.base_columns)

    for row in table.rows:
        item = str(row.get(item_column, "")).strip()
        product = str(row.get(product_column, "")).strip() if product_column else table.material
        if not product:
            product = table.material
        if not item:
            continue
        for standard in table.standard_columns:
            requirement = str(row.get(standard, "")).strip()
            if not requirement:
                continue
            clauses.append(
                StandardClause(
                    sheet=table.material,
                    row=int(row.get("source_row", 0) or 0),
                    column=header_columns.get(standard, 1),
                    product=product,
                    item=item,
                    standard=standard,
                    requirement=requirement,
                    group=table.group,
                )
            )
    return clauses


def _product_column(base_columns: list[str]) -> str | None:
    for candidate in ("部件", "产品名称"):
        if candidate in base_columns:
            return candidate
    return None


def _coerce_cell_value(value: str) -> str | int:
    stripped = value.strip()
    if stripped.isdigit():
        return int(stripped)
    return value


def _column_index_from_cell(coordinate: str) -> int:
    letters = ""
    for char in coordinate:
        if char.isalpha():
            letters += char
        else:
            break
    number = 0
    for letter in letters:
        number = number * 26 + ord(letter.upper()) - 64
    return number


def _clean_text(value: str) -> str:
    return value.replace("\r\n", "\n").strip()
