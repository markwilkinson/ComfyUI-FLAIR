# How to create a new FLAIR ComfyUI node

Written for two audiences at once: a human contributor, and a fresh Claude
(or other AI assistant) session picking this project up cold. If you're an
AI assistant reading this because someone pointed you at it: everything
below reflects things actually verified against the real running system
this session, not assumptions — where something is a genuine gotcha, it's
because it bit us for real and got fixed. Don't skip the "Testing" section
just because the code looks obviously correct; several bugs in this
project's history looked obviously correct too.

## Where things live

```text
custom-nodes/
    flair_declutter/       # infrastructure: hides SD nodes, no graph nodes of its own
    flair-analytics/         # FLAIR-GG-Analytics notebook ports
        PLAN.md                 # what's built, what's not, why -- read this first
        nodes/
            loaders.py            # network I/O in, produces FLAIR_PROVIDER_DATA
            parsers.py              # payload parsing, produces DATAFRAME
            transforms.py             # DATAFRAME -> DATAFRAME cleanup
            plots.py                   # DATAFRAME -> IMAGE via matplotlib
    flair-provenance/        # automatic provenance capture + RO-Crate export
        PLAN.md
        provider.py             # the CacheProvider hook (not a node)
        nodes/
            inspection.py          # view captured provenance
            packaging.py             # RO-Crate export node
    useless_text/           # throwaway demo, simplest possible reference example
```

Each package follows the same shape: a top-level `__init__.py` that imports
a `nodes/` subpackage, `nodes/__init__.py` merges every submodule's
`NODE_CLASS_MAPPINGS` via a `_SUBMODULES` tuple, and each `nodes/*.py` file
groups a handful of related node classes with its own
`NODE_CLASS_MAPPINGS`/`NODE_DISPLAY_NAME_MAPPINGS` at the bottom.

**Adding a new node to an existing category** (e.g. another loader): add
the class to the relevant `nodes/*.py` file, add it to that file's
`NODE_CLASS_MAPPINGS`/`NODE_DISPLAY_NAME_MAPPINGS` dicts.

**Adding a new category** (e.g. a `coordinates.py` for geospatial nodes):
new file under `nodes/`, own `NODE_CLASS_MAPPINGS`, then register the
module in that package's `nodes/__init__.py` `_SUBMODULES` tuple. Nothing
else needs to know about it.

**A whole new package** (a new top-level concern, not a new category of an
existing one): copy the `nodes/` pattern from `flair-analytics` or
`flair-provenance`, not `flair_declutter` (which is intentionally a
single-file infrastructure package with zero graph nodes — not a template
for a package that will have nodes).

## Anatomy of a node

```python
class FLAIR_SomeThing:
    """Docstring: what it does, and WHY any non-obvious choice was made."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "data": ("DATAFRAME",),
            },
            "optional": {
                "some_option": ("STRING", {"default": "", "tooltip": "..."}),
            },
        }

    RETURN_TYPES = ("DATAFRAME",)
    RETURN_NAMES = ("cleaned_data",)
    FUNCTION = "run"
    CATEGORY = "FLAIR/whatever"

    def run(self, data, some_option=""):
        ...
        return (result,)


NODE_CLASS_MAPPINGS = {"FLAIR_SomeThing": FLAIR_SomeThing}
NODE_DISPLAY_NAME_MAPPINGS = {"FLAIR_SomeThing": "Human-Readable Name"}
```

Non-negotiable conventions, established across every node in this project:

- **`NODE_CLASS_MAPPINGS` key gets a `FLAIR_` prefix.** This is the
  permanent on-disk identity saved into every workflow JSON that uses the
  node — rename it later and old saved workflows break. Pick the name
  right the first time.
- **Set `DESCRIPTION` (a class attribute, one or two sentences).** This is
  ComfyUI's own convention, not something this project invented — it shows
  up as a UI tooltip when hovering the node (stock nodes like
  `CLIPTextEncode` already use it, and it appears in `/object_info`). It's
  also read directly by `flair-provenance/nodes/packaging.py` into each
  node's `SoftwareApplication` entity in the RO-Crate — a node with only a
  docstring and no `DESCRIPTION` will have no description in the captured
  provenance at all. Don't just restate the class name; say what it
  actually does, matching the level of detail in this project's existing
  nodes' `DESCRIPTION`s.
- **`CATEGORY` must start with `"FLAIR"`** (e.g. `"FLAIR/loaders"`,
  `"FLAIR/plots"`). `flair_declutter`'s allowlist (see
  `custom-nodes/flair_declutter/__init__.py`) hides any node whose category
  doesn't match one of a small set of prefixes, and `"FLAIR"` is reserved
  specifically for nodes this project authors. A node with a different
  category prefix will silently vanish from the picker — this exact bug
  happened to `useless_text` early in this project (category was
  `"useless/text"`, not covered by the allowlist) and needed a real fix,
  not just a config tweak.
- **Fail loud on ambiguous input, never silently guess.** Every node in
  this project raises a clear `ValueError`/`RuntimeError` with an
  actionable message (what was expected, what was actually found, often
  listing real available options) rather than producing a plausible-looking
  wrong answer. See `FLAIR_DeduplicateRows`'s bad-column-name error or
  `FLAIR_PlotCategoryCounts`'s `category_order` validation for the pattern
  to copy.
- **Custom socket types are just string literals — no registration
  needed.** `"FLAIR_PROVIDER_DATA"`, `"DATAFRAME"` aren't declared
  anywhere; a producer node's `RETURN_TYPES` and a consumer node's
  `INPUT_TYPES` just need to use the identical string. ComfyUI passes the
  real Python object between them in-process, unserialized — a `DATAFRAME`
  output is a real `pandas.DataFrame`, not a wrapper.
- **`"*"` (equivalently `comfy.comfy_types.node_typing.IO.ANY`) accepts any
  type** — used by `FLAIR_PackageProvenanceCrate`'s `final_output` input
  when the node genuinely needs to take whatever the workflow's terminal
  output happens to be.

## The dependency gotcha (this will bite you if you skip it)

**Assume a new node's imports need adding somewhere — don't assume they're
already available.** `requests` happened to already be a ComfyUI
dependency; `pandas`, `matplotlib`, and `seaborn` were not, and each one
broke the Docker image the first time a node importing it got deployed,
because `custom_nodes/` is bind-mounted at runtime (see
`docker/docker-compose.yml`), not baked into the image — the Dockerfile has
no way to discover a new Python import automatically the way it picks up
new node *code* for free.

Whenever a new node imports something beyond the Python standard library:

1. `venv/bin/pip install <package>` in the local dev venv, so you can test
   at all.
2. Add it to `docker/Dockerfile`'s "FLAIR node dependencies" `pip install`
   step.
3. `docker compose build` (not just `restart` — this one genuinely needs a
   rebuild, unlike almost every other change in this project).

## Testing: direct calls vs. the real queue

Two different levels of "does this work," and they catch different bugs:

**Direct method calls** (fast, good for basic logic):

```python
import sys
sys.argv = ['main.py', '--cpu']
import comfy.options
comfy.options.enable_args_parsing()
import asyncio, nodes

async def main():
    await nodes.init_extra_nodes()
    node = nodes.NODE_CLASS_MAPPINGS['FLAIR_YourNode']()
    result = node.your_function(...)  # or `await` if FUNCTION is async
    print(result)

asyncio.run(main())
```

This is enough for most logic bugs, error-message wording, edge cases like
empty/malformed input. It is **not** enough for anything that depends on
ComfyUI's actual execution machinery:

- **`flair-provenance`'s `CacheProvider` hooks** (`on_store`, etc.) only
  fire inside the real caching layer (`comfy_execution/caching.py`) — a
  direct method call never touches it. To test provenance capture, you
  have to submit a real prompt.
- **`INPUT_IS_LIST = True`** behavior (every input arrives wrapped in a
  list, including plain widgets) is an executor-level convention, not
  something a direct call reproduces on its own — you have to actually
  pass list-shaped arguments yourself to simulate it, or better, test
  through the real queue.
- **`async def` node functions** — confirmed ComfyUI's executor genuinely
  supports them (`inspect.iscoroutinefunction` is checked in
  `execution.py`), but the only way to be sure a node's async behavior
  (e.g. `await asyncio.sleep(0)` to yield to the event loop) actually does
  what you think is to run it for real.

**Through the real queue** (slower, catches the above):

```bash
# from the ComfyUI directory
venv/bin/python main.py --cpu --listen 127.0.0.1 --port 8189 &
```

then POST a real API-format prompt JSON to `http://127.0.0.1:8189/prompt`
and read back `http://127.0.0.1:8189/history/<prompt_id>`. See any commit
in this project's git history touching `flair-provenance` for worked
examples — the packaging node especially, since its whole
async-ordering-mitigation behavior was verified exactly this way (submit
two prompts back to back, confirm the first one's provenance record is
complete once the second one starts).

**When something needs real network access** (the FLAIR-GG VP, a live
secret key), `FLAIR_ProviderDataFromText` (in `flair-analytics/nodes/loaders.py`)
exists specifically so downstream nodes can be tested against realistic
sample data with zero network dependency — its default widget value is a
working example against the real schema. Look at how it's used before
reaching for a live key.

Once a node works in the venv, **verify it in Docker too** before calling
it done — `docker compose restart` (no dependency change) or
`docker compose build && docker compose up -d` (new dependency), then
repeat the queue-based test against `127.0.0.1:8188`. Several bugs in this
project only showed up in one environment and not the other (the non-root
user file-permission fix, for one).

## Provenance: usually nothing extra to do

Every node's execution is captured automatically by
`flair-provenance`'s `CacheProvider` hook — no per-node opt-in, no base
class to inherit, no wiring. This applies to stock ComfyUI nodes and
third-party packs too, not just FLAIR's own. See
`custom-nodes/flair-provenance/PLAN.md` for exactly what is and isn't
captured yet (currently: real outputs and an input *hash*, not yet literal
input values — that's tracked as "part 2," not built at time of writing).

## Documentation and versioning (do this every session, not just when asked)

- Each package's `PLAN.md` is the source of truth for that package's
  design decisions and status — update it when you build or change
  something, in the same level of concrete, verified detail as the
  existing entries (what was tried, what broke, how it was actually
  confirmed working — not just "implemented X").
- Bump `VERSION` (semantic versioning) and add a dated entry to
  `CHANGELOG.md` (Keep a Changelog format: `Added`/`Changed`/`Fixed`
  sections) at the end of any session that changed code — this is a
  standing project convention, not something that needs to be asked for
  each time.
