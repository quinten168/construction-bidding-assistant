from __future__ import annotations

from pathlib import Path

import pandas as pd


def write_table(df: pd.DataFrame, output_path: str | Path) -> Path:
    """Write parquet when available, otherwise write a CSV fallback."""

    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    try:
        df.to_parquet(path, index=False)
        return path
    except ImportError:
        fallback = path.with_suffix(".csv")
        df.to_csv(fallback, index=False)
        print(f"Parquet engine is not installed; wrote CSV fallback instead: {fallback}")
        return fallback


def read_table(path: str | Path) -> pd.DataFrame:
    path = Path(path)
    if path.suffix == ".parquet":
        fallback = path.with_suffix(".csv")
        if fallback.exists() and (
            not path.exists() or fallback.stat().st_mtime >= path.stat().st_mtime
        ):
            return pd.read_csv(fallback)
        try:
            return pd.read_parquet(path, engine="pyarrow")
        except Exception:
            try:
                return pd.read_parquet(path, engine="fastparquet")
            except Exception:
                if fallback.exists():
                    return pd.read_csv(fallback)
                raise
    return pd.read_csv(path)
