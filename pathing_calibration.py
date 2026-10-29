"""Calibrate pathing agent stage: the selected drive model (config.DRIVE_MODEL_NAME, DCL-4) fitted on the
blind routing bundle, once on the training half (it reproduces the selection round's test-half fit,
DCL-9) and once on all pairs (the production fit, DCL-13). Writes per subject, in config.DRIVE_MODEL_DIR:
<model>_<pairs>_params.json and <model>_<pairs>_history.csv. The selection round itself is parked
(docs/parked_code/drive_model_selection.md)."""
import json
from concurrent.futures import ProcessPoolExecutor

import pandas as pd

import config
from functions.drive_model_fit import build_fit_edge_attrs, fit_drive_model
from functions.output_helper import is_already_built
from functions.routing_bundle import prep_graph
from functions.subject_paths import subject_dir, subject_layers_file, timed_graph_path

DRAW_NO_COL = "draw_no"
HALF_COL = "half"
TRAIN_HALF, TEST_HALF = "train", "test"
TRAINING_HALF_PAIRS = "training_half"
ALL_PAIRS = "all_pairs"
PARAMS_FILE = "{}_{}_params.json"         # model, pairs
HISTORY_FILE = "{}_{}_history.csv"


def training_drive_pairs(subject_lat, subject_lon):
    """The joined pairs of the training half; the test half is never returned."""
    split_df = pd.read_csv(subject_layers_file(config.DRIVE_SPLIT_PATH, subject_lat, subject_lon))
    pairs_df = pd.read_csv(subject_layers_file(config.ROUTES_DRIVE_ENRICHED_PATH, subject_lat, subject_lon))
    train_df = split_df.loc[split_df[HALF_COL] == TRAIN_HALF, [DRAW_NO_COL]]
    pairs_df = pairs_df.merge(train_df, on=DRAW_NO_COL, how="inner", validate="one_to_one")
    test_ids = set(split_df.loc[split_df[HALF_COL] == TEST_HALF, DRAW_NO_COL])
    assert not set(pairs_df[DRAW_NO_COL]) & test_ids, "a test pair reached the fit"
    assert len(pairs_df) == len(train_df), "training pairs missing from the join"
    return pairs_df.sort_values(DRAW_NO_COL).reset_index(drop=True)


def all_drive_pairs(subject_lat, subject_lon):
    """Every joined pair, both halves (DCL-13); checked against the split file."""
    split_df = pd.read_csv(subject_layers_file(config.DRIVE_SPLIT_PATH, subject_lat, subject_lon))
    pairs_df = pd.read_csv(subject_layers_file(config.ROUTES_DRIVE_ENRICHED_PATH, subject_lat, subject_lon))
    assert set(pairs_df[DRAW_NO_COL]) == set(split_df[DRAW_NO_COL]), "joined pairs differ from the split"
    return pairs_df.sort_values(DRAW_NO_COL).reset_index(drop=True)


def calibrate_pathing_agent(subject_lat, subject_lon, should_refit=False):
    """Fit config.DRIVE_MODEL_NAME on the training half, then on all pairs. Builds the base variant's
    routing bundle and edge attributes first if missing. Each fit is skipped if its files exist."""
    graph_path = timed_graph_path(config.DRIVE_FIT_BASE_VARIANT, subject_lat, subject_lon)
    od_path = subject_layers_file(config.ROUTES_DRIVE_ENRICHED_PATH, subject_lat, subject_lon)
    # the bundle is built in a fresh process, so the graph's memory is returned before the fits
    with ProcessPoolExecutor(max_workers=1, max_tasks_per_child=1) as executor:
        bundle_path = executor.submit(prep_graph, graph_path, config.DRIVE_RUN_BETAS[config.DRIVE_FIT_BASE_VARIANT],
                                      od_path).result()
    attrs_path = subject_layers_file(config.DRIVE_FIT_EDGE_ATTRS_PATH, subject_lat, subject_lon)
    if not is_already_built([attrs_path], should_rebuild=False):
        build_fit_edge_attrs(graph_path, bundle_path, attrs_path)

    out_dir = subject_dir(config.DRIVE_MODEL_DIR, subject_lat, subject_lon)
    out_dir.mkdir(parents=True, exist_ok=True)
    model, groups = config.DRIVE_MODEL_NAME, config.DRIVE_MODEL_GROUPS
    for pairs_name, load_pairs in ((TRAINING_HALF_PAIRS, training_drive_pairs), (ALL_PAIRS, all_drive_pairs)):
        params_path = out_dir / PARAMS_FILE.format(model, pairs_name)
        history_path = out_dir / HISTORY_FILE.format(model, pairs_name)
        if is_already_built([params_path, history_path], should_refit):
            continue
        pairs_df = load_pairs(subject_lat, subject_lon)
        print(f"drive model fit: {model} on {pairs_name}, {len(pairs_df):,} pairs, edge set "
              f"{config.DRIVE_FIT_EDGE_SET} -> {out_dir}")
        params, history_df = fit_drive_model(pairs_df, bundle_path, attrs_path, groups, config.DRIVE_FIT_EDGE_SET,
                                             label=f"{model} {pairs_name}")
        history_df.to_csv(history_path, index=False)
        params_path.write_text(json.dumps(dict(model=model, pairs=pairs_name, n_pairs=len(pairs_df), groups=groups,
                                               edge_set=config.DRIVE_FIT_EDGE_SET, **params), indent=1))
        print(f"saved {params_path}")
