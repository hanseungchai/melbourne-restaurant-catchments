"""ABS TableBuilder CSV exports: parse into area x category frames, and group categories into shares.

An export has a title block, one header row per crossed variable (each label written once, then blank across the
columns it spans), a row naming the area variable, one row per area, a "Total" row and a footer. Columns are named by
their header labels joined with HEADER_SEP; trailing blank columns repeat the last label and are dropped by grouping.
"""
import csv

import pandas as pd

AREA_LABELS = {"SA2 (UR)", "SA2 (EN)", "DZN (POW)"}
TOTAL_ROW = "Total"
HEADER_SEP = " | "


def read_tablebuilder(path):
    """Area x column counts (float) from one export; the index is the area label as written (SA2 name, DZN code)."""
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.reader(f))
    label_at = next(i for i, row in enumerate(rows) if row and row[0].strip() in AREA_LABELS)
    first_header = label_at
    while first_header > 0 and any(cell.strip() for cell in rows[first_header - 1]):
        first_header -= 1
    headers = []
    for row in rows[first_header:label_at]:
        filled, last = [], ""
        for cell in row[1:]:
            last = cell.strip() or last
            filled.append(last)
        headers.append(filled)
    names = [HEADER_SEP.join(header[j] for header in headers) for j in range(len(headers[0]))]
    data = []
    for row in rows[label_at + 1:]:
        if not row or not row[0].strip() or row[0].strip() == TOTAL_ROW:
            break
        data.append(row[:1 + len(names)])
    table_df = pd.DataFrame([row[1:] for row in data], index=[row[0].strip() for row in data], columns=names)
    table_df = table_df.loc[:, [name for name in names if name.strip()]]
    return table_df.apply(pd.to_numeric, errors="coerce").fillna(0)


def keep_level(table_df, level):
    """Sum columns over every header level but one (level indexes the HEADER_SEP-split name)."""
    labels = table_df.columns.str.split(HEADER_SEP.strip()).str[level].str.strip()
    return table_df.T.groupby(labels).sum().T


def group_shares(table_df, groups):
    """Each area's share per group (groups: name -> column labels) and its total over the groups."""
    table_df = table_df.T.groupby(level=0).first().T             # repeated labels (trailing blanks) once
    counts_df = pd.DataFrame({name: table_df[[c for c in table_df.columns if c in labels]].sum(axis=1)
                              for name, labels in groups.items()})
    total = counts_df.sum(axis=1)
    return counts_df.div(total, axis=0).fillna(0), total


def top_k_groups(table_df, k, excluded):
    """Groups for the k largest columns overall, by name, plus "Other" for the rest (excluded columns left out)."""
    table_df = table_df.T.groupby(level=0).first().T
    categories = [c for c in table_df.columns if c not in excluded]
    top = table_df[categories].sum().sort_values(ascending=False).index[:k].tolist()
    return {**{c: [c] for c in top}, "Other": [c for c in categories if c not in top]}
