"""cleankit: contract-driven cleanup of messy spreadsheets (xlsx/csv).

Data shape (see model.py): a Grid (raw cells + merges) -> Blocks of classified rows
-> Table of Records (value + provenance) -> cleaned Table + an Audit (changes,
drops, review flags, suspected duplicates, join reports, contract checks).
"""
