"""Tests for core.app.performance — max_workers resolution."""

from core.app.performance import default_max_workers, resolve_max_workers


class TestDefaultMaxWorkers:
    def test_returns_positive(self):
        assert default_max_workers() >= 1

    def test_capped_at_32(self):
        assert default_max_workers() <= 32


class TestResolveMaxWorkers:
    def test_none_config(self):
        assert resolve_max_workers(None) == default_max_workers()

    def test_empty_config(self):
        assert resolve_max_workers({}) == default_max_workers()

    def test_non_mapping_config(self):
        assert resolve_max_workers("bad") == default_max_workers()

    def test_missing_performance_key(self):
        assert resolve_max_workers({"other": "val"}) == default_max_workers()

    def test_performance_not_mapping(self):
        assert resolve_max_workers({"performance": "string"}) == default_max_workers()

    def test_missing_max_workers(self):
        assert resolve_max_workers({"performance": {}}) == default_max_workers()

    def test_none_max_workers(self):
        assert resolve_max_workers({"performance": {"max_workers": None}}) == default_max_workers()

    def test_empty_string_max_workers(self):
        assert resolve_max_workers({"performance": {"max_workers": ""}}) == default_max_workers()

    def test_valid_value(self):
        assert resolve_max_workers({"performance": {"max_workers": 8}}) == 8

    def test_string_value(self):
        assert resolve_max_workers({"performance": {"max_workers": "16"}}) == 16

    def test_clamped_below_1(self):
        assert resolve_max_workers({"performance": {"max_workers": 0}}) == 1
        assert resolve_max_workers({"performance": {"max_workers": -5}}) == 1

    def test_clamped_above_64(self):
        assert resolve_max_workers({"performance": {"max_workers": 100}}) == 64
        assert resolve_max_workers({"performance": {"max_workers": 1000}}) == 64

    def test_invalid_string(self):
        assert resolve_max_workers({"performance": {"max_workers": "abc"}}) == default_max_workers()
