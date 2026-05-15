from __future__ import annotations

import pickle
import re
from pathlib import Path

RANKED_KEY = "Ours-noise=0"


def _from_pkl(pkl_path: str | Path) -> list[str] | None:
    p = Path(pkl_path)
    if not p.exists():
        return None
    try:
        with p.open("rb") as f:
            obj = pickle.load(f)
    except (pickle.UnpicklingError, EOFError, OSError):
        return None
    if isinstance(obj, dict) and RANKED_KEY in obj:
        value = obj[RANKED_KEY]
        if isinstance(value, list):
            return [str(x) for x in value]
    return None


def _from_stdout(stdout: str) -> list[str]:
    if not stdout:
        return []
    m = re.search(rf"{re.escape(RANKED_KEY)}.*?\[(.*?)\]", stdout, re.DOTALL)
    if not m:
        return []
    inner = m.group(1)
    items = re.findall(r"['\"]([^'\"]+)['\"]", inner)
    return items


def parse_ranked_output(stdout: str, pkl_path: str | Path) -> list[str]:
    from_pkl = _from_pkl(pkl_path)
    if from_pkl is not None:
        return from_pkl
    return _from_stdout(stdout)
