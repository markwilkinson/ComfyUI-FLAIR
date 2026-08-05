# ComfyUI-FLAIR
The FLAIR Interoperability Platform enables the creation of multi-resource workflows.  Here we store custom nodes and workflows that can be created inside of the ComfyUI workflow design environment.

This repo (`ComfyUI-FLAIR`) holds FLAIR-specific custom nodes, workflows, and deployment tooling. It does **not** contain the ComfyUI engine itself — that's a separate clone of [ComfyUI](https://github.com/Comfy-Org/ComfyUI), expected to live as a sibling directory (`../ComfyUI`) next to this repo.

Custom node packages live under [custom-nodes/](custom-nodes/):

- `flair_declutter` — hides Stable-Diffusion/diffusion-model nodes from the ComfyUI picker at runtime (no core files patched — see the docstring in [`custom-nodes/flair_declutter/__init__.py`](custom-nodes/flair_declutter/__init__.py) for the exact mechanism).
- `flair-analytics` — ports of the [FLAIR-GG-Analytics](https://github.com/wilkinsonlab/FLAIR-GG-Analytics) Jupyter notebooks into ComfyUI nodes, one node at a time. See [`custom-nodes/flair-analytics/PLAN.md`](custom-nodes/flair-analytics/PLAN.md) for the porting strategy and package layout (organized by node category under `nodes/`, not one flat file).
- `useless_text` — throwaway 4-node demo used to learn the ComfyUI custom-node interface. Not part of the real project.

## Why this, instead of an existing tool?

The real goal of this project isn't a nicer node-editor — it's provenance: every workflow run should automatically produce a standard, machine-readable record of what ran, with what inputs, and what came out (the [Workflow Run RO-Crate](https://www.researchobject.org/workflow-run-crate/) standard, specifically its most detailed "Provenance Run Crate" flavor — a per-step record, not just a whole-workflow black box). That's a real, useful thing to build. But several existing tools already do parts of it, and we should be upfront about which parts are genuinely new here versus which parts we're just re-doing on a smaller scale.

### Benefit matrix

| | Interaction style | Non-coder friendly | Automatic FAIR/RO-Crate provenance | Distributed/cluster execution | Effort to add a new step |
| --- | --- | --- | --- | --- | --- |
| **Galaxy** | Submit a job, check back later | Yes (web form per tool) | **Yes — built-in, automatic, production.** The reference implementation this standard was designed around | Yes — real cluster/Kubernetes scheduling | Tool XML + Conda/container packaging + publishing (Planemo) |
| **LifeWatch/D4Science + NaaVRE** | Jupyter notebooks, remote/shared execution | No — still notebook-based, even with NaaVRE breaking cells into reusable pieces | Partial — auto-logs *what ran*, but making the *output* FAIR/RDF is left to whoever documents it afterward (encouraged, not enforced) | Yes — federated, multi-institution infrastructure | Write a notebook cell / NaaVRE component |
| **Nextflow / Snakemake** *(general knowledge only — not researched in depth here, worth a closer look before citing)* | Command-line, script-defined pipelines | No — authoring is code (Groovy DSL / Python-based rules) | Not built-in; RO-Crate support exists only via separate community plugins, not the default | Yes — designed for HPC/cluster schedulers (Slurm, AWS Batch, etc.) | Write a process/rule definition in the pipeline's script |
| **KNIME** *(general knowledge only — not researched in depth here)* | Live visual node canvas — closest interaction analog to this project | Yes — drag-and-drop, built for non-programmers | Not built-in by default; FAIR/RO-Crate support exists as research-community add-ons, not core | Limited — mainly single-machine, some server/cluster editions exist commercially | Build a KNIME node (Java-based extension API) |
| **This project (ComfyUI-FLAIR)** | Live visual canvas, edit-and-see-immediately | Yes — that's the design goal for lab end users | **Planned, not yet built** — aiming for the same Provenance Run Crate tier as Galaxy, generated automatically per node run | No — single process, one job at a time | A short, plain Python class (see `custom-nodes/useless_text` for a working example) |

Only Galaxy and LifeWatch/D4Science/NaaVRE were actually researched in depth for this comparison; the Nextflow/Snakemake/KNIME row is included for completeness from general knowledge and should be verified properly before it goes into anything like a grant application or paper.

**Compared to Galaxy — the load-bearing comparison, no hedging:** Galaxy already does automatic Provenance Run Crate generation, out of the box, in production, with two-way WorkflowHub integration built in. **We should never claim "better provenance than Galaxy"** — that doesn't hold up. What's actually different is the experience: Galaxy is submit-and-check-back-later, built for long command-line bioinformatics jobs on a cluster; this project is drag-a-value, see-the-result-immediately — a genuinely different fit for someone tweaking a map-rendering parameter and wanting to see the picture change right now. In exchange we give up real cluster scheduling and 15+ years of Galaxy's published tools, documentation, and community.

**Compared to LifeWatch/D4Science and NaaVRE:** large, federated, multi-institution infrastructure with shared login and remote execution. Their provenance is an automatic execution log, but not translated into FAIR/semantic (RDF) form automatically — that step is left to whoever documents the output afterward. Again, not "smarter provenance," just a different scale and interaction style: one lab, one small server, immediate visual feedback for a non-programmer.

**WorkflowHub/CWL note:** WorkflowHub (the registry where workflows get published/cited) doesn't require CWL — it accepts any workflow language, so this project's workflows could be registered there without extra translation work. A possible nice-to-have later: generate a plain descriptive CWL file purely so WorkflowHub renders a nicer diagram — not a real, runnable CWL translation, since that's not how ComfyUI executes internally.

**The honest summary:** we're not out-provenancing Galaxy or out-scaling LifeWatch/D4Science. What's actually being built is a small, low-effort, single-lab tool that a non-programmer can point-and-click through and see results immediately — while still aiming to produce the same standard FAIR provenance record the bigger platforms use, so outputs stay compatible with that wider ecosystem instead of becoming a one-off format nobody else can read.

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
ln -s ../../ComfyUI-FLAIR/custom-nodes/flair_declutter ComfyUI/custom_nodes/flair_declutter
ln -s ../../ComfyUI-FLAIR/custom-nodes/useless_text     ComfyUI/custom_nodes/useless_text
```

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

## Deployment context

- **CPU-only / no GPU:** there's no Stable Diffusion/diffusion-model workload here, so none of the usual GPU/VRAM sizing advice for ComfyUI applies — CPU-only operation is officially supported (`--cpu`).
- **Single-queue scaling caveat:** ComfyUI runs one execution queue — jobs process one at a time on one backend process, not in parallel across users. Fine at lab scale; if it ever needs real concurrency, the fix is multiple backend instances behind a dispatcher, not a bigger single machine.
- **License:** ComfyUI is GPLv3. If a patched/customized version is ever redistributed as a lab image, copyleft obligations apply — check with UPM tech transfer/legal before that step.
