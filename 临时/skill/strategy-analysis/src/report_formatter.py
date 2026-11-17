# -*- coding: utf-8 -*-
"""Excel报告格式化: 中文表头、百分比格式、筛选器、冻结首行。"""
from __future__ import annotations

from typing import Dict, Iterable, Optional

from openpyxl import load_workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter


DEFAULT_HEADER_MAP = {
    "feature": "特征名",
    "feature_name": "特征名称",
    "desc": "中文解释",
    "feature_type": "特征类型",
    "condition": "规则条件SQL",
    "rule_desc": "规则阈值",
    "y_label": "目标标签",
    "strategy_rule": "策略规则",
    "feature_combo": "特征组合数",
    "coverage": "覆盖率",
    "dev_coverage": "开发集覆盖率",
    "bad_rate": "命中坏率",
    "base_bad_rate": "整体坏率",
    "hit_rate": "命中率",
    "hit_rate_7d": "近7天命中率",
    "pre_reject_rate": "上线前拒绝率",
    "post_reject_rate": "上线后拒绝率",
    "absolute_increase": "拒绝率绝对上升",
    "relative_increase": "拒绝率相对上升",
    "absolute_reject_rate_increase": "拒绝率绝对上升",
    "relative_reject_rate_increase": "拒绝率相对上升",
    "lift": "Lift",
    "dev_lift": "开发集Lift",
    "iv": "IV值",
    "psi": "PSI稳定性",
    "global_psi": "全局PSI",
    "lift_fpd_k30": "Lift(首逾30天)",
    "lift_if_out_30d": "Lift(30天外诉)",
    "recommendation": "建议",
    "hit_count": "有效命中数",
    "global_hit_count": "全量命中数",
    "bad_count": "坏样本数",
    "dev_bad_count": "开发集坏样本数",
    "recent_7d_total": "近7天样本数",
    "hit_count_7d": "近7天命中数",
    "new_reject_count": "新增拒绝数",
    "original_reject_count": "原始拒绝数",
    "group_col": "客群字段",
    "group_value": "客群取值",
    "valid_total": "有效样本数",
    "stability_psi": "7天稳定PSI",
    "validation_result": "验证结论",
}

DEFAULT_PERCENT_HEADERS = {
    "覆盖率",
    "开发集覆盖率",
    "命中坏率",
    "整体坏率",
    "命中率",
    "近7天命中率",
    "上线前拒绝率",
    "上线后拒绝率",
    "拒绝率绝对上升",
    "拒绝率相对上升",
    "平均覆盖率",
    "平均命中率",
    "平均拒绝率绝对上升",
    "平均拒绝率相对上升",
}

SUMMARY_PERCENT_KEYWORDS = ("率", "覆盖")


def format_excel_report(
    path: str,
    header_map: Optional[Dict[str, str]] = None,
    percent_headers: Optional[Iterable[str]] = None,
) -> None:
    """Apply standard strategy-analysis report formatting in-place."""
    workbook = load_workbook(path)
    merged_header_map = dict(DEFAULT_HEADER_MAP)
    if header_map:
        merged_header_map.update(header_map)
    merged_percent_headers = set(DEFAULT_PERCENT_HEADERS)
    if percent_headers:
        merged_percent_headers.update(percent_headers)

    for worksheet in workbook.worksheets:
        header_positions = _rename_headers(worksheet, merged_header_map)
        _format_header(worksheet)
        _format_percent_columns(worksheet, header_positions, merged_percent_headers)
        _format_summary_values(worksheet)
        _autosize_columns(worksheet)
    workbook.save(path)


def _rename_headers(worksheet, header_map: Dict[str, str]) -> Dict[str, int]:
    header_positions = {}
    if worksheet.max_row < 1:
        return header_positions
    for cell in worksheet[1]:
        if cell.value in header_map:
            cell.value = header_map[cell.value]
        if cell.value:
            header_positions[str(cell.value)] = cell.column
    return header_positions


def _format_header(worksheet) -> None:
    fill = PatternFill("solid", fgColor="1F4E78")
    font = Font(color="FFFFFF", bold=True)
    for cell in worksheet[1]:
        cell.fill = fill
        cell.font = font
        cell.alignment = Alignment(horizontal="center", vertical="center")
    worksheet.freeze_panes = "A2"
    worksheet.auto_filter.ref = worksheet.dimensions


def _format_percent_columns(worksheet, header_positions: Dict[str, int], percent_headers: set) -> None:
    for header, col_idx in header_positions.items():
        if header not in percent_headers:
            continue
        for row_idx in range(2, worksheet.max_row + 1):
            cell = worksheet.cell(row_idx, col_idx)
            if isinstance(cell.value, (int, float)):
                cell.number_format = "0.00%"


def _format_summary_values(worksheet) -> None:
    if worksheet.max_column < 2:
        return
    first_header = worksheet.cell(1, 1).value
    second_header = worksheet.cell(1, 2).value
    if first_header not in ("指标", "metric") or second_header not in ("数值", "值", "value"):
        return
    for row_idx in range(2, worksheet.max_row + 1):
        metric = worksheet.cell(row_idx, 1).value
        value_cell = worksheet.cell(row_idx, 2)
        if metric and any(keyword in str(metric) for keyword in SUMMARY_PERCENT_KEYWORDS):
            if isinstance(value_cell.value, (int, float)) and abs(value_cell.value) <= 10:
                value_cell.number_format = "0.00%"


def _autosize_columns(worksheet) -> None:
    for col_idx in range(1, worksheet.max_column + 1):
        col_letter = get_column_letter(col_idx)
        max_len = 8
        for row_idx in range(1, min(worksheet.max_row, 200) + 1):
            value = worksheet.cell(row_idx, col_idx).value
            if value is not None:
                max_len = max(max_len, min(len(str(value)), 50))
        worksheet.column_dimensions[col_letter].width = max_len + 2
