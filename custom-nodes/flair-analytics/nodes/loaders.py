"""
Loader nodes -- ports of the FLAIR-GG-Analytics Jupyter notebooks (read-only
reference at ../../../../FLAIR-GG-Analytics/content/FLAIR-GG/) into ComfyUI
nodes. See ../PLAN.md for the overall porting strategy.

Every one of the 9 real analytics notebooks starts with the same step: GET
the federated-query output from the LDP store by "secret key", then do one
outer json.loads(). What differs *inside* each provider's payload (JSON vs.
two different CSV conventions) is notebook-specific and is deliberately left
to the parser nodes (see parsers.py), not handled here.
"""

import json
import logging

import requests

DEFAULT_BASE_URL = "https://bgv.cbgp.upm.es/DAV/home/LDP/FLAIR/{key}"

# The notebooks all use this literal string as the unfilled-in placeholder
# (some use 8 X's, some use 9 -- both show up across the 9 notebooks).
_PLACEHOLDER_KEYS = {"XXXXXXXX", "XXXXXXXXX", ""}

# Sample data for FLAIR_ProviderDataFromText's default widget value -- same
# {provider_url: raw_CSV_string} shape a real secret-key lookup against the
# IUCN_categorization service returns, including one empty-payload provider
# (header only, zero rows) since that's a real case downstream nodes handle.
# Category values use the real GBIF vocabulary URI form confirmed against a
# live VP run (2026-08-05) -- see plots.py's category_order default, which
# matches these same three URIs, so the whole default sample workflow
# (this node's default -> parse -> dedupe -> plot's default) works
# together out of the box rather than needing every widget hand-edited
# just to try the chain once.
_SAMPLE_PROVIDER_DATA_JSON = """{
  "https://jbo.bgv.cbgp.upm.es/api-local/IUCN_categories": "plant_scientificName,IUCN_endangerment_category\\r\\nPapaver rhoeas,http://rs.gbif.org/vocabulary/iucn/threat_status/VU\\r\\nArabidopsis thaliana,http://rs.gbif.org/vocabulary/iucn/threat_status/EN\\r\\n",
  "https://jbclm.bgv.cbgp.upm.es/api-local/IUCN_categories": "plant_scientificName,IUCN_endangerment_category\\r\\nSilene vulgaris,http://rs.gbif.org/vocabulary/iucn/threat_status/CR\\r\\nPapaver rhoeas,http://rs.gbif.org/vocabulary/iucn/threat_status/VU\\r\\n",
  "https://urjc.bgv.cbgp.upm.es/api-local/IUCN_categories": "plant_scientificName,IUCN_endangerment_category\\r\\n"
}"""


class FLAIR_LoadBySecretKey:
    """
    Fetches a FLAIR-GG Virtual Platform federated-query result by its secret
    key and returns the outer-decoded {provider_url: raw_payload_string}
    dict. Mirrors every notebook's cell 2, minus the per-provider payload
    parsing (JSON vs. CSV), which is notebook-specific and belongs in a
    separate downstream node.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "key": (
                    "STRING",
                    {
                        "default": "",
                        "tooltip": "The secret key given to you by the FLAIR-GG Virtual Platform after a federated query completes.",
                    },
                ),
            },
            "optional": {
                "base_url_template": (
                    "STRING",
                    {
                        "default": DEFAULT_BASE_URL,
                        "tooltip": "URL template with a {key} placeholder. Only change this for testing against a different LDP store.",
                    },
                ),
                "timeout_seconds": (
                    "FLOAT",
                    {"default": 30.0, "min": 1.0, "max": 300.0, "step": 1.0},
                ),
            },
        }

    RETURN_TYPES = ("FLAIR_PROVIDER_DATA",)
    RETURN_NAMES = ("provider_data",)
    FUNCTION = "load"
    CATEGORY = "FLAIR/loaders"

    def load(self, key, base_url_template=DEFAULT_BASE_URL, timeout_seconds=30.0):
        # Defends against a real failure mode: pasting a key from another
        # UI easily carries a stray leading/trailing space along with it,
        # which silently turns into a different (nonexistent) URL rather
        # than an obvious error.
        key = key.strip()

        if key in _PLACEHOLDER_KEYS:
            raise ValueError(
                "No secret key provided -- fill in the 'key' field with the "
                "secret key from your FLAIR-GG Virtual Platform federated "
                "exploration output."
            )

        url = base_url_template.format(key=key)

        try:
            response = requests.get(url, timeout=timeout_seconds, verify=True)
        except requests.exceptions.RequestException as exc:
            raise RuntimeError(
                f"Could not reach the FLAIR-GG Virtual Platform at {url}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise ValueError(
                f"No data found for key '{key}' (HTTP 404 from {url}). "
                "The key may be wrong, expired, or the exploration hasn't "
                "finished writing its output yet."
            )
        if not response.ok:
            raise RuntimeError(
                f"FLAIR-GG Virtual Platform returned HTTP {response.status_code} "
                f"for key '{key}': {response.text[:500]}"
            )

        try:
            provider_data = json.loads(response.content)
        except json.JSONDecodeError as exc:
            raise RuntimeError(
                f"Response for key '{key}' was not valid JSON: {exc}"
            ) from exc

        if not isinstance(provider_data, dict):
            raise RuntimeError(
                f"Expected a {{provider: payload}} JSON object for key '{key}', "
                f"got {type(provider_data).__name__} instead."
            )

        logging.info(
            "[FLAIR_LoadBySecretKey] loaded %d provider(s) for key '%s'",
            len(provider_data),
            key,
        )

        return (provider_data,)


class FLAIR_ProviderDataFromText:
    """
    Alternative to FLAIR_LoadBySecretKey with no network call: parses
    pasted JSON in the same {provider_url: raw_payload_string} shape a real
    secret-key lookup returns. Useful for testing downstream nodes
    (parsers/transforms/plots) against known sample data without a live
    key, or for working with provider data that didn't come from a
    secret-key lookup at all -- e.g. copied in from somewhere else. The
    default widget value is a working sample against the IUCN_categorization
    schema, so dropping this node in already has something to run.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "json_text": (
                    "STRING",
                    {
                        "default": _SAMPLE_PROVIDER_DATA_JSON,
                        "multiline": True,
                        "tooltip": "A {provider_url: raw_payload_string} JSON object, same shape FLAIR_LoadBySecretKey returns.",
                    },
                ),
            },
        }

    RETURN_TYPES = ("FLAIR_PROVIDER_DATA",)
    RETURN_NAMES = ("provider_data",)
    FUNCTION = "load"
    CATEGORY = "FLAIR/loaders"

    def load(self, json_text):
        if not json_text or not json_text.strip():
            raise ValueError(
                "No JSON provided -- paste a {provider_url: raw_payload_string} "
                "JSON object into this node (see the default value for the "
                "expected shape)."
            )

        try:
            provider_data = json.loads(json_text)
        except json.JSONDecodeError as exc:
            raise ValueError(f"Not valid JSON: {exc}") from exc

        if not isinstance(provider_data, dict):
            raise ValueError(
                f"Expected a {{provider: payload}} JSON object, got "
                f"{type(provider_data).__name__} instead."
            )

        logging.info(
            "[FLAIR_ProviderDataFromText] loaded %d provider(s) from pasted text",
            len(provider_data),
        )

        return (provider_data,)


NODE_CLASS_MAPPINGS = {
    "FLAIR_LoadBySecretKey": FLAIR_LoadBySecretKey,
    "FLAIR_ProviderDataFromText": FLAIR_ProviderDataFromText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_LoadBySecretKey": "Load FLAIR-GG Data (by secret key)",
    "FLAIR_ProviderDataFromText": "Load FLAIR-GG Data (paste JSON)",
}
