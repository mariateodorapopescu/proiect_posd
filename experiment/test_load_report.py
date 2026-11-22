"""Tests for load_report.py with synthetic rows."""
import contextlib
import io
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import load_report


def row(strategy, rate, p95=5.0, drops=0, api=10.0, kc=1.0, scenario="steady", e401=0, rps=None):
    return {"scenario": scenario, "strategy": strategy, "rate_target": str(rate), "rps": str(rps or rate),
            "p50_ms": "1", "p95_ms": str(p95), "p99_ms": "9", "dropped_iterations": str(drops),
            "status_200": "100", "status_401": str(e401), "status_403": "0", "status_5xx": "0",
            "api_cpu_load_pct": str(api), "keycloak_cpu_load_pct": str(kc),
            "api_mem_max_mib": "300", "keycloak_mem_max_mib": "700"}


class SummaryTests(unittest.TestCase):
    def test_groups_by_strategy_and_rate_with_median_and_range(self):
        rows = [row("jwt", 100, p95=p) for p in (3.0, 5.0, 40.0)] + [row("introspection", 100, p95=9.0, e401=7)]
        summary = load_report.summarize(rows)
        jwt = next(s for s in summary if s["strategy"] == "jwt")
        self.assertEqual((jwt["repeats"], jwt["p95_ms"]["median"], jwt["p95_ms"]["max"]), (3, 5.0, 40.0))
        self.assertEqual(next(s for s in summary if s["strategy"] == "introspection")["errors"], 7)

    def test_keycloak_down_rows_are_not_mixed_into_steady_groups(self):
        summary = load_report.summarize([row("jwt", 50), row("jwt", 50, scenario="keycloak_down", e401=99)])
        self.assertEqual((len(summary), summary[0]["repeats"], summary[0]["errors"]), (1, 1, 0))

    def test_cpu_slope_recovers_known_line(self):
        # CPU% = 10 + 0.1 * rps  ->  0.1 pct per req/s = 1.0 ms CPU per request, 10% fixed.
        rows = [row("jwt", r, api=10 + 0.1 * r) for r in (50, 100, 200, 400)] + [row("jwt", 800, api=500)]
        result = load_report.cpu_slope(rows, "jwt", "api", 50, 400)
        self.assertAlmostEqual(result["ms_cpu_per_request"], 1.0, places=6)
        self.assertAlmostEqual(result["fixed_cpu_pct"], 10.0, places=6)
        self.assertIsNone(load_report.cpu_slope(rows, "jwt", "api", 50, 50), "needs two distinct rates")

    def test_blank_stats_are_skipped_not_zero(self):
        blank = row("jwt", 50)
        blank["api_cpu_load_pct"] = ""
        summary = load_report.summarize([blank])
        self.assertIsNone(summary[0]["api_cpu_load_pct"])
        self.assertIn("| - |", load_report.to_markdown(summary))


class CliTests(unittest.TestCase):
    def test_writes_json_and_reports_missing_input(self):
        import csv
        with TemporaryDirectory() as directory:
            path = Path(directory) / "load.csv"
            rows = [row("jwt", 50), row("jwt", 100), row("introspection", 50), row("introspection", 100, api=20)]
            with path.open("w", newline="", encoding="utf-8") as handle:
                writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
                writer.writeheader()
                writer.writerows(rows)
            out = Path(directory) / "summary.json"
            with contextlib.redirect_stdout(io.StringIO()) as printed:
                self.assertEqual(load_report.main([str(path), "--output", str(out)]), 0)
            self.assertIn("| 50 | jwt |", printed.getvalue())
            self.assertEqual(len(json.loads(out.read_text(encoding="utf-8"))["groups"]), 4)
            with contextlib.redirect_stderr(io.StringIO()):
                self.assertEqual(load_report.main([str(Path(directory) / "missing.csv")]), 2)


if __name__ == "__main__":
    unittest.main()
