import sys, os, unittest
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
import probe


class TestClassify(unittest.TestCase):
    def test_200_is_ok(self):
        self.assertEqual(probe.classify(200), "ok")

    def test_429_is_ratelimited(self):
        self.assertEqual(probe.classify(429), "ratelimited")

    def test_401_is_auth_error(self):
        self.assertEqual(probe.classify(401), "auth_error")

    def test_403_is_auth_error(self):
        self.assertEqual(probe.classify(403), "auth_error")

    def test_500_is_unavailable(self):
        self.assertEqual(probe.classify(500), "unavailable")

    def test_502_is_unavailable(self):
        self.assertEqual(probe.classify(502), "unavailable")

    def test_400_is_unavailable(self):
        self.assertEqual(probe.classify(400), "unavailable")

    def test_404_is_unavailable(self):
        self.assertEqual(probe.classify(404), "unavailable")


import json, tempfile


class TestLoadConfig(unittest.TestCase):
    def _write(self, obj):
        f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
        json.dump(obj, f)
        f.close()
        return f.name

    def test_loads_valid_config(self):
        path = self._write({"base_url": "https://x", "auto_route": ["m1"], "manual_only": []})
        cfg = probe.load_config(path)
        self.assertEqual(cfg["base_url"], "https://x")
        self.assertEqual(cfg["auto_route"], ["m1"])

    def test_default_timeout_when_missing(self):
        path = self._write({"base_url": "https://x", "auto_route": ["m1"]})
        cfg = probe.load_config(path)
        self.assertEqual(cfg["timeout_seconds"], 10)

    def test_missing_base_url_raises(self):
        path = self._write({"auto_route": ["m1"]})
        with self.assertRaises(ValueError):
            probe.load_config(path)

    def test_empty_auto_route_raises(self):
        path = self._write({"base_url": "https://x", "auto_route": []})
        with self.assertRaises(ValueError):
            probe.load_config(path)

    def test_manual_only_defaults_empty(self):
        path = self._write({"base_url": "https://x", "auto_route": ["m1"]})
        cfg = probe.load_config(path)
        self.assertEqual(cfg["manual_only"], [])


class TestGetToken(unittest.TestCase):
    def setUp(self):
        self._saved = {k: os.environ.get(k) for k in ("ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_API_KEY")}
        for k in self._saved:
            os.environ.pop(k, None)

    def tearDown(self):
        for k, v in self._saved.items():
            if v is None:
                os.environ.pop(k, None)
            else:
                os.environ[k] = v

    def test_reads_auth_token(self):
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "tok-abc"
        self.assertEqual(probe.get_token(), "tok-abc")

    def test_falls_back_to_api_key(self):
        os.environ["ANTHROPIC_API_KEY"] = "key-xyz"
        self.assertEqual(probe.get_token(), "key-xyz")

    def test_auth_token_preferred(self):
        os.environ["ANTHROPIC_AUTH_TOKEN"] = "tok-abc"
        os.environ["ANTHROPIC_API_KEY"] = "key-xyz"
        self.assertEqual(probe.get_token(), "tok-abc")

    def test_missing_raises(self):
        with self.assertRaises(RuntimeError):
            probe.get_token()


class TestProbeModel(unittest.TestCase):
    def test_returns_ok_on_200(self):
        probe._send = lambda url, data, headers, timeout: (200, b'{"id":"x"}')
        cat, status, _ = probe.probe_model("https://x", "tok", "m1", 10)
        self.assertEqual(cat, "ok")
        self.assertEqual(status, 200)

    def test_returns_ratelimited_on_429(self):
        probe._send = lambda url, data, headers, timeout: (429, b'rate')
        cat, status, _ = probe.probe_model("https://x", "tok", "m1", 10)
        self.assertEqual(cat, "ratelimited")

    def test_returns_auth_error_on_401(self):
        probe._send = lambda url, data, headers, timeout: (401, b'no')
        cat, _, _ = probe.probe_model("https://x", "tok", "m1", 10)
        self.assertEqual(cat, "auth_error")

    def test_network_error_is_unavailable(self):
        def boom(url, data, headers, timeout):
            raise OSError("connection refused")
        probe._send = boom
        cat, status, detail = probe.probe_model("https://x", "tok", "m1", 10)
        self.assertEqual(cat, "unavailable")
        self.assertIn("connection refused", detail)

    def test_sends_both_auth_headers(self):
        captured = {}
        def spy(url, data, headers, timeout):
            captured.update(headers)
            return (200, b"{}")
        probe._send = spy
        probe.probe_model("https://x", "tok", "m1", 10)
        self.assertEqual(captured.get("x-api-key"), "tok")
        self.assertEqual(captured.get("Authorization"), "Bearer tok")
        self.assertEqual(captured.get("anthropic-version"), "2023-06-01")


class TestRun(unittest.TestCase):
    def _cfg(self, auto):
        return {"base_url": "https://x", "timeout_seconds": 10, "auto_route": auto, "manual_only": []}

    def test_selects_first_ok(self):
        probe.probe_model = lambda b, t, m, to: ("ok", 200, "{}")
        out = probe.run(self._cfg(["m1", "m2"]), "tok")
        self.assertEqual(out["selected"], "m1")
        self.assertEqual(len(out["results"]), 1)

    def test_skips_ratelimited_to_next(self):
        seq = {"m1": ("ratelimited", 429, "rl"), "m2": ("ok", 200, "{}")}
        probe.probe_model = lambda b, t, m, to: seq[m]
        out = probe.run(self._cfg(["m1", "m2"]), "tok")
        self.assertEqual(out["selected"], "m2")
        self.assertEqual(len(out["results"]), 2)

    def test_auth_error_stops_immediately(self):
        probe.probe_model = lambda b, t, m, to: ("auth_error", 401, "no")
        out = probe.run(self._cfg(["m1", "m2"]), "tok")
        self.assertIsNone(out["selected"])
        self.assertEqual(out["stopped_reason"], "auth_error")
        self.assertEqual(len(out["results"]), 1)

    def test_all_unavailable_exhausted(self):
        probe.probe_model = lambda b, t, m, to: ("unavailable", 500, "err")
        out = probe.run(self._cfg(["m1", "m2"]), "tok")
        self.assertIsNone(out["selected"])
        self.assertEqual(out["stopped_reason"], "exhausted")
        self.assertEqual(len(out["results"]), 2)

    def test_only_model_probes_single(self):
        probe.probe_model = lambda b, t, m, to: ("ok", 200, "{}")
        out = probe.run(self._cfg(["m1", "m2"]), "tok", only_model="claude-fable-5")
        self.assertEqual(out["selected"], "claude-fable-5")
        self.assertEqual(out["stopped_reason"], "manual")
        self.assertEqual(len(out["results"]), 1)
        self.assertEqual(out["results"][0][0], "claude-fable-5")


class TestFormatOutput(unittest.TestCase):
    def test_recommend_line_on_success(self):
        out = {"selected": "claude-opus-5",
               "results": [("claude-opus-5", "ok", 200, "{}")],
               "stopped_reason": None}
        text = probe.format_output(out)
        self.assertIn("RECOMMEND: claude-opus-5", text)
        self.assertIn("/model claude-opus-5", text)

    def test_recommend_none_on_exhausted(self):
        out = {"selected": None,
               "results": [("m1", "unavailable", 500, "e"), ("m2", "ratelimited", 429, "r")],
               "stopped_reason": "exhausted"}
        text = probe.format_output(out)
        self.assertIn("RECOMMEND: none", text)
        self.assertIn("exhausted", text)

    def test_auth_error_shows_token_hint(self):
        out = {"selected": None,
               "results": [("m1", "auth_error", 401, "no")],
               "stopped_reason": "auth_error"}
        text = probe.format_output(out)
        self.assertIn("token", text.lower())
        self.assertIn("RECOMMEND: none", text)


if __name__ == "__main__":
    unittest.main()
