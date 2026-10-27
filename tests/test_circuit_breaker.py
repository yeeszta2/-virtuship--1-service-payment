import unittest

from src.circuit_breaker import CircuitBreaker, CircuitOpenError


class FakeClock:
    def __init__(self):
        self.now = 0.0

    def __call__(self):
        return self.now


class CircuitBreakerTest(unittest.TestCase):
    def test_opens_after_threshold_and_blocks_calls(self):
        cb = CircuitBreaker(failure_threshold=3, reset_seconds=30, clock=FakeClock())
        for _ in range(3):
            cb.before_call()
            cb.record_failure()
        self.assertEqual(cb.state, "open")
        with self.assertRaises(CircuitOpenError):
            cb.before_call()

    def test_half_open_after_reset_and_closes_on_success(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_seconds=30, clock=clock)
        cb.before_call(); cb.record_failure()
        clock.now = 31
        cb.before_call()  # percobaan pemulihan diizinkan
        self.assertEqual(cb.state, "half_open")
        cb.record_success()
        self.assertEqual(cb.state, "closed")

    def test_half_open_failure_reopens(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_seconds=30, clock=clock)
        cb.before_call(); cb.record_failure()
        clock.now = 31
        cb.before_call(); cb.record_failure()
        self.assertEqual(cb.state, "open")

    def test_only_one_trial_in_half_open(self):
        clock = FakeClock()
        cb = CircuitBreaker(failure_threshold=1, reset_seconds=30, clock=clock)
        cb.before_call(); cb.record_failure()
        clock.now = 31
        cb.before_call()
        with self.assertRaises(CircuitOpenError):
            cb.before_call()


if __name__ == "__main__":
    unittest.main()
