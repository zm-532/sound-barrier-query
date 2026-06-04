from __future__ import annotations

from dataclasses import asdict, dataclass


def column_number_to_name(number: int) -> str:
    name = ""
    while number:
        number, remainder = divmod(number - 1, 26)
        name = chr(65 + remainder) + name
    return name


@dataclass(frozen=True)
class StandardClause:
    sheet: str
    row: int
    column: int
    product: str
    item: str
    standard: str
    requirement: str
    group: str = "国内标准"

    @property
    def source_id(self) -> str:
        return f"{self.sheet}!{column_number_to_name(self.column)}{self.row}"

    @property
    def source_link(self) -> str:
        return f"#source={self.source_id}"

    def as_dict(self) -> dict[str, str | int]:
        data = asdict(self)
        data["source_id"] = self.source_id
        data["source_link"] = self.source_link
        return data


@dataclass(frozen=True)
class StandardTable:
    material: str
    title: str
    group: str
    base_columns: list[str]
    standard_columns: list[str]
    rows: list[dict[str, str | int]]
