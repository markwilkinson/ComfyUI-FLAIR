# ComfyUI-FLAIR
The FLAIR Interoperability Platform enables the creation of multi-resource workflows.  Here we store custom nodes and workflows that can be created inside of the ComfyUI workflow design environment.

This repo (`ComfyUI-FLAIR`) holds FLAIR-specific custom deployment configuration for using ComfyUI with the FLAIR-GG infrastructure. It does **not** contain the ComfyUI engine itself (this is loaded by Docker); this customization is used to modify the default Comfy created by Docker using mounted volumes.  

Core custom node packages — the ones every deployment always has, tracked directly in this repo under [custom-nodes/](custom-nodes/):

- `flair_declutter` — hides Stable-Diffusion/diffusion-model nodes from the ComfyUI picker at runtime (no core files patched — see the docstring in [`custom-nodes/flair_declutter/__init__.py`](custom-nodes/flair_declutter/__init__.py) for the exact mechanism).
- `flair-provenance` — automatic FAIR/RO-Crate provenance capture for every workflow run, no per-node wiring required. See [`custom-nodes/flair-provenance/PLAN.md`](custom-nodes/flair-provenance/PLAN.md) for the design and current status.

Everything else — domain-specific node packages (e.g. `flair-analytics`, the FLAIR-GG-Analytics IUCN pipeline port) and example workflows — lives in the separate [ComfyUI-FLAIR-Catalog](https://github.com/markwilkinson/ComfyUI-FLAIR-Catalog) repo and is opt-in per deployment; see "Installing from the catalog" below.

**Writing a new node yourself?** See [`custom-nodes/HOW_TO_CREATE_NODES.md`](custom-nodes/HOW_TO_CREATE_NODES.md) — conventions, gotchas, and testing patterns established across the packages above, written for both a human contributor and a fresh Claude session picking this project up cold.

## Why this, instead of an existing bioinformatics workflow tool?

The real goal of this project isn't a nicer node-editor — it's provenance: every workflow run should automatically produce a standard, machine-readable record of what ran, with what inputs, and what came out (the [Workflow Run RO-Crate](https://www.researchobject.org/workflow-run-crate/) standard, specifically its most detailed "Provenance Run Crate" flavor — a per-step record, not just a whole-workflow black box). That's a real, useful thing to build. ComfyUI itself is an existing, mature tool — just not one commonly used in bioinformatics, where it's essentially unknown outside its native image-generation community. Several *bioinformatics* workflow tools already do parts of what we're after here, though, and we should be upfront about which parts are genuinely new versus which parts we're just re-doing on a smaller scale.

### Benefit matrix

| | Interaction style | Non-coder friendly | Automatic FAIR/RO-Crate provenance | Distributed/cluster execution | Runnable over the Web | Effort to add a new step |
| --- | --- | --- | --- | --- | --- | --- |
| **Galaxy** | Submit a job, check back later | Yes (web form per tool) | **Yes — built-in, automatic, production.** The reference implementation this standard was designed around | Yes — real cluster/Kubernetes scheduling | **Yes** — that's the whole architecture; browser-based by design | Tool XML + Conda/container packaging + publishing (Planemo) |
| **LifeWatch/D4Science + NaaVRE** | Jupyter notebooks, remote/shared execution | No — still notebook-based, even with NaaVRE breaking cells into reusable pieces | Partial — auto-logs *what ran*, but making the *output* FAIR/RDF is left to whoever documents it afterward (encouraged, not enforced) | Yes — federated, multi-institution infrastructure | **Yes** — VRE web portals run the notebooks server-side, no local install | Write a notebook cell / NaaVRE component |
| **Nextflow** | Command-line, script-defined pipelines (Groovy DSL) | No — authoring is code | **Yes, via the official [`nf-prov`](https://github.com/nextflow-io/nf-prov) plugin** (maintained by the Nextflow team itself, not a third party) — generates the full Workflow Run RO-Crate, all three profiles including Provenance Run Crate, automatically once enabled, no pipeline script changes needed. Opt-in (not on by default), but first-party and production-grade | Yes — designed for HPC/cluster schedulers (Slurm, AWS Batch, etc.) | No — CLI-first; [Seqera Platform](https://seqera.io/) adds a commercial web layer on top, but Nextflow itself is not web-based | Write a process definition in the pipeline's script |
| **Snakemake** | Command-line, Python-based rule pipelines | No — authoring is code | **Yes, via the official [`snakemake-report-plugin-rocrate`](https://github.com/snakemake/snakemake-report-plugin-rocrate)** (maintained under the Snakemake org itself) — Provenance Run Crate profile, opt-in report plugin, not third-party | Yes — designed for HPC/cluster schedulers | No — CLI-first, no official web execution layer | Write a rule in a Snakefile |
| **Taverna** *(legacy, largely unmaintained since ~the mid-2010s, but still relevant — WorkflowHub hosts many Taverna-origin workflows migrated from myExperiment)* | Live visual node canvas (Taverna Workbench) — actually the closest *historical* interaction analog to this project, predating ComfyUI by over a decade | Yes, for its era — drag-and-drop, widely used by non-programmer bioinformaticians | Historically pioneering, not by today's RO-Crate standard: the [Wf4Ever project](https://github.com/stain/2016-provweek-tavernaprov)'s `taverna-prov` exported W3C PROV-O provenance from Taverna runs — and Wf4Ever's "Research Object" concept is a direct ancestor of RO-Crate itself. No modern native RO-Crate export found | Limited — desktop/server execution, not built for HPC cluster scheduling | Historically yes, via **Taverna Player** (a Rails web UI that executes workflows through Taverna Server and can be iframe-embedded like a video) — but it was tied to the now largely-defunct BioVeL Portal, not something a plain Taverna install gives you today | Wrap a web service/script as a Taverna "processor" (SOAP/REST integration was its strength) |
| **KNIME** *(general knowledge only — not researched in depth here)* | Live visual node canvas — closest *current* interaction analog to this project | Yes — drag-and-drop, built for non-programmers | Not built-in by default; FAIR/RO-Crate support exists as research-community add-ons, not core | Limited — mainly single-machine, some server/cluster editions exist commercially | Only via the commercial **KNIME Business Hub** (browser "Run" + Data Apps Portal) — the free desktop Analytics Platform most people run is not web-based | Build a KNIME node (Java-based extension API) |
| **This project (ComfyUI-FLAIR)** | Live visual canvas, edit-and-see-immediately | Yes — that's the design goal for lab end users | **Built, v1 scope** — every node's execution (including stock/third-party nodes we don't own) captured automatically via ComfyUI's own `CacheProvider` hook, no per-node wiring; a real `ro-crate-metadata.json` (Provenance Run Crate profile) gets written per run. Not yet at Galaxy/Nextflow/Snakemake's level: inputs are currently a hash, not full `FormalParameter` bindings with literal values — see [`custom-nodes/flair-provenance/PLAN.md`](custom-nodes/flair-provenance/PLAN.md) for exactly what's done vs. not | No — single process, one job at a time | **Yes** — free/open-source, Docker + web server, no paid tier gate | A short, plain Python class — see [`custom-nodes/HOW_TO_CREATE_NODES.md`](custom-nodes/HOW_TO_CREATE_NODES.md) |

Galaxy, LifeWatch/D4Science/NaaVRE, Nextflow, Snakemake, and Taverna were all researched directly (official plugin repos, project docs) for this comparison, not assumed. The Taverna Player and KNIME Business Hub claims in the "Runnable over the Web" column were also verified directly. KNIME's other columns are still general-knowledge-only and need the same treatment before it goes into anything like a grant application or paper.

**Compared to Galaxy — the load-bearing comparison, no hedging:** Galaxy already does automatic Provenance Run Crate generation, out of the box, in production, with two-way WorkflowHub integration built in. **We should never claim "better provenance than Galaxy"** — that doesn't hold up. What's actually different is the experience: Galaxy is submit-and-check-back-later, built for long command-line bioinformatics jobs on a cluster; this project is drag-a-value, see-the-result-immediately — a genuinely different fit for someone tweaking a map-rendering parameter and wanting to see the picture change right now. In exchange we give up real cluster scheduling and 15+ years of Galaxy's published tools, documentation, and community.

**Compared to Nextflow and Snakemake:** both now have official, maintained RO-Crate export (not community bolt-ons) — this genuinely surprised the original comparison, which had assumed no built-in support. The real differentiator holds regardless: both are command-line, script-authored pipeline tools built for long HPC/cluster jobs, with no live visual feedback loop — a fundamentally different interaction model from a canvas where a non-programmer drags a value and immediately sees the result change.

**Compared to Taverna:** genuinely the closest *historical* relative to this project — a live visual node canvas aimed at non-programmers, predating ComfyUI by a decade or more. Its lineage matters more than its current relevance: the Wf4Ever project's Research Object concept, built around Taverna, is a direct ancestor of RO-Crate itself, and WorkflowHub (descended from myExperiment, Taverna's original home) still hosts a real population of Taverna workflows today. But it's largely unmaintained now, with no modern RO-Crate export found — worth citing for lineage/precedent, not as a live competitor.

**Compared to LifeWatch/D4Science and NaaVRE:** large, federated, multi-institution infrastructure with shared login and remote execution. Their provenance is an automatic execution log, but not translated into FAIR/semantic (RDF) form automatically — that step is left to whoever documents the output afterward. Again, not "smarter provenance," just a different scale and interaction style: one lab, one small server, immediate visual feedback for a non-programmer.

**WorkflowHub/CWL note:** WorkflowHub (the registry where workflows get published/cited) doesn't require CWL — it accepts any workflow language, so this project's workflows could be registered there without extra translation work. A possible nice-to-have later: generate a plain descriptive CWL file purely so WorkflowHub renders a nicer diagram — not a real, runnable CWL translation, since that's not how ComfyUI executes internally.

**The honest summary:** we're not out-provenancing Galaxy, Nextflow, or Snakemake, and we're not out-scaling LifeWatch/D4Science. What's actually being built is a small, low-effort, single-lab tool that a non-programmer can point-and-click through and see results immediately — while producing the same standard FAIR provenance record the bigger platforms use (even if not yet at full parity — see the Status section in `flair-provenance/PLAN.md`), so outputs stay compatible with that wider ecosystem instead of becoming a one-off format nobody else can read.

There are two supported ways to run this: a native Python install (for local development/editing), and Docker (the preferred way to actually deploy it). Both are documented below — pick whichever fits what you're doing.

## Option A: Native install (venv)

Useful for local development where you want to `import nodes` directly, run quick scripts against the ComfyUI registry, etc.

Requires Python 3.10 (later versions may not have prebuilt wheels for every dependency yet) and `python3.10-venv`:

```bash
sudo apt install python3.10-venv   # if not already installed
```

Then, from your `ComfyUI` clone:

```bash
cd ComfyUI
python3.10 -m venv venv
venv/bin/pip install --upgrade pip
# CPU-only torch -- there is no GPU workload here (no diffusion models),
# see "Deployment context" below for why.
venv/bin/pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
venv/bin/pip install -r requirements.txt
```

Strip the Stable-Diffusion workflow-template gallery (the "Templates" menu) — it's ~420MB of packaged SD workflow JSON + preview media across several sub-packages, irrelevant to a non-SD deployment. `requirements.txt` is left as-is; ComfyUI already handles this package being absent gracefully (it just doesn't register the `/templates` route):

```bash
venv/bin/pip uninstall -y \
    comfyui-workflow-templates comfyui-workflow-templates-core \
    comfyui-workflow-templates-json comfyui-workflow-templates-media-api \
    comfyui-workflow-templates-media-image comfyui-workflow-templates-media-video \
    comfyui-workflow-templates-media-other comfyui-workflow-templates-media-assets-01
```

Symlink the FLAIR custom nodes in:

```bash
ln -s ../../ComfyUI-FLAIR/custom-nodes/flair_declutter  ComfyUI/custom_nodes/flair_declutter
ln -s ../../ComfyUI-FLAIR/custom-nodes/flair-provenance ComfyUI/custom_nodes/flair-provenance
```

(Symlink in anything installed from the catalog the same way, once you've run `scripts/install_from_catalog.sh` — see "Installing from the catalog" below.)

Run it:

```bash
cd ComfyUI
venv/bin/python main.py --cpu --listen 0.0.0.0 --port 8188
```

`--cpu` is required even with the CPU-only torch build above — without it, ComfyUI still tries `torch.cuda.current_device()` on startup and crashes. `--listen 0.0.0.0` is only needed if you want it reachable from outside localhost (e.g. behind a reverse proxy on another host).

## Option B: Docker (preferred for deployment)

Everything needed is in [docker/](docker/): a `Dockerfile` that clones ComfyUI pinned to a known-good commit and installs CPU-only torch + dependencies inside the image, and a `docker-compose.yml` that bind-mounts everything mutable so it never needs a rebuild for day-to-day changes:

- `docker/data/{models,input,output,user}` — persistent ComfyUI data, on the host.
- `../custom-nodes/` — the whole directory, mounted read-only as ComfyUI's entire `custom_nodes/` folder. Edit a node's `.py` file on the host, restart the container, done — no image rebuild, no compose edit either.

Build and run:

```bash
cd ComfyUI-FLAIR/docker
mkdir -p data/models data/input data/output data/user
docker compose build
docker compose up -d
```

Check it's up:

```bash
docker compose logs -f
curl http://127.0.0.1:8188/
```

The container publishes port 8188 bound to `127.0.0.1` only (not exposed to the outside network directly) — see "Reverse proxy" below.

**Adding a new FLAIR custom-node package:** just create the folder under `custom-nodes/` — the whole directory is mounted as one, so it appears automatically on the next container restart (`docker compose up -d`, no rebuild). No `docker-compose.yml` or Dockerfile changes needed — **unless the node imports a new Python package** ComfyUI doesn't already ship (e.g. `pandas`, added for `flair-analytics`'s CSV parsing). `custom_nodes/` is mounted, not baked in, so the Dockerfile has no way to discover a new import automatically; add a `pip install` line to `docker/Dockerfile`'s "FLAIR node dependencies" step and rebuild (`docker compose build`).

**Bumping the pinned ComfyUI version:** edit `COMFYUI_REF` (a commit hash) at the top of `docker/Dockerfile`, then `docker compose build`.

**Non-root container user:** the container runs as UID/GID 1000 (not root), so files it writes into the bind-mounted `docker/data/` (saved workflows, RO-Crate outputs, etc.) come out owned by the host user, not root — no `sudo` needed to read or back them up. 1000 is the default first-user UID/GID on Debian/Ubuntu; override at build time with `docker compose build --build-arg UID=$(id -u) --build-arg GID=$(id -g)` if deploying on a host where the target user has a different one. If you already had a container running as root before this change, fix the existing files once: `cd docker && sudo chown -R $(id -u):$(id -g) data/`.

### Reverse proxy (lighttpd)

The Docker container's port 8188 is bound to `127.0.0.1` on the host, not exposed externally. Point lighttpd at it with `mod_proxy`, e.g.:

```lighttpd
$HTTP["host"] == "your-flair-hostname" {
    proxy.server = ( "" =>
        ( "comfyui" =>
            ( "host" => "127.0.0.1", "port" => 8188 )
        )
    )
}
```

ComfyUI uses WebSockets for live execution progress in the graph editor, so make sure `mod_proxy` on your lighttpd version forwards Upgrade/Connection headers (recent lighttpd 1.4.x does this automatically for `mod_proxy`; older versions may need explicit config).

### Deploying to a new server

`git clone` this repo, `git clone` [ComfyUI](https://github.com/Comfy-Org/ComfyUI) as its sibling directory, then follow Option B above. What that single `git clone` does and doesn't bring with it:

- **Core custom nodes: yes, automatically.** `custom-nodes/flair_declutter` (the node-hiding mechanism) and `custom-nodes/flair-provenance` (the RO-Crate/PROV-O capture system — the whole reason this project exists) are normal tracked files, nothing gitignored. A fresh clone always has these two, and only these two, immediately.
- **Everything else (domain node packages, workflows): no, opt-in via the catalog.** `custom-nodes/` and `workflows/` are still real, git-tracked, whole-directory bind-mounted onto ComfyUI's actual paths (see `docker-compose.yml`) — but a fresh clone of *this* repo ships them empty (beyond the two core packages above and a `workflows/.gitkeep` placeholder so the directory itself survives the clone). What actually populates them is a deliberate choice: see "Installing from the catalog" below.
- **`docker/data/{models,input,output,user}`: no, deliberately not.** This is runtime state — downloaded model weights, run history, the asset-tracking SQLite DB — gitignored on purpose (`docker/data/` in `.gitignore`) and not meant to travel via git. A new server starts with these genuinely empty; nothing needs to be copied in for the system to work.

Because saving through the web UI writes straight into this repo's tracked `workflows/` folder, this repo's maintainer is the sole authority over which workflows/nodes ship in *this* repo — nothing lands here without going through a normal commit (or a pull request) and review. Anyone running their own deployment is free to save, edit, or delete whatever they like in their own checkout; that's local to their fork/clone and never affects the upstream repo unless they open a PR.

### Installing from the catalog

Domain-specific nodes (like the FLAIR-GG-Analytics IUCN pipeline) and example workflows live in a separate repo, [ComfyUI-FLAIR-Catalog](https://github.com/markwilkinson/ComfyUI-FLAIR-Catalog), not in this one. The idea: a distro's custodian decides what their deployment actually needs and installs only that — a lab running a single-purpose kiosk can ship just one workflow, instead of everyone's contributions bundled in by default.

```bash
# clone the catalog as a sibling of this repo, same convention as ComfyUI itself
git clone https://github.com/markwilkinson/ComfyUI-FLAIR-Catalog ../ComfyUI-FLAIR-Catalog

# install whatever you want -- node packages and/or workflows, by name
scripts/install_from_catalog.sh flair-analytics iucn_endangered_species_survey
```

This copies the named items into `custom-nodes/`/`workflows/` (not symlinks — Docker's bind mounts only see this repo's own tree, so a symlink to the sibling catalog checkout would dangle inside the container). Nothing is auto-committed; review with `git status`/`git diff` and commit it as part of your own deployment, same as any other change. See the catalog repo's README for the full list of what's available and how to contribute something back to it.

## Deployment context

- **CPU-only / no GPU:** there's no Stable Diffusion/diffusion-model workload here, so none of the usual GPU/VRAM sizing advice for ComfyUI applies — CPU-only operation is officially supported (`--cpu`).
- **Single-queue scaling caveat:** ComfyUI runs one execution queue — jobs process one at a time on one backend process, not in parallel across users. Fine at lab scale; if it ever needs real concurrency, the fix is multiple backend instances behind a dispatcher, not a bigger single machine.
- **License:** ComfyUI is GPLv3. If a patched/customized version is ever redistributed as a lab image, copyleft obligations apply — check with UPM tech transfer/legal before that step.
