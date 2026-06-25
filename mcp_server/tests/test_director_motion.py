from __future__ import annotations

import math
import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from rook import director_motion as dm


@pytest.mark.parametrize("name", sorted(dm.EASING_NAMES))
def test_easing_pins_endpoints(name):
    assert dm.apply_easing(name, 0.0) == pytest.approx(0.0)
    assert dm.apply_easing(name, 1.0) == pytest.approx(1.0)


def test_easing_linear_is_identity():
    assert dm.apply_easing("linear", 0.25) == pytest.approx(0.25)


def test_easing_in_starts_slow():
    # ease_in is below the linear line in the first half
    assert dm.apply_easing("ease_in", 0.5) < 0.5


def test_easing_out_starts_fast():
    assert dm.apply_easing("ease_out", 0.5) > 0.5


def test_easing_in_out_is_symmetric_about_midpoint():
    assert dm.apply_easing("ease_in_out", 0.5) == pytest.approx(0.5)
    assert dm.apply_easing("ease_in_out", 0.25) == pytest.approx(
        1.0 - dm.apply_easing("ease_in_out", 0.75)
    )
