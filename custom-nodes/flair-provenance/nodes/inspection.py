"""
Nodes for inspecting what FLAIRProvenanceCacheProvider has captured. See
../PLAN.md.
"""

import json

from ..provider import provider


class FLAIR_ShowProvenanceLog:
    """
    Formats the provenance records FLAIRProvenanceCacheProvider has
    captured as readable JSON text -- wire the output into a stock
    PreviewAny/Show Text node to view it on the canvas.

    Has no required inputs: this node reads global process state (the
    provider's store), not anything computed from a particular upstream
    node, so ComfyUI's dependency scheduler has nothing to order it
    against. That means it can run at any point relative to the workflow
    you're trying to inspect -- if you want to see a specific run's
    records, run that workflow first, then queue this node by itself
    afterward, rather than relying on it sitting in the same graph.

    "last_completed" (the default) is more reliable than "current": due to
    an async ordering quirk in ComfyUI's executor (see PLAN.md), a
    still-in-progress prompt's records aren't guaranteed complete yet, but
    a prompt only becomes "last_completed" after the *next* prompt starts,
    by which point its stragglers have had a full generation to land.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "which": (
                    ["last_completed", "current", "both"],
                    {"default": "last_completed"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("provenance_log",)
    FUNCTION = "show"
    CATEGORY = "FLAIR/provenance"
    DESCRIPTION = (
        "Shows FLAIRProvenanceCacheProvider's captured records as readable "
        "JSON -- view provenance without digging through container logs. "
        "No required inputs (reads global process state); run the "
        "workflow you want to inspect first, then queue this separately."
    )

    def show(self, which):
        sections = []

        if which in ("last_completed", "both"):
            sections.append(
                self._format_section(
                    "Last completed prompt",
                    provider.last_completed_prompt_id,
                    provider.last_completed_records,
                )
            )

        if which in ("current", "both"):
            sections.append(
                self._format_section(
                    "Current prompt (may be incomplete -- see docstring)",
                    provider.current_prompt_id,
                    provider.store.get(provider.current_prompt_id, [])
                    if provider.current_prompt_id
                    else [],
                )
            )

        return ("\n\n".join(sections),)

    @staticmethod
    def _format_section(label, prompt_id, records):
        if prompt_id is None:
            return f"=== {label} ===\n(none yet)"
        return (
            f"=== {label}: {prompt_id} ({len(records)} node execution(s)) ===\n"
            + json.dumps(records, indent=2, default=str)
        )


NODE_CLASS_MAPPINGS = {
    "FLAIR_ShowProvenanceLog": FLAIR_ShowProvenanceLog,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_ShowProvenanceLog": "Show FLAIR Provenance Log",
}
