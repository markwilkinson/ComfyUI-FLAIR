#!/usr/bin/env bash
# Copies named items from a ComfyUI-FLAIR-Catalog checkout into this repo's
# custom-nodes/ or workflows/ directory. See ../README.md's "Installing from
# the catalog" section and https://github.com/markwilkinson/ComfyUI-FLAIR-Catalog
# for what's available.
#
# Usage:
#   scripts/install_from_catalog.sh <item> [<item> ...]
#
# Looks for the catalog at ../ComfyUI-FLAIR-Catalog by default (a sibling
# clone, same convention this repo already uses for ComfyUI itself).
# Override with CATALOG_DIR=/path/to/catalog.
#
# For each item, checks nodes/<item>/ first, then workflows/<item>.json.
# Copies (not symlinks) so the result works unchanged with this repo's
# existing whole-directory Docker bind-mounts of custom-nodes/ and
# workflows/ -- a symlink into a sibling repo would dangle inside the
# container, which only ever sees this repo's own tree.
#
# Does not git add or commit anything -- review with `git status`/`git diff`
# and commit it yourself, same as any other change to your deployment.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
CATALOG_DIR="${CATALOG_DIR:-$REPO_ROOT/../ComfyUI-FLAIR-Catalog}"

if [ "$#" -eq 0 ]; then
    echo "Usage: $0 <item> [<item> ...]" >&2
    exit 1
fi

if [ ! -d "$CATALOG_DIR" ]; then
    echo "Catalog not found at $CATALOG_DIR" >&2
    echo "Clone it as a sibling of this repo, or set CATALOG_DIR:" >&2
    echo "  git clone https://github.com/markwilkinson/ComfyUI-FLAIR-Catalog $REPO_ROOT/../ComfyUI-FLAIR-Catalog" >&2
    exit 1
fi

list_available() {
    echo "Available in $CATALOG_DIR:" >&2
    for d in "$CATALOG_DIR"/nodes/*/; do
        [ -d "$d" ] && echo "  node:     $(basename "$d")" >&2
    done
    for f in "$CATALOG_DIR"/workflows/*.json; do
        [ -f "$f" ] && echo "  workflow: $(basename "$f" .json)" >&2
    done
}

for item in "$@"; do
    node_src="$CATALOG_DIR/nodes/$item"
    workflow_src="$CATALOG_DIR/workflows/$item.json"

    if [ -d "$node_src" ]; then
        dest="$REPO_ROOT/custom-nodes/$item"
        rm -rf "$dest"
        cp -r "$node_src" "$dest"
        find "$dest" -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
        echo "Installed node package: custom-nodes/$item"
    elif [ -f "$workflow_src" ]; then
        dest="$REPO_ROOT/workflows/$item.json"
        cp "$workflow_src" "$dest"
        echo "Installed workflow: workflows/$item.json"
    else
        echo "Error: '$item' not found in catalog (checked nodes/$item/ and workflows/$item.json)" >&2
        list_available
        exit 1
    fi
done

echo
echo "Done. Review with 'git status'/'git diff' and commit when ready."
