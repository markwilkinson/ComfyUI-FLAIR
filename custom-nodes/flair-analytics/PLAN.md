# Plan: porting FLAIR-GG-Analytics notebooks into ComfyUI nodes

Source material: `/home/osboxes/CODE/FLAIR-GG-Analytics/content/FLAIR-GG/` (9 real
analytics notebooks). That folder is reference-only — nothing in it gets
changed as part of this work.

## Correction to the starting assumption: it's not actually multi-language

All 9 real notebooks declare a **Python** kernel (`pyodide`, i.e. Python
compiled to WebAssembly and run *in the browser* via JupyterLite — there is
no server-side Jupyter kernel at all here). There is no R kernel (`IRkernel`),
no Ruby kernel, and no `.rb`/`.R` file anywhere in the repository. `git log`
and `requirements.txt` confirm only Python, JavaScript, and P5 kernels were
ever configured for this JupyterLite deployment.

What *is* true, and probably what prompted the "mix of languages" impression:
two notebooks (`vpbeacon2_individuals.ipynb`, `vpbeacon2_individuals_4.ipynb`)
contain a stray Ruby idiom inside a nominally-Python cell:

```python
sites << site
counts << data["responseSummary"]['numTotalResults']
```

`<<` is Ruby's array-append operator. In Python this is the bit-shift
operator, and `[] << "some string"` raises `TypeError` — so this cell has
never actually run successfully. It also references an undefined variable
(`provider` is never assigned in that notebook's loop, only `site`). This
reads as a copy-paste artifact from an earlier Ruby prototype of the same
notebook, left unported. **When we port these two notebooks' logic into
nodes, we should implement the evident intent (append each site's count),
not reproduce the bug** — flagging this explicitly since it means the node's
behavior will differ from what's literally written in the source notebook.

**Net effect on this project: no multi-language runtime problem to solve.**
Every notebook here is single-source-of-truth Python we can read directly and
port line-by-line. This significantly simplifies the plan versus what a
genuine Python/Ruby/R mix would have required (e.g. shelling out to
`Rscript`/`ruby` from within a node, or separate node families per language).

## The common pattern across all 9 notebooks

Every notebook follows the same three-part shape:

1. **Setup cell** — `%pip install` a fixed list of packages (altair, pandas,
   requests, etc.) into the Pyodide runtime, then import them. This step is
   irrelevant to a ComfyUI port: `requirements.txt`/the Docker image already
   installs real Python packages once, so there's no per-notebook
   reinstall step needed as a node.
2. **Data-loading cell** — *this is the one common piece of real logic,
   identical (modulo the copy-paste bug above) across all 9 notebooks:*

   ```python
   key = "XXXXXXXX"   # secret key from the FLAIR-GG Virtual Platform
   url = "https://bgv.cbgp.upm.es/DAV/home/LDP/FLAIR/{}".format(key)
   response = requests.get(url)
   response = json.loads(response.content)
   # response is now: { provider_name: raw_payload_string, ... }
   ```

   The outer shape is always the same: one GET request, one JSON parse,
   yielding a dict keyed by data-provider name. What's *inside* each
   provider's `raw_payload_string` varies by notebook/data service — see
   below.
3. **Per-provider parsing + plotting cell(s)** — notebook-specific. The raw
   per-provider string is one of:
   - a **JSON string**, requiring a second `json.loads()` (`driada.ipynb`;
     also the two buggy Beacon2 notebooks, structurally)
   - a **CSV string with a header row**, hand-parsed via
     `.splitlines()`/`.split(",")` (`countingcase.ipynb`, `kpi_000007.ipynb`,
     `phenotypefrequency.ipynb`)
   - a **CSV string**, parsed via `pandas.read_csv(io.StringIO(...))`
     (`sparql.ipynb`, `iucn_categorization.ipynb`)

   `coordinates_by_species.ipynb` (the large one, 45 cells) also follows this
   same load step but then does considerably more — including loading the
   Spanish administrative-boundary/vegetation shapefiles for mapping. Save
   that one for later; it's the biggest single porting effort and depends on
   deciding how ComfyUI nodes should handle large reference geodata (see
   Housekeeping section below — those shapefiles are the folder's real size
   problem).

## Proposed node breakdown (one at a time, as requested)

**Node 1 — `FLAIR_LoadBySecretKey`: built and verified, status DONE.**
Lives in `custom-nodes/flair-analytics/nodes.py`. Built and tested against
`iucn_categorization.ipynb` as the reference notebook (see Open Questions
below for what was actually decided/verified, not just proposed).

- Input: `key` (STRING widget, required — no silent placeholder default;
  reject the literal `"XXXXXXXX"`/`"XXXXXXXXX"` placeholder the same way the
  notebooks' `sys.exit(...)` guard does, but as a raised exception, which is
  how ComfyUI surfaces a failed node in the queue/UI rather than crashing the
  process).
- Behavior: GET `https://bgv.cbgp.upm.es/DAV/home/LDP/FLAIR/{key}`, parse the
  outer JSON, return the `{provider: raw_payload_string}` dict as-is. Do
  **not** attempt to guess/parse the inner payload format here — that's
  provider/notebook-specific and belongs in downstream nodes, mirroring how
  the notebooks themselves only agree on this first step.
- Output: a single typed socket carrying the provider dict. Decision needed
  (see Open Questions) on whether that's a generic ComfyUI `STRING` (JSON
  round-tripped) or a custom type (e.g. `FLAIR_PROVIDER_DATA`) so it can only
  be wired into nodes that expect this shape.
- This is also the natural first place to pilot the base-class/decorator
  provenance-capture mechanism designed earlier (see `handoff.md`) — one
  external HTTP call with a clean input (key) and output (provider dict) is
  about as simple a case as we'll get for testing that the capture wrapper
  records inputs/outputs correctly, before wiring it into more nodes.

**Node 2 (next session, not yet): a per-payload-shape parser**, likely split
into `FLAIR_ParseJSONPayload` and `FLAIR_ParseCSVPayload` rather than one
node per notebook, since the real variation between notebooks is which of
these two shapes they expect, not anything else. Exact split still to be
confirmed once Node 1 exists and we can test it against a real payload.

**Later nodes:** the notebook-specific transforms/plots (bar chart via
Altair, etc.), and eventually the `coordinates_by_species.ipynb` shapefile
workflow as its own multi-node effort.

## Decisions made building Node 1 (were open questions, now resolved)

1. **Output type: custom type, `FLAIR_PROVIDER_DATA`.** Chosen over a plain
   `STRING`/JSON-serialized output specifically because more nodes in this
   family are coming and we want the graph to reject wiring provider data
   into the wrong kind of socket. In ComfyUI a "custom type" is just a
   string literal used consistently across a node family's
   `RETURN_TYPES`/`INPUT_TYPES` — no separate registration step exists or is
   needed; the actual Python object (a plain dict) is passed in-process
   between node calls, unserialized. Every future node that consumes
   provider data should declare its input type as `"FLAIR_PROVIDER_DATA"` to
   match.
2. **TLS verification: on by default (`verify=True`), not disabled.**
   Tested directly against `bgv.cbgp.upm.es`: `curl`'s
   `ssl_verify_result: 0` (success) — the cert validates cleanly. The
   notebooks' `urllib3.disable_warnings(InsecureRequestWarning)` calls look
   like unnecessary copy-paste caution, not a real workaround for a cert
   problem, so the node does not carry that behavior forward.
3. **Testing key: confirmed dead, but useful anyway.** The notebooks'
   inline example key (`630e5b25-bc4e-4568-833c-8b8bc7303dcb`) now 404s —
   expired, not a network/reachability problem (the host itself responds
   normally). Used this as a real test of the node's 404 error path rather
   than the happy path. Still need a fresh key from an actual VP run to
   verify the happy-path JSON shape end-to-end.
4. **Error surfacing: confirmed via a real `/prompt` submission**, not just
   direct method calls — chained `FLAIR_LoadBySecretKey` into the stock
   `PreviewAny` node (accepts `IO.ANY`, so it happily takes our custom type)
   and posted to a running server's `/prompt` endpoint. A raised exception
   shows up in `/history` as an `execution_error` message carrying
   `exception_message` (exactly the string the node raised), `exception_type`,
   a full `traceback`, and `current_inputs`. The frontend renders this as a
   red-bordered failed node with `exception_message` as the tooltip. Both
   the placeholder-key rejection and the 404 case were verified this way.
   **Implication for the later Sinatra end-user frontend:** it should surface
   only `exception_message` to non-coder users, not the full traceback.

## Housekeeping finding (report only — nothing in FLAIR-GG-Analytics touched)

Repo working tree is 138MB (`.git` history adds another 61MB on top). Almost
all of it is Spanish shapefile datasets under
`content/FLAIR-GG/shapefiles/`, used by exactly one notebook
(`coordinates_by_species.ipynb`) via `geopandas`/`rasterio`. Nothing else in
the repo is large, and no genuine multi-institution data-loss risk was found
— these look like a deliberate local cache of flaky government data sources,
which is a reasonable thing to keep.

| Item | Size | Status |
| --- | --- | --- |
| `shapefiles/rn2000-shp/` (Natura 2000) | 25MB | Used (geopandas) |
| `shapefiles/potential_vegetation/` | 12MB | Used (geopandas) |
| `shapefiles/gadm41_ESP_1-4.shp` + sidecars | ~24MB | Used (geopandas) |
| `shapefiles/P/p/w001001.adf` (annual precip. raster) | 0.9MB | Used (rasterio) |
| `shapefiles/gadm41_ESP_1-4.json` | ~3.9MB | **Not referenced anywhere** in the notebook — looks like a leftover GeoJSON duplicate of the `.shp` files above |
| `shapefiles/P/{pw,pene,pdic,pfeb,poct,pjun,pmar,pabr,pnov,psep,pmay,pago}/` (12 monthly precip. grids) | ~10MB | **Not referenced anywhere** — only the annual `P/p/` grid is used in code |

So ~14MB looks like safely-removable duplicate/unused data, without touching
the ~58MB that's genuinely in active use. The `.git` history bloat (61MB,
mostly the same shapefiles — `git log` shows one was moved to Git LFS then
reverted back to plain storage at some point) is a separate, more invasive
lever that would need history rewriting + force-push; not something to act
on without Alberto. No urgency on any of this per the user (2026-08-03) —
noted here for reference, not as a to-do.
