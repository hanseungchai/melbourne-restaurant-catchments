"""Readers for hand-made project inputs (see frozen_inputs/README.md, "Hand-made")."""

import config


def read_subject_location(coord_path):
    """Return the subject business location as (lat, lng) floats.

    Input: Path to a text file whose first line is "lat, lng" (e.g. config.SUBJECT_COORD_PATH).
    """
    first_line = coord_path.read_text(encoding="utf-8").splitlines()[0].strip()
    lat_text, lng_text = first_line.split(",")
    return float(lat_text), float(lng_text)


def subject_coord_path(subject_name=None):
    """Return the coordinate file of a subject.

    None -> the default subject, config.SUBJECT_COORD_PATH. A name -> "<name>.txt" in
    config.ALT_SUBJECTS_DIR; the name must match the file name exactly (without ".txt").
    """
    if subject_name is None:
        return config.SUBJECT_COORD_PATH
    coord_path = config.ALT_SUBJECTS_DIR / f"{subject_name}{config.SUBJECT_COORD_SUFFIX}"
    if not coord_path.is_file():
        available_names = sorted(path.stem for path in
                                 config.ALT_SUBJECTS_DIR.glob(f"*{config.SUBJECT_COORD_SUFFIX}"))
        raise FileNotFoundError(f"no coordinate file for subject '{subject_name}' at {coord_path}; "
                                f"subjects available: {available_names}")
    return coord_path
