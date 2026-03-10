"""
Unit tests for retry policy.
"""
import pytest

from omnidapter.transport.retry import RetryPolicy


class TestRetryPolicy:
    def test_default_policy(self):
        policy = RetryPolicy.default()
        assert policy.max_retries == 3
        assert policy.retry_on_network_error is True
        assert 429 in policy.retry_on_status
        assert 500 in policy.retry_on_status

    def test_no_retry_policy(self):
        policy = RetryPolicy.no_retry()
        assert policy.max_retries == 0

    def test_backoff_increases(self):
        policy = RetryPolicy(backoff_base=1.0, backoff_max=100.0, jitter=False)
        delay_0 = policy.get_backoff(0)
        delay_1 = policy.get_backoff(1)
        delay_2 = policy.get_backoff(2)
        assert delay_0 < delay_1 < delay_2

    def test_backoff_capped_at_max(self):
        policy = RetryPolicy(backoff_base=1.0, backoff_max=5.0, jitter=False)
        # After enough attempts, should be capped
        for i in range(20):
            assert policy.get_backoff(i) <= 5.0

    def test_jitter_adds_randomness(self):
        policy = RetryPolicy(backoff_base=10.0, backoff_max=100.0, jitter=True)
        delays = {policy.get_backoff(3) for _ in range(10)}
        # With jitter, delays should vary
        assert len(delays) > 1
