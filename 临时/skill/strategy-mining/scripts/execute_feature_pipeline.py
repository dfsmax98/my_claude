#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
strategy-mining skill - 通用特征执行器 (extended timeout + progress logging)
用法: python execute_feature_pipeline.py --config configs/my_features.yaml
"""
import sys, os, yaml, logging, time, traceback, re

# 正确添加lib路径
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

from db_connector import get_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

DEFAULT_DERIVATION_MODES = ['labeled', 'recent7d']

def _mode_names(cfg, requested=None):
    if requested:
        return requested
    configured = cfg.get('derivation_modes')
    if not configured:
        return DEFAULT_DERIVATION_MODES
    if isinstance(configured, str):
        return [configured]
    names = []
    for item in configured:
        names.append(item.get('name') if isinstance(item, dict) else item)
    return names

def _sql_filename(feature_group, stage, source, mode):
    if mode == 'full':
        return feature_group + '_' + stage + '_' + source + '.sql'
    return feature_group + '_' + stage + '_' + mode + '_' + source + '.sql'

def find_sql_files(cfg, sql_dir, stages, modes, sources):
    files = []
    for stage in stages:
        for mode in modes:
            for source in sources:
                path = os.path.join(sql_dir, _sql_filename(cfg['feature_group'], stage, source, mode))
                if os.path.exists(path):
                    files.append((stage, mode, source, path))
                else:
                    logger.warning('SQL not found: '+path+' (skipping)')
    return files

def is_forbidden_sql(stmt):
    compact = re.sub(r'\s+', ' ', stmt.strip().lower())
    if re.search(r'\bdrop\s+(table|database)\b', compact):
        return True, 'DROP TABLE/DATABASE is forbidden'
    if re.search(r'\btruncate\s+table\b', compact):
        return True, 'TRUNCATE TABLE is forbidden'
    if re.search(r'\balter\s+table\b.*\bdrop\s+column\b', compact):
        return True, 'ALTER TABLE DROP COLUMN is forbidden'
    if re.search(r'\bdelete\s+from\b', compact) and not re.search(r'\bwhere\b', compact):
        return True, 'DELETE without WHERE is forbidden'
    return False, ''

def execute_sql(cursor, conn, sql_path):
    """Execute SQL file with statement-by-statement execution and progress logging"""
    with open(sql_path, 'r', encoding='utf-8') as f:
        sql_content = f.read()
    
    # Split by semicolon but keep DROP/CREATE together
    statements = []
    current = []
    for line in sql_content.split('\n'):
        stripped = line.strip()
        if not stripped or stripped.startswith('--'):
            continue
        current.append(line)
        if stripped.endswith(';'):
            stmt = '\n'.join(current).strip()
            if stmt:
                statements.append(stmt)
            current = []
    
    logger.info('Found '+str(len(statements))+' SQL statements to execute')
    
    for i, stmt in enumerate(statements, 1):
        if not stmt or stmt.startswith('--'):
            continue
        forbidden, reason = is_forbidden_sql(stmt)
        if forbidden:
            raise ValueError('Refusing forbidden SQL in '+sql_path+': '+reason)
        
        # Log statement preview
        preview = stmt[:100].replace('\n', ' ') + '...' if len(stmt) > 100 else stmt.replace('\n', ' ')
        logger.info('['+str(i)+'/'+str(len(statements))+'] Executing: '+preview)
        
        start = time.time()
        try:
            cursor.execute(stmt)
            conn.commit()
            elapsed = time.time() - start
            logger.info('  -> Completed in '+str(round(elapsed, 2))+'s')
        except Exception as e:
            logger.error('  -> FAILED: '+str(e)[:150])
            raise
    
    return True

def verify_table(cursor, table_name):
    try:
        logger.info('Verifying table: '+table_name)
        cursor.execute('SELECT COUNT(*) FROM '+table_name)
        count = cursor.fetchone()[0]
        logger.info('  -> Row count: '+str(count))
        return count
    except Exception as e:
        logger.warning('Verify failed: '+str(e)[:50])
        return None

def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--config', required=True)
    parser.add_argument('--sql-dir', default='assets')
    parser.add_argument('--stages', nargs='*', default=['preloan', 'inloan'])
    parser.add_argument('--modes', nargs='*', default=None,
                        help='Derivation modes to execute: labeled recent7d full')
    parser.add_argument('--sources', nargs='*', default=None,
                        help='Data source names to execute. Default: all config data_sources')
    args = parser.parse_args()
    
    cfg = yaml.safe_load(open(args.config, 'r', encoding='utf-8'))
    account = cfg.get('database',{}).get('account', 'starrocks_mysql')
    sources = args.sources or [d['name'] for d in cfg.get('data_sources', [])]
    modes = _mode_names(cfg, args.modes)
    
    logger.info('='*60)
    logger.info('Starting feature pipeline execution')
    logger.info('Config: '+args.config)
    logger.info('Account: '+account)
    logger.info('='*60)
    
    conn, cursor = get_connection(account, use_trino=False)
    
    try:
        sql_files = find_sql_files(cfg, args.sql_dir, args.stages, modes, sources)
        if not sql_files:
            logger.warning('No SQL files matched config/stages/modes/sources')
            return 0

        for stage, mode, source, sql_path in sql_files:
            logger.info('')
            logger.info('>>> Executing '+stage.upper()+' / '+mode+' / '+source+' <<<')
            logger.info('SQL file: '+sql_path)
            
            start_stage = time.time()
            if execute_sql(cursor, conn, sql_path):
                elapsed = time.time() - start_stage
                logger.info(stage+'/'+mode+'/'+source+' completed in '+str(round(elapsed/60, 2))+' minutes')
                
                base_table = cfg.get('output_table_'+stage, cfg['output_table']+'_'+stage)
                out_table = base_table + ('_'+source if mode == 'full' else '_'+mode+'_'+source)
                count = verify_table(cursor, out_table)
                logger.info('Table: '+out_table+' ('+str(count)+' rows)')
                
    except Exception as e:
        logger.error('Pipeline FAILED: '+str(e)[:200])
        logger.error('Full traceback:')
        traceback.print_exc()
        conn.rollback()
        return 1
    finally:
        cursor.close()
        conn.close()
        logger.info('Connection closed')
    
    logger.info('')
    logger.info('='*60)
    logger.info('Pipeline completed successfully!')
    logger.info('='*60)
    return 0

if __name__ == '__main__':
    sys.exit(main())
