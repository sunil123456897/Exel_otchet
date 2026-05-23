from core.app.performance import default_max_workers, resolve_max_workers


def test_resolve_max_workers_keeps_default_when_unset() -> None:
    assert resolve_max_workers({}) == default_max_workers()
    assert resolve_max_workers({"performance": {"max_workers": None}}) == default_max_workers()


def test_resolve_max_workers_accepts_bounded_integer() -> None:
    assert resolve_max_workers({"performance": {"max_workers": 6}}) == 6
    assert resolve_max_workers({"performance": {"max_workers": "2"}}) == 2
    assert resolve_max_workers({"performance": {"max_workers": 0}}) == 1
    assert resolve_max_workers({"performance": {"max_workers": 1000}}) == 64


def test_resolve_max_workers_ignores_invalid_value() -> None:
    assert resolve_max_workers({"performance": {"max_workers": "fast"}}) == default_max_workers()
