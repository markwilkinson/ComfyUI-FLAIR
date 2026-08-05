"""
Merges NODE_CLASS_MAPPINGS/NODE_DISPLAY_NAME_MAPPINGS from each node-category
submodule. Add a new submodule (e.g. a future packaging.py) and register it
in _SUBMODULES below -- that's the only wiring needed for it to be picked
up by ComfyUI.
"""

from . import inspection, packaging

_SUBMODULES = (inspection, packaging)

NODE_CLASS_MAPPINGS = {}
NODE_DISPLAY_NAME_MAPPINGS = {}

for _module in _SUBMODULES:
    NODE_CLASS_MAPPINGS.update(_module.NODE_CLASS_MAPPINGS)
    NODE_DISPLAY_NAME_MAPPINGS.update(_module.NODE_DISPLAY_NAME_MAPPINGS)
