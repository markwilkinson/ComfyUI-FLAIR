"""
The packaging node: turns what FLAIRProvenanceCacheProvider has captured
for the current run into a Workflow Run RO-Crate. See ../PLAN.md.

v1 scope, deliberately not the full spec in one shot (matching how every
other FLAIR node started simple and iterated): real terminal output(s)
saved as File entities, one CreateAction per captured node execution, one
SoftwareApplication per distinct node class acting as `instrument` (with a
`description`, read from that node's own DESCRIPTION attribute -- ComfyUI's
own convention, also shown as a UI tooltip, not something FLAIR invented;
added per Alberto's request that node descriptions be part of captured
provenance, not just a source comment). Not yet built: full FormalParameter
bindings from INPUT_TYPES/RETURN_TYPES, native PROV-O/NanoPub storage (see
PLAN.md's Format decision) -- this writes RO-Crate JSON-LD directly as the
working format, not as a derived export from an RDF layer that doesn't
exist yet.
"""

import asyncio
import hashlib
import inspect
import json
import logging
import os
import shutil
import time
import urllib.parse

import folder_paths
import nodes as comfy_nodes

from ..provider import provider

_logger = logging.getLogger(__name__)

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
CRATE_SUBFOLDER = "flair_crates"
RETENTION_SECONDS = 7 * 24 * 60 * 60
WORKFLOW_RUN_PROFILE = "https://w3id.org/ro/wfrun/process/0.5"
PROVENANCE_RUN_PROFILE = "https://w3id.org/ro/wfrun/provenance/0.5"


def _save_artifact(value, directory, base_name):
    """
    Saves a single node output value as a real file, returning (filename,
    encoding_format). Handles the shapes FLAIR nodes actually produce
    today (an IMAGE tensor, a pandas DataFrame); anything else falls back
    to a text repr so packaging never hard-fails on an unrecognized type --
    just produces a less useful File entity, which is honest given we
    don't know how to serialize it properly yet.
    """
    # IMAGE tensor: (1, H, W, 3) float32 [0, 1] -- see flair-analytics'
    # _figure_to_image_tensor for the inverse of this conversion.
    if hasattr(value, "shape") and hasattr(value, "numpy"):
        import numpy as np
        from PIL import Image

        arr = value
        if len(arr.shape) == 4:
            arr = arr[0]
        arr = (arr.numpy() * 255).astype(np.uint8)
        filename = f"{base_name}.png"
        Image.fromarray(arr).save(os.path.join(directory, filename))
        return filename, "image/png"

    if hasattr(value, "to_csv"):
        filename = f"{base_name}.csv"
        value.to_csv(os.path.join(directory, filename), index=False)
        return filename, "text/csv"

    filename = f"{base_name}.txt"
    with open(os.path.join(directory, filename), "w") as f:
        f.write(str(value))
    return filename, "text/plain"


def _sha256_of_file(path):
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _node_provenance_metadata(class_type):
    """
    Looks up what we can about a node class for its SoftwareApplication
    entity: (description, source_code_sha256). Returns (None, None) if the
    class can't be found or its source can't be read -- this must never
    break packaging over metadata that's inherently best-effort (a stock
    ComfyUI node, or a class that's since been removed/edited on disk
    since the process started).

    description: DESCRIPTION class attribute -- ComfyUI's own convention
    (shown as a UI tooltip, not something FLAIR invented). Per Alberto's
    request that node descriptions be part of captured provenance, not
    just a source comment.

    source_code_sha256: SHA-256 of the class's actual Python source
    (inspect.getsource), not a manually-maintained version number.
    Deliberately not the project's repo-wide VERSION (also included
    separately, see softwareVersion below) -- a human-maintained version
    number only changes if someone remembers to bump it, and a stale "GUID
    that's the same after modification" is explicitly the failure mode
    flagged as unacceptable. A content hash is correct by construction:
    it's mechanically impossible for it to stay the same if the node's
    code changed, and impossible for it to differ if the code didn't,
    with no bump-discipline required from anyone.
    """
    cls = comfy_nodes.NODE_CLASS_MAPPINGS.get(class_type)
    if cls is None:
        return None, None

    description = getattr(cls, "DESCRIPTION", None)

    try:
        source = inspect.getsource(cls)
        source_hash = hashlib.sha256(source.encode("utf-8")).hexdigest()
    except (OSError, TypeError):
        source_hash = None

    return description, source_hash


def _flair_version():
    """
    Reads the FLAIR-GG toolchain's repo-wide VERSION (bumped every session
    per this project's changelog convention -- see docker-compose.yml's
    mount of ../VERSION). Human-readable and useful for correlating with
    CHANGELOG.md, but NOT the mechanism relied on for "did this exact node
    change" -- that's source_code_sha256 above, which can't drift stale.
    """
    try:
        with open("/app/ComfyUI/flair_version.txt") as f:
            return f.read().strip()
    except OSError:
        return None


def _sweep_old_crates(crates_dir):
    """
    Deletes any crate zip older than RETENTION_SECONDS. Simpler than a
    delete-after-download route (which would need its own aiohttp route
    with deferred registration, since PromptServer.instance isn't
    available at package-import time -- see PLAN.md) and, per the user,
    "basically solves the problem": don't retain people's results
    indefinitely, without needing to detect a completed download. Scoped
    to CRATE_SUBFOLDER specifically, never the wider output/ tree, so a
    bug here can't delete something unrelated a user saved.
    """
    now = time.time()
    try:
        entries = os.listdir(crates_dir)
    except FileNotFoundError:
        return

    for name in entries:
        if not name.endswith(".zip"):
            continue
        path = os.path.join(crates_dir, name)
        try:
            age = now - os.path.getmtime(path)
            if age > RETENTION_SECONDS:
                os.remove(path)
                _logger.info(
                    "[FLAIR provenance] deleted crate older than %d day(s): %s",
                    RETENTION_SECONDS // 86400,
                    name,
                )
        except OSError as exc:
            _logger.warning("[FLAIR provenance] couldn't sweep %s: %s", path, exc)


class FLAIR_PackageProvenanceCrate:
    """
    Wired to the workflow's actual terminal output(s) as a genuine data
    input (not a synthetic provenance pin) -- gets correct execution
    ordering for free from ComfyUI's own dependency scheduler, since it
    only runs after everything it depends on is done.

    Accepts multiple terminal outputs: set INPUT_IS_LIST = True and pair
    with the stock `Create List` node upstream (bundle several same-typed
    outputs into one list there first, then wire that into final_output
    here). INPUT_IS_LIST also means a single directly-wired output arrives
    as a length-1 list -- every input is a list either way, so there's one
    code path instead of two.

    Reads FLAIRProvenanceCacheProvider's store for the CURRENT prompt (not
    "last_completed" -- this node IS part of the run it's packaging).
    Because on_store is dispatched as a fire-and-forget asyncio task with no
    ordering guarantee (see PLAN.md), some immediately-prior sibling nodes'
    records may not have landed yet by the time this node's own FUNCTION
    starts. Mitigation, not a guarantee: this node's FUNCTION is async and
    yields to the event loop a few times before reading the store, giving
    those background tasks a real chance to finish first. The crate records
    how many executions it actually captured so this is never silently
    incomplete.

    The crate is zipped into a single file under output/flair_crates/
    rather than left as a loose folder -- both because RO-Crates are
    conventionally distributed that way, and because it's what makes the
    crate downloadable at all: ComfyUI's own /view endpoint already serves
    any file type from output/ generically (checked directly in server.py,
    not assumed), so a single zip gets a real, working download URL for
    free -- no new server route needed, no shared filesystem with the VP
    needed either.

    Crates older than a week are swept (deleted) each time a new one is
    written, scoped to output/flair_crates/ specifically -- the user didn't
    want results retained on the server indefinitely, and this is simpler
    than a real delete-after-download route (which would need its own
    aiohttp route with deferred registration, since PromptServer.instance
    isn't ready at package-import time -- see PLAN.md) while still solving
    the actual concern.
    """

    INPUT_IS_LIST = True

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "final_output": ("*",),
            },
            "optional": {
                "crate_name": ("STRING", {"default": "flair-run"}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("crate_url",)
    FUNCTION = "package"
    OUTPUT_NODE = True
    CATEGORY = "FLAIR/provenance"
    DESCRIPTION = (
        "Packages this run's captured provenance and its terminal output(s) "
        "into a Workflow Run RO-Crate (Provenance Run Crate profile), "
        "zipped for download. Wire the workflow's actual final output(s) "
        "in -- for multiple outputs, bundle them with a stock Create List "
        "node first."
    )

    async def package(self, final_output, crate_name=("flair-run",)):
        # INPUT_IS_LIST wraps every input, including plain widgets -- take
        # the first (only) crate_name value regardless of how it arrived.
        crate_name = crate_name[0] if crate_name else "flair-run"

        # Let pending on_store tasks for sibling nodes flush before we read
        # the store -- see class docstring. Not a guarantee, just improves
        # the odds substantially; asyncio.sleep(0) yields once, a few
        # passes gives multiple pending tasks a turn each.
        for _ in range(5):
            await asyncio.sleep(0)

        prompt_id = provider.current_prompt_id
        records = list(provider.store.get(prompt_id, [])) if prompt_id else []

        crates_dir = os.path.join(folder_paths.get_output_directory(), CRATE_SUBFOLDER)
        os.makedirs(crates_dir, exist_ok=True)
        _sweep_old_crates(crates_dir)

        work_dir = os.path.join(crates_dir, f"{crate_name}_{prompt_id or 'unknown'}")
        os.makedirs(work_dir, exist_ok=True)

        artifacts = []
        for i, item in enumerate(final_output):
            suffix = "" if len(final_output) == 1 else f"_{i}"
            filename, encoding_format = _save_artifact(item, work_dir, f"final_output{suffix}")
            path = os.path.join(work_dir, filename)
            artifacts.append(
                {
                    "filename": filename,
                    "encoding_format": encoding_format,
                    "sha256": _sha256_of_file(path),
                    "size": os.path.getsize(path),
                }
            )

        graph = self._build_graph(records=records, artifacts=artifacts)
        crate = {"@context": RO_CRATE_CONTEXT, "@graph": graph}
        with open(os.path.join(work_dir, "ro-crate-metadata.json"), "w") as f:
            json.dump(crate, f, indent=2)

        zip_path = shutil.make_archive(work_dir, "zip", work_dir)
        shutil.rmtree(work_dir)
        zip_filename = os.path.basename(zip_path)

        # FLAIR_PUBLIC_URL (set in docker-compose.yml's environment: block
        # by whoever deploys this, not something an end user ever sees or
        # configures) turns this into a fully-qualified URL that can be
        # copy-pasted into any browser tab. Falls back to a relative path
        # if unset -- correct behavior for local dev (venv/direct
        # 127.0.0.1 access), just requires manually prepending the host.
        base_url = os.environ.get("FLAIR_PUBLIC_URL", "").rstrip("/")
        crate_url = (
            base_url
            + "/view?filename=" + urllib.parse.quote(zip_filename)
            + "&subfolder=" + urllib.parse.quote(CRATE_SUBFOLDER)
            + "&type=output"
        )

        _logger.info(
            "[FLAIR provenance] packaged crate at %s (%s): %d node execution(s), "
            "%d artifact(s) captured for prompt %s (some upstream nodes may be "
            "missing if their provenance hadn't landed yet -- see this node's "
            "docstring)",
            zip_path,
            crate_url,
            len(records),
            len(artifacts),
            prompt_id,
        )

        return (crate_url,)

    @staticmethod
    def _build_graph(records, artifacts):
        now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

        graph = [
            {
                "@id": "ro-crate-metadata.json",
                "@type": "CreativeWork",
                "about": {"@id": "./"},
                "conformsTo": [
                    {"@id": "https://w3id.org/ro/crate/1.1"},
                    {"@id": WORKFLOW_RUN_PROFILE},
                    {"@id": PROVENANCE_RUN_PROFILE},
                ],
            },
            {
                "@id": "./",
                "@type": "Dataset",
                "name": "FLAIR-GG ComfyUI workflow run",
                "datePublished": now,
                "hasPart": [{"@id": a["filename"]} for a in artifacts]
                + [{"@id": f"#action-{r['node_id']}"} for r in records],
            },
        ]

        for a in artifacts:
            graph.append(
                {
                    "@id": a["filename"],
                    "@type": "File",
                    "contentSize": str(a["size"]),
                    "sha256": a["sha256"],
                    "encodingFormat": a["encoding_format"],
                }
            )

        flair_version = _flair_version()
        tools_seen = set()
        for record in records:
            class_type = record["class_type"]
            tool_id = f"#node-{class_type}"
            if class_type not in tools_seen:
                tools_seen.add(class_type)
                tool_entity = {
                    "@id": tool_id,
                    "@type": "SoftwareApplication",
                    "name": class_type,
                }
                description, source_hash = _node_provenance_metadata(class_type)
                if description:
                    tool_entity["description"] = description
                if flair_version:
                    tool_entity["softwareVersion"] = flair_version
                if source_hash:
                    # Not a schema.org-standard property (there isn't one
                    # for "exact source code identity" -- softwareVersion
                    # above is the closest standard field, but see
                    # _node_provenance_metadata's docstring for why a
                    # content hash is the actual correctness guarantee,
                    # not the human-maintained version number).
                    tool_entity["flair:sourceCodeSha256"] = source_hash
                graph.append(tool_entity)

            graph.append(
                {
                    "@id": f"#action-{record['node_id']}",
                    "@type": "CreateAction",
                    "name": f"Execution of {class_type} (node {record['node_id']})",
                    "instrument": {"@id": tool_id},
                    # Already ISO 8601 -- provider.py stores it that way at
                    # the source now, not a raw epoch float.
                    "endTime": record["timestamp"],
                    # Not yet real FormalParameter bindings (see module
                    # docstring) -- input_hash lets a repeat run be checked
                    # for identical inputs even without literal values.
                    "flair:inputHash": record["input_hash"],
                    "flair:outputSummary": record["outputs"],
                }
            )

        return graph


NODE_CLASS_MAPPINGS = {
    "FLAIR_PackageProvenanceCrate": FLAIR_PackageProvenanceCrate,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_PackageProvenanceCrate": "Package FLAIR Provenance (RO-Crate)",
}
