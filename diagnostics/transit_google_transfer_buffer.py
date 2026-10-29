"""Google's waiting rules at boardings, read from its saved transit routes: evidence for R5 patch 3 (TRN-16 register).

Claim (concepts/transit.md TRN-16; DESIGN.md Q24): Google plans (a) no wait at the first boarding: it leaves so its
walk reaches the first vehicle just in time; and (b) a fixed minimum connection time at every transfer, about 200 s
on top of its own listed walk, the same for every mode pair, not taken from the feed (PTV's transfers.txt carries no
minimum transfer times) and not a slower walk hidden behind the listed one. Where the pipeline relies on it: R5 patch 3
(FastRaptorWorker board wait 0 s in round 1, TRANSFER_BUFFER_S from round 2; diagnostics/transit_r5_patch_board_wait.py),
replacing R5's single 60 s and the model of record's 1-min departure shift.

Data: Google's raw Routes responses for the training sets only (first batch's train half, second batch, top-up); the
first batch's test and smoke-test records are skipped, the test extension and holdout never read. Every route, default
and alternatives. No API calls.

Quantities (per route; Google's times are whole minutes, its walk steps whole seconds):
  transfer gap_s = next ride's departureTime - previous ride's arrivalTime; walk_s = summed staticDuration of the walk
      steps between them; fixed_s = the part of walk_s in steps without a distance (station pathway times);
      slack_s = gap_s - walk_s.
  first_wait_s = duration - sum(step staticDuration) - sum(transfer slack_s): the most a first-boarding wait can be
      (Google reports no leave time; transit_fetch.route_times assumes none).
Checks (Claude's; quantities and bins set before this file's first run, after the scratch reads of 2026-10-21 that
prompted them, so not blind):
  (C1) slack_s distribution, and its floor per walk-length bin: a fixed buffer gives a flat floor; a slower hidden walk
       a floor rising with the walk.
  (C2) edge sharpness: for floor models y >= x_of(walk) + c, c the C_QUANTILE quantile of the residual, the share of
       transfers within EDGE_WINDOW_S above the line (whole-minute departures put about a fifth of transfers there under
       the right model). Models: (i) Google's listed distance-step seconds times k, k in K_GRID; (ii) walk_m / v, v in
       SPEED_GRID_KMH. y = gap_s - fixed_s. Split by rail / no rail.
  (C3) first_wait_s distribution; against the access walk and the leave second within the minute.
  (C4) fixed (no-distance) walk steps beside rides: share and values at the access tail, egress head and both sides of a
       transfer, by vehicle type (where an alighting or boarding charge would show).
  (C5) Google's listed transfer walk steps that carry a distance: OLS duration on distance, and the median ratio on
       steps >= 50 m.

Conclusion (run 2026-10-21):
  (C1) 8,159 transfers in 2,232 pairs; slack > 0 on 8,156 (3 negative: one bus-bus alternative geometry with 2.4 km of
       walk listed between rides, excluded). No slack in (0, 200 s]; 68 in (200, 210]; median 362 s. Floor flat by
       walk length: 201-214 s from 37 s to 500 s of walk (fit 0.007 * walk_s + 208); no walk step: 240 s (whole minutes,
       so the buffer is over 180 s). Same floor for every mode pair and for same-stop transfers.
  (C2) sharpest edge with Google's listed walk at k = 1.0, c = 210 s (share 0.234; k 0.9: 0.205, 1.1: 0.127), rail and
       no rail alike; distance / speed models blur the edge (best 0.188 at 5 km/h, no rail). The floor is Google's own
       listed walk plus one constant, not distance at some speed plus mode-pair penalties.
  (C3) first_wait_s on 19,414 transit routes: median 1 s, 59% within +-1.5 s, 95% < 43 s, 99% < 62 s; the same by
       first vehicle; flat in access walk; uncorrelated with the leave second (-0.006). PTV stop times are on :00 (bus
       99.96%, train and tram 100%), so it is not hidden schedule seconds. Read: no first-boarding wait; a small duration-vs-steps residue of
       unknown cause.
  (C4) fixed steps sit only where a train is left (63-64% of destination and transfer exits; 30-120 s); none at
       boardings or at bus / tram alightings. An alighting or boarding charge would show at the trip ends; nothing
       unlisted does, so Google's extra time exists only between two rides.
  (C5) 18,431 steps: duration = 0.790 s/m * distance + 5.4 s (4.557 km/h); median ratio >= 50 m 4.312 km/h.
  Reading (Claude's): Google charges about 200 s per transfer on top of its listed walk (a minimum connection time,
  equivalent to alight + board charged only at transfers) and nothing at the first boarding. TRANSFER_BUFFER_S = 200
  (bounds: over 180 s from C1's no-walk floor, at most 201 s from the smallest slack).

Writes diagnostics/diagnostic_data/transit_google_transfer_buffer_<date>_{transfers.csv,first_wait.csv,summary.txt}.
Self-contained (CLAUDE.md D1). Usage: `python transit_google_transfer_buffer.py`.
"""
import datetime
import io
import json
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
RAW_PATHS = {"first_batch": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
             "second_batch": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
             "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}
FIRST_BATCH = "first_batch"
TRAIN_HALF = "train"
GTFS_DIR = PROJECT_ROOT / "inputs" / "gtfs_ptv_20261018"
FEED_NAMES = ["metro_bus", "metro_train", "tram"]
GTFS_ZIP_NAME = "google_transit.zip"
NAME = "transit_google_transfer_buffer"

MODE_WALK = "WALK"
MODE_TRANSIT = "TRANSIT"
RAIL_TYPE = "HEAVY_RAIL"
DEFAULT_LABEL = "DEFAULT_ROUTE"
MPS_TO_KMH = 3.6
SECONDS_PER_MIN = 60
SLACK_BINS_S = [-1e9, -60, -1e-9, 1e-9, 60, 120, 180, 190, 200, 210, 220, 240, 300, 1e9]
WALK_M_BINS = [-1, 0, 50, 100, 200, 300, 500, 800, 1200, 3000]
WALK_S_BIN_WIDTH_S = 60
WALK_S_BIN_MAX_S = 1500
MIN_BIN_N = 30
FIRST_WAIT_BINS_S = [-1e9, -60, -1.5, 1.5, 30, 60, 120, 300, 1e9]
FIRST_WAIT_NEAR_RANGE_S = (-1.5, 130)             # (C3) rows read against access walk and leave second
ACCESS_BINS_S = [-1, 0, 60, 120, 240, 480, 900, 3000]
EDGE_WINDOW_S = 60
C_QUANTILE = 0.002
K_GRID = [0, 0.5, 0.8, 0.9, 1.0, 1.1, 1.2, 1.5]
SPEED_GRID_KMH = [2.5, 3.0, 3.5, 4.143, 4.5, 5.0, 6.0, 8.0]
LONG_STEP_M = 50
QUANTILES = [0, .01, .05, .5, .95, .99, 1]


def run_date():
    return f"{datetime.date.today():%Y%m%d}"


def seconds(text):
    return float(text.rstrip("s"))


def utc(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def step_s(step):
    return seconds(step.get("staticDuration", "0s"))


def vehicle(step):
    return step["transitDetails"]["transitLine"]["vehicle"]["type"]


def training_records():
    split_df = pd.read_csv(SPLIT_PATH)
    train_draws = set(split_df.loc[split_df["half"] == TRAIN_HALF, "draw_no"])
    n_skipped = 0
    for set_name, path in RAW_PATHS.items():
        for line in open(path, encoding="utf-8"):
            rec = json.loads(line)
            if set_name == FIRST_BATCH and rec["draw_no"] not in train_draws:
                n_skipped += 1
                continue
            yield set_name, rec
    print(f"first-batch test / smoke-test records skipped: {n_skipped}")


def read_routes():
    transfer_rows, route_rows, fixed_rows, walk_step_rows = [], [], [], []
    for set_name, rec in training_records():
        for route_ix, route in enumerate(rec.get("resp", {}).get("routes", [])):
            steps = [s for leg in route["legs"] for s in leg.get("steps", [])]
            rides = [i for i, s in enumerate(steps) if s["travelMode"] == MODE_TRANSIT]
            if not rides:
                continue
            is_default = DEFAULT_LABEL in route.get("routeLabels", [])
            base = {"set_name": set_name, "draw_no": rec["draw_no"], "route_ix": route_ix, "is_default": is_default}
            slack_sum_s = 0.0
            for a, b in zip(rides, rides[1:]):
                between = steps[a + 1:b]
                walk_s = sum(step_s(s) for s in between)
                fixed_s = sum(step_s(s) for s in between if "distanceMeters" not in s)
                arrive = steps[a]["transitDetails"]["stopDetails"]
                depart = steps[b]["transitDetails"]["stopDetails"]
                gap_s = (utc(depart["departureTime"]) - utc(arrive["arrivalTime"])).total_seconds()
                slack_sum_s += gap_s - walk_s
                transfer_rows.append({**base, "from_type": vehicle(steps[a]), "to_type": vehicle(steps[b]),
                                      "is_same_stop_name": arrive["arrivalStop"]["name"] == depart["departureStop"]["name"],
                                      "gap_s": gap_s, "walk_s": walk_s, "fixed_s": fixed_s,
                                      "walk_m": sum(s.get("distanceMeters", 0) for s in between)})
                walk_step_rows += [(s["distanceMeters"], step_s(s)) for s in between if "distanceMeters" in s]
            route_rows.append({**base, "n_rides": len(rides), "first_type": vehicle(steps[rides[0]]),
                               "access_s": sum(step_s(s) for s in steps[:rides[0]]),
                               "first_wait_s": seconds(route["duration"]) - sum(step_s(s) for s in steps) - slack_sum_s})
            positions = [("access_tail", rides[0] - 1, vehicle(steps[rides[0]])),
                         ("egress_head", rides[-1] + 1, vehicle(steps[rides[-1]]))]
            for a, b in zip(rides, rides[1:]):
                positions += [("transfer_head", a + 1, vehicle(steps[a])), ("transfer_tail", b - 1, vehicle(steps[b]))]
            for position, i, vehicle_type in positions:
                is_fixed = 0 <= i < len(steps) and steps[i]["travelMode"] == MODE_WALK and "distanceMeters" not in steps[i]
                fixed_rows.append({"position": position, "vehicle_type": vehicle_type, "is_fixed": is_fixed,
                                   "fixed_s": step_s(steps[i]) if is_fixed else np.nan})
    transfers_df = pd.DataFrame(transfer_rows)
    transfers_df["slack_s"] = transfers_df["gap_s"] - transfers_df["walk_s"]
    return (transfers_df, pd.DataFrame(route_rows), pd.DataFrame(fixed_rows),
            pd.DataFrame(walk_step_rows, columns=["distance_m", "duration_s"]))


def feed_seconds_share():
    shares = {}
    for name in FEED_NAMES:
        with zipfile.ZipFile(GTFS_DIR / name / GTFS_ZIP_NAME) as archive:
            stop_times_df = pd.read_csv(io.BytesIO(archive.read("stop_times.txt")),
                                        usecols=["arrival_time", "departure_time"], dtype=str)
            transfers_df = pd.read_csv(io.BytesIO(archive.read("transfers.txt")), dtype=str)
        times = pd.concat([stop_times_df["arrival_time"], stop_times_df["departure_time"]]).dropna()
        shares[name] = {"stop_times_on_00": round(float((times.str[-2:] == "00").mean()), 4),
                        "transfers_rows": len(transfers_df),
                        "min_transfer_time_set": int(transfers_df["min_transfer_time"].replace("", np.nan).notna().sum()),
                        "transfer_types": transfers_df["transfer_type"].value_counts().to_dict()}
    return shares


def edge_table(df, xs, x_of):
    rows = []
    for x in xs:
        resid = df["y_s"] - x_of(df, x)
        c = resid.quantile(C_QUANTILE)
        rows.append({"x": x, "c_s": round(c, 1),
                     "edge_share": round(float(((resid >= c) & (resid < c + EDGE_WINDOW_S)).mean()), 4),
                     "n_below": int((resid < c - 1).sum())})
    return pd.DataFrame(rows)


def main():
    transfers_df, routes_df, fixed_df, steps_df = read_routes()
    lines = [f"{NAME} {run_date()}"]

    # (C1)
    slack = transfers_df["slack_s"]
    lines.append(f"(C1) transfers {len(transfers_df)} (default routes {int(transfers_df.is_default.sum())}), pairs "
                 f"{transfers_df[['set_name', 'draw_no']].drop_duplicates().shape[0]}; slack < 0: {int((slack < 0).sum())}")
    lines.append(pd.cut(slack, SLACK_BINS_S).value_counts().sort_index().to_string())
    pos_df = transfers_df[slack > 0].copy()
    lines.append(f"slack > 0 quantiles: {pos_df.slack_s.quantile(QUANTILES).round(1).to_dict()}")
    by_m = pos_df.groupby(pd.cut(pos_df.walk_m, WALK_M_BINS), observed=True)
    lines.append("floor by walk_m bin:\n" + pd.DataFrame(
        {"n": by_m.size(), "walk_s_median": by_m.walk_s.median(), "slack_min": by_m.slack_s.min(),
         "slack_p05": by_m.slack_s.quantile(.05)}).round(1).to_string())
    by_s = pos_df.groupby(pd.cut(pos_df.walk_s, np.arange(0, WALK_S_BIN_MAX_S, WALK_S_BIN_WIDTH_S)), observed=True)
    floor_df = pd.DataFrame({"n": by_s.size(), "walk_s": by_s.walk_s.median(), "floor_s": by_s.slack_s.min()})
    floor_df = floor_df[floor_df.n >= MIN_BIN_N]
    slope, intercept = np.polyfit(floor_df.walk_s, floor_df.floor_s, 1)
    lines.append(f"floor by walk_s bin (n >= {MIN_BIN_N}):\n{floor_df.to_string()}\n"
                 f"floor ~ {slope:.3f} * walk_s + {intercept:.0f} s")
    pos_df["pair"] = pos_df.from_type + ">" + pos_df.to_type
    lines.append("slack by mode pair:\n" + pos_df.groupby("pair").slack_s.describe(percentiles=[.01, .05, .5]).round(0).to_string())
    lines.append("slack by same stop name:\n" + pos_df.groupby("is_same_stop_name").slack_s.describe(
        percentiles=[.01, .05, .5]).round(0).to_string())
    lines.append(f"feeds: {feed_seconds_share()}")

    # (C2)
    pos_df["y_s"] = pos_df.gap_s - pos_df.fixed_s
    pos_df["dist_s"] = pos_df.walk_s - pos_df.fixed_s
    is_rail = (pos_df.from_type == RAIL_TYPE) | (pos_df.to_type == RAIL_TYPE)
    for label, sub_df in [("all", pos_df), ("no rail", pos_df[~is_rail]), ("rail", pos_df[is_rail])]:
        lines.append(f"(C2) {label} (n {len(sub_df)}): y >= k * listed distance-step seconds + c\n"
                     + edge_table(sub_df, K_GRID, lambda d, k: k * d.dist_s).to_string(index=False))
        lines.append(f"(C2) {label}: y >= walk_m / v + c (x = v km/h)\n"
                     + edge_table(sub_df, SPEED_GRID_KMH, lambda d, v: d.walk_m / (v / MPS_TO_KMH)).to_string(index=False))

    # (C3)
    wait = routes_df.first_wait_s
    lines.append(f"(C3) transit routes {len(routes_df)} (default {int(routes_df.is_default.sum())})\n"
                 + pd.cut(wait, FIRST_WAIT_BINS_S).value_counts().sort_index().to_string())
    lines.append(f"first_wait quantiles: {wait.quantile(QUANTILES).round(1).to_dict()}; by first vehicle (median): "
                 f"{routes_df.groupby('first_type').first_wait_s.median().to_dict()}")
    near_df = routes_df[wait.between(*FIRST_WAIT_NEAR_RANGE_S)].copy()
    near_df["leave_second"] = (-near_df.access_s) % SECONDS_PER_MIN
    lines.append("first_wait by access walk:\n" + near_df.groupby(pd.cut(near_df.access_s, ACCESS_BINS_S), observed=True)
                 .first_wait_s.describe(percentiles=[.5, .9]).round(1).to_string())
    lines.append(f"corr(first_wait, leave second within the minute): "
                 f"{np.corrcoef(near_df.first_wait_s, near_df.leave_second)[0, 1]:.3f}")

    # (C4)
    lines.append("(C4) fixed (no-distance) walk steps beside rides:\n" + fixed_df.groupby(["position", "vehicle_type"]).agg(
        n=("is_fixed", "size"), share_fixed=("is_fixed", "mean"), median_fixed_s=("fixed_s", "median"),
        top_values=("fixed_s", lambda x: x.dropna().value_counts().head(4).to_dict())).round(3).to_string())

    # (C5)
    step_slope, step_intercept = np.polyfit(steps_df.distance_m, steps_df.duration_s, 1)
    long_df = steps_df[steps_df.distance_m >= LONG_STEP_M]
    lines.append(f"(C5) listed transfer walk steps with a distance: n {len(steps_df)}; OLS duration = {step_slope:.4f} s/m "
                 f"* distance + {step_intercept:.1f} s ({MPS_TO_KMH / step_slope:.3f} km/h); median ratio >= {LONG_STEP_M} m "
                 f"{MPS_TO_KMH * (long_df.distance_m / long_df.duration_s).median():.3f} km/h (n {len(long_df)})")

    text = "\n".join(lines)
    print(text)
    prefix = DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}"
    (prefix.parent / f"{prefix.name}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    transfers_df.to_csv(prefix.parent / f"{prefix.name}_transfers.csv", index=False)
    routes_df.to_csv(prefix.parent / f"{prefix.name}_first_wait.csv", index=False)


if __name__ == "__main__":
    main()
