# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.6.0] - 2026-08-04

### Added

- `custom-nodes/flair-analytics/nodes/loaders.py` —
  `FLAIR_ProviderDataFromText`: a testing/authoring node that parses pasted
  `{provider_url: raw_payload_string}` JSON (no network call) into the same
  `FLAIR_PROVIDER_DATA` type `FLAIR_LoadBySecretKey` produces. Requested so
  sample/copied data can be tested against the downstream nodes without a
  live secret key -- a plain stock text node can't substitute for the real
  loader here, since ComfyUI's type system blocks wiring `STRING` into a
  `FLAIR_PROVIDER_DATA` socket. Default widget value is a working sample
  against the real IUCN schema. Verified end-to-end through the full chain
  (this node → `FLAIR_ParseCSVPayload` → `FLAIR_DeduplicateRows` →
  `FLAIR_PlotCategoryCounts`) using that default text.

- `custom-nodes/flair-analytics/nodes/plots.py` — `FLAIR_PlotCategoryCounts`
  and `FLAIR_PlotStackedCategoryCounts`, the fourth and fifth ported nodes,
  completing `iucn_categorization.ipynb`'s full port (cells 4 and 5: a
  Seaborn countplot and a stacked bar plot by provider, plus the
  category/group summary counts the notebook printed to stdout, now a real
  `STRING` output). Both take caller-specified column names rather than
  hardcoding IUCN's schema, so other notebooks with the same
  count/stack-by-category shape can reuse them. Includes a shared
  `_figure_to_image_tensor()` helper converting a matplotlib `Figure` into
  ComfyUI's native `IMAGE` tensor format, so plots feed straight into stock
  `PreviewImage`/`SaveImage`. Verified against synthetic data matching the
  real IUCN schema; output tensors and rendered PNGs visually inspected.

### Fixed

- `docker/Dockerfile`: added `matplotlib`/`seaborn` to the "FLAIR node
  dependencies" step (same gotcha as `pandas` in 0.3.0) -- neither is a
  ComfyUI dependency.

- `custom-nodes/flair-analytics/nodes/transforms.py` — `FLAIR_DeduplicateRows`,
  the third ported node. Generic dedupe + drop-missing-values on
  caller-specified column names, matching `iucn_categorization.ipynb` cell
  3's cleanup step but generalized to any columns rather than hardcoded to
  that notebook's schema. Verified against synthetic data (exact-duplicate
  and missing-value cases); bad column names raise a clear error listing
  the real available columns.

### Fixed

- Confirmed the IUCN_categorization service's "no parameters" display in
  the FLAIR-GG VP GUI is correct, not a bug: its live OpenAPI spec shows
  `"parameters": []` by design (a fixed SPARQL lookup, no variable
  bindings) -- unlike `species_location`, which does take a parameter. What
  looked like a bug during investigation was actually several
  `*.linkeddata.systems` provider hosts being mid-migration and not yet
  live; the corresponding `*.bgv.cbgp.upm.es` hostnames are the currently-
  functional ones. No code change needed.

## [0.3.0] - 2026-08-04

### Added

- `custom-nodes/flair-analytics/nodes/parsers.py` — `FLAIR_ParseCSVPayload`,
  the second ported node. Parses each provider's CSV payload from
  `FLAIR_LoadBySecretKey`'s output via `pandas.read_csv`, tags each row with
  `provider_url`/`provider_host`, and concatenates into one combined
  `DATAFRAME`-typed output. Zero-row providers (header only) contribute
  nothing without erroring; a provider whose payload isn't valid CSV is
  skipped with a warning rather than failing the whole batch. Verified
  end-to-end through the real container queue against a live secret key
  (`708aba31-b0c3-45be-a04e-546fe674d460`, species-location service): 5
  providers in, 2 empty handled cleanly, 3 rows combined correctly.

### Changed

- `custom-nodes/flair-analytics/` reorganized from a single flat `nodes.py`
  into a `nodes/` package split by category (`loaders.py`, `parsers.py`),
  merged via `nodes/__init__.py`. Adding a new category is now: new file
  under `nodes/`, register it in `nodes/__init__.py`'s `_SUBMODULES` tuple.

### Fixed

- `docker/Dockerfile`: added a "FLAIR node dependencies" `pip install`
  step (starting with `pandas`, needed by the new CSV parser). New Python
  imports in a FLAIR node are a real exception to "no rebuild needed" --
  `custom_nodes/` is bind-mounted, not baked into the image, so the
  Dockerfile has no way to discover a node's new imports automatically the
  way it discovers new node *code* for free. Documented in README.md.

## [0.2.2] - 2026-08-03

### Changed

- `docker/docker-compose.yml`: replaced the per-package custom-node
  bind-mounts with a single mount of the whole `custom-nodes/` directory
  onto ComfyUI's `custom_nodes/`. New node packages now appear on container
  restart with zero `docker-compose.yml`/Dockerfile edits, closing the gap
  that caused the 0.2.1 bug. Trade-off: the container's one stock example
  node (`websocket_image_save.py`) no longer appears, since the mount
  replaces the directory rather than adding to it -- not part of this
  project, not a loss that matters here. Verified: 159 nodes visible via
  `/object_info` after the change, all FLAIR nodes present.

## [0.2.1] - 2026-08-03

### Fixed

- `docker/docker-compose.yml` was missing the bind-mount for
  `custom-nodes/flair-analytics`, added in 0.2.0 -- it was never actually
  wired into the container, so `FLAIR_LoadBySecretKey` didn't appear in the
  node picker despite existing in the repo. `flair_declutter`/`useless_text`
  were unaffected (mounted correctly from the start).

## [0.2.0] - 2026-08-03

### Added

- `custom-nodes/flair-analytics/PLAN.md` — porting plan for turning the
  FLAIR-GG-Analytics Jupyter notebooks (read-only reference, not part of this
  repo) into ComfyUI nodes, one node at a time. Corrects an initial
  assumption of a Python/Ruby/R language mix: all 9 real notebooks are
  Python (JupyterLite/Pyodide), no R/Ruby kernel exists anywhere; two
  notebooks do contain a dead/never-executed Ruby array-append idiom
  (`sites << site`) left over from an earlier prototype, to be fixed rather
  than faithfully ported.
- `custom-nodes/flair-analytics/FLAIR_LoadBySecretKey` — the first ported
  node. Fetches a FLAIR-GG Virtual Platform federated-query result by its
  secret key (`GET .../LDP/FLAIR/{key}`, outer JSON decode), matching the
  data-loading step common to all 9 notebooks. Outputs a new custom type,
  `FLAIR_PROVIDER_DATA`, so downstream nodes can only be wired to sockets
  that expect this shape. Verified end-to-end through a real `/prompt`
  submission (chained into the stock `PreviewAny` node) for both the
  placeholder-key-rejection and HTTP-404 error paths, confirming how a
  raised exception surfaces via `/history`'s `execution_error` message.

### Fixed

- Confirmed the FLAIR-GG Virtual Platform's TLS certificate validates
  cleanly (`bgv.cbgp.upm.es`) — the node defaults to verified HTTPS rather
  than carrying forward the source notebooks'
  `urllib3.disable_warnings(InsecureRequestWarning)`, which was unwarranted.

## [0.1.0] - 2026-08-03

### Added

- `custom-nodes/flair_declutter` — a runtime `custom_nodes/` package that hides
  Stable-Diffusion/diffusion-model nodes from the ComfyUI picker without
  patching any ComfyUI core file. Prunes `NODE_CLASS_MAPPINGS` by node
  category after ComfyUI's own startup has registered everything, and wraps
  `nodes.load_custom_node` so the sweep re-runs after every subsequent
  custom-node package loads — `custom_nodes/` directory scan order is not
  alphabetical, so this keeps node visibility correct regardless of load
  order. Verified live: drops the node registry from 827 to 155 nodes.
- `docker/` — CPU-only Docker deployment: a `Dockerfile` pinned to a known-good
  ComfyUI commit, and a `docker-compose.yml` that bind-mounts everything
  mutable (`models/`, `input/`, `output/`, `user/`, and each FLAIR
  custom-node package) so day-to-day node edits and data never require an
  image rebuild.
- `README.md` — install instructions for both a native venv setup and the
  Docker deployment, a lighttpd reverse-proxy config snippet, and a
  comparative "benefit matrix" positioning this project honestly against
  Galaxy, LifeWatch/D4Science + NaaVRE, and (from general knowledge only)
  Nextflow/Snakemake/KNIME — targeting the same Workflow Run RO-Crate
  (Provenance Run Crate tier) standard Galaxy already implements, not
  claiming to out-provenance or out-scale the larger platforms.
- `custom-nodes/useless_text` — a throwaway 4-node demo pipeline used to learn
  the ComfyUI custom-node interface (`Load -> Capitalize -> Rearrange ->
  Show`). Not part of the real project, kept as a working reference example.

### Removed

- The Stable-Diffusion workflow-template gallery (the frontend's "Templates"
  menu) from both the venv and Docker install paths, by uninstalling the
  `comfyui-workflow-templates` package and its per-media-type sub-packages
  after the main `requirements.txt` install (~420MB of packaged SD workflow
  JSON and thumbnail/preview media, irrelevant to a non-SD deployment).
  `requirements.txt` itself is left untouched; ComfyUI already handles the
  package being absent gracefully.

### Fixed

- `flair_declutter` was hiding some of its own project's nodes
  (`useless_text`'s `CATEGORY = "useless/text"` fell outside the allow-list)
  and, more generally, any custom node package that happened to load before
  `flair_declutter` in an arbitrary directory scan. See "Added" above for the
  fix.
