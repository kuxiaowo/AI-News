import json
from pathlib import Path


def get_config(path: str):
    """Load JSON config from path.

    Parameters
    ----------
    path: str
        Path to JSON config file.

    Returns
    -------
    dict
    """
    p = Path(path)
    with p.open('r', encoding='utf-8') as f:
        return json.load(f)

