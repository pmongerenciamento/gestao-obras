"""Feriados nacionais brasileiros — fixos + móveis (calculados a partir da
Páscoa, algoritmo de Gauss/computus). Usado pra pré-popular sim_holidays
quando um estudo é criado.
"""
from __future__ import annotations

from datetime import date, timedelta

_FIXED_HOLIDAYS = (
    (1, 1, "Confraternização Universal"),
    (4, 21, "Tiradentes"),
    (5, 1, "Dia do Trabalho"),
    (9, 7, "Independência do Brasil"),
    (10, 12, "Nossa Senhora Aparecida"),
    (11, 2, "Finados"),
    (11, 15, "Proclamação da República"),
    (12, 25, "Natal"),
)


def _easter_date(year: int) -> date:
    """Algoritmo de Gauss (computus) pra domingo de Páscoa no calendário gregoriano."""
    a = year % 19
    b = year // 100
    c = year % 100
    d = b // 4
    e = b % 4
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i = c // 4
    k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def generate_national_holidays(start_year: int, num_years: int = 4) -> list[tuple[date, str]]:
    """Gera feriados nacionais (fixos + móveis) de start_year até start_year + num_years - 1."""
    holidays: list[tuple[date, str]] = []
    for year in range(start_year, start_year + num_years):
        for month, day, description in _FIXED_HOLIDAYS:
            holidays.append((date(year, month, day), description))

        easter = _easter_date(year)
        holidays.append((easter - timedelta(days=47), "Carnaval"))
        holidays.append((easter - timedelta(days=2), "Sexta-feira Santa"))
        holidays.append((easter + timedelta(days=60), "Corpus Christi"))

    return holidays
