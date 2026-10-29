"""Does Google's transit route duration exclude the initial wait? Evidence for the route table's times.

Claim under test (TRN-8 smoke findings, 2026-10-16): a Google transit route's `duration` runs from the
moment you leave (just in time to walk to the first boarding) to arrival, not from the requested departure,
so any wait before leaving is not in it. Where the pipeline relies on it: transit_fetch.route_times and
build_route_table (leave, arrival and arrival_from_request_s per route), and through them every T7 (f) fit
target that reads arrival from the requested departure.
Leave = the first transit step's departureTime minus the walk steps' staticDuration before it; arrival =
the last transit step's arrivalTime plus the walk steps' staticDuration after it. Walk-only routes leave at
the requested departure and are listed apart.
Pre-registered rule (set before the first run, 2026-10-16): SUPPORTED if, on every transit route,
|arrival - leave - duration| <= TOL_S, and the requested-departure reading (arrival - requested departure)
differs from duration by more than TOL_S on at least one route (else the data can't tell the two apart).
Otherwise NOT SUPPORTED: list the routes. Also reported, no rule (T7 (f) context): per pair, whether
Google's default route is its earliest arrival from the requested departure.

Conclusion (run 2026-10-16): SUPPORTED on 27 transit routes from 5 answers: arrival - leave matches
duration within 8 s on every route, while arrival - requested departure exceeds it on all 27 (up to 35
min). Caveat: TOL_S was set after the session's route table had shown gaps of 0-8 s, so the tolerance is
not blind; the request reading fails by minutes, not seconds, so the verdict doesn't hinge on it. Default
route = earliest arrival from the request on 3 of 5 pairs (draw_no 68: a train arrives 6.6 min earlier;
707: walk-only arrives 2.7 min earlier). 5 answers only: recheck on the exploration fetch.

Inputs (read only): the smoke-test answers outputs/transit_validation/<subject>/
transit_google_smoke_<tag>.raw.jsonl (5 paid calls, 2026-10-16; also in output_backup/). No API calls.
Self-contained (CLAUDE.md D1). Reads saved answers only; results carry the run date; a same-day rerun
replaces that day's results.
"""
import datetime
import json
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
RAW_PATH = SUBJECT_DIR / "transit_google_smoke_res2021_wrk2021_ven20260925_-37.76870_144.97196.raw.jsonl"
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_google_duration"

TOL_S = 10                         # walk steps are whole seconds, stop times whole minutes; seen gaps 0-8 s
DEFAULT_ROUTE_LABEL = "DEFAULT_ROUTE"
STEP_MODE_TRANSIT = "TRANSIT"


def utc(timestamp):
    return datetime.datetime.fromisoformat(timestamp).astimezone(datetime.timezone.utc)


def seconds(duration):
    return int(duration.rstrip("s")) if duration else 0


def route_rows(record):
    """One row per route: duration, leave, arrival and the requested departure, in seconds."""
    requested = utc(record["request"]["departureTime"])
    rows = []
    for route_ix, route in enumerate(record["resp"].get("routes", [])):
        steps = [step for leg in route.get("legs", []) for step in leg.get("steps", [])]
        transit_ix = [i for i, step in enumerate(steps) if step.get("travelMode") == STEP_MODE_TRANSIT]
        duration_s = seconds(route.get("duration"))
        if transit_ix:
            first, last = transit_ix[0], transit_ix[-1]
            leave = (utc(steps[first]["transitDetails"]["stopDetails"]["departureTime"])
                     - datetime.timedelta(seconds=sum(seconds(step.get("staticDuration")) for step in steps[:first])))
            arrival = (utc(steps[last]["transitDetails"]["stopDetails"]["arrivalTime"])
                       + datetime.timedelta(seconds=sum(seconds(step.get("staticDuration")) for step in steps[last + 1:])))
        else:
            leave, arrival = requested, requested + datetime.timedelta(seconds=duration_s)
        rows.append({"draw_no": record["draw_no"], "route_ix": route_ix, "is_transit": bool(transit_ix),
                     "is_default": DEFAULT_ROUTE_LABEL in route.get("routeLabels", []), "duration_s": duration_s,
                     "leave_wait_s": (leave - requested).total_seconds(),
                     "leave_reading_gap_s": (arrival - leave).total_seconds() - duration_s,
                     "request_reading_gap_s": (arrival - requested).total_seconds() - duration_s,
                     "arrival_from_request_s": (arrival - requested).total_seconds()})
    return rows


def main():
    DIAGNOSTIC_DATA_DIR.mkdir(parents=True, exist_ok=True)
    run_date = datetime.date.today().strftime("%Y%m%d")
    with open(RAW_PATH) as raw_file:
        routes_df = pd.DataFrame([row for record in map(json.loads, raw_file) for row in route_rows(record)])
    transit_df = routes_df[routes_df.is_transit]
    is_leave_ok = transit_df.leave_reading_gap_s.abs() <= TOL_S
    is_distinguishable = (transit_df.request_reading_gap_s.abs() > TOL_S).any()
    verdict = "SUPPORTED" if is_leave_ok.all() and is_distinguishable else "NOT SUPPORTED"

    earliest_ix = routes_df.groupby("draw_no").arrival_from_request_s.idxmin()
    default_df = routes_df[routes_df.is_default].set_index("draw_no")
    is_default_earliest = (routes_df.loc[earliest_ix].set_index("draw_no").route_ix == default_df.route_ix)

    lines = [f"{NAME} {run_date}: {verdict}",
             f"transit routes {len(transit_df)} (walk-only {int((~routes_df.is_transit).sum())}) from "
             f"{routes_df.draw_no.nunique()} answers",
             f"leave reading |arrival - leave - duration|: max {transit_df.leave_reading_gap_s.abs().max():.0f} s "
             f"(rule <= {TOL_S} s on every route: {bool(is_leave_ok.all())})",
             f"request reading |arrival - requested - duration|: {int((transit_df.request_reading_gap_s.abs() > TOL_S).sum())}"
             f" of {len(transit_df)} routes differ by > {TOL_S} s (max {transit_df.request_reading_gap_s.max():.0f} s)",
             f"default route is the earliest arrival from the request on {int(is_default_earliest.sum())} of "
             f"{len(is_default_earliest)} pairs",
             routes_df.round(0).to_string(index=False)]
    if not is_leave_ok.all():
        lines += ["routes breaking the leave reading:", transit_df[~is_leave_ok].to_string(index=False)]
    summary = "\n".join(lines)
    print(summary)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_summary.txt").write_text(summary, encoding="utf-8")
    routes_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_routes.csv", index=False)


if __name__ == "__main__":
    main()
