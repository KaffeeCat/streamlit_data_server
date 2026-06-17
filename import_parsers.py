import io
from pathlib import Path

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".tsv", ".xlsx", ".json", ".jsonl", ".ndjson"}


def parse_upload(filename: str, content: bytes) -> pd.DataFrame:
    suffix = Path(filename).suffix.lower()
    if suffix not in SUPPORTED_EXTENSIONS:
        raise ValueError(
            f"Unsupported file type: {suffix or '(none)'}."
            f" Supported: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
        )

    buffer = io.BytesIO(content)

    if suffix == ".csv":
        df = pd.read_csv(buffer)
    elif suffix == ".tsv":
        df = pd.read_csv(buffer, sep="\t")
    elif suffix == ".xlsx":
        df = pd.read_excel(buffer, engine="openpyxl")
    elif suffix == ".json":
        df = pd.read_json(buffer)
    elif suffix in {".jsonl", ".ndjson"}:
        df = pd.read_json(buffer, lines=True)
    else:
        raise ValueError(f"Cannot parse: {suffix}")

    if df.empty and len(df.columns) == 0:
        raise ValueError("File is empty or has no parseable columns")

    df.columns = [str(c).strip() for c in df.columns]
    if df.columns.duplicated().any():
        raise ValueError("File contains duplicate column names")

    for col in df.columns:
        if not col:
            raise ValueError("File contains an empty column name")

    return df
