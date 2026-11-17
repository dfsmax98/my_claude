import importlib.util
import sys
import types
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def load_module(name, path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def sample_config():
    return {
        "feature_group": "contact_risk",
        "output_table": "d_dq.dfs_contact_risk",
        "sample_table": {
            "preloan": "d_dq.dfs_dq_fqz_base_final",
            "inloan": "d_dq.dfs_dz_fqz_base_final",
            "primary_keys": {
                "preloan": ["cust_no", "apply_no"],
                "inloan": ["cust_no", "order_no", "trans_seqno", "rsk_log_id"],
            },
            "time_field": {
                "preloan": "close_datetime",
                "inloan": "create_datetime",
            },
            "target_fields": {
                "preloan": ["apply_result", "cust_group_dq", "fpd_k30"],
                "inloan": ["risk_decision_result", "cust_group_dz", "fpd_k30"],
            },
        },
        "data_sources": [
            {
                "name": "contacts",
                "table": "default.t_bd_cust_relation_info",
                "join_field": "cust_no",
                "time_field": "create_datetime",
                "partition_field": "dt",
                "select_fields": ["cust_no", "relation_mobile_no", "create_datetime", "dt"],
                "filters": ["relation_mobile_no IS NOT NULL"],
            }
        ],
        "features": [
            {
                "name": "contact_valid_phone_cnt",
                "desc": "valid phone count",
                "source": "contacts",
                "agg": "COUNT_DISTINCT",
                "field": "relation_mobile_no",
                "condition": "LENGTH(relation_mobile_no) = 11",
                "window": "365d",
            }
        ],
    }


class FeatureSqlModeTests(unittest.TestCase):
    def test_labeled_mode_adds_label_filter_without_drop(self):
        gen = load_module("generate_feature_sql", ROOT / "scripts" / "generate_feature_sql.py")
        mode = gen.normalize_modes(sample_config(), ["labeled"])[0]

        sql = gen.generate_single_source_sql(sample_config(), "preloan", "contacts", mode)

        self.assertIn("CREATE TABLE IF NOT EXISTS d_dq.dfs_contact_risk_preloan_labeled_contacts AS", sql)
        self.assertNotIn("DROP TABLE", sql)
        self.assertIn("s.fpd_k30 >= 0", sql)
        self.assertNotIn("DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)", sql)
        self.assertIn("LENGTH(contacts.relation_mobile_no) = 11", sql)

    def test_recent7d_mode_adds_time_filter_without_label_filter(self):
        gen = load_module("generate_feature_sql_recent", ROOT / "scripts" / "generate_feature_sql.py")
        mode = gen.normalize_modes(sample_config(), ["recent7d"])[0]

        sql = gen.generate_single_source_sql(sample_config(), "inloan", "contacts", mode)

        self.assertIn("CREATE TABLE IF NOT EXISTS d_dq.dfs_contact_risk_inloan_recent7d_contacts AS", sql)
        self.assertIn("s.create_datetime >= DATE_SUB(CURRENT_DATE(), INTERVAL 7 DAY)", sql)
        self.assertNotIn("s.fpd_k30 >= 0", sql)

    def test_executor_refuses_forbidden_sql(self):
        fake_db = types.ModuleType("db_connector")
        fake_db.get_connection = lambda *args, **kwargs: None
        sys.modules["db_connector"] = fake_db

        executor = load_module("execute_feature_pipeline", ROOT / "scripts" / "execute_feature_pipeline.py")

        self.assertTrue(executor.is_forbidden_sql("DROP TABLE d_dq.bad_table")[0])
        self.assertTrue(executor.is_forbidden_sql("TRUNCATE TABLE d_dq.bad_table")[0])
        self.assertTrue(executor.is_forbidden_sql("DELETE FROM d_dq.bad_table")[0])
        self.assertFalse(executor.is_forbidden_sql("DELETE FROM d_dq.bad_table WHERE id = 1")[0])


if __name__ == "__main__":
    unittest.main()
