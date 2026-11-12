import time

import pytest

from app.clock import Clock, SystemClock
from tests.fakes import FakeClock


def test_fake_clock_does_not_move_between_reads() -> None:
    clock = FakeClock(start_seconds=100.0)
    assert clock.now_seconds() == 100.0
    assert clock.now_seconds() == 100.0


def test_fake_clock_starts_at_zero_by_default() -> None:
    assert FakeClock().now_seconds() == 0.0


def test_fake_clock_advance_adds_seconds_and_accumulates() -> None:
    clock = FakeClock(start_seconds=10.0)
    clock.advance(2.5)
    assert clock.now_seconds() == 12.5
    clock.advance(1)
    assert clock.now_seconds() == 13.5


def test_fake_clock_advance_zero_keeps_time() -> None:
    clock = FakeClock(start_seconds=5.0)
    clock.advance(0)
    assert clock.now_seconds() == 5.0


def test_fake_clock_rejects_negative_advance_and_keeps_time() -> None:
    clock = FakeClock(start_seconds=5.0)
    with pytest.raises(ValueError, match="negative"):
        clock.advance(-0.001)
    assert clock.now_seconds() == 5.0


def test_system_clock_tracks_wall_time() -> None:
    before = time.time()
    now = SystemClock().now_seconds()
    after = time.time()
    assert before <= now <= after


def test_fake_and_system_clock_satisfy_clock_protocol() -> None:
    clocks: list[Clock] = [FakeClock(), SystemClock()]
    assert all(isinstance(clock.now_seconds(), float) for clock in clocks)
