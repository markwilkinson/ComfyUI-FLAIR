# Plan: FAIR/PROV-O provenance capture

Goal (the actual point of this whole project, per `handoff.md`/
`handoff2_galaxy_cwl.md` -- local-only design notes, gitignored, not in this
repo): every workflow run should automatically produce a per-step
provenance record -- what ran, with what inputs, producing what outputs --
without the workflow author wiring anything for it, ultimately exported as
a Workflow Run RO-Crate (Provenance Run Crate tier).

## Rejected approach

A capture *node* placed in the graph. It only sees whatever's wired
directly into it, so every other node's data contract would need a
synthetic "provenance" pin threaded through it just to reach the collector.
Invasive, and silently incomplete if anyone forgets a wire.

## Adopted approach, part 1 (built) -- observe via ComfyUI's own CacheProvider hook

Discovered by reading ComfyUI's actual execution internals (not assumed):
`comfy_execution/cache_provider.py` defines a public `CacheProvider`
interface (source of truth: `comfy_api/latest/_caching.py`) with a real
registration function, `register_cache_provider()`. The core executor
(`comfy_execution/caching.py`) calls every registered provider's:

- `on_prompt_start(prompt_id)` -- once, before any node in that queued run
  executes
- `on_store(context, value)` -- **after every single node's execution,
  own or not, stock or third-party or ours, unconditionally** (dispatched
  from `BasicCache._notify_providers_store`, called from `_set_immediate`,
  which every node execution path goes through). `context` carries
  `node_id`, `class_type`, and `cache_key_hash` (a SHA256 hash of that
  node's resolved inputs -- not the literal input values). `value` carries
  the node's *actual real output values* (`value.outputs`, a list).
- `on_lookup(context) -> Optional[CacheValue]` -- called before a node
  would execute, to check an external cache. We always return `None`
  (never serve a fake cached value) -- we are a pure observer, not a real
  cache, and must never short-circuit real execution.
- `on_prompt_end(prompt_id)` -- once, after the run finishes.

This means: **the "escape hatch for nodes we don't own" problem from the
original design is mostly solved for free.** No manual opaque-passthrough
node needed (that would have had the same "someone has to remember to add
it" flaw as the rejected capture-node idea) -- `on_store` fires
automatically, unconditionally, for every node ComfyUI runs. The
honest trade-off: for a node we don't own, we get node identity + real
outputs + an input *fingerprint* (hash), not literal input values. For
nodes we own (part 2, not yet built), we additionally capture literal
inputs via our own base-class/decorator on `FUNCTION`.

**Implementation: `FLAIRProvenanceCacheProvider`**, in this package's
`__init__.py`, registered once at module-load time via
`register_cache_provider()`. Since ComfyUI runs a single execution queue
(confirmed earlier in the FLAIR-GG-Analytics porting work), a plain
instance dict keyed by `prompt_id` is safe as the store -- no
thread-locals/`contextvars` needed *unless* ComfyUI ever adds concurrent
execution, worth a comment flagging that assumption.

`on_prompt_end` is the natural place to hand the accumulated records off
(to a future packaging node, or for now just log a summary) and clear that
`prompt_id`'s entry -- this is a long-running server across many separate
executions, the store needs a lifecycle, not an unbounded accumulate-forever
dict.

## Adopted approach, part 2 (not yet built)

A shared base class or `FUNCTION`-wrapping decorator applied to FLAIR node
classes we author (`FLAIR_LoadBySecretKey`, etc.), capturing literal input
values (which `on_store` alone can't give us) alongside a PROV-O-shaped
record. Fires automatically on every execution of an instrumented node,
same "no wiring, no gap" property as part 1, additive to it rather than a
replacement.

## Open question for the future packaging node (not yet built)

A real graph node, wired to the workflow's actual terminal output(s) as
genuine data inputs (not synthetic provenance pins) -- gets correct
execution ordering for free from ComfyUI's own dependency scheduler, since
it only runs after everything it depends on is done. It needs to read "the
accumulated records for *this* run" from `FLAIRProvenanceCacheProvider`'s
store -- but a node's `FUNCTION` doesn't receive `prompt_id` as a hidden
input (only `UNIQUE_ID`/`PROMPT`/`EXTRA_PNGINFO`/`DYNPROMPT` are exposed
that way, confirmed by reading `execution.py`). Resolution: the packaging
node's module can simply import the same provider *singleton instance*
this package already creates and registers, and read
`provider.store.get(provider.current_prompt_id, [])` directly -- everything
lives in the same process, so no ComfyUI-provided hidden input is actually
needed for this.

## Format decision (unchanged from the original design)

Canonical per-step record stays PROV-O/NanoPub-shaped (richer, consistent
with the existing FDP/nanopub infrastructure elsewhere). RO-Crate JSON-LD
(`CreateAction`/`FormalParameter`) gets generated as a *derived export* at
packaging time, not the native representation. Not yet built -- current
records are a lightweight Python dict, not yet RDF.

## A real bug found and fixed while verifying this against the live queue

Empirically, `on_store` calls for a prompt's nodes arrived **after that
prompt's own `on_prompt_end` had already fired** (confirmed: `caching.py`
dispatches `on_store` via `asyncio.create_task` into a
`_pending_store_tasks` set that is tracked, via a done-callback, but never
awaited anywhere in the codebase -- so there is no ordering guarantee
between "a node's output got stored" and "the executor considers the whole
prompt finished"). A first version that cleared `current_prompt_id`/the
store in `on_prompt_end` lost every record -- 0 recorded despite 5 nodes
having actually run.

**Fix:** don't clear anything in `on_prompt_end` (log a same-time "so far"
count only, explicitly not final). Do the real cleanup -- and log the real
final tally -- lazily in the *next* `on_prompt_start`, sweeping the
previous prompt's entry only once a new, different prompt begins. Verified
by submitting two prompts back to back: prompt 1 correctly ends up with all
5 records (including the stock `PreviewImage` node, proving the
"nodes we don't own" universal-coverage claim empirically, not just in
theory), tallied once prompt 2 starts.

This also flags a real open risk for the future packaging node (see below):
even reading the store *during* the packaging node's own synchronous
`FUNCTION` call isn't guaranteed to see every immediately-prior sibling
node's record yet, for the same fire-and-forget reason. Worth designing
around directly rather than assuming it away -- one likely mitigation:
part 2's base-class/decorator (synchronous, not dispatched as a background
task) becomes the reliable path for anything the packaging node itself
needs to depend on having, with the `CacheProvider` observer staying the
best-effort fallback for non-owned nodes specifically.

## Status

- [x] `FLAIRProvenanceCacheProvider` registered, observes every node
      execution via `on_store`, verified live against a real queued prompt
      (see the bug/fix above for what "verified" actually required).
- [ ] Base-class/decorator for literal-input capture on FLAIR-owned nodes.
- [ ] Packaging node (accumulator -> PROV-O -> RO-Crate JSON-LD ->
      `ro-crate-metadata.json` + `File`/`hasPart` entities).
- [ ] Cache-hit provenance behavior (does a cache hit still emit a record?
      Decided in the original design discussion: yes, provenance purists
      would say so -- but `on_store` as currently used only fires on a
      *fresh* execution+store, not a cache hit served from `on_lookup`.
      Needs a decision on whether `on_lookup` returning a hit should also
      emit a "not re-executed, served from cache" record.)
- [ ] rdflib (+ JSON-LD library) integration for real PROV-O/NanoPub
      emission, replacing the current plain-dict records.
