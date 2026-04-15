import logging

from core.infra.metrics import Metrics


def test_metrics_increment_set_gauge_and_snapshot():
    m = Metrics()

    m.increment("rows_processed")
    m.increment("rows_processed", 4)
    m.increment("files_read", 2)
    m.set_gauge("active_threads", 3)

    snap = m.get_snapshot()

    assert snap["counters"]["rows_processed"] == 5
    assert snap["counters"]["files_read"] == 2
    assert snap["gauges"]["active_threads"] == 3
    assert isinstance(snap["uptime_s"], float)


def test_metrics_timers_record_elapsed_time():
    m = Metrics()

    m.start_timer("ingestion")
    elapsed = m.stop_timer("ingestion")

    assert elapsed >= 0.0
    snap = m.get_snapshot()
    assert "ingestion_elapsed_s" in snap["gauges"]
    assert snap["gauges"]["ingestion_elapsed_s"] >= 0.0


def test_metrics_stop_unknown_timer_returns_zero():
    m = Metrics()
    assert m.stop_timer("missing") == 0.0


def test_metrics_log_summary_emits_info(caplog):
    m = Metrics()
    m.increment("rows_processed", 10)

    with caplog.at_level(logging.INFO):
        m.log_summary()

    assert "[METRICS]" in caplog.text
    assert "rows_processed" in caplog.text


def test_metrics_reset_clears_state():
    m = Metrics()
    m.increment("rows_processed", 3)
    m.set_gauge("active_threads", 2)
    m.start_timer("write")

    m.reset()
    snap = m.get_snapshot()

    assert snap["counters"] == {}
    assert snap["gauges"] == {}
