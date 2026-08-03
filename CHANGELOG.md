# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
