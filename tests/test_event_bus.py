"""Tests for core.infra.event_bus — thread-safe publish-subscribe bus."""

from core.infra.event_bus import EventBus, EventType, Event


class TestEventBusSingleton:
    def setup_method(self):
        EventBus.reset()

    def teardown_method(self):
        EventBus.reset()

    def test_get_returns_singleton(self):
        a = EventBus.get()
        b = EventBus.get()
        assert a is b

    def test_reset_clears_singleton(self):
        a = EventBus.get()
        EventBus.reset()
        b = EventBus.get()
        assert a is not b


class TestEventBusPubSub:
    def setup_method(self):
        self.bus = EventBus()

    def test_subscribe_and_publish(self):
        received = []
        self.bus.subscribe(EventType.PROGRESS_UPDATED, lambda e: received.append(e))
        self.bus.publish(Event(EventType.PROGRESS_UPDATED, data=42))
        self.bus.poll()
        assert len(received) == 1
        assert received[0].data == 42

    def test_publish_without_subscriber_does_not_raise(self):
        self.bus.publish(Event(EventType.ERROR_OCCURRED, data="err"))
        self.bus.poll()

    def test_multiple_subscribers(self):
        r1, r2 = [], []
        self.bus.subscribe(EventType.OPERATION_STARTED, lambda e: r1.append(e))
        self.bus.subscribe(EventType.OPERATION_STARTED, lambda e: r2.append(e))
        self.bus.publish(Event(EventType.OPERATION_STARTED))
        self.bus.poll()
        assert len(r1) == 1
        assert len(r2) == 1

    def test_unsubscribe(self):
        received = []

        def cb(e):
            received.append(e)

        self.bus.subscribe(EventType.PROGRESS_UPDATED, cb)
        self.bus.unsubscribe(EventType.PROGRESS_UPDATED, cb)
        self.bus.publish(Event(EventType.PROGRESS_UPDATED, data="x"))
        self.bus.poll()
        assert received == []

    def test_unsubscribe_unknown_callback_no_error(self):
        self.bus.unsubscribe(EventType.ERROR_OCCURRED, lambda e: None)

    def test_poll_drains_multiple_events(self):
        received = []
        self.bus.subscribe(EventType.PROGRESS_UPDATED, lambda e: received.append(e.data))
        self.bus.publish(Event(EventType.PROGRESS_UPDATED, data=1))
        self.bus.publish(Event(EventType.PROGRESS_UPDATED, data=2))
        self.bus.publish(Event(EventType.PROGRESS_UPDATED, data=3))
        self.bus.poll()
        assert received == [1, 2, 3]

    def test_poll_callback_error_does_not_stop_drain(self):
        received = []

        def bad_cb(e):
            raise RuntimeError("boom")

        def good_cb(e):
            received.append(e.data)

        self.bus.subscribe(EventType.OPERATION_FINISHED, bad_cb)
        self.bus.subscribe(EventType.OPERATION_FINISHED, good_cb)
        self.bus.publish(Event(EventType.OPERATION_FINISHED, data="ok"))
        self.bus.poll()
        assert received == ["ok"]

    def test_event_types_independent(self):
        r_progress, r_error = [], []
        self.bus.subscribe(EventType.PROGRESS_UPDATED, lambda e: r_progress.append(e))
        self.bus.subscribe(EventType.ERROR_OCCURRED, lambda e: r_error.append(e))
        self.bus.publish(Event(EventType.PROGRESS_UPDATED))
        self.bus.poll()
        assert len(r_progress) == 1
        assert len(r_error) == 0

    def test_poll_empty_queue_no_error(self):
        self.bus.poll()

    def test_title_refresh_event(self):
        received = []
        self.bus.subscribe(EventType.TITLE_REFRESH, lambda e: received.append(e.data))
        self.bus.publish(Event(EventType.TITLE_REFRESH, data="new title"))
        self.bus.poll()
        assert received == ["new title"]
