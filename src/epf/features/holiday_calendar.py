"""Public holidays per country, from the `holidays` package.

This is the only module that calls the package. A holiday is a calendar date
of the country. Every zone of this project keeps market time, so the date is
also the delivery day.
"""

from collections.abc import Iterable, Sequence
from datetime import date

import holidays


def holiday_dates(country: str, categories: Sequence[str], years: Iterable[int],
                  subdivision: str | None = None) -> set[date]:
    """Return the holiday dates of a country in the given years.

    Input: a country code such as "DE", the holiday categories of the package
        such as ["public"], the years, and optionally one subdivision code.
    Output: calendar dates. Without a subdivision these are the nationwide
        holidays. A day on which a holiday is observed in lieu counts too,
        which is the default of the package.
    Raises ValueError when the package has no such category for the country.
    """
    calendar = holidays.country_holidays(country, subdiv=subdivision, years=list(years),
                                         categories=tuple(categories))
    return set(calendar.keys())


def subdivisions(country: str) -> list[str]:
    """Return the subdivision codes the package has for a country, empty when it has none."""
    return holidays.list_supported_countries(include_aliases=False)[country]


def regional_days(country: str, categories: Sequence[str],
                  years: Iterable[int]) -> dict[date, int]:
    """Return the days that are a holiday in some subdivision and not nationwide.

    Input: as for holiday_dates.
    Output: per date the number of subdivisions in which it is a holiday.
        The package lists some cities beside the regions, for example Augsburg
        beside the German states. They count as subdivisions here.
    """
    years = list(years)
    nationwide = holiday_dates(country, categories, years)
    counts: dict[date, int] = {}
    for code in subdivisions(country):
        for day in holiday_dates(country, categories, years, code) - nationwide:
            counts[day] = counts.get(day, 0) + 1
    return counts
