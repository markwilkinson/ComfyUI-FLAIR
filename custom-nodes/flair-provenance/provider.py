"""
FLAIRProvenanceCacheProvider -- observes every node execution via ComfyUI's
own CacheProvider extension point, with no per-node wiring required. See
PLAN.md for the full design and what's built vs. not yet.
"""

import logging
import time

from comfy_execution.cache_provider import CacheProvider, register_cache_provider

_logger = logging.getLogger(__name__)


def _safe_output_summary(value):
    """
    A short, safe-to-log/display description of a node output value --
    never the full value itself (could be a large tensor/DataFrame), never
    raises (some objects' __repr__ can itself fail).

    ComfyUI wraps each output slot's value in its own list (its
    per-output-slot batch representation), so unwrap a single-item list
    before describing it -- otherwise every summary just reads
    "list(len=1)" regardless of what the node actually produced.
    """
    if isinstance(value, list) and len(value) == 1:
        value = value[0]

    try:
        type_name = type(value).__name__
        if hasattr(value, "shape"):
            return f"{type_name}(shape={tuple(value.shape)})"
        if hasattr(value, "__len__"):
            return f"{type_name}(len={len(value)})"
        return f"{type_name}: {str(value)[:100]}"
    except Exception as exc:
        return f"<unrepresentable output: {exc}>"


class FLAIRProvenanceCacheProvider(CacheProvider):
    """
    Pure observer, not a real external cache: on_lookup always returns None
    (never serves a fake cached value, never short-circuits real
    execution). Records one entry per on_store call -- which the core
    executor calls after every node's execution, own or not, stock or
    third-party or ours, unconditionally. See PLAN.md for what this does
    and doesn't capture (real outputs + an input hash; not literal input
    values -- that's part 2, not yet built).

    Assumes ComfyUI executes one prompt at a time (true as of this writing
    -- single execution queue), so a plain instance dict keyed by prompt_id
    is a safe store without thread-locals/contextvars. Revisit if ComfyUI
    ever adds concurrent prompt execution.
    """

    def __init__(self):
        self.store = {}
        self.current_prompt_id = None
        # Retained across the sweep in on_prompt_start, instead of being
        # discarded after just logging a count -- lets FLAIR_ShowProvenanceLog
        # (see nodes/inspection.py) show a *complete* run's records, which
        # the still-in-progress current prompt can't reliably promise (see
        # PLAN.md's ordering caveat).
        self.last_completed_prompt_id = None
        self.last_completed_records = []

    def on_prompt_start(self, prompt_id):
        # Sweep the PREVIOUS prompt's entry now, one generation late, rather
        # than in its own on_prompt_end (see on_prompt_end for why: on_store
        # is dispatched by the core executor as a fire-and-forget
        # asyncio.create_task with no ordering guarantee against
        # on_prompt_end -- confirmed empirically, every on_store call for a
        # 5-node test prompt arrived AFTER that prompt's on_prompt_end had
        # already fired and logged 0 records). By the time a genuinely new
        # prompt starts, the previous prompt's stragglers have had a full
        # prompt's worth of time to land -- safe under the single-execution-
        # queue assumption already noted on this class.
        if self.current_prompt_id is not None and self.current_prompt_id != prompt_id:
            stale = self.store.pop(self.current_prompt_id, [])
            self.last_completed_prompt_id = self.current_prompt_id
            self.last_completed_records = stale
            _logger.info(
                "[FLAIR provenance] prompt %s: final tally %d node execution(s) recorded",
                self.current_prompt_id,
                len(stale),
            )

        self.current_prompt_id = prompt_id
        self.store.setdefault(prompt_id, [])
        _logger.info("[FLAIR provenance] prompt %s started", prompt_id)

    def on_prompt_end(self, prompt_id):
        # Deliberately does NOT clear self.store[prompt_id] or reset
        # current_prompt_id -- on_store calls for this same prompt can and
        # do arrive after this fires. This count is a snapshot, not final;
        # see on_prompt_start for where the real cleanup (and final tally
        # log) happens.
        _logger.info(
            "[FLAIR provenance] prompt %s ended, %d node execution(s) recorded so far "
            "(more may still arrive -- see on_prompt_start's final tally log)",
            prompt_id,
            len(self.store.get(prompt_id, [])),
        )

    async def on_lookup(self, context):
        return None

    async def on_store(self, context, value):
        prompt_id = self.current_prompt_id
        if prompt_id is None:
            # Shouldn't happen (on_prompt_start always precedes node
            # execution) -- but provenance capture failing must never take
            # the actual workflow down with it.
            _logger.warning(
                "[FLAIR provenance] on_store fired for node %s with no "
                "current prompt_id -- dropping this record",
                context.node_id,
            )
            return

        record = {
            "node_id": context.node_id,
            "class_type": context.class_type,
            "input_hash": context.cache_key_hash,
            "outputs": [_safe_output_summary(o) for o in value.outputs],
            "timestamp": time.time(),
        }
        self.store.setdefault(prompt_id, []).append(record)
        _logger.info(
            "[FLAIR provenance] recorded %s (node %s) for prompt %s: outputs=%s",
            context.class_type,
            context.node_id,
            prompt_id,
            record["outputs"],
        )


# Singleton instance, registered once when this package loads. Nodes (see
# nodes/inspection.py) and the future packaging node import this same
# instance directly to read its store -- no ComfyUI hidden input needed for
# that, everything lives in the same process.
provider = FLAIRProvenanceCacheProvider()
register_cache_provider(provider)
