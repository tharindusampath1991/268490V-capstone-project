"""Tests for the seed helper. They use no network and no data files."""

import random

import numpy as np

from epf.seed import set_seed


def draws() -> tuple[float, float]:
    """One random number from the standard library and one from numpy."""
    return random.random(), float(np.random.rand())


def test_set_seed_returns_the_seed_of_the_config():
    assert set_seed({"seed": 42}) == 42


def test_set_seed_makes_random_and_numpy_repeat_their_numbers():
    set_seed({"seed": 7})
    first = draws()
    set_seed({"seed": 7})
    second = draws()

    assert first == second


def test_set_seed_gives_other_numbers_for_another_seed():
    set_seed({"seed": 7})
    first = draws()
    set_seed({"seed": 8})
    second = draws()

    assert first[0] != second[0]
    assert first[1] != second[1]
