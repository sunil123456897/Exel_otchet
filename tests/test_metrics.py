"""Tests for core.infra.metrics — in-process counters and timers."""

import time

from core.infra.metrics import Metrics


class TestMetricsCounters:
    def test_increment_default(self):
        m = Metrics()
        m.increment("files_read")
        snap = m.get_snapshot()
        assert snap["counters"]["files_read"] == 1

    def test_increment_by_amount(self):
        m = Metrics()
        m.increment("rows_processed", 100)
        m.increment("rows_processed", 50)
        snap = m.get_snapshot()
        assert snap["counters"]["rows_processed"] == 150

    def test_multiple_counters(self):
        m = Metrics()
        m.increment("a")
        m.increment("b", 5)
        snap = m.get_snapshot()
        assert snap["counters"]["a"] == 1
        assert snap["counters"]["b"] == 5


class TestMetricsGauges:
    def test_set_gauge(self):
        m = Metrics()
        m.set_gauge("active_threads", 3)
        snap = m.get_snapshot()
        assert snap["gauges"]["active_threads"] == 3

    def test_set_gauge_overwrites(self):
        m = Metrics()
        m.set_gauge("x", 10)
        m.set_gauge("x", 20)
        snap = m.get_snapshot()
        assert snap["gauges"]["x"] == 20


class TestMetricsTimers:
    def test_start_stop_timer(self):
        m = Metrics()
        m.start_timer("ingestion")
        time.sleep(0.01)
        elapsed = m.stop_timer("ingestion")
        assert elapsed > 0
        snap = m.get_snapshot()
        assert "ingestion_elapsed_s" in snap["gauges"]

    def test_stop_unstarted_timer(self):
        m = Metrics()
        elapsed = m.stop_timer("no_such_timer")
        assert elapsed == 0.0


class TestMetricsSnapshot:
    def test_snapshot_contains_uptime(self):
        m = Metrics()
        snap = m.get_snapshot()
        assert "uptime_s" in snap
        assert snap["uptime_s"] >= 0

    def test_snapshot_empty_initially(self):
        m = Metrics()
        snap = m.get_snapshot()
        assert snap["counters"] == {}
        assert snap["gauges"] == {}


class TestMetricsReset:
    def test_reset_clears_all(self):
        m = Metrics()
        m.increment("x", 5)
        m.set_gauge("y", 3.0)
        m.start_timer("z")
        m.reset()
        snap = m.get_snapshot()
        assert snap["counters"] == {}
        assert snap["gauges"] == {}


class TestMetricsLogSummary:
    def test_log_summary_does_not_raise(self):
        m = Metrics()
        m.increment("rows", 10)
        m.set_gauge("threads", 2)
        m.log_summary()
