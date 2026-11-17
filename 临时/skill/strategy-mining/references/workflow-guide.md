## 🔁 Automated Workflow: SQL → Temp Table → Python Analysis

> Complete automation pipeline for feature derivation and strategy mining

`mermaid
flowchart LR
    A[Feature Template] --> B[Generate SQL]
    B --> C[Execute: CREATE TABLE AS SELECT]
    C --> D[Temp Table Created]
    D --> E[Python: Read to DataFrame]
    E --> F[Join with Sample Table]
    F --> G[RuleMiner / Strategy Analysis]
    G --> H[Output: Rules / Insights]
    D -.-> I[Optional: DROP TABLE]
`

### Step-by-Step Execution

#### 1. Generate Feature SQL
`python
from rule_miner.feature_template import get_template

tpl = get_template('has_loan_app')
sql = tpl.generate_sql(
    event_time_col='create_time',
    cust_col='cust_no',
    table_name='dwd.app_install_log'
)
# Output: Standard StarRocks/Impala compatible SQL
`

#### 2. Execute SQL to Create Temp Table (Python)
`python
from rule_miner.feature_template import execute_feature_pipeline

result = execute_feature_pipeline(
    template=tpl,
    db_config={'host': 'sr-host', 'port': 9030, 'user': 'xxx', 'password': 'xxx', 'database': 'd_dq'},
    output_table='tmp_feature_loan_app_20260707',  # Naming convention: tmp_feature_{name}_{date}
    source_table='dwd.app_install_log'
)
# Creates: tmp_feature_loan_app_20260707 with derived features
# Returns: {feature_names, row_count, sample_sql, success}
`

#### 3. Read Temp Table & Join with Sample
`python
import pandas as pd
from impala.dbapi import connect

conn = connect(**db_config)

# Read feature temp table
feature_df = pd.read_sql("SELECT * FROM tmp_feature_loan_app_20260707", conn)

# Read sample table (pre-loan or in-loan)
sample_df = pd.read_sql("""
    SELECT apply_no, cust_no, close_datetime, fpd_k30, if_out_30d 
    FROM d_dq.dfs_dq_fqz_base_final
""", conn)

# Join derived features on cust_no (raw table feature derivation)
# Note: For wide table features, join on apply_no = req_flow_no instead
merged_df = sample_df.merge(feature_df, on='cust_no', how='left')
`

#### 4. Run Rule Mining / Strategy Analysis
`python
from rule_miner import mine_rules

# Execute rule mining with merged data
mining_result = mine_rules(
    df=merged_df,
    inputx=['loan_app_借贷_消费金融_2y'],  # Use generated feature name
    y='fpd_k30',  # Target label
    primary_key='cust_no',
    config={'mining': {'max_depth': 3}}
)

# Output: RuleMiningResult with rules, lift, coverage metrics
`

#### 5. Cleanup (Optional)
`python
# Drop temp tables after analysis
conn.cursor().execute("DROP TABLE IF EXISTS tmp_feature_loan_app_20260707")
conn.close()
`

### Pipeline Configuration

`yaml
# config/strategy_pipeline.yaml
pipeline:
  temp_table:
    prefix: "tmp_feature"
    naming: "{prefix}_{feature_name}_{YYYYMMDD}_{seq}"
    auto_drop: true  # Auto cleanup after analysis
    
  feature_derivation:
    module: "rule_miner.feature_template"
    enforce_paradigm: true  # Must use fixed time windows
    
  sample_join:
    pre_loan: "d_dq.dfs_dq_fqz_base_final"
    in_loan: "d_dq.dfs_dz_fqz_base_final"
    # Wide table join keys
    pre_loan_wide_key: "apply_no = req_flow_no"
    in_loan_wide_key: "rsk_log_id = req_flow_no"
    # Strategy sub-table join keys
    pre_loan_strategy_key: "apply_no = org_flow_no"
    in_loan_strategy_key: "rsk_log_id = org_flow_no"
    # Raw table join key (with time constraint for anti-leakage)
    raw_table_key: "cust_no + time_constraint"
    
  rule_mining:
    module: "rule_miner.mine_rules"
    default_config:
      mining.max_depth: 3
      hard_filter.min_bad: 10
`

### Error Handling & Monitoring

| Stage | Common Issues | Mitigation |
|-------|--------------|------------|
| SQL Generation | Invalid field names | Validate against data dictionary first |
| Temp Table Creation | Permission denied | Use 	mp_ prefix, request DBA approval for prod |
| Data Reading | Memory overflow | Add LIMIT clause, use chunked reading |
| Sample Join | Key mismatch | Wide table: verify req_flow_no; Raw table: verify cust_no + time constraint |
| Rule Mining | Low coverage | Adjust hard_filter.min_coverage_pct |

### Logging Requirements

All pipeline executions must log to WORKLOG.md:
`markdown
### 🤖 Strategy Mining Pipeline Run
- **Timestamp**: 2026-07-07 14:30:00
- **Templates Used**: has_loan_app, requent_sms_short
- **Temp Tables**: 	mp_feature_loan_app_20260707, 	mp_feature_sms_20260707
- **Sample Table**: d_dq.dfs_dq_fqz_base_final
- **Features Generated**: 7 (3 from SHORT + 4 from MEDIUM windows)
- **Rules Mined**: 12 rules with lift > 2.0
- **Cleanup**: ✅ Temp tables dropped
`
