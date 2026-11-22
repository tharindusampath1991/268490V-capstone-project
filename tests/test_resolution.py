"""Tests for the index check, the price resolution split and the covariate alignment."""

import pandas as pd
import pytest

from epf.data.resolution import check_utc_index

HOURS = pd.date_range("2025-01-14 23:00", periods=4, freq="h", tz="UTC")


def test_check_utc_index_accepts_a_sorted_utc_index_without_repeats():
    check_utc_index(pd.Series(1.0, index=HOURS))
    check_utc_index(pd.DataFrame({"price": 1.0}, index=HOURS))


def test_check_utc_index_rejects_an_index_without_a_time_zone():
    naive = pd.Series(1.0, index=HOURS.tz_localize(None))

    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(naive)


def test_check_utc_index_rejects_an_index_in_local_time():
    local = pd.Series(1.0, index=HOURS.tz_convert("Europe/Berlin"))

    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(local)


def test_check_utc_index_rejects_an_index_that_is_not_a_time_index():
    with pytest.raises(ValueError, match="UTC"):
        check_utc_index(pd.Series([1.0, 2.0]))


def test_check_utc_index_rejects_an_unsorted_index():
    unsorted = pd.Series(1.0, index=HOURS[::-1])

    with pytest.raises(ValueError, match="sorted"):
        check_utc_index(unsorted)


def test_check_utc_index_rejects_a_repeated_timestamp():
    repeated = pd.Series(1.0, index=HOURS.append(HOURS[-1:]))

    with pytest.raises(ValueError, match="1 repeated"):
        check_utc_index(repeated)
