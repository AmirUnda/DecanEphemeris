#!/usr/bin/env python3
"""
Ephemeris ingress book: one landscape PDF page per year.

  columns : Saturn, Jupiter, Mars, Sun, Venus, Mercury, Moon   (Chaldean order)
  rows    : the 12 zodiac signs, Aries at the top
  cells   : every DECAN (10-degree third of a sign) each planet entered that year,
            filed under the sign that decan belongs to
              "II: Mar 30"   = entered decan II of that sign on Mar 30
              "II: Mar 30 R" = retrograde entry (planet backed into that decan)
              shaded cell    = planet was already in that sign on Jan 1
  Moon    : new moons only, each with date, decan and degree
              "* Aug 12" / "Decan II, 19 deg"

Dates are UT, tropical zodiac, built-in Moshier ephemeris (no data files needed).

Setup :  pip install pyswisseph reportlab
GUI   :  python ephemeris_book.py
Test  :  python ephemeris_book.py 2026 2026     (one page, a few seconds)
Full  :  python ephemeris_book.py 1926 2126     (a few minutes)
"""
import sys
import datetime
import threading
from collections import defaultdict
from pathlib import Path

try:
    import swisseph as swe
except ImportError:
    sys.exit("Swiss Ephemeris not found.  Run:  pip install pyswisseph")

try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4, landscape, letter, portrait
    from reportlab.lib.units import inch
    from reportlab.pdfbase.pdfmetrics import stringWidth
    from reportlab.pdfgen import canvas
    from reportlab.platypus import Table, TableStyle
except ImportError:
    sys.exit("ReportLab not found.  Run:  pip install reportlab")

# ----------------------------------------------------------------------
# Settings
# ----------------------------------------------------------------------
START_YEAR = 1926
END_YEAR = 2126
STEP_HOURS = 3            # scan interval; exact times come from bisection
SHOW_DECANS = True        # True = every 10-degree decan entry (I / II / III); False = signs only
PAGE_SIZE = landscape(letter)   # or landscape(A4); portrait(letter) gives taller rows = bigger type

FLAGS = swe.FLG_MOSEPH    # built-in Moshier model: no .se1 files needed

SIGNS = [
    "Aries", "Taurus", "Gemini", "Cancer", "Leo", "Virgo",
    "Libra", "Scorpio", "Sagittarius", "Capricorn", "Aquarius", "Pisces",
]

# Chaldean order (slowest to fastest). The Moon is the 7th column; it gets
# new moons only (with decan and degree), not ingresses.
PLANETS = {
    "Saturn": swe.SATURN,
    "Jupiter": swe.JUPITER,
    "Mars": swe.MARS,
    "Sun": swe.SUN,
    "Venus": swe.VENUS,
    "Mercury": swe.MERCURY,
}
COLUMNS = list(PLANETS) + ["Moon"]

ROMAN = {1: "I", 2: "II", 3: "III"}
MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
          "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]

PAD_X, PAD_Y = 3, 2       # table cell padding, points
LEAD = 1.15               # line spacing as a multiple of font size


# ----------------------------------------------------------------------
# Astronomy helpers
# ----------------------------------------------------------------------
def lon(jd, body):
    """Tropical ecliptic longitude in degrees, 0 <= lon < 360."""
    res = swe.calc_ut(jd, body, FLAGS)
    # pyswisseph 2.10+ returns (xx, retflag); very old versions return xx alone.
    pos = res[0] if isinstance(res[0], (tuple, list)) else res
    x = pos[0] % 360.0
    return 0.0 if x >= 360.0 else x


def to_datetime(jd):
    """Julian Day (UT) -> datetime. timedelta avoids the hour == 24.0 edge case."""
    y, m, d, h = swe.revjul(jd)
    return datetime.datetime(y, m, d) + datetime.timedelta(hours=h)


def fmt(d):
    return f"{MONTHS[d.month - 1]} {d.day:02d}"


def elongation(jd):
    """Moon minus Sun, 0-360. Wraps from ~360 to ~0 at every new moon."""
    return (lon(jd, swe.MOON) - lon(jd, swe.SUN)) % 360.0


def find_crossing(jd_a, jd_b, body, unit, cell_before):
    """Bisect [jd_a, jd_b] for the moment the planet leaves `cell_before`.
    A 'cell' is a sign (unit=30) or a decan (unit=10). Works for direct and
    retrograde motion and across the 360 -> 0 wrap."""
    lo, hi = jd_a, jd_b
    for _ in range(16):
        mid = (lo + hi) / 2.0
        if int(lon(mid, body) // unit) == cell_before:
            lo = mid
        else:
            hi = mid
    return hi


def find_new_moon(jd_a, jd_b):
    """Bisect for the instant elongation wraps past 360 -> 0."""
    lo, hi = jd_a, jd_b
    for _ in range(16):
        mid = (lo + hi) / 2.0
        if elongation(mid) > 180.0:      # still before the new moon
            lo = mid
        else:
            hi = mid
    return hi


# ----------------------------------------------------------------------
# Scan the whole range once
# ----------------------------------------------------------------------
def scan(start_year, end_year):
    """Return {(year, sign_index, column_name): [entry text, ...]} in date order."""
    cells = defaultdict(list)
    unit = 10.0 if SHOW_DECANS else 30.0
    step = STEP_HOURS / 24.0
    jd0 = swe.julday(start_year, 1, 1, 0.0)
    jd1 = swe.julday(end_year + 1, 1, 1, 0.0)
    n_steps = int(round((jd1 - jd0) / step))
    steps_per_year = int(round(365.25 * 24 / STEP_HOURS))

    prev = {name: lon(jd0, body) for name, body in PLANETS.items()}
    prev_elong = elongation(jd0)
    progressed = False

    for i in range(1, n_steps + 1):
        jd_a = jd0 + (i - 1) * step
        jd_b = jd0 + i * step
        cur = {}

        # Planet ingresses (decan, or sign if SHOW_DECANS is False)
        for name, body in PLANETS.items():
            a, b = prev[name], lon(jd_b, body)
            cur[name] = b
            if int(a // unit) != int(b // unit):
                t = find_crossing(jd_a, jd_b, body, unit, int(a // unit))
                when = to_datetime(t)
                pos = lon(t, body)                    # just past the boundary
                sign = int(pos // 30) % 12
                decan = int((pos % 30) // 10) + 1
                retro = ((b - a + 180.0) % 360.0) - 180.0 < 0
                text = fmt(when)
                if SHOW_DECANS:
                    text = f"{ROMAN[decan]}: {text}"
                if retro:
                    text += " R"
                cells[(when.year, sign, name)].append(text)

        # New moon: elongation only ever increases, so a drop means it wrapped
        elong = (lon(jd_b, swe.MOON) - cur["Sun"]) % 360.0
        if elong < prev_elong:
            t = find_new_moon(jd_a, jd_b)
            when = to_datetime(t)
            pos = lon(t, swe.MOON)
            sign = int(pos // 30) % 12
            deg = int(pos % 30)                       # whole degrees into the sign
            decan = deg // 10 + 1
            cells[(when.year, sign, "Moon")].append(
                f"\u2022 {fmt(when)}\nDecan {ROMAN[decan]}, {deg:02d}\u00b0"
            )

        prev, prev_elong = cur, elong

        if i % steps_per_year == 0:
            sys.stdout.write(f"\r  scanned through ~{start_year + i // steps_per_year - 1}   ")
            sys.stdout.flush()
            progressed = True
    if progressed:
        sys.stdout.write("\n")
    return cells


def signs_on_jan1(start_year, end_year):
    """Which sign each planet is in at 00:00 UT on Jan 1 (used for shading)."""
    out = {}
    for y in range(start_year, end_year + 1):
        jd = swe.julday(y, 1, 1, 0.0)
        for name, body in PLANETS.items():
            out[(y, name)] = int(lon(jd, body) // 30) % 12
    return out


# ----------------------------------------------------------------------
# PDF: one page per year
# ----------------------------------------------------------------------
def n_lines(entries):
    return sum(e.count("\n") + 1 for e in entries)


def page_layout(year, cells, body_h, col_w):
    """Cell text, row heights, and the biggest font (<= 10 pt) that fits the page
    both vertically (row heights) and horizontally (column width)."""
    rows, lines = [], []
    for s, sign in enumerate(SIGNS):
        row, n_max = [sign], 1
        for col in COLUMNS:
            entries = cells.get((year, s, col), [])
            row.append("\n".join(entries))
            n_max = max(n_max, n_lines(entries))
        rows.append(row)
        lines.append(n_max)

    widest = max(stringWidth(line, "Helvetica", 1.0)       # width of the longest line at 1 pt
                 for row in rows for cell in row[1:] for line in cell.split("\n"))
    font = min(10.0, (col_w - 2 * PAD_X) / widest)
    while True:
        label = min(11.0, font + 1.5)             # sign-name font
        need = [max(n * font, label) * LEAD + 2 * PAD_Y for n in lines]
        if sum(need) <= body_h or font <= 5.0:
            break
        font -= 0.1
    spare = body_h - sum(need)
    if spare < 0:
        print(f"  warning: {year} page is overfull even at {font:.1f} pt")
    heights = [h + spare * n / sum(lines) for h, n in zip(need, lines)]  # spare space to busier rows
    return rows, heights, font, label


def draw_page(c, year, cells, jan1):
    W, H = PAGE_SIZE
    margin = 0.5 * inch
    table_w = W - 2 * margin
    table_top = H - 1.0 * inch
    table_bottom = 0.7 * inch
    header_h = 0.45 * inch
    body_h = (table_top - table_bottom) - header_h

    # Title
    c.setFillColor(colors.black)
    c.setFont("Helvetica-Bold", 26)
    c.drawCentredString(W / 2, H - 0.6 * inch, str(year))
    c.setFont("Helvetica", 9)
    what = "Decan ingresses" if SHOW_DECANS else "Sign ingresses"
    c.drawCentredString(
        W / 2, H - 0.82 * inch,
        f"{what} and new moons  \u00b7  tropical zodiac  \u00b7  dates in UT",
    )

    # Table: header + 12 sign rows
    sign_w = 1.1 * inch
    col_w = (table_w - sign_w) / len(COLUMNS)
    body_rows, heights, font, label = page_layout(year, cells, body_h, col_w)
    rows = [["Sign"] + list(PLANETS) + ["Moon\n(new moons)"]] + body_rows

    t = Table(rows, colWidths=[sign_w] + [col_w] * len(COLUMNS),
              rowHeights=[header_h] + heights)
    style = [
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), font),
        ("LEADING", (0, 0), (-1, -1), font * LEAD),
        ("LEFTPADDING", (0, 0), (-1, -1), PAD_X),
        ("RIGHTPADDING", (0, 0), (-1, -1), PAD_X),
        ("TOPPADDING", (0, 0), (-1, -1), PAD_Y),
        ("BOTTOMPADDING", (0, 0), (-1, -1), PAD_Y),
        ("ALIGN", (0, 0), (-1, -1), "CENTER"),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("GRID", (0, 0), (-1, -1), 0.6, colors.HexColor("#7b8794")),
        # header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1f2d3a")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, 0), 10),
        ("LEADING", (0, 0), (-1, 0), 12),
        # sign labels
        ("BACKGROUND", (0, 1), (0, -1), colors.HexColor("#eef1f4")),
        ("FONTNAME", (0, 1), (0, -1), "Helvetica-Bold"),
        ("FONTSIZE", (0, 1), (0, -1), label),
        ("LEADING", (0, 1), (0, -1), label * LEAD),
    ]
    # Shade the sign each planet is already in on Jan 1
    for j, name in enumerate(PLANETS, start=1):
        s = jan1[(year, name)]
        style.append(("BACKGROUND", (j, s + 1), (j, s + 1), colors.HexColor("#d8e6f7")))
    t.setStyle(TableStyle(style))
    _, th = t.wrapOn(c, table_w, H)
    t.drawOn(c, margin, table_top - th)

    # Legend
    c.setFont("Helvetica", 8)
    if SHOW_DECANS:
        line1 = ("I / II / III = decan entered (0-10, 10-20, 20-30 degrees of the sign)     "
                 "R = retrograde entry (planet backed into that decan)")
    else:
        line1 = "R = retrograde ingress (planet backed into the sign)"
    line2 = ("Shaded = planet already in that sign on Jan 1     "
             "\u2022 = new moon: date, decan, degree")
    c.drawString(margin, 0.50 * inch, line1)
    c.drawString(margin, 0.36 * inch, line2)
    c.showPage()


def generate_book(start, end):
    """Generate an ephemeris PDF and return its path."""
    output_dir = Path(__file__).resolve().parent / "Test outputs"
    output_dir.mkdir(parents=True, exist_ok=True)
    out = output_dir / f"ephemeris_{start}_{end}.pdf"

    print(f"Scanning {start}-{end} ({end - start + 1} pages)...")
    cells = scan(start, end)
    jan1 = signs_on_jan1(start, end)

    c = canvas.Canvas(str(out), pagesize=PAGE_SIZE)
    c.setTitle(f"Ephemeris ingress book {start}-{end}")
    for year in range(start, end + 1):
        draw_page(c, year, cells, jan1)
    c.save()
    print(f"Done: {out}")
    return out


def run_gui():
    """Show a small desktop form for choosing the year range."""
    import tkinter as tk
    from tkinter import messagebox

    root = tk.Tk()
    root.title("Ephemeris Book Generator")
    root.resizable(False, False)

    frame = tk.Frame(root, padx=18, pady=18)
    frame.grid()

    tk.Label(frame, text="Start year:").grid(row=0, column=0, sticky="e", padx=5, pady=5)
    start_entry = tk.Entry(frame, width=12)
    start_entry.insert(0, str(START_YEAR))
    start_entry.grid(row=0, column=1, padx=5, pady=5)

    tk.Label(frame, text="End year:").grid(row=1, column=0, sticky="e", padx=5, pady=5)
    end_entry = tk.Entry(frame, width=12)
    end_entry.insert(0, str(END_YEAR))
    end_entry.grid(row=1, column=1, padx=5, pady=5)

    status = tk.StringVar(value="Choose a year range, then click Generate.")
    status_label = tk.Label(frame, textvariable=status, wraplength=320, justify="left")
    status_label.grid(row=3, column=0, columnspan=2, sticky="w", pady=(12, 0))

    def generation_finished(out=None, error=None):
        generate_button.config(state="normal")
        if error is not None:
            status.set("Generation failed.")
            messagebox.showerror("Generation failed", str(error))
        else:
            status.set(f"Done: {out}")
            messagebox.showinfo("PDF generated", f"Saved to:\n{out}")

    def generate_clicked():
        try:
            start = int(start_entry.get().strip())
            end = int(end_entry.get().strip())
            if start > end:
                raise ValueError("Start year must be less than or equal to end year.")
        except ValueError as exc:
            message = str(exc) if str(exc) else "Enter valid whole-number years."
            messagebox.showerror("Invalid years", message)
            return

        generate_button.config(state="disabled")
        status.set(f"Generating {start}-{end}... This may take a few minutes.")

        def worker():
            try:
                out = generate_book(start, end)
            except Exception as exc:
                root.after(0, generation_finished, None, exc)
            else:
                root.after(0, generation_finished, out, None)

        threading.Thread(target=worker, daemon=True).start()

    generate_button = tk.Button(frame, text="Generate", width=18, command=generate_clicked)
    generate_button.grid(row=2, column=0, columnspan=2, pady=(12, 0))

    start_entry.focus_set()
    root.mainloop()


def main():
    if len(sys.argv) == 1:
        run_gui()
    elif len(sys.argv) == 3:
        try:
            start, end = int(sys.argv[1]), int(sys.argv[2])
        except ValueError:
            sys.exit("Start and end years must be whole numbers.")
        if start > end:
            sys.exit("Start year must be less than or equal to end year.")
        generate_book(start, end)
    else:
        sys.exit("Usage: python ephemeris_book.py [START_YEAR END_YEAR]")


if __name__ == "__main__":
    main()
