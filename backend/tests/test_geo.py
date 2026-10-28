from __future__ import annotations

import pytest

from app.geo import parse_coordinates


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("36.751112, -3.491751", (36.751112, -3.491751)),
        ("36,751112, -3,491751", (36.751112, -3.491751)),
        ("36.751112 -3.491751", (36.751112, -3.491751)),
        ('36°45\'04.0"N 3°29\'30.3"W', (36.751111, -3.49175)),
        ("36° 45' 04.0\" N, 3° 29' 30.3\" W", (36.751111, -3.49175)),
        ("36 45 04.0 N 3 29 30.3 W", (36.751111, -3.49175)),
        ("36.751112 N, 3.491751 W", (36.751112, -3.491751)),
        ("36º45′04.0″N 3º29′30.3″W", (36.751111, -3.49175)),
        ("3.491751 W, 36.751112 N", (36.751112, -3.491751)),
        ("-36.751112, 3.491751", (-36.751112, 3.491751)),
    ],
)
def test_parse_coordinates_accepts_common_formats(raw: str, expected: tuple[float, float]) -> None:
    assert parse_coordinates(raw) == pytest.approx(expected, abs=1e-5)


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "36.751112",
        "not coordinates",
        "91, 0",
        "0, 181",
        "36.7 N, 3.4 N",
        "nan, 0",
        "36.7, 3.4 extra",
    ],
)
def test_parse_coordinates_rejects_invalid_values(raw: str) -> None:
    assert parse_coordinates(raw) is None
