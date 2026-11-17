#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Agent 内部工具函数 - 仅供 Codex Agent 调用，不暴露给用户

提供统一的 skill 调用接口，简化 Agent 内部逻辑
"""

import os
import sys
import subprocess
from pathlib import Path
from typing import Optional, Union
from datetime import datetime, timedelta

# 路径配置
SKILL_ROOT = Path(r'D:\反欺诈策略室\daifansheng\新反欺诈\codex\skill')
OUTPUT_ROOT = Path(r'D:\反欺诈策略室\daifansheng\新反欺诈\codex\_temp\skill_output')


# ============ 通用工具 ============
def get_date_suffix() -> str:
    """生成日期后缀，用于特征表命名"""
    return datetime.now().strftime('%Y%m%d')


def is_fresh(file_path: Path, hours: int = 24) -> bool:
    """检查文件是否在指定小时内更新过"""
    if not file_path.exists():
        return False
    mtime = datetime.fromtimestamp(file_path.stat().st_mtime)
    return datetime.now() - mtime < timedelta(hours=hours)


def run_skill_script(skill_name: str, script_args: list[str], 
                    cwd: Optional[Path] = None, timeout: int = 300) -> tuple[bool, str, str]:
    """
    执行 skill 脚本，返回 (success, stdout, stderr)
    
    Args:
        skill_name: skill 目录名
        script_args: 脚本参数列表
        cwd: 工作目录（默认 skill 目录）
        timeout: 超时秒数
    """
    work_dir = cwd or (SKILL_ROOT / skill_name)
    cmd = [sys.executable] + script_args
    
    try:
        result = subprocess.run(
            cmd, cwd=work_dir, capture_output=True, text=True, timeout=timeout
        )
        return result.returncode == 0, result.stdout, result.stderr
    except subprocess.TimeoutExpired:
        return False, '', f'Timeout after {timeout}s'
    except Exception as e:
        return False, '', str(e)


# ============ table-explorer 调用 ============
def explore_table(table_name: str, fields_only: bool = False) -> dict:
    """
    Agent 内部: 探查表结构
    
    Returns:
        dict with keys: table, fields, time_field, join_key, sample_filters, success
    """
    output_dir = OUTPUT_ROOT / 'table_explorer'
    output_dir.mkdir(parents=True, exist_ok=True)
    
    cache_file = output_dir / f"{table_name.replace('.', '_')}.md"
    
    # 1. 检查缓存
    if cache_file.exists() and is_fresh(cache_file):
        return _parse_cached_md(cache_file, fields_only)
    
    # 2. 执行探查
    success, stdout, stderr = run_skill_script(
        'table-explorer',
        ['explore_table.py', table_name, '--output', str(output_dir)],
        timeout=120
    )
    
    if success and cache_file.exists():
        return _parse_cached_md(cache_file, fields_only)
    
    return {'success': False, 'error': stderr[:200] if stderr else 'Unknown error'}


def _parse_cached_md(md_path: Path, fields_only: bool) -> dict:
    """解析缓存的 md 文件"""
    content = md_path.read_text(encoding='utf-8')
    fields = []
    in_table = False
    
    for line in content.split('\n'):
        if '## 字段清单' in line:
            in_table = True
            continue
        if in_table and line.strip().startswith('|') and '字段名' not in line:
            parts = [p.strip() for p in line.split('|') if p.strip()]
            if len(parts) >= 2:
                fields.append({'name': parts[0], 'type': parts[1]})
        if in_table and not line.strip():
            break
    
    return {
        'table': md_path.stem.replace('_', '.'),
        'fields': [f['name'] for f in fields] if fields_only else fields,
        'time_field': _detect_time_field(fields),
        'join_key': _detect_join_key(fields),
        'sample_filters': _generate_filters(fields),
        'success': True
    }


def _detect_time_field(fields: list) -> Optional[str]:
    """自动识别时间字段"""
    time_keywords = ['time', 'date', 'datetime', 'create', 'update', 'dt']
    for f in fields:
        name = f.get('name', '').lower()
        if any(kw in name for kw in time_keywords):
            return f['name']
    return None


def _detect_join_key(fields: list) -> Optional[str]:
    """自动识别关联键"""
    join_keywords = ['cust_no', 'user_id', 'apply_no', 'order_no', 'id']
    for kw in join_keywords:
        for f in fields:
            if f.get('name') == kw:
                return kw
    return 'cust_no'  # 默认


def _generate_filters(fields: list) -> list[str]:
    """生成示例过滤条件"""
    filters = []
    for f in fields:
        name = f.get('name', '')
        if 'mobile' in name.lower() or 'phone' in name.lower():
            filters.append(f'{name} IS NOT NULL')
            filters.append(f'LENGTH({name}) = 11')
        elif 'type' in name.lower() or 'flag' in name.lower():
            filters.append(f'{name} IN (0,1)')
    return filters[:3]  # 限制数量


# ============ strategy-mining 调用 ============
def generate_features(feature_group: str, stage: str = 'preloan', 
                     config_overrides: Optional[dict] = None) -> dict:
    """
    Agent 内部: 执行特征衍生
    
    Returns:
        dict with keys: target_table, sql_file, dict_file, success, error
    """
    config_dir = SKILL_ROOT / 'strategy-mining' / 'configs'
    assets_dir = SKILL_ROOT / 'strategy-mining' / 'assets'
    
    # 1. 准备配置
    config_path = config_dir / f'{feature_group}.yaml'
    if not config_path.exists():
        # 复制模板
        template = config_dir / 'feature_template.yaml'
        if template.exists():
            import shutil
            shutil.copy(template, config_path)
            # 这里可添加 config_overrides 应用逻辑
        else:
            return {'success': False, 'error': 'Template config not found'}
    
    # 2. 生成 SQL + 字典
    success, stdout, stderr = run_skill_script(
        'strategy-mining',
        ['scripts/generate_feature_sql.py', '--config', str(config_path), '--output', str(assets_dir)],
        timeout=180
    )
    
    if not success:
        return {'success': False, 'error': stderr[:200] if stderr else 'SQL generation failed'}
    
    # 3. 解析输出文件
    date_suffix = get_date_suffix()
    target_table = f"d_dq.dfs_{feature_group}_{stage}_{date_suffix}"
    
    return {
        'success': True,
        'target_table': target_table,
        'sql_file': str(assets_dir / f'{feature_group}_features_{stage}.sql'),
        'dict_file': str(assets_dir / f'{feature_group}_dictionary.csv'),
        'logs': stdout[-200:] if stdout else ''
    }


def execute_feature_table(config_path: Union[str, Path]) -> dict:
    """
    Agent 内部: 执行建表（需数据库权限）
    
    Returns:
        dict with keys: success, table_name, logs
    """
    success, stdout, stderr = run_skill_script(
        'strategy-mining',
        ['scripts/execute_feature_pipeline.py', '--config', str(config_path)],
        timeout=600  # 建表可能较慢
    )
    
    return {
        'success': success,
        'logs': (stdout + stderr)[-500:],
        'error': stderr[:200] if not success and stderr else None
    }


# ============ strategy-analysis 调用 ============
def analyze_strategy(feature_table: str, scene: Optional[str] = None,
                    two_step: bool = True, config_overrides: Optional[dict] = None) -> dict:
    """
    Agent 内部: 执行策略评估
    
    Returns:
        dict with keys: success, user_summary, reports, result, fallback
    """
    # 1. 推断场景
    if scene is None:
        scene = 'dz' if ('inloan' in feature_table or '_dz_' in feature_table) else 'dq'
    
    # 2. 准备执行代码
    analysis_code = f'''
import sys, os
sys.path.insert(0, r'{SKILL_ROOT / "strategy-analysis"}')
from src.analyzer import StrategyAnalyzer
from src.config_loader import load_config

config = load_config()
if {config_overrides}:
    config.get("strategy_analysis", {{}}).update({config_overrides})

analyzer = StrategyAnalyzer(scene="{scene}", db_config=config.get("db", {{}}))

try:
    if {two_step}:
        result = analyzer.run_full(
            feature_table="{feature_table}",
            output_prefix=r"{OUTPUT_ROOT}/analysis/{scene}_{feature_table.split(".")[-1]}"
        )
        summary = f"Step1: {{result.get("step1_summary", "")}}\\nStep2: {{result.get("step2_summary", "")}}"
    else:
        path, summary_str, results = analyzer.run_step1(
            feature_table="{feature_table}",
            output_path=r"{OUTPUT_ROOT}/analysis/{scene}_{feature_table.split(".")[-1]}_step1.xlsx"
        )
        result = {{"step1_report": path, "summary": summary_str}}
        summary = summary_str
    print(f"RESULT:{{result}}")
    print(f"SUMMARY:{{summary}}")
except Exception as e:
    print(f"ERROR:{{str(e)}}")
'''
    
    # 3. 执行分析
    try:
        result = subprocess.run(
            [sys.executable, '-c', analysis_code],
            cwd=SKILL_ROOT / 'strategy-analysis',
            capture_output=True, text=True, timeout=600
        )
        
        # 解析输出
        output = result.stdout
        if 'RESULT:' in output and 'SUMMARY:' in output:
            import json
            # 简化解析，实际可更健壮
            summary = output.split('SUMMARY:')[1].strip() if 'SUMMARY:' in output else ''
            return {
                'success': True,
                'user_summary': summary,
                'reports': [f for f in output.split() if f.endswith('.xlsx')],
                'fallback': False
            }
        else:
            return _fallback_basic_analysis(feature_table, scene)
            
    except Exception as e:
        return _fallback_basic_analysis(feature_table, scene, str(e))


def _fallback_basic_analysis(feature_table: str, scene: str, error: str = None) -> dict:
    """兜底: 调用 anti_fraud_analyzer 生成基础报告"""
    try:
        sys.path.insert(0, r'D:\反欺诈策略室\daifansheng\新反欺诈\codex\策略分析')
        from anti_fraud_analyzer import AnalysisPipeline
        
        config = {
            'scene': scene,
            'y_column': 'fpd_k30',
            'output': {'report_mode': 'standard'}
        }
        pipeline = AnalysisPipeline(config=config)
        
        # 简化执行
        result = pipeline.run(
            from_csv=None,  # 实际需从 DB 加载
            feature_cols=None,
            output_path=str(OUTPUT_ROOT / 'analysis' / f'basic_{scene}.xlsx')
        )
        
        return {
            'success': False,
            'fallback': True,
            'user_summary': f"⚠️ 高级分析暂不可用 ({error or '未知错误'}), 已生成基础报告",
            'reports': [str(OUTPUT_ROOT / 'analysis' / f'basic_{scene}.xlsx')],
            'error': error
        }
    except:
        return {
            'success': False,
            'fallback': True,
            'user_summary': "⚠️ 分析执行失败，请检查数据库连接或联系管理员",
            'error': error or 'Pipeline execution failed'
        }


# ============ 编排入口 ============
def run_workflow(user_request: str, context: Optional[dict] = None) -> dict:
    """
    Agent 主入口: 根据用户需求自动编排 skill 调用
    
    Args:
        user_request: 用户自然语言请求
        context: 上下文信息（如已探查的表、已生成的特征表等）
    
    Returns:
        dict with keys: success, user_response, next_suggestion, artifacts
    """
    context = context or {}
    
    # 1. 解析需求（简化关键词匹配）
    if any(kw in user_request for kw in ['探查', '字段', '结构', '枚举']):
        # 表结构探查
        table_name = _extract_table_name(user_request)
        if not table_name:
            return _error_response("未识别到表名，请指定如 '探查 t_bd_xxx 字段'")
        
        result = explore_table(table_name)
        if result['success']:
            return {
                'success': True,
                'user_response': _format_explorer_response(result),
                'next_suggestion': "需要我帮你衍生这些特征吗？(回复'衍生{feature_group}特征')",
                'artifacts': {'table_info': result}
            }
        else:
            return _error_response(f"表结构探查失败: {result.get('error')}")
    
    elif any(kw in user_request for kw in ['衍生', '生成', '创建']) and '特征' in user_request:
        # 特征衍生
        feature_group = _extract_feature_group(user_request)
        stage = 'dz' if '贷中' in user_request or 'inloan' in user_request else 'dq'
        
        result = generate_features(feature_group, stage)
        if result['success']:
            return {
                'success': True,
                'user_response': f"✅ 特征表 {result['target_table']} 已就绪\n📄 特征字典: {result['dict_file']}",
                'next_suggestion': "是否需要执行策略分析评估效果？(回复'分析{table_name}')",
                'artifacts': {'feature_table': result['target_table'], 'dict': result['dict_file']}
            }
        else:
            return _error_response(f"特征衍生失败: {result.get('error')}")
    
    elif any(kw in user_request for kw in ['分析', '评估', '效果']) and ('特征' in user_request or '表' in user_request):
        # 策略分析
        feature_table = _extract_table_name(user_request) or context.get('feature_table')
        if not feature_table:
            return _error_response("未指定特征表，请提供表名如 '分析 d_dq.dfs_xxx'")
        
        two_step = '两步' not in user_request and '快速' not in user_request
        result = analyze_strategy(feature_table, two_step=two_step)
        
        return {
            'success': result['success'],
            'user_response': result['user_summary'],
            'next_suggestion': "需要查看详细报告请打开: " + (result['reports'][0] if result['reports'] else ''),
            'artifacts': {'reports': result['reports'], 'fallback': result.get('fallback')}
        }
    
    else:
        return _error_response("未识别需求，支持: 探查表结构 / 衍生特征 / 分析策略效果")


# ============ 辅助函数 ============
def _extract_table_name(text: str) -> Optional[str]:
    """从文本中提取表名 (d_dq.xxx 或 t_bd_xxx 格式)"""
    import re
    match = re.search(r'(d_dq\.[\w_]+|t_bd_[\w_]+|dwh\.[\w_\.]+)', text)
    return match.group(1) if match else None


def _extract_feature_group(text: str) -> Optional[str]:
    """从文本中提取特征组名"""
    # 简化: 取"衍生"和"特征"之间的内容
    import re
    match = re.search(r'衍生(.+?)特征', text)
    if match:
        return match.group(1).strip().replace(' ', '_')
    return None


def _format_explorer_response(result: dict) -> str:
    """格式化 table-explorer 结果为用户可读文本"""
    if not result['success']:
        return f"❌ 探查失败: {result.get('error')}"
    
    lines = [f"📋 {result['table']} 字段速览:"]
    
    # 主键/时间字段
    if result.get('join_key'):
        lines.append(f"🔑 关联键: {result['join_key']}")
    if result.get('time_field'):
        lines.append(f"⏰ 时间字段: {result['time_field']} (防穿越用)")
    
    # 字段列表（前 8 个）
    fields = result.get('fields', [])
    if fields:
        lines.append("\n📌 关键字段:")
        for f in fields[:8]:
            fname = f if isinstance(f, str) else f.get('name', '')
            lines.append(f"  - {fname}")
        if len(fields) > 8:
            lines.append(f"  ... 共{len(fields)}个字段")
    
    # 过滤建议
    if result.get('sample_filters'):
        lines.append("\n✅ 建议过滤条件:")
        for cond in result['sample_filters']:
            lines.append(f"  - {cond}")
    
    return "\n".join(lines)


def _error_response(message: str) -> dict:
    """标准化错误响应"""
    return {
        'success': False,
        'user_response': f"❌ {message}",
        'next_suggestion': "请检查输入或联系管理员",
        'artifacts': {}
    }


# ============ CLI 测试入口 ============
if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='Agent 工具函数测试')
    parser.add_argument('--explore', type=str, help='探查表: --explore t_bd_xxx')
    parser.add_argument('--generate', type=str, help='衍生特征: --generate app_risk')
    parser.add_argument('--analyze', type=str, help='分析策略: --analyze d_dq.dfs_xxx')
    parser.add_argument('--scene', type=str, default='dq', choices=['dq', 'dz'])
    parser.add_argument('--single-step', action='store_true', help='仅 Step1')
    
    args = parser.parse_args()
    
    if args.explore:
        result = explore_table(args.explore)
        print(_format_explorer_response(result))
        
    elif args.generate:
        result = generate_features(args.generate, stage='dz' if args.scene=='dz' else 'dq')
        if result['success']:
            print(f"✅ Target table: {result['target_table']}")
            print(f"📄 Dict: {result['dict_file']}")
        else:
            print(f"❌ Failed: {result['error']}")
            
    elif args.analyze:
        result = analyze_strategy(args.analyze, scene=args.scene, two_step=not args.single_step)
        print(result['user_summary'])
        if result['reports']:
            print(f"📄 Reports: {result['reports']}")
            
    else:
        print("Usage: python _agent_utils.py --explore|--generate|--analyze <name> [--scene dq|dz]")
