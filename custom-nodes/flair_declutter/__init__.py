"""
FLAIR declutter: hide Stable-Diffusion/diffusion-model nodes from the picker
without touching ComfyUI core.

How it fits into ComfyUI's startup sequence (see nodes.py):
    1. init_builtin_extra_nodes() imports every file in comfy_extras/ and
       registers all classes into the global nodes.NODE_CLASS_MAPPINGS dict.
    2. init_external_custom_nodes() then imports every package under
       custom_nodes/, via os.listdir() order. This package is one of them.
    3. Because (1) always finishes before (2) starts, by the time this file
       runs, every core + comfy_extras node is already sitting in
       nodes.NODE_CLASS_MAPPINGS. We don't prevent anything from loading; we
       just pop the entries we don't want out of the registry before the
       server advertises them to the frontend (/object_info) or the node
       search UI.

IMPORTANT: os.listdir() order is NOT alphabetical -- it's filesystem-
dependent and effectively arbitrary. That means other custom_nodes/
packages (a future FLAIR node package, useless_text, a third-party pack)
can load either before or after this one on any given run. A pruning pass
that only runs once, at this file's own import time, would only see
whatever happened to already be registered -- silently and
nondeterministically hiding anything that loads later. To close that gap,
after the initial sweep below we also wrap nodes.load_custom_node so every
subsequent custom-node package that loads (regardless of order) triggers
another pass. The pass is idempotent and cheap, so re-running it after each
load is fine.

Two node-definition styles exist in this ComfyUI version, so category lookup
has to handle both:
    - "V1" classes: a plain CATEGORY = "..." class attribute.
    - "V3" classes (io.ComfyNode subclasses): category lives on the Schema
      returned by the class's GET_SCHEMA() classmethod.

Decision rule per node, in order:
    1. Name in ALWAYS_KEEP            -> keep, no matter what.
    2. Name in ALWAYS_HIDE             -> hide, no matter what.
    3. Category's top-level segment (the part before the first "/") is in
       ALLOWED_CATEGORY_PREFIXES       -> keep.
    4. Otherwise                       -> hide.

This is a runtime filter, not a source patch: it never edits nodes.py or any
comfy_extras/*.py file, so it survives `git pull` on ComfyUI unchanged. The
trade-off is that every node still gets imported at startup (cheap - no
model weights are loaded just by importing a node class), it's just kept out
of the registry the frontend reads from.

Tune the three lists below as you find nodes that are mis-classified.
"""

import logging

import nodes as _nodes_module

# Top-level category segment (string before the first "/") that we keep.
# Everything else (model/*, advanced/*, 3d/*, audio/*, video/* etc.) is
# Stable-Diffusion/diffusion-workflow territory and gets hidden.
ALLOWED_CATEGORY_PREFIXES = {
    "image",
    "text",
    "utilities",
    "Basics",
    "Image Tools",
    "dataset",
    "FLAIR",  # our own future capture/packaging nodes
    "useless",  # useless_text demo package (custom-nodes/useless_text)
}

# Force-keep by exact NODE_CLASS_MAPPINGS key, regardless of category.
ALWAYS_KEEP = {
    # e.g. "PreviewAny",
}

# Force-hide by exact NODE_CLASS_MAPPINGS key, regardless of category
# (use this for stragglers that slip in under an allowed category).
ALWAYS_HIDE = {
    # e.g. "SomeNode",
}


def _category_of(node_cls):
    cat = getattr(node_cls, "CATEGORY", None)
    if cat is not None:
        return cat
    get_schema = getattr(node_cls, "GET_SCHEMA", None)
    if callable(get_schema):
        try:
            return get_schema().category
        except Exception:
            return None
    return None


def _should_hide(name, node_cls):
    if name in ALWAYS_KEEP:
        return False
    if name in ALWAYS_HIDE:
        return True
    category = _category_of(node_cls)
    if category is None:
        return False  # unknown shape: leave it visible rather than guess
    top_level = category.split("/", 1)[0]
    return top_level not in ALLOWED_CATEGORY_PREFIXES


def _declutter():
    mappings = _nodes_module.NODE_CLASS_MAPPINGS
    display_names = _nodes_module.NODE_DISPLAY_NAME_MAPPINGS

    hidden = []
    for name, node_cls in list(mappings.items()):
        if _should_hide(name, node_cls):
            hidden.append(name)
            mappings.pop(name, None)
            display_names.pop(name, None)

    if hidden:
        logging.info(
            "[FLAIR declutter] hid %d more SD/diffusion node(s), %d nodes remain visible",
            len(hidden),
            len(mappings),
        )
        logging.debug("[FLAIR declutter] hidden this pass: %s", sorted(hidden))


_declutter()

# Cover packages that load after us in os.listdir()'s arbitrary order (see
# module docstring): re-run the sweep after every subsequent custom-node
# package finishes loading, so visibility never depends on load order.
_original_load_custom_node = _nodes_module.load_custom_node


async def _load_custom_node_then_declutter(*args, **kwargs):
    result = await _original_load_custom_node(*args, **kwargs)
    _declutter()
    return result


_nodes_module.load_custom_node = _load_custom_node_then_declutter

# Required so ComfyUI's loader treats this as a valid (if empty) node
# package instead of logging an "import failed" warning at startup.
NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}
