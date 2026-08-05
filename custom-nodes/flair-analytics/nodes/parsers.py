"""
Parser nodes -- turn the raw per-provider payloads from FLAIR_LoadBySecretKey
(loaders.py) into usable data. See ../PLAN.md for the overall porting
strategy: the payload shape (JSON vs. CSV) is notebook/service-specific, so
each shape gets its own parser node rather than one node trying to guess.
"""

import io
import logging
import urllib.parse

import pandas as pd


class FLAIR_ParseCSVPayload:
    """
    Parses each provider's CSV-formatted payload into a single combined
    pandas DataFrame, tagged with which provider each row came from. Mirrors
    the "combine all CSV data into a single DataFrame" step common to the
    CSV-payload notebooks (iucn_categorization.ipynb, sparql.ipynb,
    coordinates_by_species.ipynb's data-loading service): parse, tag,
    concatenate.

    Deliberately does NOT do schema-specific cleanup (deduplicating on
    particular columns, dropping rows missing particular fields) -- that
    varies per service/notebook and belongs in a downstream, service-specific
    node, not this generic one. A provider with zero data rows (header only)
    contributes zero rows without erroring; a provider whose payload isn't
    valid CSV is skipped with a warning rather than failing the whole batch,
    so one misbehaving provider doesn't block everyone else's clean data.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "provider_data": ("FLAIR_PROVIDER_DATA",),
            },
        }

    RETURN_TYPES = ("DATAFRAME",)
    RETURN_NAMES = ("combined_data",)
    FUNCTION = "parse"
    CATEGORY = "FLAIR/parsers"
    DESCRIPTION = (
        "Parses each provider's CSV payload via pandas, tags rows with "
        "provider_url/provider_host, and concatenates into one combined "
        "DataFrame. A provider returning zero rows contributes nothing "
        "without erroring; a provider whose payload isn't valid CSV is "
        "skipped with a warning rather than failing the whole batch."
    )

    def parse(self, provider_data):
        frames = []
        empty_count = 0
        failed = []

        for provider_url, raw_csv in provider_data.items():
            try:
                df = pd.read_csv(io.StringIO(raw_csv))
            except Exception as exc:
                failed.append((provider_url, str(exc)))
                continue

            if df.empty:
                # Header row only, zero data rows -- a valid, successful
                # response, just nothing to contribute. Skipped from the
                # concat list itself (not just filtered after) because
                # pandas warns/plans to change behavior around concatenating
                # empty-or-all-NA frames; excluding them up front sidesteps
                # that entirely rather than working around a warning.
                empty_count += 1
                continue

            df["provider_url"] = provider_url
            df["provider_host"] = urllib.parse.urlparse(provider_url).netloc
            frames.append(df)

        if failed:
            logging.warning(
                "[FLAIR_ParseCSVPayload] %d provider(s) could not be parsed as CSV: %s",
                len(failed),
                "; ".join(f"{url} ({err})" for url, err in failed),
            )

        if not frames:
            if empty_count and not failed:
                raise ValueError(
                    f"All {empty_count} provider(s) returned zero data rows "
                    "(header only) -- nothing to combine."
                )
            raise ValueError(
                "None of the providers' payloads could be parsed as CSV -- "
                f"{len(failed)} provider(s) failed: "
                + "; ".join(f"{url}: {err}" for url, err in failed)
            )

        combined = pd.concat(frames, ignore_index=True)

        logging.info(
            "[FLAIR_ParseCSVPayload] parsed %d provider(s) into %d total row(s) "
            "(%d returned no rows, %d failed to parse)",
            len(frames),
            len(combined),
            empty_count,
            len(failed),
        )

        return (combined,)


NODE_CLASS_MAPPINGS = {
    "FLAIR_ParseCSVPayload": FLAIR_ParseCSVPayload,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_ParseCSVPayload": "Parse FLAIR-GG CSV Payload",
}
