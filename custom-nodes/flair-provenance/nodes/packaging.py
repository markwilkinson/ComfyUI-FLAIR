"""
The packaging node: turns what FLAIRProvenanceCacheProvider has captured
for the current run into a Workflow Run RO-Crate. See ../PLAN.md.

v1 scope, deliberately not the full spec in one shot (matching how every
other FLAIR node started simple and iterated): one real terminal output
saved as a File entity, one CreateAction per captured node execution, one
SoftwareApplication per distinct node class acting as `instrument`. Not yet
built: full FormalParameter bindings from INPUT_TYPES/RETURN_TYPES,
multi-terminal-output support, native PROV-O/NanoPub storage (see PLAN.md's
Format decision) -- this writes RO-Crate JSON-LD directly as the working
format, not as a derived export from an RDF layer that doesn't exist yet.
"""

import asyncio
import hashlib
import io
import json
import logging
import os
import time

import folder_paths

from ..provider import provider

_logger = logging.getLogger(__name__)

RO_CRATE_CONTEXT = "https://w3id.org/ro/crate/1.1/context"
WORKFLOW_RUN_PROFILE = "https://w3id.org/ro/wfrun/process/0.5"
PROVENANCE_RUN_PROFILE = "https://w3id.org/ro/wfrun/provenance/0.5"


def _save_artifact(value, directory, base_name):
    """
    Saves a node output value as a real file, returning (filename,
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


class FLAIR_PackageProvenanceCrate:
    """
    Wired to the workflow's actual terminal output as a genuine data input
    (not a synthetic provenance pin) -- gets correct execution ordering for
    free from ComfyUI's own dependency scheduler, since it only runs after
    everything it depends on is done.

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
    """

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
    RETURN_NAMES = ("crate_path",)
    FUNCTION = "package"
    OUTPUT_NODE = True
    CATEGORY = "FLAIR/provenance"

    async def package(self, final_output, crate_name="flair-run"):
        # Let pending on_store tasks for sibling nodes flush before we read
        # the store -- see class docstring. Not a guarantee, just improves
        # the odds substantially; asyncio.sleep(0) yields once, a few
        # passes gives multiple pending tasks a turn each.
        for _ in range(5):
            await asyncio.sleep(0)

        prompt_id = provider.current_prompt_id
        records = list(provider.store.get(prompt_id, [])) if prompt_id else []

        crate_dir = os.path.join(
            folder_paths.get_output_directory(), f"{crate_name}_{prompt_id or 'unknown'}"
        )
        os.makedirs(crate_dir, exist_ok=True)

        artifact_name, encoding_format = _save_artifact(
            final_output, crate_dir, "final_output"
        )
        artifact_path = os.path.join(crate_dir, artifact_name)
        artifact_hash = _sha256_of_file(artifact_path)
        artifact_size = os.path.getsize(artifact_path)

        graph = self._build_graph(
            records=records,
            artifact_name=artifact_name,
            artifact_hash=artifact_hash,
            artifact_size=artifact_size,
            encoding_format=encoding_format,
        )

        crate = {"@context": RO_CRATE_CONTEXT, "@graph": graph}
        metadata_path = os.path.join(crate_dir, "ro-crate-metadata.json")
        with open(metadata_path, "w") as f:
            json.dump(crate, f, indent=2)

        _logger.info(
            "[FLAIR provenance] packaged crate at %s: %d node execution(s) captured "
            "for prompt %s (some upstream nodes may be missing if their "
            "provenance hadn't landed yet -- see this node's docstring)",
            crate_dir,
            len(records),
            prompt_id,
        )

        return (crate_dir,)

    @staticmethod
    def _build_graph(records, artifact_name, artifact_hash, artifact_size, encoding_format):
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
                "hasPart": [{"@id": artifact_name}]
                + [{"@id": f"#action-{r['node_id']}"} for r in records],
            },
            {
                "@id": artifact_name,
                "@type": "File",
                "contentSize": str(artifact_size),
                "sha256": artifact_hash,
                "encodingFormat": encoding_format,
            },
        ]

        tools_seen = set()
        for record in records:
            class_type = record["class_type"]
            tool_id = f"#node-{class_type}"
            if class_type not in tools_seen:
                tools_seen.add(class_type)
                graph.append(
                    {
                        "@id": tool_id,
                        "@type": "SoftwareApplication",
                        "name": class_type,
                    }
                )

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
