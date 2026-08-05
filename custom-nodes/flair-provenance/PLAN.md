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

## `FLAIR_ShowProvenanceLog`: built and verified, status DONE

User-requested: "is there any way to view what is currently being
captured?" Lives in `nodes/inspection.py`. Reads `provider.store` (and the
new `provider.last_completed_prompt_id`/`last_completed_records`, added to
`provider.py` specifically to support this -- previously a sweep just
logged a count and discarded the actual records, so there was nothing
retained to show) and formats it as indented JSON for display via a stock
`PreviewAny`/`Show Text` node.

Has no required inputs by design: it reads global process state, not
anything computed from a particular upstream node, so ComfyUI's dependency
scheduler has nothing to order it against. Documented directly in the
node's docstring/tooltip rather than treated as a hidden gotcha: to inspect
a specific run, run that workflow first, then queue this node separately
afterward. Defaults to `which="last_completed"` over `"current"` because a
still-in-progress prompt's records aren't guaranteed complete yet (same
async-ordering reason as above) -- `"last_completed"` only becomes
available once the *next* prompt has started, by which point the previous
one's stragglers have landed.

Also fixed while building this: `_safe_output_summary()` was unwrapping
ComfyUI's per-output-slot batch-list incorrectly, so every summary read the
unhelpful `"list(len=1)"` regardless of the real value inside. Now unwraps
single-item lists first, giving genuinely useful summaries (`"dict(len=2)"`,
`"DataFrame(shape=(2, 4))"`, `"Tensor(shape=(1, 553, 850, 3))"`).

Verified end-to-end: ran a real 5-node chain as one prompt, then a second,
separate prompt containing just `FLAIR_ShowProvenanceLog` → `PreviewAny`,
and confirmed it correctly displayed all 5 records from the first prompt.

## `FLAIR_PackageProvenanceCrate`: built and verified, status DONE (v1 scope)

Lives in `nodes/packaging.py`. Wired to the workflow's actual terminal
output(s) as a genuine data input (`final_output`, type `"*"`/`IO.ANY`) --
gets correct execution ordering for free from ComfyUI's own dependency
scheduler, exactly per the original design. Writes a real
`ro-crate-metadata.json` (JSON-LD, `RO-Crate 1.1` + Workflow Run Crate +
Provenance Run Crate `conformsTo`), the content-hashed artifact(s), zips
the whole thing into a single file under `output/`, and returns a working
`/view?filename=...&type=output` download URL.

**Multi-terminal-output: actually implemented, not just resolved at the
design level.** The user pointed out their real workflow has multiple image
outputs, surfacing this as a live blocker, not a hypothetical. Fix:
`INPUT_IS_LIST = True` on the node -- pair with the stock `Create List`
node upstream (bundle several same-typed outputs into one list there,
wire that into `final_output`), and because `INPUT_IS_LIST` wraps *every*
input in a list uniformly, a single directly-wired output arrives as a
length-1 list too -- one code path handles both cases, not two. Verified
directly (bypassing the graph, since `Create List` uses ComfyUI's newer
"Autogrow" UI mechanism which doesn't have fixed input key names to
construct via raw API JSON): two images in, `final_output_0.png` +
`final_output_1.png` in the crate, both listed correctly in `hasPart`.

**Downloadability: solved via ComfyUI's existing `/view` endpoint, not new
server code.** The user asked how an end user would ever get this file off
a web-hosted server's filesystem, and floated using the VP as a proxy over
a shared filesystem. Checked `server.py` directly rather than assuming:
`/view?filename=X&type=output` already serves *any* file type generically
(mimetype-guessed, `application/octet-stream` fallback, proper
`Content-Disposition`) when requested without `preview`/`channel=rgb` --
not just images. So zipping the crate into one file under `output/` and
returning that URL gets a real, working download for free. Verified with a
plain `curl` GET: `HTTP 200`, `Content-Type: application/zip`, correct
bytes. No shared filesystem with the VP needed.

**Retention, not delete-after-download: built and verified, status DONE.**
User request: "I don't want to store people's results on my server."
First plan was a real delete-after-download route -- the stock `/view`
endpoint has no such behavior and patching ComfyUI core is off the table,
so this would've meant FLAIR's own aiohttp route, with a real wrinkle:
`PromptServer.instance` (confirmed directly in `server.py`/`main.py`) isn't
set until well after custom nodes finish loading, same reason
`nodes_replacements.py` warns "PromptServer has no attribute instance" at
import time in every session's logs this whole project -- so registering a
route at package-import time like `register_cache_provider()` wouldn't
work, and it would've needed deferred registration instead.

The user then proposed something simpler before that got built: sweep
(delete) any crate older than a week, triggered each time a new one is
written, rather than trying to detect a completed download. **"Basically
solves the problem"** without the route/deferred-registration complexity,
and doesn't depend on the download actually happening (a route-based
approach wouldn't clean up a crate nobody ever downloaded). Implemented as
`_sweep_old_crates()` in `packaging.py`, scoped specifically to a new
`output/flair_crates/` subfolder (crates moved out of bare `output/` for
this reason) -- the sweep only ever touches `*.zip` files in that one
directory, never the wider `output/` tree, so a bug in it can't delete
something unrelated a user saved. Verified directly: pre-created a fake
8-day-old zip, ran the packaging node, confirmed the old one was deleted
and the new one survived.

**The async-ordering risk flagged when this was still just a design note
turned out to be addressable, not just a caveat to document.** This node's
`FUNCTION` is `async def` and yields to the event loop
(`await asyncio.sleep(0)`) a few times before reading
`provider.store[provider.current_prompt_id]` -- confirmed ComfyUI's
executor genuinely supports async node functions (`inspect.iscoroutinefunction`
is checked in `execution.py`, including the case where the coroutine
doesn't resolve immediately), so this isn't a hack. Verified against a real
4-node upstream chain: all 4 sibling records landed correctly in the crate,
not just some -- the mitigation works in practice, not just in theory. Still
not a hard guarantee (hence still "v1 scope," not "solved") -- part 2's
synchronous base-class/decorator remains the fully reliable path once built.

**What v1 does and doesn't do**, deliberately not the full spec in one
shot: one `CreateAction` per captured node execution, one
`SoftwareApplication` per distinct node class as `instrument`, real
`endTime` (ISO 8601), and the actual terminal artifact as a content-hashed
`File` entity. Not yet built: real `FormalParameter` bindings from
`INPUT_TYPES`/`RETURN_TYPES` (inputs are still just a hash, not literal
values -- same limitation as part 1, unresolved until part 2 exists),
native PROV-O/NanoPub storage (this writes RO-Crate JSON-LD directly, not
as a derived export from an RDF layer -- see Format decision above).

**A real bug found and fixed while building this:** the internal record's
`timestamp` field was a raw `time.time()` float, not ISO 8601 -- caught by
the user asking "is that a Crate standard?" before it shipped anywhere.
Fixed at the source in `provider.py` (stored as ISO 8601 directly, once,
rather than converted separately by every consumer), so `FLAIR_ShowProvenanceLog`
and the crate's `endTime` are both correct now, not just the crate.

## Package layout

```text
custom-nodes/flair-provenance/
    __init__.py          # imports provider.py (registration side effect)
                          # + nodes/ (NODE_CLASS_MAPPINGS)
    provider.py            # FLAIRProvenanceCacheProvider + singleton
    nodes/
        __init__.py          # merges submodules -- register new ones in
                              # _SUBMODULES here, nothing else needed
        inspection.py          # FLAIR_ShowProvenanceLog
        packaging.py            # FLAIR_PackageProvenanceCrate
```

## Status

- [x] `FLAIRProvenanceCacheProvider` registered, observes every node
      execution via `on_store`, verified live against a real queued prompt
      (see the bug/fix above for what "verified" actually required).
- [x] `FLAIR_ShowProvenanceLog` -- view captured records without digging
      through logs.
- [x] Packaging node -- `FLAIR_PackageProvenanceCrate`, v1 scope (see
      above for exactly what that does and doesn't cover yet).
- [x] Multi-terminal-output support (`INPUT_IS_LIST = True` +
      stock `Create List`) -- implemented and verified, not just designed.
- [x] Downloadable as a single zip via ComfyUI's existing `/view` endpoint
      -- no new server code needed for this part.
- [x] Crates older than a week are swept on every new write (explicit user
      request -- don't retain people's results on the server indefinitely).
      Simpler alternative to a real delete-after-download route, chosen by
      the user once the route's deferred-registration complexity was
      explained -- see the section above.
- [x] `FLAIR_PUBLIC_URL` env var (set in `docker-compose.yml`, not
      user-facing) turns `crate_url` into a fully-qualified,
      copy-paste-anywhere URL instead of a relative path end users would
      have to manually combine with the hostname.
- [x] Node descriptions in the crate (Alberto's request): every FLAIR
      node now carries a `DESCRIPTION` class attribute -- ComfyUI's own
      convention (shown as a UI tooltip too, confirmed via `/object_info`,
      not something FLAIR invented), read into each `SoftwareApplication`
      entity's `description` field. Verified in a real crate's
      `ro-crate-metadata.json`. See
      `custom-nodes/HOW_TO_CREATE_NODES.md` for the convention going
      forward -- every new node should set `DESCRIPTION`, not just a
      docstring, or it won't show up in the crate.
- [x] Node code identity in the crate ("which version of a node produced
      this output" -- explicit follow-up question once descriptions
      landed). Two fields on each `SoftwareApplication`: `softwareVersion`
      (the repo-wide `VERSION` file, mounted read-only from
      `docker-compose.yml`) and a non-standard `flair:sourceCodeSha256`
      (SHA-256 of that node class's actual Python source via
      `inspect.getsource`). The version alone was explicitly rejected as
      insufficient -- "if the GUID of a node is the same after
      modification, then I am not happy" -- because it only changes if a
      human remembers to bump it. The source hash is correct by
      construction instead: mechanically guaranteed to differ if and only
      if the node's code differs, no bump discipline required from anyone.
      Verified directly, not just argued: made a one-line comment edit to
      a node with `VERSION` deliberately left unchanged, reran, confirmed
      `softwareVersion` stayed identical while `sourceCodeSha256` changed.
- [ ] Base-class/decorator for literal-input capture on FLAIR-owned nodes
      -- now also the path to real `FormalParameter` bindings in the crate,
      not just literal inputs in the log.
- [ ] Cache-hit provenance behavior (does a cache hit still emit a record?
      Decided in the original design discussion: yes, provenance purists
      would say so -- but `on_store` as currently used only fires on a
      *fresh* execution+store, not a cache hit served from `on_lookup`.
      Needs a decision on whether `on_lookup` returning a hit should also
      emit a "not re-executed, served from cache" record.)
- [ ] rdflib (+ JSON-LD library) integration for real PROV-O/NanoPub
      emission, replacing the current plain-dict records.
