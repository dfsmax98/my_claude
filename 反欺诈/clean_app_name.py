"""清理 applist_tag_merged_v3.csv 的 app_name 列：逗号、空格、Tab 等 → -

用法: python clean_app_name.py
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

SRC = Path(r'd:\my_claude\反欺诈\applist_tag_merged_v3.csv')
DST = Path(r'd:\my_claude\反欺诈\applist_tag_merged_v3_clean.csv')


def clean_name(s: object) -> object:
    if not isinstance(s, str):
        return s
    # 所有空白字符（空格/Tab/全角空格/零宽字符）和逗号统一替换为 -
    s = re.sub(r'[\s,，​-\u200F⁠﻿]+', '-', s)
    # 折叠多个连续 -
    s = re.sub(r'-+', '-', s).strip('-')
    return s


def main() -> int:
    print(f'读取: {SRC}')
    df = pd.read_csv(SRC, dtype=str, keep_default_na=False)
    print(f'  {len(df)} 行 × {len(df.columns)} 列')
    print(f'  列名: {df.columns.tolist()}')

    if 'app_name' not in df.columns:
        print('ERROR: 没有 app_name 列', file=sys.stderr)
        return 1

    before = df['app_name'].copy()
    df['app_name'] = df['app_name'].map(clean_name)

    changed = (before != df['app_name']).sum()
    print(f'  app_name 被改写: {changed} 行')

    if changed:
        # 写示例到文件，避免 Windows GBK 终端打不出零宽字符
        sample = df[before != df['app_name']][['app_package', 'app_name']].head(20)
        sample.insert(1, 'app_name_原', before[before != df['app_name']].head(20).values)
        sample_path = DST.with_suffix('.sample.csv')
        sample.to_csv(sample_path, index=False, encoding='utf-8-sig')
        print(f'  示例（20 行）已写入: {sample_path}')

    # 空值/全 - 的检查
    empty = (df['app_name'] == '').sum() + (df['app_name'] == '-').sum()
    if empty:
        print(f'  WARN: 清理后 {empty} 行 app_name 为空或全是分隔符')

    if 'reason' in df.columns:
        df = df.drop(columns=['reason'])
        print(f'  已删除 reason 列，剩余列: {df.columns.tolist()}')

    print(f'\n写出: {DST}')
    df.to_csv(DST, index=False, encoding='utf-8')
    print(f'  完成')
    return 0


if __name__ == '__main__':
    sys.exit(main())
