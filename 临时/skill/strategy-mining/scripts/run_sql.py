#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
strategy-mining skill - Simple SQL Executor (BOM-safe)
??: python run_sql.py --sql assets/my_features_preloan.sql
"""
import sys, os, argparse, logging, time

# Add lib to path
script_dir = os.path.dirname(os.path.abspath(__file__))
lib_dir = os.path.join(script_dir, '..', 'lib')
sys.path.insert(0, lib_dir)

from db_connector import get_connection

logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
logger = logging.getLogger(__name__)

def execute_sql_file(sql_path, account='starrocks_mysql'):
    """Execute a SQL file statement by statement"""
    logger.info('Connecting to database...')
    conn, cursor = get_connection(account, use_trino=False)
    
    try:
        # Read file and strip BOM if present
        with open(sql_path, 'r', encoding='utf-8-sig') as f:
            sql_content = f.read()
        
        # Split by semicolon, keeping multi-line statements together
        statements = []
        current = []
        for line in sql_content.split('\n'):
            stripped = line.strip()
            if stripped and not stripped.startswith('--'):
                current.append(line)
            if stripped.endswith(';'):
                stmt = '\n'.join(current).strip()
                if stmt and not stmt.startswith('--'):
                    statements.append(stmt.rstrip(';'))
                current = []
        
        logger.info('Found {} statements to execute'.format(len(statements)))
        
        for i, stmt in enumerate(statements, 1):
            if not stmt.strip():
                continue
            preview = stmt[:80].replace('\n', ' ') + '...' if len(stmt) > 80 else stmt.replace('\n', ' ')
            logger.info('[{}/{}] Executing: {}'.format(i, len(statements), preview))
            
            start = time.time()
            cursor.execute(stmt)
            conn.commit()
            elapsed = time.time() - start
            logger.info('  -> Completed in {:.2f}s'.format(elapsed))
        
        logger.info('All statements executed successfully!')
        return True
        
    except Exception as e:
        logger.error('Execution failed: {}'.format(str(e)[:200]))
        conn.rollback()
        import traceback
        traceback.print_exc()
        return False
    finally:
        cursor.close()
        conn.close()
        logger.info('Connection closed')

def main():
    parser = argparse.ArgumentParser(description='Execute SQL file on StarRocks')
    parser.add_argument('--sql', required=True, help='Path to SQL file')
    parser.add_argument('--account', default='starrocks_mysql', help='Database account')
    args = parser.parse_args()
    
    if not os.path.exists(args.sql):
        logger.error('SQL file not found: {}'.format(args.sql))
        return 1
    
    success = execute_sql_file(args.sql, args.account)
    return 0 if success else 1

if __name__ == '__main__':
    sys.exit(main())
