"""Tests for the p99, ECDF and denial-versus-lifetime additions to analyze.py."""
import contextlib
import io
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest

import analyze
import measure


def run_row(run_id, outcome="denied", strategy="jwt", delay="1", remaining=None):
    row = dict(run_id=run_id, outcome=outcome, strategy=strategy, token_ttl_s="60",
               time_to_deny_s=delay if outcome == "denied" else "", error="", observation_s="90")
    if remaining is not None:
        row["remaining_at_revoke_s"] = remaining
    return row


class ExtendedAnalysisTests(unittest.TestCase):
    def test_p99_is_reported_and_interpolated(self):
        stats = analyze.distribution(list(range(1, 101)))
        self.assertAlmostEqual(stats["p99"], 99.01)
        self.assertIsNone(analyze.distribution([])["p99"])

    def test_ecdf_is_sorted_and_reaches_one(self):
        cdf = analyze.ecdf([3, 1, 2])
        self.assertEqual(cdf["values"], [1, 2, 3])
        self.assertEqual(cdf["cumulative_probability"], [1 / 3, 2 / 3, 1.0])
        self.assertEqual(analyze.ecdf([]), {"values": [], "cumulative_probability": []})

    def test_group_ecdf_contains_only_confirmed_denials(self):
        rows = [run_row("a", delay="2"), run_row("b", delay="4"), run_row("c", "censored"),
                run_row("d", "invalid")]
        group = analyze.analyze(rows, [], 100)["groups"][0]
        self.assertEqual(group["time_to_deny_ecdf"]["values"], [2.0, 4.0])

    def test_denial_is_compared_with_the_lifetime_left_at_revocation(self):
        rows = [run_row("a", delay="39.9", remaining="40"), run_row("b", delay="0.05", remaining="30"),
                run_row("c", delay="3"), run_row("d", "censored", remaining="20")]
        group = analyze.analyze(rows, [], 100)["groups"][0]
        self.assertEqual(group["denial_vs_remaining_s"], [[40.0, 39.9], [30.0, 0.05]])
        offsets = group["denial_minus_remaining_s"]
        self.assertEqual(offsets["n"], 2)
        self.assertAlmostEqual(offsets["max"], -0.1)
        self.assertAlmostEqual(offsets["min"], -29.95)

    def test_runs_without_remaining_lifetime_have_no_pairs(self):
        group = analyze.analyze([run_row("a")], [], 100)["groups"][0]
        self.assertEqual(group["denial_vs_remaining_s"], [])
        self.assertIsNone(group["denial_minus_remaining_s"]["p50"])

    def test_ecdf_plot_is_written_and_refused_without_denials(self):
        summary = analyze.analyze([run_row("a", delay="39.9", remaining="40"),
                                   run_row("b", strategy="introspection", delay="0.01", remaining="30")], [], 100)
        with TemporaryDirectory() as directory:
            path = Path(directory) / "ecdf.png"
            analyze.save_ecdf_plot(summary, path)
            self.assertGreater(path.stat().st_size, 0)
            empty = analyze.analyze([run_row("c", "censored")], [], 100)
            with self.assertRaises(ValueError):
                analyze.save_ecdf_plot(empty, Path(directory) / "none.png")

    def test_cli_writes_the_ecdf_plot_from_raw_csv(self):
        with TemporaryDirectory() as directory:
            row = run_row("a", delay="2", remaining="30")
            measure.append_csv(Path(directory) / "runs.csv", list(row), [row])
            plot = Path(directory) / "ecdf.png"
            with contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(analyze.main([directory, "--ecdf-plot", str(plot), "--bootstrap", "100"]), 0)
            self.assertTrue(plot.exists())


if __name__ == "__main__":
    unittest.main()
