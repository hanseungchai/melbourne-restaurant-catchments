"""Snapshot of the data-layer diagnostics: print each one's latest results and show them in one page.

Not a diagnostic: makes no claim of its own. It runs or replays the diagnostics in SNAPSHOT_DIAGNOSTICS
for a subject, as a basic-statistics snapshot before later stages alter the data for analysis.

For each diagnostic, in order:
- already computed for the subject (a saved run log whose figures all still exist): print the
  latest log; nothing is rerun;
- otherwise: run the diagnostic in its own process (one at a time, low memory), save its printed
  output as diagnostic_data/<diagnostic>_<YYYYMMDD>_log.txt (the run's own prefix, read from its
  "Saved ..." lines; a same-day rerun replaces that day's log, as D1).
Then one HTML page, diagnostic_data/snapshot_report_<YYYYMMDD>.html (a same-day run replaces it),
holds every diagnostic's printed results (quiet lines dropped) and its figures with their file
names, and opens once in the browser: one window instead of one image viewer per figure (several
viewer windows launched at once failed to load). Click a figure to open it at full size.
A run that fails is reported with its output and no log is saved; the other diagnostics still run.
Quiet by default: file paths, "already computed"/"running" notices and similar housekeeping lines
(QUIET_LINE_PREFIXES) are not printed; logs always keep every line. Pass --verbose (main.py:
is_snapshot_verbose) to print everything.

Subject: as main.py's subject_name (None = default subject; else a file name, no .txt, in
inputs/alt_subjects/). Only a subject at the default subject's location is accepted for now: the
hex diagnostics' conclusions are about that place. drive_speed_limits and pt_stop_walk_access are
not tagged by subject (only their map centre depends on it), so any of their runs counts.

Self-contained: imports nothing from functions/, config.py, the pipeline or other diagnostics; runs
them as scripts (CLAUDE.md D1).
"""
import datetime
import html
import os
import re
import subprocess
import sys
from pathlib import Path

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTICS_DIR = PROJECT_ROOT / "diagnostics"
DIAGNOSTIC_DATA_DIR = DIAGNOSTICS_DIR / "diagnostic_data"
DEFAULT_SUBJECT_COORD_PATH = PROJECT_ROOT / "frozen_inputs" / "manual_inputs" / "subject_business_coord.txt"
ALT_SUBJECTS_DIR = PROJECT_ROOT / "inputs" / "alt_subjects"
SUBJECT_COORD_SUFFIX = ".txt"

# ---------------------------------------------------------------------------
# Snapshot contents
# ---------------------------------------------------------------------------
SUBJECT_NAME = None             # None = default subject; else a file name (no .txt) in inputs/alt_subjects/

# diagnostic name -> whether its figures carry the subject tag
SNAPSHOT_DIAGNOSTICS = {
    "drive_speed_limits": False,
    "pt_stop_walk_access": False,
    "residents_per_hex_distribution": True,
    "residents_vs_workers_geography": True,
    "venue_count_distribution": True,
    "road_density_distribution": True,
}
SUBJECT_TAG_DECIMALS = 5        # as the hex stage's "<lat>_<lon>" tag
LOG_SUFFIX = "_log.txt"
SAVED_LINE_PREFIX = "Saved "
FIGURE_SUFFIX = ".png"
RUN_STAMP_PATTERN = r"\d{8}(?:_\d{4})?"   # a run prefix's YYYYMMDD (older runs: YYYYMMDD_HHMM)
SHOULD_OPEN_REPORT = True       # open the HTML report in the default browser (Windows)
REPORT_PATH = DIAGNOSTIC_DATA_DIR / f"snapshot_report_{datetime.datetime.now():%Y%m%d}.html"
REPORT_STYLE = ("body{font-family:sans-serif;margin:16px;max-width:1400px}"
                "pre{background:#f4f4f4;padding:8px;overflow-x:auto;font-size:12px}"
                "figure{margin:12px 0}img{max-width:100%;border:1px solid #ccc}"
                "figcaption{font-size:12px;color:#555;word-break:break-all}")
RULE = "=" * 100
VERBOSE_FLAG = "--verbose"      # command-line switch: print housekeeping lines too
# Housekeeping lines hidden unless verbose: saved/opened file paths, run notices, log headers.
QUIET_LINE_PREFIXES = ("Saved ", "Figure: ", "Already computed", "Running ", "Loading ",
                       "Subject check passed", "# ")


def emit(text, is_verbose):
    """Print text, dropping housekeeping lines unless is_verbose."""
    for line in text.splitlines():
        if is_verbose or not line.startswith(QUIET_LINE_PREFIXES):
            print(line)


def read_coord(coord_path):
    first_line = coord_path.read_text(encoding="utf-8").splitlines()[0].strip()
    lat_text, lon_text = first_line.split(",")
    return float(lat_text), float(lon_text)


def subject_coord_path(subject_name):
    """As functions/input_helper.subject_coord_path."""
    if subject_name is None:
        return DEFAULT_SUBJECT_COORD_PATH
    coord_path = ALT_SUBJECTS_DIR / f"{subject_name}{SUBJECT_COORD_SUFFIX}"
    if not coord_path.is_file():
        raise FileNotFoundError(f"no coordinate file for subject '{subject_name}' at {coord_path}")
    return coord_path


def subject_tag(subject_lat, subject_lon):
    return f"{subject_lat:.{SUBJECT_TAG_DECIMALS}f}_{subject_lon:.{SUBJECT_TAG_DECIMALS}f}"


def check_subject(subject_name):
    """Return the subject's tag; stop unless the subject sits at the default subject's location."""
    subject_lat, subject_lon = read_coord(subject_coord_path(subject_name))
    default_lat, default_lon = read_coord(DEFAULT_SUBJECT_COORD_PATH)
    if (subject_lat, subject_lon) != (default_lat, default_lon):
        raise SystemExit(f"subject '{subject_name}' at ({subject_lat}, {subject_lon}) is not the default subject "
                         f"({default_lat}, {default_lon}); the snapshot diagnostics cover the default subject only")
    return subject_tag(subject_lat, subject_lon)


def saved_paths(log_text):
    """Paths from a run's "Saved ..." lines."""
    return [Path(line[len(SAVED_LINE_PREFIX):].strip()) for line in log_text.splitlines()
            if line.startswith(SAVED_LINE_PREFIX)]


def figure_paths(log_text):
    return [path for path in saved_paths(log_text) if path.suffix == FIGURE_SUFFIX]


def latest_valid_log(diagnostic_name, tag):
    """Newest log whose figures all exist (and carry tag, when given); None if there is none."""
    logs = sorted(DIAGNOSTIC_DATA_DIR.glob(f"{diagnostic_name}_*{LOG_SUFFIX}"), reverse=True)
    for log_path in logs:   # run date in the name: name order is time order
        figures = figure_paths(log_path.read_text(encoding="utf-8"))
        if figures and all(path.exists() for path in figures) \
                and (tag is None or all(tag in path.name for path in figures)):
            return log_path
    return None


def run_diagnostic(diagnostic_name, is_verbose):
    """Run the diagnostic, echoing its output; save the output as its run's log. Return the log path or None."""
    script_path = DIAGNOSTICS_DIR / f"{diagnostic_name}.py"
    emit(f"Running {script_path.name} ...", is_verbose)
    environment = dict(os.environ, PYTHONIOENCODING="utf-8")
    process = subprocess.Popen([sys.executable, str(script_path)], cwd=PROJECT_ROOT, env=environment,
                               stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8")
    lines = []
    for line in process.stdout:
        emit(line, is_verbose)
        lines.append(line)
    output_text = "".join(lines)
    if process.wait() != 0:
        if not is_verbose:   # a failure shows the full output, quiet or not
            print(output_text)
        print(f"\n{diagnostic_name} FAILED (exit {process.returncode}); no log saved")
        return None

    stamps = {match.group(0) for path in saved_paths(output_text)
              for match in [re.match(rf"{diagnostic_name}_({RUN_STAMP_PATTERN})", path.name)] if match}
    if len(stamps) != 1:
        print(f"\n{diagnostic_name}: expected one run prefix in its Saved lines, found {sorted(stamps)}; no log saved")
        return None
    log_path = DIAGNOSTIC_DATA_DIR / f"{stamps.pop()}{LOG_SUFFIX}"   # same day: replaces that day's log
    header = f"# {script_path.name}, run {datetime.datetime.now():%Y-%m-%d %H:%M} by snapshot_report.py\n"
    log_path.write_text(header + output_text, encoding="utf-8")
    emit(f"Saved log {log_path}", is_verbose)
    return log_path


def show(log_path, should_print, is_verbose):
    """Print the log (skipped right after a run, whose output was just echoed) and list its figures."""
    if should_print:
        emit(log_path.read_text(encoding="utf-8"), is_verbose)
    for path in figure_paths(log_path.read_text(encoding="utf-8")):
        emit(f"Figure: {path}", is_verbose)


def report_section(diagnostic_name, status, log_path):
    """One diagnostic's HTML: heading, its printed results (quiet lines dropped), its figures with names."""
    parts = [f"<h2>{html.escape(diagnostic_name)}</h2>",
             f"<p>{html.escape(status)}: {html.escape(log_path.name if log_path else '-')}</p>"]
    if log_path is None:
        return "\n".join(parts)
    log_text = log_path.read_text(encoding="utf-8")
    kept_lines = [line for line in log_text.splitlines() if not line.startswith(QUIET_LINE_PREFIXES)]
    parts.append(f"<pre>{html.escape(chr(10).join(kept_lines))}</pre>")
    for path in figure_paths(log_text):
        uri = path.as_uri()
        parts.append(f'<figure><a href="{uri}"><img src="{uri}" alt="{html.escape(path.name)}"></a>'
                     f"<figcaption>{html.escape(path.name)}</figcaption></figure>")
    return "\n".join(parts)


def write_report(tag, sections):
    """Write the day's HTML report (replacing a same-day one) and return its path."""
    title = f"Snapshot review, subject {tag}, {datetime.datetime.now():%Y-%m-%d %H:%M}"
    page = (f"<!doctype html><html><head><meta charset='utf-8'><title>{html.escape(title)}</title>"
            f"<style>{REPORT_STYLE}</style></head><body><h1>{html.escape(title)}</h1>"
            + "\n".join(sections) + "</body></html>")
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    REPORT_PATH.write_text(page, encoding="utf-8")
    return REPORT_PATH


def main(is_verbose=False):
    tag = check_subject(SUBJECT_NAME)
    print(f"Snapshot for subject {SUBJECT_NAME or 'default'} ({tag})")
    summary, sections = [], []
    for diagnostic_name, is_subject_tagged in SNAPSHOT_DIAGNOSTICS.items():
        print(f"\n{RULE}\n{diagnostic_name}\n{RULE}")
        log_path = latest_valid_log(diagnostic_name, tag if is_subject_tagged else None)
        if log_path is not None:
            emit(f"Already computed: {log_path.name}", is_verbose)
            status = "reused"
        else:
            log_path = run_diagnostic(diagnostic_name, is_verbose)
            status = "ran" if log_path else "FAILED"
        if log_path is not None:
            show(log_path, should_print=status == "reused", is_verbose=is_verbose)
        summary.append((diagnostic_name, status, log_path.name if log_path else "-"))
        sections.append(report_section(diagnostic_name, status, log_path))

    print(f"\n{RULE}\nSnapshot summary")
    for diagnostic_name, status, log_name in summary:
        print(f"  {diagnostic_name:<34}{status:<8}{log_name}")
    report_path = write_report(tag, sections)
    print(f"Report: {report_path}")
    if SHOULD_OPEN_REPORT:
        os.startfile(report_path)


if __name__ == "__main__":
    main(is_verbose=VERBOSE_FLAG in sys.argv[1:])
