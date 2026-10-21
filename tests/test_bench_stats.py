"""Tests of the exercise-level statistics of the frozen sets (bench/stats.py, FROZEN_SET.md §4, §6.3, §11; T-083).
The expected figures are the ones printed in FROZEN_SET.md before any code existed."""
import os, sys, unittest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
from bench import stats  # noqa: E402

pct = lambda x: round(100 * x, 1)

class TestBounds(unittest.TestCase):
    def test_zero_failure_bounds_of_section_4(self):
        self.assertEqual([pct(stats.upper_bound_zero(n)) for n in (25, 40, 60, 299)], [11.3, 7.2, 4.9, 1.0])

    def test_clopper_pearson_of_section_4(self):
        table = {(40, 1): [0.1, 13.2], (40, 2): [0.6, 16.9], (40, 4): [2.8, 23.7], (60, 1): [0.0, 8.9], (60, 2): [0.4, 11.5], (60, 4): [1.8, 16.2]}
        for (n, f), want in table.items():
            self.assertEqual([pct(x) for x in stats.clopper_pearson(f, n)], want, (n, f))
        self.assertEqual([pct(1 - x) for x in reversed(stats.clopper_pearson(5, 25))], [59.3, 93.2])     # 20 of 25 perfect (T-083)

    def test_failure_interval(self):
        fi = stats.failure_interval(0, 40)
        self.assertEqual((fi["failed"], fi["rate"], pct(fi["interval"][1])), (0, 0.0, 7.2))
        self.assertIn("one-sided", fi["kind"])
        self.assertIn("Clopper", stats.failure_interval(2, 40)["kind"])

class TestPassK(unittest.TestCase):
    def test_pass_hat_k(self):
        self.assertEqual(stats.pass_hat_k(3, 3, 3), 1.0); self.assertEqual(stats.pass_hat_k(2, 3, 3), 0.0)
        self.assertAlmostEqual(stats.pass_hat_k(2, 3, 2), 1 / 3); self.assertAlmostEqual(stats.pass_hat_k(2, 3, 1), 2 / 3)
        curve = stats.pass_k_curve([3, 3, 2, 0, 3], 3)
        self.assertAlmostEqual(curve[1], 11 / 15)                    # the mean pass rate over seeds
        self.assertAlmostEqual(curve[3], 3 / 5)                      # the strict rule of §6.3: passed on every seed
        self.assertGreaterEqual(curve[1], curve[2]); self.assertGreaterEqual(curve[2], curve[3])

class TestPaired(unittest.TestCase):
    def test_mcnemar_power_of_section_11_3(self):
        """6 discordant exercises in one direction, 9 with one against, 12 with two against reach p < 0.05; 5 do not."""
        self.assertLess(stats.mcnemar_exact(6, 0), 0.05); self.assertLess(stats.mcnemar_exact(8, 1), 0.05)
        self.assertLess(stats.mcnemar_exact(10, 2), 0.05); self.assertGreater(stats.mcnemar_exact(5, 0), 0.05)
        self.assertGreater(stats.mcnemar_exact(7, 2), 0.05); self.assertEqual(stats.mcnemar_exact(0, 0), 1.0)

    def test_bootstrap_and_sign_flip_are_deterministic(self):
        d = [0.125, 0.0, -0.125, 0.25, 0.0, 0.125, 0.0, 0.0, 0.375, 0.0]
        a, b = stats.paired_bootstrap_mean(d), stats.paired_bootstrap_mean(d)
        self.assertEqual(a, b); self.assertLessEqual(a[0], sum(d) / len(d)); self.assertGreaterEqual(a[1], sum(d) / len(d))
        self.assertEqual(stats.sign_flip_test(d), stats.sign_flip_test(d))
        self.assertGreater(stats.sign_flip_test([0.0] * 10), 0.99)
        self.assertLess(stats.sign_flip_test([1.0] * 12), 0.01)
        ci = stats.cluster_bootstrap([(1, 8), (0, 8), (2, 8), (0, 8)])
        self.assertTrue(0 <= ci[0] <= 3 / 32 <= ci[1] <= 1)

if __name__ == "__main__":
    unittest.main()
