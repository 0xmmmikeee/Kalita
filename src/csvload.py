"""Чтение большого signals.csv кусками: пик памяти парсера pandas на 8M строк с category-адресами — ~6 ГБ,
кусками по 500k строк с объединением категорий — ~2–2.5 ГБ. Результат идентичен pd.read_csv(..., dtype=...)."""
import pandas as pd
from pandas.api.types import union_categoricals

def read_signals(path, usecols, dtype, chunksize=500_000):
    parts = []
    for ch in pd.read_csv(path, usecols=usecols, dtype=dtype, chunksize=chunksize):
        parts.append(ch)
    if len(parts) == 1: return parts[0]
    cat_cols = [c for c, t in dtype.items() if t == 'category' and c in parts[0].columns]
    out = {}
    for c in parts[0].columns:
        if c in cat_cols: out[c] = union_categoricals([p[c] for p in parts], ignore_order=True)
        else: out[c] = pd.concat([p[c] for p in parts], ignore_index=True)
    df = pd.DataFrame(out); parts.clear()
    return df
