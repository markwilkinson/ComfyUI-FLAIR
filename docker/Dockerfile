# CPU-only ComfyUI, pinned to a known-good commit, with FLAIR's custom nodes
# and all mutable data (models/input/output/user) left OUT of the image on
# purpose -- they're bind-mounted at runtime (see docker-compose.yml). This
# image is meant to be rebuilt rarely (only when bumping the pinned ComfyUI
# commit); day-to-day node development never requires a rebuild.

FROM python:3.10-slim AS base

# Pin to the exact commit this project was developed and tested against.
# Bump deliberately -- don't float on a branch.
ARG COMFYUI_REF=14b05228cef127ce529bc0c08660770d4af3e9a8

RUN apt-get update && apt-get install -y --no-install-recommends \
        git \
        build-essential \
        libgl1 \
        libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

RUN git clone https://github.com/Comfy-Org/ComfyUI.git ComfyUI \
    && cd ComfyUI \
    && git checkout ${COMFYUI_REF}

WORKDIR /app/ComfyUI

# CPU-only torch build (no CUDA/GPU in this deployment -- see handoff.md's
# deployment plan for why: no diffusion-model workload, so no GPU need).
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir torch torchvision torchaudio \
        --index-url https://download.pytorch.org/whl/cpu \
    && pip install --no-cache-dir -r requirements.txt

# Strip the Stable-Diffusion workflow-template gallery (the "Templates" menu
# in the frontend) -- ~420MB of packaged SD workflow JSON + thumbnail/preview
# media across comfyui-workflow-templates and its per-media-type sub-
# packages, none of it relevant to a non-SD deployment. requirements.txt is
# left untouched (same prune-after-install approach as flair_declutter, not
# a source patch): ComfyUI's own FrontendManager (app/frontend_management.py)
# already handles this package being absent -- it catches the ImportError,
# logs it, and simply never registers the /templates route, so the frontend
# just shows no templates instead of failing to start.
RUN pip uninstall -y \
        comfyui-workflow-templates \
        comfyui-workflow-templates-core \
        comfyui-workflow-templates-json \
        comfyui-workflow-templates-media-api \
        comfyui-workflow-templates-media-image \
        comfyui-workflow-templates-media-video \
        comfyui-workflow-templates-media-other \
        comfyui-workflow-templates-media-assets-01 \
    || true

# FLAIR node dependencies. custom_nodes/ itself is bind-mounted at runtime
# (see docker-compose.yml), not baked into the image, so the Dockerfile has
# no way to discover what a given node needs automatically -- unlike a code
# change under custom-nodes/, adding a new import to a FLAIR node DOES
# require adding it here and rebuilding the image. Keep this list in sync
# with what the nodes under ../custom-nodes/*/nodes/*.py actually import.
RUN pip install --no-cache-dir \
        pandas

# Data directories that get bind-mounted over at runtime. Creating them here
# means a fresh container has correct empty dirs even before any volume is
# attached (e.g. `docker run` without compose).
RUN mkdir -p models input output user custom_nodes

EXPOSE 8188

# --listen 0.0.0.0 is required inside a container: ComfyUI's default
# (127.0.0.1) would be unreachable from outside the container network
# namespace. --cpu is required even with the CPU-only torch build above --
# without it ComfyUI still tries torch.cuda.current_device() and crashes.
ENTRYPOINT ["python", "main.py", "--listen", "0.0.0.0", "--port", "8188", "--cpu"]
