# Decan Ephemeris

A small Python application that generates a landscape PDF ephemeris book for a
chosen range of years. Each year gets one page showing planetary decan ingresses
and new moons across the twelve zodiac signs.

## Requirements

Install these before trying to run the program:

1. **64-bit Python 3.11**
   - Python 3.11 is the recommended version on Windows because `pyswisseph`
     provides a prebuilt Windows package for it.
   - The standard Python installer includes Tkinter, which provides the GUI.
   - After installing Python, close and reopen your terminal so the `python`
     command is available.
2. **Swiss Ephemeris for Python (`pyswisseph`)**
3. **ReportLab (`reportlab`)**

Install the required Python packages with:

```powershell
python -m pip install pyswisseph reportlab
```

You can verify the installation with:

```powershell
python -c "import swisseph, reportlab, tkinter; print('Requirements OK')"
```

## Getting started

Clone the repository and enter its directory:

```powershell
git clone https://github.com/AmirUnda/DecanEphemeris.git
cd DecanEphemeris
```

Install the dependencies if you have not already done so:

```powershell
python -m pip install pyswisseph reportlab
```

## Run the GUI

Launch the program without year arguments:

```powershell
python ephemeris_book.py
```

Enter a start year and an end year, then select **Generate**. The button is
disabled while generation is running, and the window reports when the PDF is
ready or if an error occurs.

The default range is 1926 through 2126. Generating the full range can take a
few minutes. Use a short range first to confirm that the installation works.

## Run from the command line

Pass the start and end years directly to bypass the GUI:

```powershell
python ephemeris_book.py 2026 2026
```

For the complete default range:

```powershell
python ephemeris_book.py 1926 2126
```

The start year must be less than or equal to the end year.

## Output location

PDFs are always written to the `Test outputs` folder beside
`ephemeris_book.py`, regardless of the directory from which the program is
launched:

```text
Test outputs/ephemeris_STARTYEAR_ENDYEAR.pdf
```

For example:

```text
Test outputs/ephemeris_2026_2026.pdf
```

Generating the same year range again replaces the PDF with the same filename.
The output directory is created automatically if it does not exist.

## What the PDF contains

Each landscape page represents one year:

- Columns: Saturn, Jupiter, Mars, Sun, Venus, Mercury, and Moon.
- Rows: the twelve tropical zodiac signs, beginning with Aries.
- Planet cells: every 10-degree decan entered during that year.
- Moon cells: new moons with their date, decan, and degree.
- `I`, `II`, and `III`: the three decans within a sign.
- `R`: a retrograde entry into a decan.
- Shaded cells: the sign occupied by that planet on January 1.

Dates are calculated in UT using the tropical zodiac and the built-in Moshier
ephemeris. No separate Swiss Ephemeris data files are required.

## Configuration

The main settings are near the top of `ephemeris_book.py`:

```python
START_YEAR = 1926
END_YEAR = 2126
STEP_HOURS = 3
SHOW_DECANS = True
PAGE_SIZE = landscape(letter)
```

- Set `SHOW_DECANS` to `False` to record sign ingresses instead of every decan.
- Change `PAGE_SIZE` to `landscape(A4)` if A4 output is preferred.
- A smaller `STEP_HOURS` value increases scan frequency but takes longer.

## Troubleshooting

### `python` is not recognized

Close and reopen the terminal after installing Python. Confirm the installation:

```powershell
python --version
```

On Windows, the Python launcher may also work:

```powershell
py -3.11 ephemeris_book.py
```

### `Swiss Ephemeris not found`

Install `pyswisseph` using the same Python interpreter that runs the program:

```powershell
python -m pip install pyswisseph
```

If installation asks for Microsoft Visual C++ Build Tools, check that you are
using 64-bit Python 3.11 rather than a newer Python version for which
`pyswisseph` may not provide a compatible Windows wheel.

### `ReportLab not found`

```powershell
python -m pip install reportlab
```

### The full generation appears slow

The program calculates positions at three-hour intervals across every requested
year. Test with a single year first:

```powershell
python ephemeris_book.py 2026 2026
```
