"""Why does R5 reach the Holmesglen and Reservoir platforms without the pathway spur? (maps; curiosity, user)

Claim looked at (transit_pathway_network.py, build check): on the derived network R5's walk to a platform point
goes through an entrance and its spur. At Holmesglen (2 sides) and Reservoir (1) the walk equals the old network's,
shorter than any entrance + spur. Where the pipeline would rely on it: the pathways network for transit bands 1-2,
if adopted. The user expects no substantive effect on the model; this is a look, not a test.

Method: per station, a map around the station (ZOOM_M either way): grey = walkable OSM ways of the derived extract
(release 20261009), red = the ways transit_pathway_network added (spurs, entrance links, stubs), star = the station
(parent stop), black squares = platforms, red dots = entrances, blue = R5's walk-only route (r5py
DetailedItineraries, 4.16 km/h) for each residual side, from the side's end to the platform point.

Also: R5's StreetLayer.findSplit (WALK, 300 m) at every hub platform's feed coordinates names the edge R5 links the
stop to.

Conclusion (look 2026-10-19): two different causes, both small.
  Holmesglen: platform 8766's feed coordinate lies 11 mm from OSM way 45414809; R5 links the stop to that way, not to
  the stub at the same spot (a centimetre-level tie: at the hub's 7-decimal coordinate, ~1 mm away, the stub wins).
  So 8766 bypasses its pathways, as on the old network. It is the only one: 585 of 586 platform stops link to their
  own stub. Robust fix if productionised: move the stop to the stub's far end in a copy of the train feed.
  Reservoir: no bypass. The stop links to its stub and R5's route uses the EN1 (High St) spur; it is 32 s shorter
  than the check expected because the check's entrance walk is R5's own linking of the entrance point, while the
  build joins EN1 to the street at a different spot (nearest walkable, linkable way or a node within 0.5 m).

Inputs (read only): transit_pathway_network's derived extract and check table (newest), the cleaned 2026-10-09 train
feed. Self-contained (CLAUDE.md D1). No API calls. Saved data (reused if present): the ways near each station and
R5's route geometry. Usage: `python transit_pathway_residual_map.py`.
"""
import datetime
import math
import sys
import zipfile
from pathlib import Path

import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DIAGNOSTIC_DATA_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_data"
DIAGNOSTIC_IMG_DIR = PROJECT_ROOT / "diagnostics" / "diagnostic_img"
NAME = "transit_pathway_residual_map"
NETWORK_NAME = "transit_pathway_network"
RELEASE = "20261009"
DERIVED_PBF_PATH = DIAGNOSTIC_DATA_DIR / f"{NETWORK_NAME}_osm_{RELEASE}.osm.pbf"
TRAIN_ZIP_PATH = PROJECT_ROOT / "outputs" / "pt_graph" / "gtfs_cleaned" / "ptv_metro_train.zip"
FEED_NAMES = ["ptv_metro_train", "ptv_tram", "ptv_metro_bus"]
STATIONS = {"Holmesglen": "vic:rail:HOL", "Reservoir": "vic:rail:RES"}

R5_MAX_MEMORY = "7G"
WINDOW_DATE = datetime.date(2026, 10, 21)
WALK_SPEED_KMH = 4.16
CHECK_TOLERANCE_S = 15                 # as transit_pathway_network
ZOOM_M = 160                           # map half-width
FETCH_M = 600                          # ways fetched within this of the station
METRES_PER_DEG_LAT = 110_574.0
METRES_PER_DEG_LON_EQUATOR = 111_320.0
TAG_SOURCE = ("platica", "pathway")
LINK_RADIUS_M = 300.0                  # as R5's first stop-link radius
NEW_WAY_ID_BASE = 9_000_000_000        # as transit_pathway_network
ENTRANCE_TYPE, STATION_TYPE = "2", "1"
GTFS_ENCODING = "utf-8-sig"
GREY, RED, BLUE, INK = "#9a9a9a", "#d62728", "#1f5fbf", "#222222"
FIGURE_SIZE_IN = (7.5, 7.5)
DPI = 150


def newest(pattern):
    paths = sorted(DIAGNOSTIC_DATA_DIR.glob(pattern))
    return paths[-1] if paths else None


def station_stops():
    with zipfile.ZipFile(TRAIN_ZIP_PATH) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
    stops_df["stop_lat"] = stops_df.stop_lat.astype(float)
    stops_df["stop_lon"] = stops_df.stop_lon.astype(float)
    return stops_df[stops_df.stop_id.isin(STATIONS.values()) | stops_df.parent_station.isin(STATIONS.values())]


def residual_sides():
    frames = []
    for path in sorted(DIAGNOSTIC_DATA_DIR.glob(f"{NETWORK_NAME}_*_check_{RELEASE}.csv")):
        frames.append(pd.read_csv(path, dtype={"platform_id": str, "entrance_id": str}))
    check_df = frames[-1]
    return check_df[(check_df.diff_s.abs() > CHECK_TOLERANCE_S) & check_df.stop_name.isin(STATIONS)]


def nearby_ways(stops_df):
    """Ways of the derived extract with a node within FETCH_M of a station (saved, reused)."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    saved = newest(f"{NAME}_*_ways.csv")
    if saved:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return pd.read_csv(saved)
    import osmium
    centres = stops_df[stops_df.location_type == STATION_TYPE][["stop_lat", "stop_lon"]].to_numpy()
    lat_pad = FETCH_M / METRES_PER_DEG_LAT
    rows = []
    for obj in osmium.FileProcessor(str(DERIVED_PBF_PATH)).with_locations():
        if not obj.is_way() or "highway" not in obj.tags:
            continue
        if not all(node.location.valid() for node in obj.nodes):
            continue
        lats = [node.lat for node in obj.nodes]
        lons = [node.lon for node in obj.nodes]
        for lat0, lon0 in centres:
            lon_pad = FETCH_M / (METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0)))
            if any(abs(lat - lat0) <= lat_pad and abs(lon - lon0) <= lon_pad for lat, lon in zip(lats, lons)):
                rows.append({"way_id": obj.id, "highway": obj.tags.get("highway"),
                             "is_added": obj.tags.get(TAG_SOURCE[0]) == TAG_SOURCE[1], "tunnel": obj.tags.get("tunnel", ""),
                             "lats": " ".join(f"{lat:.7f}" for lat in lats), "lons": " ".join(f"{lon:.7f}" for lon in lons)})
                break
    ways_df = pd.DataFrame(rows)
    ways_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_ways.csv", index=False)
    return ways_df


def r5_routes(sides_df):
    """R5 walk-only route geometry (WKT) per residual side, end -> platform point (saved, reused)."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    saved = newest(f"{NAME}_*_routes.csv")
    if saved:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return pd.read_csv(saved)
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import geopandas as gpd
    from r5py import DetailedItineraries, TransportMode, TransportNetwork
    network = TransportNetwork(DERIVED_PBF_PATH, [TRAIN_ZIP_PATH.parent / f"{name}.zip" for name in FEED_NAMES])
    sides_df = sides_df.reset_index(drop=True)
    is_board = sides_df.side == "board"
    origins = gpd.GeoDataFrame({"id": sides_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, sides_df.end_lon, sides_df.platform_lon), np.where(is_board, sides_df.end_lat, sides_df.platform_lat)))
    destinations = gpd.GeoDataFrame({"id": sides_df.index}, crs="EPSG:4326", geometry=gpd.points_from_xy(
        np.where(is_board, sides_df.platform_lon, sides_df.end_lon), np.where(is_board, sides_df.platform_lat, sides_df.end_lat)))
    di_df = pd.DataFrame(DetailedItineraries(network, origins=origins, destinations=destinations,
                                             departure=datetime.datetime.combine(WINDOW_DATE, datetime.time(12)),
                                             transport_modes=[TransportMode.WALK], speed_walking=WALK_SPEED_KMH))
    out_df = pd.DataFrame({"side_ix": di_df.from_id, "travel_s": di_df.travel_time.dt.total_seconds(),
                           "distance_m": di_df.distance, "wkt": di_df.geometry.apply(lambda geometry: geometry.wkt)})
    out_df = out_df.merge(sides_df[["stop_name", "side", "draw_no", "set_name", "new_platform_s", "expected_s"]],
                          left_on="side_ix", right_index=True)
    out_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_routes.csv", index=False)
    return out_df


def hub_links():
    """The street edge R5 links each platform hub point to (StreetLayer.findSplit, WALK, LINK_RADIUS_M; saved, reused)."""
    run_date = f"{datetime.date.today():%Y%m%d}"
    saved = newest(f"{NAME}_*_hub_links_{RELEASE}.csv")
    if saved:
        print(f"reusing {saved.name} ({datetime.date.fromtimestamp(saved.stat().st_mtime)})")
        return pd.read_csv(saved)
    sys.argv += ["--max-memory", R5_MAX_MEMORY]
    import jpype
    from r5py import TransportNetwork
    network = TransportNetwork(DERIVED_PBF_PATH, [TRAIN_ZIP_PATH.parent / f"{name}.zip" for name in FEED_NAMES])
    street_layer = network._transport_network.streetLayer
    walk_mode = jpype.JClass("com.conveyal.r5.profile.StreetMode").WALK
    spurs_df = pd.read_csv(newest(f"{NETWORK_NAME}_*_spurs_{RELEASE}.csv"))
    with zipfile.ZipFile(TRAIN_ZIP_PATH) as gtfs_zip:
        stops_df = pd.read_csv(gtfs_zip.open("stops.txt"), dtype=str, encoding=GTFS_ENCODING)
    stops_df = stops_df[stops_df.location_type.fillna("").isin(["0", ""])].copy()
    stops_df["hub"] = stops_df.stop_lat.astype(float).round(7).astype(str) + "," + stops_df.stop_lon.astype(float).round(7).astype(str)
    platforms_df = stops_df[stops_df.hub.isin(set(spurs_df.end))]
    rows = []
    for platform in platforms_df.itertuples():      # the feed's own coordinates: what R5 links the stop at
        split = street_layer.findSplit(float(platform.stop_lat), float(platform.stop_lon), LINK_RADIUS_M, walk_mode)
        osm_way = int(street_layer.edgeStore.getCursor(split.edge).getOSMID()) if split is not None else None
        rows.append({"platform_id": platform.stop_id, "stop_name": platform.stop_name, "hub": platform.hub, "osm_way": osm_way, "distance_mm": int(split.distanceToEdge_mm) if split is not None else None,
                     "is_added_way": osm_way is not None and osm_way >= NEW_WAY_ID_BASE})
    links_df = pd.DataFrame(rows)
    links_df.to_csv(DIAGNOSTIC_DATA_DIR / f"{NAME}_{run_date}_hub_links_{RELEASE}.csv", index=False)
    return links_df


def plot(station_name, stops_df, ways_df, routes_df):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from shapely import wkt
    station = stops_df[stops_df.stop_id == STATIONS[station_name]].iloc[0]
    lat0, lon0 = station.stop_lat, station.stop_lon
    x_scale = METRES_PER_DEG_LON_EQUATOR * math.cos(math.radians(lat0))

    def to_xy(lats, lons):
        return (np.asarray(lons) - lon0) * x_scale, (np.asarray(lats) - lat0) * METRES_PER_DEG_LAT

    fig, ax = plt.subplots(figsize=FIGURE_SIZE_IN)
    for way in ways_df[~ways_df.is_added].itertuples():
        x, y = to_xy([float(v) for v in way.lats.split()], [float(v) for v in way.lons.split()])
        ax.plot(x, y, color=GREY, linewidth=1.2, zorder=1)
    for way in ways_df[ways_df.is_added].itertuples():
        x, y = to_xy([float(v) for v in way.lats.split()], [float(v) for v in way.lons.split()])
        ax.plot(x, y, color=RED, linewidth=1.0 if way.tunnel == "yes" else 2.0, alpha=0.8, zorder=2)
    for route in routes_df[routes_df.stop_name == station_name].itertuples():
        line = wkt.loads(route.wkt)
        lons, lats = zip(*line.coords)
        x, y = to_xy(lats, lons)
        ax.plot(x, y, color=BLUE, linewidth=2.5, alpha=0.85, zorder=3)
    members = stops_df[stops_df.parent_station == STATIONS[station_name]]
    entrances = members[members.location_type == ENTRANCE_TYPE]
    platforms = members[members.location_type.fillna("").isin(["0", ""])]
    x, y = to_xy(entrances.stop_lat, entrances.stop_lon)
    ax.scatter(x, y, s=40, color=RED, edgecolor="white", zorder=4)
    for (xi, yi, label) in zip(x, y, entrances.stop_id.str.split("_").str[-1]):
        ax.annotate(label, (xi, yi), xytext=(4, 4), textcoords="offset points", fontsize=8, color=INK)
    x, y = to_xy(platforms.stop_lat, platforms.stop_lon)
    ax.scatter(x, y, s=36, marker="s", color=INK, zorder=4)
    for (xi, yi, label) in zip(x, y, platforms.stop_id):
        ax.annotate(label, (xi, yi), xytext=(4, -10), textcoords="offset points", fontsize=8, color=INK)
    ax.scatter([0], [0], s=260, marker="*", color="#f2b600", edgecolor=INK, zorder=5)
    ax.set_xlim(-ZOOM_M, ZOOM_M)
    ax.set_ylim(-ZOOM_M, ZOOM_M)
    ax.set_aspect("equal")
    ax.set_xlabel("metres east of the station")
    ax.set_ylabel("metres north of the station")
    for spine in ("top", "right"):
        ax.spines[spine].set_visible(False)
    station_routes = routes_df[routes_df.stop_name == station_name].drop_duplicates("side_ix")
    caption = "; ".join(f"{r.side} {r.set_name} {r.draw_no}: R5 {r.new_platform_s:.0f} s vs entrance + spur {r.expected_s:.0f} s"
                        for r in station_routes.itertuples())
    ax.set_title(f"{station_name}: R5's walk route and the added pathways\n{caption}", fontsize=9, loc="left")
    handles = [plt.Line2D([], [], color=GREY, linewidth=1.2, label="OSM walkable ways"),
               plt.Line2D([], [], color=RED, linewidth=1.0, label="added pathway spurs (tunnel), links, stub"),
               plt.Line2D([], [], color=BLUE, linewidth=2.5, label="R5 walk route (r5py DetailedItineraries)"),
               plt.Line2D([], [], marker="s", color=INK, linestyle="", label="platform"),
               plt.Line2D([], [], marker="o", color=RED, linestyle="", label="entrance"),
               plt.Line2D([], [], marker="*", color="#f2b600", markeredgecolor=INK, markersize=14, linestyle="", label="station")]
    ax.legend(handles=handles, loc="lower left", fontsize=8, frameon=False)
    path = DIAGNOSTIC_IMG_DIR / f"{NAME}_{datetime.date.today():%Y%m%d}_{station_name.lower()}.png"
    fig.savefig(path, dpi=DPI, bbox_inches="tight")
    plt.close(fig)
    print(f"saved {path.name}")


def main():
    stops_df = station_stops()
    sides_df = residual_sides()
    print(sides_df[["stop_name", "side", "set_name", "draw_no", "platform_id", "entrance_id", "expected_s", "new_platform_s",
                    "old_platform_s"]].to_string())
    ways_df = nearby_ways(stops_df)
    routes_df = r5_routes(sides_df)
    print(routes_df.drop(columns="wkt").to_string())
    links_df = hub_links()
    off_stub = links_df[~links_df.is_added_way]
    print(f"hubs linked by R5 to their own stub: {int(links_df.is_added_way.sum())} of {len(links_df)}; off the stub:")
    print(off_stub.to_string())
    for station_name in STATIONS:
        plot(station_name, stops_df, ways_df, routes_df)


if __name__ == "__main__":
    main()
