"""Writers for pipeline outputs, and the path form they store in metadata."""
import pickle
from pathlib import Path

import config


def write_pickle_new(obj, path):
    """Pickle obj to path; refuse to overwrite an existing file.

    Raises FileExistsError if path exists: archive the old file or pass a new path.
    """
    path = Path(path)
    if path.exists():
        raise FileExistsError(f"{path} exists; archive it or pass a new path")
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def write_pickle(obj, path):
    """Pickle obj to path, replacing any existing file. Pair with is_already_built to skip unasked rebuilds."""
    with open(path, "wb") as f:
        pickle.dump(obj, f)


def is_already_built(paths, should_rebuild):
    """True (and says so) when every file in paths exists and should_rebuild is off."""
    if should_rebuild or not all(path.exists() for path in paths):
        return False
    print(f"Skipped, already built: {', '.join(path.name for path in paths)}")
    return True


def project_relative(path):
    """Path as stored in graph metadata: relative to the project root, forward slashes."""
    return Path(path).relative_to(config.PROJECT_ROOT).as_posix()
