"""Census profile of a weighted set of hexes: each hex takes its census area's category mix (SA2 for residents, DZN for
workers, by the area holding the hex centroid); a profile is the weight-averaged mix. No within-area variation."""
import geopandas as gpd
import pandas as pd
import pyogrio

from functions import abs_tablebuilder

LONLAT_CRS = 4326
SA2_COL, GCC_COL, STATE_COL, DZN_COL = "SA2_NAME21", "GCC_NAME21", "STE_NAME21", "DZN_CODE21"


def hex_areas(hex_df, sa1_path, dzn_path, state, comparison_gcc):
    """(SA2 name and DZN code per hex_id, comparison SA2 names, comparison DZN codes) from hex centroids.

    hex_df: hex_id, centroid_lat, centroid_lon. Comparison areas: SA2s in comparison_gcc and the DZNs inside them.
    """
    state_filter = f"{STATE_COL} = '{state}'"
    # the where filter sees only the columns read, so the state column is read too
    sa1_gdf = pyogrio.read_dataframe(sa1_path, columns=[SA2_COL, GCC_COL, STATE_COL],
                                     where=state_filter).to_crs(LONLAT_CRS)
    dzn_gdf = pyogrio.read_dataframe(dzn_path, columns=[DZN_COL, SA2_COL, STATE_COL],
                                     where=state_filter).to_crs(LONLAT_CRS)
    assert len(sa1_gdf) and len(dzn_gdf), f"no SA1 or DZN boundaries for {state}"
    points_gdf = gpd.GeoDataFrame(hex_df[["hex_id"]], crs=LONLAT_CRS,
                                  geometry=gpd.points_from_xy(hex_df.centroid_lon, hex_df.centroid_lat))
    points_gdf = gpd.sjoin(points_gdf, sa1_gdf[[SA2_COL, "geometry"]], how="left", predicate="within")
    points_gdf = gpd.sjoin(points_gdf.drop(columns="index_right"), dzn_gdf[[DZN_COL, "geometry"]], how="left",
                           predicate="within")
    areas_df = pd.DataFrame(points_gdf.drop(columns=["geometry", "index_right"])).drop_duplicates("hex_id")
    areas_df[DZN_COL] = areas_df[DZN_COL].astype("string")
    comparison_sa2 = set(sa1_gdf.loc[sa1_gdf[GCC_COL] == comparison_gcc, SA2_COL])
    comparison_dzn = set(dzn_gdf.loc[dzn_gdf[SA2_COL].isin(comparison_sa2), DZN_COL].astype(str))
    return areas_df.set_index("hex_id"), comparison_sa2, comparison_dzn


def area_mix(path, level, groups, excluded):
    """(area x group shares, area totals) of one TableBuilder export; groups a dict or a top-k count."""
    table_df = abs_tablebuilder.read_tablebuilder(path)
    if level is not None:
        table_df = abs_tablebuilder.keep_level(table_df, level)
    if isinstance(groups, int):
        groups = abs_tablebuilder.top_k_groups(table_df, groups, excluded)
    mix_df, total = abs_tablebuilder.group_shares(table_df, groups)
    mix_df.index, total.index = mix_df.index.astype(str), total.index.astype(str)
    return mix_df, total


def profile(weights, areas, mix_df):
    """Weight-averaged mix over hexes (weights and areas aligned) and the weight share whose area is in the table."""
    is_known = areas.astype(str).isin(mix_df.index)
    known_weights = weights[is_known]
    mix = mix_df.loc[areas[is_known].astype(str)].mul(known_weights.to_numpy(), axis=0).sum() / known_weights.sum()
    return mix, known_weights.sum() / max(weights.sum(), 1e-12)


def comparison_mix(mix_df, total, areas):
    """Population-weighted mix over the given areas (the comparison region)."""
    is_in = mix_df.index.isin(areas)
    return mix_df[is_in].mul(total[is_in], axis=0).sum() / total[is_in].sum()
