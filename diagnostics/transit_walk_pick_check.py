"""Free check for P5 / P6 (TRN-16, 63rd): would a two-run walk-weight pick, with or without an exact transfer penalty,
pick Google's default route about as often as the ideal weighted pick does?

Claim under test (DESIGN.md Q24 63rd; concepts/transit.md TRN-16 63rd): Google's default behaves as the least-cost
route under C(r) = A(r) + (w - 1) * T(r) + tau * transfers(r) (transit_walk_weight.py: w 1.70 picks 0.853; w 1.95 with
tau 450 s picks 0.942). R5 cannot minimise C directly (walk is no RAPTOR criterion). The plan: P5 (Java) picks per stop
the RAPTOR round minimising real time + tau x transfers; P6 (Python) runs TTM twice, default and walk slowed by w (both
with P5), and keeps the default only if C(default) < C(slowed), with the slowed path re-timed at real speed. Where the
pipeline would rely on it: whether P5 and P6 are built (TRN-16), and at which (w, tau).

Simulation on Google's own candidate routes (no JVM), per training pair with 2+ routes (as transit_walk_weight.py):
  A = arrival_from_request_s; T = walk_m at WALK_SPEED_KMH (as transit_walk_weight.py); transfers = boardings - 1.
  Default run: among all candidates, the least A + tau x transfers (earliest arrival with P5).
  Slowed run: walking w times slower. A candidate stays catchable if, before each boarding k, the extra walk time
  (w - 1) x walk_k (walk_k = that walk's metres at WALK_SPEED_KMH) fits in Google's own wait there (slack_k = departure
  of ride k minus the end of the previous ride, or the request time, minus Google's listed walk durations between).
  Walk-only routes always catchable. An uncatchable candidate drops out of the slowed run (R5 would board something
  later, which Google's list does not show: an approximation). Slowed arrival = A + (w - 1) x egress walk; the slowed
  run picks the least slowed arrival + tau x transfers.
  P6 pick: the default pick d, unless the slowed pick s has C(s) <= C(d) (time saved by d must exceed (w - 1) x extra
  walk, plus the penalty difference). Ties inside a run or between d and s share the hit: 1 / n_tied when Google's
  default is among the picked, else 0 (as transit_walk_weight.py's hit).
  Ideal = least C over all candidates (transit_walk_weight.py's share), reproduced here first.
  Strict variant (report only): at transfers, slack_k minus TRANSFER_BUFFER_S (P3's 200 s, which R5 also needs).

Rule (Claude's, written before any result):
  Check first, else stop: (F1) ideal shares reproduce transit_walk_weight.py: w 1 0.720, w 1.70 0.853, (w 1.95,
      tau 450) 0.942, each within REPRO_TOLERANCE.
  (a, reported) share of pairs whose Google default stays catchable in the slowed run, at w 1.70 and 1.95: all, and by
      where it breaks (access, a transfer); strict variant beside.
  (G1) P6 worth building: P6's share at (1.70, 0) >= the w = 1 share + MIN_GAIN and >= its ideal - MAX_LOSS.
  (G2) P5 worth building too: P6 with P5 at (1.95, 450) >= P6 at (1.70, 0) + MIN_TAU_GAIN.
  Outcome: G1 and G2 -> build P5, then P6, at (1.95, 450). G1 only -> build P6 alone at w 1.70, no P5. G1 fails ->
  freeze, the weight a finding (TRN-16).
  Report only: P6 share on a grid of (w, tau) around both settings; P6 with every candidate catchable (the loss from
  the two-run restriction alone vs from catchability).

Predictions (Claude's, before any result): default catchable at 1.70 on ~85%, at 1.95 ~80% (access breaks most,
waits at home are free so the slack sits at the first stop); P6 at (1.70, 0) ~0.82-0.84 (G1 passes); with P5 at
(1.95, 450) ~0.90 (G2 passes).

Conclusion (run 2026-10-21; rule above OK'd by the user before any result; 3,340 pairs: train 1,209, second 1,939,
top-up 192): F1 PASS (0.7201, 0.8531, 0.9418). (a) Google's default stays catchable at w 1.70 on 0.555 (breaks at
access 0.442, at a transfer 0.005; strict 0.509), at 1.95 on 0.455 (access 0.538; strict 0.411). (G1) P6 at w 1.70
0.7999: beats w = 1 (0.7201) by 0.080, but 0.053 below its ideal 0.8531 -> FAIL. (G2) P6 + P5 at (1.95, 450) 0.8133
vs 0.8199 needed (ideal 0.9418) -> FAIL. OUTCOME: freeze, the weight a finding.
  Report only: P6 with every candidate catchable 0.7936 (1.70) / 0.8100 (1.95, 450), no better than plain: the loss is
  the two-run restriction itself, not catchability. Grid best P6 0.8169 at (1.70, 300 s) (ideal there 0.9145).
  Post-hoc (after the rule, descriptive): P5 alone (w = 1) lowers the share: tau 150 0.711, 450 0.703, 900 0.684.
  Prediction check: catchable shares far lower than predicted (0.555 vs ~0.85), access breaking as predicted; P6 0.80
  (0.82-0.84 predicted); P5 + P6 0.81 (~0.90 predicted).
  Reading (Claude's): slowing the walk in a timed search does not price the walk. Where a route keeps its vehicles,
  the slower access and transfer walks only use up the wait, so the slowed run's arrival charges the egress walk
  alone; where a route loses its vehicle, it drops out instead of being charged. Neither run sees access walking as a
  cost, which is where Google's preference sits. A walk weight needs a cost criterion inside the search (McRaptor-style),
  not a second run.

Inputs (read only): the split, Google route tables and raw records in outputs/transit_validation/ (test-half lines
of the first raw file skipped unread). Self-contained: imports nothing from functions/ or config.py (CLAUDE.md D1). No
paid API calls, no r5py. Results carry the run date; a same-day rerun replaces that day's results.
"""
import datetime
import json
from pathlib import Path

import numpy as np
import pandas as pd

# --- paths -----------------------------------------------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parent.parent
SUBJECT_DIR = PROJECT_ROOT / "outputs" / "transit_validation" / "-37.76870_144.97196"
FILE_TAG = "res2021_wrk2021_ven20260925_-37.76870_144.97196"
SPLIT_PATH = SUBJECT_DIR / f"transit_split_{FILE_TAG}.csv"
GOOGLE_ROUTES_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.routes.csv",   # holds the test half too
                       "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.routes.csv",
                       "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.routes.csv"}
GOOGLE_RAW_PATHS = {"train": SUBJECT_DIR / f"transit_google_{FILE_TAG}.raw.jsonl",
                    "second": SUBJECT_DIR / f"transit_google_20261016_{FILE_TAG}.raw.jsonl",
                    "topup": SUBJECT_DIR / f"transit_google_topup_{FILE_TAG}.raw.jsonl"}
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
NAME = "transit_walk_pick_check"

# --- values copied from config.py and the record ---------------------------------------------------
TRAIN_HALF = "train"
WALK_SPEED_KMH = 4.143                         # DESIGN Q24 (2), final (user, 59th)
S_PER_HOUR = 3600
M_PER_KM = 1000
TRANSFER_BUFFER_S = 200                        # P3's transfer board wait (strict variant only)
REFERENCE_SHARES = [(1.0, 0, 0.720), (1.70, 0, 0.853), (1.95, 450, 0.942)]   # transit_walk_weight.py, 62nd

# --- rule ------------------------------------------------------------------------------------------
P6_SETTING = (1.70, 0)                         # (w, tau_s)
P5_P6_SETTING = (1.95, 450)
REPRO_TOLERANCE = 0.001
MIN_GAIN = 0.05                                # G1: over earliest arrival (as transit_walk_weight.py R1)
MAX_LOSS = 0.03                                # G1: below the ideal at the same setting
MIN_TAU_GAIN = 0.02                            # G2
W_REPORT = [1.40, 1.55, 1.70, 1.85, 1.95, 2.10]
TAU_REPORT_S = [0, 150, 300, 450, 600]
TIE_TOLERANCE_S = 1e-6

# --- columns ---------------------------------------------------------------------------------------
DRAW_NO_COL = "draw_no"
ROUTE_IX_COL = "route_ix"
ARRIVAL_COL = "arrival_from_request_s"
WALK_M_COL = "walk_m"
BOARDINGS_COL = "n_transit_steps"
DEFAULT_COL = "is_default"
HALF_COL = "half"


def run_date():
    return datetime.date.today().strftime("%Y%m%d")


def seconds_of(duration):
    return int(duration.rstrip("s"))


def utc_of(text):
    return datetime.datetime.fromisoformat(text.replace("Z", "+00:00"))


def route_legs(route, requested):
    """Per boarding: walk metres before it and Google's slack (wait) there; egress walk metres."""
    steps = route["legs"][0]["steps"]
    boardings, walk_m, walk_s, prev_end_s = [], 0, 0, 0.0
    for step in steps:
        if step["travelMode"] == "TRANSIT":
            stop_details = step["transitDetails"]["stopDetails"]
            departure_s = (utc_of(stop_details["departureTime"]) - requested).total_seconds()
            boardings.append({"walk_m": walk_m, "slack_s": departure_s - prev_end_s - walk_s})
            prev_end_s = (utc_of(stop_details["arrivalTime"]) - requested).total_seconds()
            walk_m, walk_s = 0, 0
        else:
            walk_m += step.get("distanceMeters", 0)
            walk_s += seconds_of(step.get("staticDuration", "0s"))
    return boardings, walk_m


def load_pairs():
    """Per training pair with 2+ routes: arrays per candidate route (as transit_walk_weight.py) plus legs."""
    split_df = pd.read_csv(SPLIT_PATH)
    train_draws = set(split_df.loc[split_df[HALF_COL] == TRAIN_HALF, DRAW_NO_COL])
    speed_mps = WALK_SPEED_KMH * M_PER_KM / S_PER_HOUR
    pairs = []
    for set_name, routes_path in GOOGLE_ROUTES_PATHS.items():
        routes_df = pd.read_csv(routes_path)
        if set_name == "train":
            routes_df = routes_df[routes_df[DRAW_NO_COL].isin(train_draws)]
        n_routes = routes_df.groupby(DRAW_NO_COL)[DRAW_NO_COL].transform("size")
        routes_df = routes_df[n_routes >= 2]
        wanted = {draw_no: df.sort_values(ROUTE_IX_COL) for draw_no, df in routes_df.groupby(DRAW_NO_COL)}
        with open(GOOGLE_RAW_PATHS[set_name], encoding="utf-8") as file:
            for line in file:
                draw_no = int(line[line.index(":") + 1:line.index(",")])   # read the id before parsing: test lines skipped
                if draw_no not in wanted:
                    continue
                record = json.loads(line)
                pair_df = wanted.pop(draw_no)
                requested = utc_of(record["request"]["departureTime"])
                routes = record["resp"]["routes"]
                access_m, access_slack, transfer_m, transfer_slack, egress_m = [], [], [], [], []
                for route_ix in pair_df[ROUTE_IX_COL]:
                    boardings, egress = route_legs(routes[int(route_ix)], requested)
                    access_m.append(boardings[0]["walk_m"] if boardings else 0)
                    access_slack.append(boardings[0]["slack_s"] if boardings else np.inf)
                    transfer_m.append([b["walk_m"] for b in boardings[1:]])
                    transfer_slack.append([b["slack_s"] for b in boardings[1:]])
                    egress_m.append(egress if boardings else 0)
                n_boardings = pair_df[BOARDINGS_COL].to_numpy(int)
                walk_only = n_boardings == 0
                pairs.append({"set": set_name, "draw_no": draw_no,
                              "arrival": pair_df[ARRIVAL_COL].to_numpy(float),
                              "walk": pair_df[WALK_M_COL].to_numpy(float) / speed_mps,
                              "transfers": np.clip(n_boardings - 1, 0, None).astype(float),
                              "default": pair_df[DEFAULT_COL].to_numpy(bool),
                              "walk_only": walk_only,
                              "access_s": np.array(access_m, float) / speed_mps,
                              "access_slack_s": np.array(access_slack, float),
                              "transfer_s": [np.array(m, float) / speed_mps for m in transfer_m],
                              "transfer_slack_s": [np.array(s, float) for s in transfer_slack],
                              "egress_s": np.array(egress_m, float) / speed_mps})
        assert not wanted, f"{set_name}: {len(wanted)} pairs without a raw record"
    return pairs


def catchable(pair, w, is_strict=False):
    """Per candidate: (access ok, transfers ok) when walking w times slower."""
    extra = w - 1
    access_ok = pair["walk_only"] | (extra * pair["access_s"] <= pair["access_slack_s"] + TIE_TOLERANCE_S)
    buffer_s = TRANSFER_BUFFER_S if is_strict else 0
    transfer_ok = np.array([bool(np.all(extra * m <= s - buffer_s + TIE_TOLERANCE_S))
                            for m, s in zip(pair["transfer_s"], pair["transfer_slack_s"])])
    return access_ok, transfer_ok


def least(cost, mask):
    """Indices of the least-cost candidates among mask (empty if none)."""
    if not mask.any():
        return np.array([], int)
    masked = np.where(mask, cost, np.inf)
    return np.flatnonzero(masked <= masked.min() + TIE_TOLERANCE_S)


def share_of(picked, is_default):
    return 1.0 / len(picked) if len(picked) and is_default[picked].any() else 0.0


def full_cost(pair, w, tau_s):
    return pair["arrival"] + (w - 1) * pair["walk"] + tau_s * pair["transfers"]


def ideal_hit(pair, w, tau_s):
    return share_of(least(full_cost(pair, w, tau_s), np.ones(len(pair["arrival"]), bool)), pair["default"])


def p6_hit(pair, w, tau_s, is_strict=False, is_all_catchable=False):
    """P6 (with P5 at tau_s) on Google's candidates (docstring)."""
    everyone = np.ones(len(pair["arrival"]), bool)
    default_picks = least(pair["arrival"] + tau_s * pair["transfers"], everyone)
    if is_all_catchable:
        is_ok = everyone
    else:
        access_ok, transfer_ok = catchable(pair, w, is_strict)
        is_ok = access_ok & transfer_ok
    slowed_cost = pair["arrival"] + (w - 1) * pair["egress_s"] + tau_s * pair["transfers"]
    slowed_picks = least(slowed_cost, is_ok)
    cost = full_cost(pair, w, tau_s)
    candidates = np.union1d(default_picks, slowed_picks)
    picked = candidates[cost[candidates] <= cost[candidates].min() + TIE_TOLERANCE_S]
    return share_of(picked, pair["default"])


def main():
    pairs = load_pairs()
    lines = [f"{NAME} {run_date()}: {len(pairs)} training pairs with 2+ Google routes "
             f"({pd.Series([p['set'] for p in pairs]).value_counts().to_dict()})"]

    # (F1) reproduction of transit_walk_weight.py
    is_repro_ok = True
    for w, tau_s, reference in REFERENCE_SHARES:
        share = np.mean([ideal_hit(p, w, tau_s) for p in pairs])
        is_ok = abs(share - reference) <= REPRO_TOLERANCE
        is_repro_ok &= is_ok
        lines.append(f"(F1) ideal share w {w:.2f} tau {tau_s} s: {share:.4f} vs {reference:.3f} -> {'PASS' if is_ok else 'FAIL'}")
    if not is_repro_ok:
        print("\n".join(lines))
        raise SystemExit("F1 failed: stop")

    # (a) is Google's default catchable in the slowed run?
    for w in [P6_SETTING[0], P5_P6_SETTING[0]]:
        for is_strict in [False, True]:
            counts = {"all": 0, "access_breaks": 0, "transfer_breaks": 0}
            for p in pairs:
                d = np.flatnonzero(p["default"])[0]
                access_ok, transfer_ok = catchable(p, w, is_strict)
                counts["all"] += bool(access_ok[d] and transfer_ok[d])
                counts["access_breaks"] += not access_ok[d]
                counts["transfer_breaks"] += not transfer_ok[d]
            label = "strict" if is_strict else "plain"
            lines.append(f"(a) w {w:.2f} {label}: default catchable {counts['all'] / len(pairs):.3f}; breaks at access "
                         f"{counts['access_breaks'] / len(pairs):.3f}, at a transfer {counts['transfer_breaks'] / len(pairs):.3f}")

    # (G1), (G2)
    base_share = np.mean([ideal_hit(p, 1.0, 0) for p in pairs])
    p6_share = np.mean([p6_hit(p, *P6_SETTING) for p in pairs])
    p6_ideal = np.mean([ideal_hit(p, *P6_SETTING) for p in pairs])
    p56_share = np.mean([p6_hit(p, *P5_P6_SETTING) for p in pairs])
    p56_ideal = np.mean([ideal_hit(p, *P5_P6_SETTING) for p in pairs])
    is_g1 = p6_share >= base_share + MIN_GAIN and p6_share >= p6_ideal - MAX_LOSS
    is_g2 = p56_share >= p6_share + MIN_TAU_GAIN
    lines.append(f"(G1) P6 at w {P6_SETTING[0]:.2f}: {p6_share:.4f} (w = 1 {base_share:.4f}, need >= "
                 f"{base_share + MIN_GAIN:.4f}; ideal {p6_ideal:.4f}, need >= {p6_ideal - MAX_LOSS:.4f}) -> {'PASS' if is_g1 else 'FAIL'}")
    lines.append(f"(G2) P6 + P5 at w {P5_P6_SETTING[0]:.2f} tau {P5_P6_SETTING[1]} s: {p56_share:.4f} (ideal {p56_ideal:.4f}; "
                 f"need >= {p6_share + MIN_TAU_GAIN:.4f}) -> {'PASS' if is_g2 else 'FAIL'}")
    outcome = ("build P5, then P6, at (1.95, 450)" if is_g1 and is_g2 else
               "build P6 alone at w 1.70, no P5" if is_g1 else "freeze, the weight a finding")
    lines.append(f"OUTCOME: {outcome}")

    # report only
    for setting in [P6_SETTING, P5_P6_SETTING]:
        strict = np.mean([p6_hit(p, *setting, is_strict=True) for p in pairs])
        relaxed = np.mean([p6_hit(p, *setting, is_all_catchable=True) for p in pairs])
        lines.append(f"report: w {setting[0]:.2f} tau {setting[1]} s: P6 strict {strict:.4f}; P6 all catchable {relaxed:.4f}")
    grid_rows = []
    for w in W_REPORT:
        for tau_s in TAU_REPORT_S:
            grid_rows.append({"w": w, "tau_s": tau_s,
                              "p6": np.mean([p6_hit(p, w, tau_s) for p in pairs]),
                              "ideal": np.mean([ideal_hit(p, w, tau_s) for p in pairs])})
    grid_df = pd.DataFrame(grid_rows)
    best = grid_df.loc[grid_df.p6.idxmax()]
    lines.append(f"report: grid best P6 {best.p6:.4f} at w {best.w:.2f} tau {best.tau_s:.0f} s (ideal there {best.ideal:.4f})")
    lines.append("report: P6 share by (w rows, tau columns):\n" + grid_df.pivot(index="w", columns="tau_s", values="p6").round(3).to_string())

    text = "\n".join(lines)
    print(text)
    (DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_summary.txt").write_text(text + "\n", encoding="utf-8", newline="\n")
    grid_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date()}_grid.csv", index=False)


if __name__ == "__main__":
    main()
