#!/usr/bin/env python3
"""
200-Year Planetary Decan Ingress Ephemeris Generator
======================================================

Generates a printable-book-layout grid of decan ingresses for the seven
classical planets, 1926-2126, and exports it to
``ephemeris_200_years_grid.csv``.

REQUIREMENTS
------------
    pip install pyswisseph pandas

METHOD
------
- Bodies are computed as apparent GEOCENTRIC TROPICAL ecliptic longitudes
  (Swiss Ephemeris default), using the built-in Moshier analytic ephemeris
  (SEFLG_MOSEPH) so no external Swiss Ephemeris data files need to be
  downloaded. If you have real .se1 data files and want Swiss Ephemeris
  precision instead of Moshier, point EPHE_PATH at their folder and set
  USE_MOSEPH = False below.

- DECAN INGRESS DETECTION (Saturn, Jupiter, Mars, Sun, Venus, Mercury):
  The ecliptic (0-360 deg) is divided into 36 "decans" of 10 degrees each.
  The script walks time forward in STEP_HOURS (default 3h) increments; the
  moment the coarse-step decan index changes it bisects the interval
  (BISECT_ITERS iterations, ~24 -> sub-second precision) to pinpoint the
  exact UTC ingress time. Both forward AND retrograde (backward) crossings
  are logged as separate ingress lines, since a station/retrograde loop can
  cross the same boundary more than once in a year.

- MOON COLUMN ("Moon_Volvelle_Key"): per spec, the Moon does NOT get daily
  decan ingresses. Instead the script logs every New Moon (Sun-Moon
  conjunction, i.e. apparent elongation crossing 0 deg), located the same
  way: coarse 3h scan + bisection refinement.

- OUTPUT GRID: 12 rows per year (Aries..Pisces) x (END_YEAR-START_YEAR+1)
  years. Columns are in strict Chaldean order: Saturn, Jupiter, Mars, Sun,
  Venus, Mercury, then Moon_Volvelle_Key. Multiple ingress events landing
  in the same (Year, Zodiac_Sign) cell for a planet are newline-separated
  (\\n) in chronological order, ready for spreadsheet/InDesign wrapping.

PERFORMANCE
-----------
At the default 3-hour resolution this script evaluates roughly 5-6 million
planetary positions across the 201-year span (6 boundary-tracked planets +
Sun/Moon for New Moon detection, plus bisection refinement calls). With the
Moshier analytic ephemeris this typically runs in a few minutes on a normal
laptop. Progress is printed per planet. If you need it faster for testing,
temporarily shrink START_YEAR/END_YEAR or raise STEP_HOURS (at the cost of
resolution - keep it well under the fastest body's minimum time-to-cross-
10-degrees, which for these seven classical bodies is comfortably satisfied
by 3h, and would still be safe up to roughly 24h, but 3h is what was
specified and is what makes retrograde stations reliably resolved to a
single event).
"""

import swisseph as swe
import pandas as pd

# =================================================================
# CONFIGURATION
# =================================================================
START_YEAR = 1926
END_YEAR = 2126                 # inclusive
STEP_HOURS = 3                  # coarse scan resolution (spec requirement)
BISECT_ITERS = 24               # ~ (STEP_HOURS/2**24) day precision (<< 1 second)
OUTPUT_CSV = "ephemeris_200_years_grid.csv"

USE_MOSEPH = True               # built-in analytic ephemeris, no data files needed
EPHE_PATH = None                # set to a folder of .se1 files if USE_MOSEPH=False

STEP_DAYS = STEP_HOURS / 24.0

# =================================================================
# STATIC TABLES
# =================================================================
CHALDEAN_ORDER = ["Saturn", "Jupiter", "Mars", "Sun", "Venus", "Mercury"]  # Moon handled separately

PLANET_IDS = {
    "Sun": swe.SUN,
    "Moon": swe.MOON,
    "Mercury": swe.MERCURY,
    "Venus": swe.VENUS,
    "Mars": swe.MARS,
    "Jupiter": swe.JUPITER,
    "Saturn": swe.SATURN,
}

ZODIAC_SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]
SIGN_ABBR = {
    "Aries": "Ari", "Taurus": "Tau", "Gemini": "Gem", "Cancer": "Can",
    "Leo": "Leo", "Virgo": "Vir", "Libra": "Lib", "Scorpio": "Sco",
    "Sagittarius": "Sag", "Capricorn": "Cap", "Aquarius": "Aqu", "Pisces": "Pis",
}
ROMAN_DECAN = {0: "I", 1: "II", 2: "III"}
MONTH_ABBR = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
              "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

EPHE_FLAG = (swe.FLG_MOSEPH if USE_MOSEPH else swe.FLG_SWIEPH) | swe.FLG_SPEED

# =================================================================
# LOW-LEVEL HELPERS
# =================================================================

def jd_ut(year, month, day, hour=0.0):
    return swe.julday(year, month, day, hour, swe.GREG_CAL)


def lon_of(jd, planet_id):
    """Apparent geocentric tropical ecliptic longitude (0-360) at UT Julian Day jd."""
    pos, _ret = swe.calc_ut(jd, planet_id, EPHE_FLAG)
    return pos[0] % 360.0


def decan_index(lon):
    """Absolute decan index 0-35 across the whole zodiac (10 degrees each)."""
    return int(lon // 10.0) % 36


def signed_gap(lon, boundary_deg):
    """Shortest signed angular distance from boundary_deg to lon, range (-180,180]."""
    return ((lon - boundary_deg + 180.0) % 360.0) - 180.0


def sign_and_decan(lon):
    """(sign_name, decan_roman, degrees_into_sign) for an ecliptic longitude."""
    lon = lon % 360.0
    sign_idx = int(lon // 30.0) % 12
    deg_in_sign = lon - sign_idx * 30.0
    decan_in_sign = int(deg_in_sign // 10.0)
    return ZODIAC_SIGNS[sign_idx], ROMAN_DECAN[decan_in_sign], deg_in_sign


def jd_to_civil(jd):
    """(year, month, day, hour, minute) for a UT Julian Day."""
    y, m, d, h = swe.revjul(jd, swe.GREG_CAL)
    hour = int(h)
    minute = int(round((h - hour) * 60))
    if minute == 60:
        minute = 0
        hour += 1
        if hour == 24:  # exceedingly rare rounding edge case
            hour = 0
    return y, m, d, hour, minute


def fmt_date(month, day):
    return f"{MONTH_ABBR[month - 1]} {day:02d}"


def fmt_dm(deg_in_sign):
    """'3\u00b049\u2032' style degree/arcminute string within a sign (0-30)."""
    d = int(deg_in_sign)
    m = int(round((deg_in_sign - d) * 60))
    if m == 60:
        m = 0
        d += 1
    return f"{d}\u00b0{m:02d}\u2032"


def bisect_time(t0, t1, target_func, iters=BISECT_ITERS):
    """Bisection root-find for target_func, which changes sign between t0 and t1."""
    f0 = target_func(t0)
    for _ in range(iters):
        tm = 0.5 * (t0 + t1)
        fm = target_func(tm)
        if (f0 <= 0) == (fm <= 0):
            t0, f0 = tm, fm
        else:
            t1 = tm
    return 0.5 * (t0 + t1)


# =================================================================
# DECAN INGRESS SCANNING (Saturn, Jupiter, Mars, Sun, Venus, Mercury)
# =================================================================

def find_crossings(pid, t0, t1, idx0, idx1, depth=0, max_depth=40):
    """Recursively locate ALL decan-boundary crossings of body `pid` in [t0,t1].
    Handles forward crossings, retrograde (backward) crossings, and - purely
    defensively - the case where more than one boundary is skipped inside a
    single coarse step (not expected for these bodies at 3h resolution)."""
    diff = (idx1 - idx0) % 36
    if diff == 0:
        return []
    if diff in (1, 35) or depth >= max_depth:
        boundary_deg = (idx1 * 10) % 360 if diff == 1 else (idx0 * 10) % 360

        def f(tt, _pid=pid, _b=boundary_deg):
            return signed_gap(lon_of(tt, _pid), _b)

        t_cross = bisect_time(t0, t1, f)
        # Derive the entered decan from the already-known integer index
        # (idx1), NOT by re-deriving it from the bisection-converged
        # longitude: right at a boundary, floating-point noise can land
        # lon_cross a hair on either side, silently flipping the reported
        # sign/decan to the wrong (pre-crossing) one. idx1 is exact.
        sign_idx, decan_in_sign = divmod(idx1, 3)
        sign_name = ZODIAC_SIGNS[sign_idx]
        decan_roman = ROMAN_DECAN[decan_in_sign]
        y, mo, da, hh, mi = jd_to_civil(t_cross)
        return [{
            "jd": t_cross, "year": y, "month": mo, "day": da,
            "hour": hh, "minute": mi, "sign": sign_name, "decan": decan_roman,
        }]
    tm = 0.5 * (t0 + t1)
    idx_m = decan_index(lon_of(tm, pid))
    left = find_crossings(pid, t0, tm, idx0, idx_m, depth + 1, max_depth)
    right = find_crossings(pid, tm, t1, idx_m, idx1, depth + 1, max_depth)
    return left + right


def scan_decan_ingresses(planet_name, jd_start, jd_end, step_days=STEP_DAYS):
    pid = PLANET_IDS[planet_name]
    events = []
    t0 = jd_start
    idx0 = decan_index(lon_of(t0, pid))
    while t0 < jd_end - 1e-9:
        t1 = min(t0 + step_days, jd_end)
        idx1 = decan_index(lon_of(t1, pid))
        if idx1 != idx0:
            events.extend(find_crossings(pid, t0, t1, idx0, idx1))
        t0, idx0 = t1, idx1
    return events


# =================================================================
# NEW MOON SCANNING (Volvelle anchor)
# =================================================================

def elong(t):
    """Moon-minus-Sun apparent ecliptic elongation, 0-360 deg."""
    return (lon_of(t, swe.MOON) - lon_of(t, swe.SUN)) % 360.0


def scan_new_moons(jd_start, jd_end, step_days=STEP_DAYS):
    """New Moon = Sun-Moon conjunction = elongation wraps 360 -> 0.
    Elongation increases monotonically (~10.8-14.4 deg/day) since the Moon
    always outpaces the Sun in geocentric longitude, so a same-step decrease
    unambiguously marks a conjunction."""
    events = []
    t0 = jd_start
    e0 = elong(t0)
    while t0 < jd_end - 1e-9:
        t1 = min(t0 + step_days, jd_end)
        e1 = elong(t1)
        if e1 < e0:
            def f(tt):
                return signed_gap(elong(tt), 0.0)
            t_cross = bisect_time(t0, t1, f)
            lon_cross = lon_of(t_cross, swe.MOON)
            sign_name, decan_roman, deg_in_sign = sign_and_decan(lon_cross)
            y, mo, da, hh, mi = jd_to_civil(t_cross)
            events.append({
                "jd": t_cross, "year": y, "month": mo, "day": da,
                "hour": hh, "minute": mi, "sign": sign_name,
                "decan": decan_roman, "deg_in_sign": deg_in_sign,
            })
        t0, e0 = t1, e1
    return events


# =================================================================
# GRID ASSEMBLY
# =================================================================

def build_grid(jd_start, jd_end):
    # empty scaffold: one row per (year, sign), in that fixed order
    rows = {}
    for year in range(START_YEAR, END_YEAR + 1):
        for sign in ZODIAC_SIGNS:
            row = {"Year": year, "Zodiac_Sign": sign}
            for p in CHALDEAN_ORDER:
                row[p] = ""
            row["Moon_Volvelle_Key"] = ""
            rows[(year, sign)] = row

    def append_cell(year, sign, col, text):
        key = (year, sign)
        if key not in rows:
            return  # crossing landed outside [START_YEAR, END_YEAR] (shouldn't happen)
        cell = rows[key][col]
        rows[key][col] = text if not cell else cell + "\n" + text

    for planet in CHALDEAN_ORDER:
        print(f"Scanning decan ingresses: {planet} ...")
        events = scan_decan_ingresses(planet, jd_start, jd_end)
        print(f"  {planet}: {len(events)} ingress events")
        for ev in events:
            line = f"{ev['decan']}: {fmt_date(ev['month'], ev['day'])}"
            append_cell(ev["year"], ev["sign"], planet, line)

    print("Scanning New Moons (Moon_Volvelle_Key) ...")
    nm_events = scan_new_moons(jd_start, jd_end)
    print(f"  New Moons: {len(nm_events)} events")
    for ev in nm_events:
        abbr = SIGN_ABBR[ev["sign"]]
        line = (f"{ev['decan']}: {fmt_date(ev['month'], ev['day'])} "
                f"{ev['hour']:02d}:{ev['minute']:02d} UTC \u2014 "
                f"{fmt_dm(ev['deg_in_sign'])} {abbr}")
        append_cell(ev["year"], ev["sign"], "Moon_Volvelle_Key", line)

    ordered = []
    for year in range(START_YEAR, END_YEAR + 1):
        for sign in ZODIAC_SIGNS:
            ordered.append(rows[(year, sign)])

    df = pd.DataFrame(ordered)
    df = df[["Year", "Zodiac_Sign"] + CHALDEAN_ORDER + ["Moon_Volvelle_Key"]]
    return df


def main():
    if EPHE_PATH:
        swe.set_ephe_path(EPHE_PATH)

    jd_start = jd_ut(START_YEAR, 1, 1, 0.0)
    jd_end = jd_ut(END_YEAR + 1, 1, 1, 0.0)  # exclusive upper bound: through Dec 31 END_YEAR

    print(f"Building {START_YEAR}-{END_YEAR} decan ingress ephemeris "
          f"({STEP_HOURS}h scan step, {BISECT_ITERS}-iteration bisection)...")
    df = build_grid(jd_start, jd_end)

    df.to_csv(OUTPUT_CSV, index=False)
    print(f"\nWrote {len(df)} rows to {OUTPUT_CSV}")


if __name__ == "__main__":
    main()
