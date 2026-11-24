"""Tests for the holiday calendar. They call the `holidays` package and use no data files."""

from datetime import date

import pytest

from epf.features.holiday_calendar import holiday_dates, regional_days, subdivisions

PUBLIC = ["public"]


def test_holiday_dates_gives_the_nationwide_days_of_the_asked_years_only():
    days = holiday_dates("DE", PUBLIC, [2026])

    assert len(days) == 9
    assert date(2026, 1, 1) in days
    assert date(2026, 1, 6) not in days            # Epiphany is a holiday in three states only
    assert {day.year for day in days} == {2026}


def test_holiday_dates_keeps_a_holiday_that_falls_on_a_weekend():
    days = holiday_dates("DE", PUBLIC, [2026])

    assert date(2026, 10, 3).weekday() == 5        # German Unity Day 2026 is a Saturday
    assert date(2026, 10, 3) in days


def test_holiday_dates_adds_the_days_of_a_second_category():
    public = holiday_dates("SE", PUBLIC, [2026])
    with_de_facto = holiday_dates("SE", ["public", "de_facto"], [2026])

    added = with_de_facto - public
    assert len(public) == 13
    assert added == {date(2026, 6, 19), date(2026, 12, 24), date(2026, 12, 31)}


def test_holiday_dates_of_a_subdivision_include_its_regional_days():
    bavaria = holiday_dates("DE", PUBLIC, [2026], subdivision="BY")

    assert date(2026, 1, 6) in bavaria
    assert holiday_dates("DE", PUBLIC, [2026]) < bavaria


def test_holiday_dates_refuses_a_category_the_country_does_not_have():
    with pytest.raises(ValueError, match="de_facto"):
        holiday_dates("DE", ["de_facto"], [2026])


def test_subdivisions_lists_the_codes_of_the_package_and_none_for_sweden():
    assert "BY" in subdivisions("DE")
    assert subdivisions("SE") == []


def test_regional_days_counts_the_subdivisions_and_leaves_out_nationwide_days():
    days = regional_days("DE", PUBLIC, [2026])

    # BW, BY, ST and the city of Augsburg, which the package lists beside the states.
    assert days[date(2026, 1, 6)] == 4
    assert date(2026, 1, 1) not in days


def test_regional_days_is_empty_for_a_country_without_subdivisions():
    assert regional_days("SE", PUBLIC, [2026]) == {}
