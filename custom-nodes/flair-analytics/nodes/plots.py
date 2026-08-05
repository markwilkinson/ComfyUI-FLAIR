"""
Plot nodes -- render a DATAFRAME into a ComfyUI IMAGE tensor via
matplotlib/seaborn, so charts feed into stock PreviewImage/SaveImage nodes
like any other image. See ../PLAN.md.
"""

import io
import logging

import matplotlib

matplotlib.use("Agg")  # headless: no display in a server/container context
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import seaborn as sns  # noqa: E402
import torch  # noqa: E402
from PIL import Image  # noqa: E402


def _figure_to_image_tensor(fig):
    """
    Renders a matplotlib Figure to a ComfyUI IMAGE tensor: float32, [0, 1],
    shape (1, H, W, 3) -- the same format nodes.LoadImage produces, so the
    result can feed straight into stock PreviewImage/SaveImage.
    """
    buf = io.BytesIO()
    fig.savefig(buf, format="png", bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    img = Image.open(buf).convert("RGB")
    arr = np.array(img).astype(np.float32) / 255.0
    return torch.from_numpy(arr)[None,]


class FLAIR_PlotCategoryCounts:
    """
    Bar plot of how many rows fall into each value of a category column.
    Mirrors iucn_categorization.ipynb cell 4 (sns.countplot), generalized to
    any category column/order rather than hardcoded to IUCN categories, so
    other notebooks with the same "count rows per category" shape
    (e.g. phenotypefrequency.ipynb) can reuse it.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "data": ("DATAFRAME",),
                "category_column": (
                    "STRING",
                    {"default": "IUCN_endangerment_category"},
                ),
            },
            "optional": {
                "category_order": (
                    "STRING",
                    {
                        "default": "Vulnerable, Endangered, Critically endangered",
                        "tooltip": "Comma-separated category order, left to right. Leave empty for descending count order.",
                    },
                ),
                "title": ("STRING", {"default": "Distribution by Category"}),
            },
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("plot",)
    FUNCTION = "plot"
    CATEGORY = "FLAIR/plots"

    def plot(
        self,
        data,
        category_column,
        category_order="",
        title="Distribution by Category",
    ):
        if category_column not in data.columns:
            raise ValueError(
                f"Column '{category_column}' not found. Available columns: "
                f"{', '.join(data.columns)}"
            )

        order = [c.strip() for c in category_order.split(",") if c.strip()] or None

        sns.set_style("whitegrid")
        fig, ax = plt.subplots(figsize=(10, 6))
        # hue=category_column + legend=False is the current seaborn-approved
        # way to get a per-category palette without the "palette without
        # hue" deprecation warning that plain palette= now raises.
        sns.countplot(
            data=data,
            x=category_column,
            order=order,
            hue=category_column,
            palette="viridis",
            legend=False,
            ax=ax,
        )
        ax.set_title(title, fontsize=14)
        ax.set_xlabel(category_column, fontsize=12)
        ax.set_ylabel("Count", fontsize=12)

        logging.info(
            "[FLAIR_PlotCategoryCounts] plotted %d row(s) by '%s'",
            len(data),
            category_column,
        )

        return (_figure_to_image_tensor(fig),)


class FLAIR_PlotStackedCategoryCounts:
    """
    Stacked bar plot of category counts, grouped by a second column (e.g.
    provider/repository). Mirrors iucn_categorization.ipynb cell 5. Also
    returns a plain-text summary (category counts + group counts), matching
    what the notebook printed to stdout, since the notebook clearly treats
    that as real output the user cares about, not debug logging.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "data": ("DATAFRAME",),
                "group_column": ("STRING", {"default": "provider_host"}),
                "category_column": (
                    "STRING",
                    {"default": "IUCN_endangerment_category"},
                ),
            },
            "optional": {
                "category_order": (
                    "STRING",
                    {"default": "Vulnerable, Endangered, Critically endangered"},
                ),
                "title": ("STRING", {"default": "Categories by Group"}),
            },
        }

    RETURN_TYPES = ("IMAGE", "STRING")
    RETURN_NAMES = ("plot", "summary")
    FUNCTION = "plot"
    CATEGORY = "FLAIR/plots"

    def plot(
        self,
        data,
        group_column,
        category_column,
        category_order="",
        title="Categories by Group",
    ):
        for col in (group_column, category_column):
            if col not in data.columns:
                raise ValueError(
                    f"Column '{col}' not found. Available columns: "
                    f"{', '.join(data.columns)}"
                )

        order = [c.strip() for c in category_order.split(",") if c.strip()]

        pivot = data.pivot_table(
            index=group_column, columns=category_column, aggfunc="size", fill_value=0
        )
        if order:
            missing = [c for c in order if c not in pivot.columns]
            if missing:
                raise ValueError(
                    f"category_order value(s) not present in the data: "
                    f"{', '.join(missing)}. Present categories: "
                    f"{', '.join(str(c) for c in pivot.columns)}"
                )
            pivot = pivot[order]

        fig, ax = plt.subplots(figsize=(12, 7))
        pivot.plot(kind="bar", stacked=True, colormap="viridis", ax=ax)
        ax.set_title(title, fontsize=14)
        ax.set_xlabel(group_column, fontsize=12)
        ax.set_ylabel("Count", fontsize=12)
        ax.legend(title=category_column)
        plt.setp(ax.get_xticklabels(), rotation=45, ha="right")
        fig.tight_layout()

        category_counts = data[category_column].value_counts()
        group_counts = data[group_column].value_counts()
        summary = (
            f"{category_column} counts:\n{category_counts.to_string()}\n\n"
            f"{group_column} counts:\n{group_counts.to_string()}"
        )

        logging.info(
            "[FLAIR_PlotStackedCategoryCounts] plotted %d row(s) across %d group(s)",
            len(data),
            len(pivot),
        )

        return (_figure_to_image_tensor(fig), summary)


NODE_CLASS_MAPPINGS = {
    "FLAIR_PlotCategoryCounts": FLAIR_PlotCategoryCounts,
    "FLAIR_PlotStackedCategoryCounts": FLAIR_PlotStackedCategoryCounts,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "FLAIR_PlotCategoryCounts": "Plot FLAIR-GG Category Counts",
    "FLAIR_PlotStackedCategoryCounts": "Plot FLAIR-GG Categories by Group",
}
