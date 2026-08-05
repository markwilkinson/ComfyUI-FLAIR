"""
FLAIR provenance capture -- observes every node execution via ComfyUI's
own CacheProvider extension point, with no per-node wiring required. See
PLAN.md for the full design and what's built vs. not yet.

Importing this package has a real side effect: provider.py registers
FLAIRProvenanceCacheProvider with ComfyUI's core executor at import time.
The nodes/ subpackage (currently just FLAIR_ShowProvenanceLog) is for
inspecting what that provider has captured, not for capturing it -- that
part needs no node at all, by design (see PLAN.md's "rejected approach").
"""

from . import provider  # noqa: F401 -- import side effect: registers the provider
from .nodes import NODE_CLASS_MAPPINGS, NODE_DISPLAY_NAME_MAPPINGS

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
