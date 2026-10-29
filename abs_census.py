"""Census stage: Victoria residents by SA1 and workers by Destination Zone (DZN), each joined to
its boundaries and saved as one GeoPackage per layer and census year in config.CENSUS_DIR.

build_census_2021 builds both layers from the frozen 2021 inputs (the default). build_census_update
builds one layer ("abs" residents or "dzn" workers) from a newer year folder in
config.CENSUS_INPUTS_DIR; the two are released and updated separately. The later stages read
residents for config.CENSUS_RESIDENTS_YEAR and workers for config.CENSUS_WORKERS_YEAR: the same
year by default, mixed years allowed with a warning (DESIGN_pre_spine "Data layers").
"""
import re

import geopandas as gpd
import pandas as pd

import config

# The two updatable layers, as named in config.CENSUS_INPUTS_DIR.
LAYER_ABS = "abs"                    # SA1 residents: SA1 boundaries + DataPack G01
LAYER_DZN = "dzn"                    # DZN workers: DZN boundaries + TableBuilder export

# ASGS boundary columns carry a two-digit year (STE_NAME21); census table columns a four-digit one.
ASGS_STATE_COL = "STE_NAME{yy}"
ASGS_SA1_CODE_COL = "SA1_CODE{yy}"
ASGS_DZN_CODE_COL = "DZN_CODE{yy}"
SA1_CODE_COL = "SA1_CODE_{year}"     # also the key column of the G01 table
DZN_CODE_COL = "DZN_CODE_{year}"
RESIDENTS_COL = "Tot_P_P"            # G01: total persons, by place of usual residence
WORKERS_COL = "Tot_W_P"              # TableBuilder: persons 15+, by place of work

TABLEBUILDER_HEADER_ROWS = 8         # title rows above the TableBuilder Pro data
TABLEBUILDER_CODE_COL_POS = 0        # zone codes are in the first column
DZN_CODE_PATTERN = r"\d{9}"          # a real zone code; other rows are supplementary zones, the
                                     # total and the footer

MERGE_INDICATOR_COL = "_merge"
MERGE_MATCHED = "both"
YEAR_PATTERN = r"(\d{4})"            # the year in an input folder name
GPKG_DRIVER = "GPKG"


def build_census_2021():
    """Default: build both layers from the frozen 2021 inputs."""
    year = config.CENSUS_FROZEN_YEAR
    sa1_residents_gdf = build_sa1_residents(year, config.SA1_BOUNDARIES_PATH,
                                            config.CENSUS_G01_SA1_PATH)
    dzn_workers_gdf = build_dzn_workers(year, config.DZN_BOUNDARIES_PATH,
                                        config.DZN_WORKERS_XLSX_PATH)
    return sa1_residents_gdf, dzn_workers_gdf


def build_census_update(layer, year=None, inputs_dir=config.CENSUS_INPUTS_DIR):
    """Build one layer from inputs_dir/<layer>_<year>/.

    layer: LAYER_ABS ("abs", SA1 residents) or LAYER_DZN ("dzn", DZN workers).
    year: the census year to build; None picks the newest year folder with both input files.
    Year folders with a file missing are reported and never built.
    """
    dir_name, input_names, build_layer = _update_layer_spec(layer)
    complete_years, missing_by_year = _scan_input_years(inputs_dir, dir_name, input_names)
    for incomplete_year, missing_names in sorted(missing_by_year.items()):
        print(f"{layer} {incomplete_year}: incomplete, missing {missing_names}")

    if year is None:
        if not complete_years:
            print(f"{layer}: no complete year folder in {inputs_dir}; nothing built")
            return None
        year = max(complete_years)
    elif year not in complete_years:
        missing_names = missing_by_year.get(year, "the whole year folder")
        raise FileNotFoundError(f"{layer} {year} is not complete in {inputs_dir}; "
                                f"missing {missing_names}")

    print(f"building {layer} {year} from {inputs_dir / dir_name.format(year=year)}")
    return build_layer(year, *complete_years[year])


def build_sa1_residents(year, boundaries_path, g01_path):
    """SA1 polygons with resident counts, saved as config.SA1_RESIDENTS_NAME for this year."""
    sa1_residents_gdf = _build_sa1_residents(year, boundaries_path, g01_path)
    _save_layer(sa1_residents_gdf, config.SA1_RESIDENTS_NAME.format(year=year))
    return sa1_residents_gdf


def build_dzn_workers(year, boundaries_path, workers_xlsx_path):
    """DZN polygons with worker counts, saved as config.DZN_WORKERS_NAME for this year."""
    dzn_workers_gdf = _build_dzn_workers(year, boundaries_path, workers_xlsx_path)
    _save_layer(dzn_workers_gdf, config.DZN_WORKERS_NAME.format(year=year))
    return dzn_workers_gdf


def _update_layer_spec(layer):
    """layer -> (year folder name template, input file name templates, build function)."""
    if layer == LAYER_ABS:
        return config.CENSUS_ABS_DIR_NAME, config.CENSUS_ABS_INPUT_NAMES, build_sa1_residents
    if layer == LAYER_DZN:
        return config.CENSUS_DZN_DIR_NAME, config.CENSUS_DZN_INPUT_NAMES, build_dzn_workers
    raise ValueError(f"layer must be {LAYER_ABS!r} or {LAYER_DZN!r}, got {layer!r}")


def _save_layer(layer_gdf, file_name):
    config.CENSUS_DIR.mkdir(parents=True, exist_ok=True)
    layer_gdf.to_file(config.CENSUS_DIR / file_name, driver=GPKG_DRIVER)


def _build_sa1_residents(year, boundaries_path, g01_path):
    yy = _two_digit_year(year)
    code_col = SA1_CODE_COL.format(year=year)
    sa1_gdf = _read_state_boundaries(boundaries_path, ASGS_SA1_CODE_COL.format(yy=yy), code_col, yy)
    residents_df = pd.read_csv(g01_path, usecols=[code_col, RESIDENTS_COL], dtype={code_col: str})
    return _join_counts(sa1_gdf, residents_df, code_col, RESIDENTS_COL, "SA1s", "persons")


def _build_dzn_workers(year, boundaries_path, workers_xlsx_path):
    """DZNs are a place-of-work geography and aggregate to SA2, not SA1, so workers get their own
    boundaries rather than being joined to the SA1 layer."""
    yy = _two_digit_year(year)
    code_col = DZN_CODE_COL.format(year=year)
    dzn_gdf = _read_state_boundaries(boundaries_path, ASGS_DZN_CODE_COL.format(yy=yy), code_col, yy)
    workers_df = _read_tablebuilder_workers(workers_xlsx_path, code_col)
    return _join_counts(dzn_gdf, workers_df, code_col, WORKERS_COL, "zones", "workers")


def _read_state_boundaries(boundaries_path, asgs_code_col, code_col, yy):
    """National ASGS boundaries -> config.STATE_NAME only, with the code column renamed to code_col."""
    boundaries_gdf = gpd.read_file(boundaries_path)
    boundaries_gdf = boundaries_gdf[boundaries_gdf[ASGS_STATE_COL.format(yy=yy)] == config.STATE_NAME]
    boundaries_gdf = boundaries_gdf.loc[:, [asgs_code_col, boundaries_gdf.geometry.name]]
    boundaries_gdf = boundaries_gdf.rename(columns={asgs_code_col: code_col})
    boundaries_gdf[code_col] = boundaries_gdf[code_col].astype(str)
    return boundaries_gdf


def _read_tablebuilder_workers(workers_xlsx_path, code_col):
    """Workers per zone from the TableBuilder Pro export. Non-zone rows are found by the code
    pattern, not by a fixed footer length, and every dropped row is printed."""
    rows_df = pd.read_excel(workers_xlsx_path, skiprows=TABLEBUILDER_HEADER_ROWS,
                            dtype={TABLEBUILDER_CODE_COL_POS: str})
    rows_df.columns = [code_col, WORKERS_COL]
    rows_df[code_col] = rows_df[code_col].str.strip()

    is_zone = rows_df[code_col].str.fullmatch(DZN_CODE_PATTERN).fillna(False)
    print(f"dropping {(~is_zone).sum()} non-zone rows:")
    print(rows_df.loc[~is_zone].to_string())
    workers_df = rows_df[is_zone].copy()

    workers_df[WORKERS_COL] = pd.to_numeric(workers_df[WORKERS_COL], errors="coerce")
    print(f"non-numeric worker counts coerced: {workers_df[WORKERS_COL].isna().sum()}")
    return workers_df


def _join_counts(boundaries_gdf, counts_df, code_col, count_col, zone_label, count_label):
    """Outer join so misses on either side are counted, then keep matched zones with geometry."""
    merged_gdf = pd.merge(boundaries_gdf, counts_df, on=code_col, how="outer", indicator=True)
    print(merged_gdf[MERGE_INDICATOR_COL].value_counts())
    is_null_geometry = merged_gdf.geometry.isna()
    print(f"null geometry: {is_null_geometry.sum()}, "
          f"{count_label} in them: {merged_gdf.loc[is_null_geometry, count_col].sum():,.0f}")
    merged_gdf = (merged_gdf[merged_gdf[MERGE_INDICATOR_COL] == MERGE_MATCHED]
                  .drop(columns=MERGE_INDICATOR_COL).dropna())
    print(f"{len(merged_gdf)} {zone_label}, {int(merged_gdf[count_col].sum()):,} {count_label}")
    return merged_gdf


def _scan_input_years(inputs_dir, dir_name, input_names):
    """Year folders named dir_name in inputs_dir -> ({year: input paths} for complete years,
    {year: missing file names} for the rest)."""
    complete_years, missing_by_year = {}, {}
    if not inputs_dir.exists():
        return complete_years, missing_by_year
    dir_pattern = re.escape(dir_name).replace(re.escape("{year}"), YEAR_PATTERN)
    for year_dir in sorted(inputs_dir.iterdir()):
        dir_match = re.fullmatch(dir_pattern, year_dir.name)
        if not (year_dir.is_dir() and dir_match):
            continue
        year = int(dir_match.group(1))
        input_paths = [year_dir / name.format(year=year) for name in input_names]
        missing_names = [path.name for path in input_paths if not path.exists()]
        if missing_names:
            missing_by_year[year] = missing_names
        else:
            complete_years[year] = input_paths
    return complete_years, missing_by_year


def _two_digit_year(year):
    return f"{year % 100:02d}"
