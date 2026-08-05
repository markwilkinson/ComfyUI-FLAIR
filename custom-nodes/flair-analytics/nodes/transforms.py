"""
Transform nodes -- generic cleanup operations on a DATAFRAME (as produced by
parsers.py), not specific to any one payload shape. See ../PLAN.md.
"""

import logging


class FLAIR_DeduplicateRows:
    """
    Drops duplicate rows and rows missing a value, based on caller-specified
    column names. Mirrors the cleanup step common to the CSV-payload
    notebooks (e.g. iucn_categorization.ipynb cell 3:
    `combined_df.drop_duplicates(subset=[...]).dropna()`), generalized to
    whatever columns the caller cares about rather than hardcoded to one
    notebook's schema.

    Leaving subset_columns empty considers all columns (matches pandas'
    default drop_duplicates()/dropna() behavior with no subset).
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "data": ("DATAFRAME",),
            },
            "optional": {
                "subset_columns": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "Comma-separated column names to check for duplicates/missing values. Leave empty to consider all columns.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("DATAFRAME",)
    RETURN_NAMES = ("cleaned_data",)
    FUNCTION = "deduplicate"
    CATEGORY = "FLAIR/transforms"
    DESCRIPTION = (
        "Drops duplicate rows and rows missing a value, checked against "
        "caller-specified column names (comma-separated). Leave empty to "
        "consider all columns."
    )

    def deduplicate(self, data, subset_columns=""):
        columns = [c.strip() for c in subset_columns.split(",") if c.strip()]

        if columns:
            missing = [c for c in columns if c not in data.columns]
            if missing:
                raise ValueError(
                    f"Column(s) not found in data: {', '.join(missing)}. "
                    f"Available columns: {', '.join(data.columns)}"
                )

        subset = columns or None
        before = len(data)
        cleaned = data.drop_duplicates(subset=subset).dropna(subset=subset)
        after = len(cleaned)

        logging.info(
            "[FLAIR_DeduplicateRows] %d -> %d row(s) (dropped %d) using columns: %s",
            before,
            after,
            before - after,
            columns or "(all)",
        )
        if after == 0 and before > 0:
            logging.warning(
                "[FLAIR_DeduplicateRows] all %d row(s) were dropped -- check "
                "that subset_columns matches real column names",
                before,
            )

        return (cleaned,)


NODE_CLASS_MAPPINGS = {
    "FLAIR_DeduplicateRows": FLAIR_DeduplicateRows,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_DeduplicateRows": "Deduplicate FLAIR-GG Rows",
}
