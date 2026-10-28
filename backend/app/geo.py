from __future__ import annotations

import math
import re

# A coordinate part can be decimal ("36.751112"), decimal + hemisphere
# ("36.751112 N") or degrees/minutes/seconds ("36°45'04.0\"N").
_COMPONENT = re.compile(
    r"""
    (?P<sign>[+-])?\s*
    (?P<deg>\d{1,3}(?:[.,]\d+)?)\s*(?:°|º|d(?:eg)?\.?)?\s*
    (?:(?P<min>\d{1,2}(?:[.,]\d+)?)\s*(?:'|′|m(?:in)?\.?)?\s*)?
    (?:(?P<sec>\d{1,2}(?:[.,]\d+)?)\s*(?:"|″|''|s(?:ec)?\.?)?\s*)?
    (?P<hemi>[NSEW])?
    """,
    re.IGNORECASE | re.VERBOSE,
)

_SEPARATORS = set(" \t\r\n,;|/")
_TRANSLATION = str.maketrans(
    {
        "º": "°",
        "′": "'",
        "″": '"',
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
    }
)


def _number(raw: str | None) -> float:
    return float((raw or "0").replace(",", "."))


def _axis(hemisphere: str | None) -> str | None:
    if hemisphere in {"N", "S"}:
        return "lat"
    if hemisphere in {"E", "W"}:
        return "lon"
    return None


def parse_coordinates(value: object) -> tuple[float, float] | None:
    """Return ``(latitude, longitude)`` from common human-entered formats.

    Accepted examples::

        36.751112, -3.491751
        36,751112, -3,491751
        36°45'04.0"N 3°29'30.3"W
        36 45 04.0 N 3 29 30.3 W
        36.751112 N, 3.491751 W

    The pair is interpreted as latitude first, except when the hemisphere
    letters clearly indicate the opposite order. Invalid or out-of-range values
    return ``None`` so callers can fall back to legacy tags.
    """

    text = str(value or "").strip().translate(_TRANSLATION)
    if not text:
        return None

    matches: list[re.Match[str]] = []
    position = 0
    for match in _COMPONENT.finditer(text):
        if any(char not in _SEPARATORS for char in text[position : match.start()]):
            return None
        matches.append(match)
        position = match.end()
        if len(matches) > 2:
            return None
    if any(char not in _SEPARATORS for char in text[position:]):
        return None
    if len(matches) != 2:
        return None

    parts: list[tuple[float, str | None]] = []
    for match in matches:
        degrees = _number(match.group("deg"))
        minutes = _number(match.group("min"))
        seconds = _number(match.group("sec"))
        hemisphere = (match.group("hemi") or "").upper() or None
        total = abs(degrees) + minutes / 60 + seconds / 3600
        if match.group("sign") == "-" or hemisphere in {"S", "W"}:
            total = -total
        elif hemisphere in {"N", "E"}:
            total = abs(total)
        parts.append((total, hemisphere))

    first_axis = _axis(parts[0][1])
    second_axis = _axis(parts[1][1])
    if first_axis and second_axis and first_axis == second_axis:
        return None
    if first_axis == "lon" or second_axis == "lat":
        latitude, longitude = parts[1][0], parts[0][0]
    else:
        latitude, longitude = parts[0][0], parts[1][0]

    if not (math.isfinite(latitude) and math.isfinite(longitude)):
        return None
    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None
    return latitude, longitude
