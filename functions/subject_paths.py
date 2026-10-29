"""Subject-tagged output paths: where a subject's files live and how their names carry the
subject ("<lat>_<lon>") and the data layers they were built from (census years, venue table)."""
from pathlib import Path

import config
from functions.input_helper import read_subject_location

# File-name tag prefixes of the hex grid's data layers.
RESIDENTS_TAG_PREFIX = "res"
WORKERS_TAG_PREFIX = "wrk"
VENUES_TAG_PREFIX = "ven"


def resolve_subject(subject_lat=None, subject_lon=None):
    """Both None -> the default subject (config.SUBJECT_COORD_PATH); else the two given."""
    if subject_lat is None and subject_lon is None:
        return read_subject_location(config.SUBJECT_COORD_PATH)
    if subject_lat is None or subject_lon is None:
        raise ValueError("pass both subject_lat and subject_lon, or neither")
    return subject_lat, subject_lon


def subject_tag(subject_lat, subject_lon):
    """The subject's "<lat>_<lon>" tag."""
    decimals = config.SUBJECT_TAG_DECIMALS
    return f"{subject_lat:.{decimals}f}_{subject_lon:.{decimals}f}"


def subject_dir(folder, subject_lat, subject_lon):
    """The subject's own "<lat>_<lon>" subfolder of folder."""
    return folder / subject_tag(subject_lat, subject_lon)


def subject_file(path, subject_lat, subject_lon, data_tags=()):
    """path moved into the subject's subfolder, with the data-layer tags and "_<lat>_<lon>" added
    to its file name."""
    name_parts = [path.stem, *data_tags, subject_tag(subject_lat, subject_lon)]
    return subject_dir(path.parent, subject_lat, subject_lon) / f"{'_'.join(name_parts)}{path.suffix}"


def residents_tags():
    """Tag of the residents census year the stage reads (config.CENSUS_RESIDENTS_YEAR)."""
    return (f"{RESIDENTS_TAG_PREFIX}{config.CENSUS_RESIDENTS_YEAR}",)


def workers_tags():
    """Tag of the workers census year the stage reads (config.CENSUS_WORKERS_YEAR)."""
    return (f"{WORKERS_TAG_PREFIX}{config.CENSUS_WORKERS_YEAR}",)


def venues_tags():
    """Tag of the venue table the stage reads (config.HEX_VENUES_DATE)."""
    return (f"{VENUES_TAG_PREFIX}{config.HEX_VENUES_DATE}",)


def all_layers_tags():
    """Tags of every data layer in the filled grid: census years, then venues."""
    return (*residents_tags(), *workers_tags(), *venues_tags())


def subject_layers_file(path, subject_lat, subject_lon):
    """path in the subject's subfolder, tagged with the filled grid's data layers (as routing_graph)."""
    return subject_file(Path(path), subject_lat, subject_lon, all_layers_tags())


def timed_graph_path(variant, subject_lat, subject_lon):
    """The subject's timed graph for one variant, named as speed_graphs.enrich writes it."""
    stem = Path(config.TIMED_DRIVE_GRAPH_PATH)
    return subject_layers_file(stem.with_name(f"{stem.stem}_{variant}{stem.suffix}"), subject_lat, subject_lon)
