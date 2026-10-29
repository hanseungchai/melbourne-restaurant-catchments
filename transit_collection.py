"""Transit collection runs: the one-off pair sets fetched after the main draw, each in its own files, run from
the command line by set and step. main.py keeps the stages: the draw, the split and the first fetch.

Sets: reserve (second batch, TRN-10), topup (boundary top-up, TRN-14), test_ext (test-half extension, TRN-15),
holdout (fresh holdout, sealed until the freeze record). Steps, where a set has them:
    screen  route the stream on past the last checkpoint, checkpoint only (hours; r5py workers)
    draw    the set's pairs from the checkpoints, no routing; skipped if they exist
    check   free dry run of the fetch: every body checked, the ledger guard asked, nothing sent
    pilot   PAID: the top-up pilot (TRN-14 (2))
    fetch   PAID: Routes Essentials, one call per pair (S5: only on the user's go)
    report  free: the top-up's yield per call, zone counts, projected calls

Usage: python transit_collection.py <set> <step> [--paid]
Paid steps refuse to start without --paid; the API ledger's guard applies on top.
"""
import argparse
from functools import partial

import transit_fetch
import transit_samples
from functions.input_helper import read_subject_location, subject_coord_path

PAID_FLAG = "--paid"

# set -> step -> (function, is_paid); each function takes (subject_lat, subject_lon).
COLLECTION_STEPS = {
    "reserve": {
        "screen": (transit_samples.extend_transit_checkpoint, False),   # into the draw's own checkpoint
        "draw": (partial(transit_samples.draw_transit_set, "reserve"), False),
        "check": (partial(transit_fetch.check_set_fetch, "reserve"), False),
        "fetch": (partial(transit_fetch.fetch_set, "reserve"), True),
    },
    "topup": {
        "draw": (transit_samples.draw_transit_topup, False),
        "check": (transit_fetch.check_transit_topup_fetch, False),
        "pilot": (transit_fetch.fetch_transit_topup_pilot, True),
        "fetch": (transit_fetch.fetch_transit_topup, True),
        "report": (transit_fetch.report_topup, False),
    },
    **{set_name: {
        "screen": (partial(transit_samples.screen_transit_stream, set_name), False),
        "draw": (partial(transit_samples.draw_transit_set, set_name), False),
        "check": (partial(transit_fetch.check_set_fetch, set_name), False),
        "fetch": (partial(transit_fetch.fetch_set, set_name), True),
    } for set_name in ("test_ext", "holdout")},
}


def run_collection_step(set_name, step, is_paid_allowed=False, subject_name=None):
    """Run one step of one collection set for the subject (None = default subject).
    Refuses a paid step unless is_paid_allowed."""
    steps = COLLECTION_STEPS[set_name]
    if step not in steps:
        raise ValueError(f"set {set_name!r} has no step {step!r}; its steps: {', '.join(steps)}")
    step_function, is_paid = steps[step]
    if is_paid and not is_paid_allowed:
        raise RuntimeError(f"{set_name} {step} spends API calls: rerun with {PAID_FLAG} (S5: only on the user's go)")
    subject_lat, subject_lon = read_subject_location(subject_coord_path(subject_name))
    return step_function(subject_lat, subject_lon)


def main():
    parser = argparse.ArgumentParser(description="Transit collection runs by set and step.")
    parser.add_argument("set_name", choices=COLLECTION_STEPS)
    parser.add_argument("step")
    parser.add_argument(PAID_FLAG, dest="is_paid_allowed", action="store_true",
                        help="allow a step that spends API calls")
    args = parser.parse_args()
    run_collection_step(args.set_name, args.step, args.is_paid_allowed)


if __name__ == "__main__":  # also guards the screen steps' worker processes (spawn on Windows)
    main()
