"""
Useless Text Pipeline — a deliberately pointless ComfyUI node set.

Four nodes:
  LoadUselessText  -> a text box you type/paste into
  CapitalizeText   -> UPPERCASES the input
  RearrangeWords   -> shuffles or reverses word order
  ShowUselessText  -> displays the final string in the node UI

Chain them: Load -> Capitalize -> Rearrange -> Show
"""

import random


class LoadUselessText:
    """Entry point: a free-text widget."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": (
                    "STRING",
                    {
                        "multiline": True,
                        "default": "The quick brown fox jumps over the lazy dog",
                    },
                ),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "load"
    CATEGORY = "useless/text"

    def load(self, text):
        return (text,)


class CapitalizeText:
    """Uppercases every character in the incoming text."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                # forceInput=True means this socket must be wired,
                # rather than showing its own editable widget.
                "text": ("STRING", {"forceInput": True}),
            }
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "capitalize"
    CATEGORY = "useless/text"

    def capitalize(self, text):
        return (text.upper(),)


class RearrangeWords:
    """Shuffles (seeded) or reverses the word order of the input text."""

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "text": ("STRING", {"forceInput": True}),
                # A dropdown widget: pass a list as the type.
                "mode": (["shuffle", "reverse"], {"default": "shuffle"}),
            },
            "optional": {
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xFFFFFFFF}),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "rearrange"
    CATEGORY = "useless/text"

    def rearrange(self, text, mode, seed=0):
        words = text.split()
        if mode == "reverse":
            words = words[::-1]
        else:
            random.Random(seed).shuffle(words)
        return (" ".join(words),)


class ShowUselessText:
    """
    Terminal display node. OUTPUT_NODE=True tells ComfyUI this node's
    result should be sent back to the frontend UI (shown under the node)
    rather than only being an internal pipe. It also passes the value
    through as a real output, so you can keep chaining if you want.
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {"required": {"text": ("STRING", {"forceInput": True})}}

    INPUT_IS_LIST = True
    RETURN_TYPES = ("STRING",)
    FUNCTION = "notify"
    OUTPUT_NODE = True
    CATEGORY = "useless/text"

    def notify(self, text):
        return {"ui": {"text": text}, "result": (text,)}


# ComfyUI discovers custom nodes via these two dicts.
NODE_CLASS_MAPPINGS = {
    "LoadUselessText": LoadUselessText,
    "CapitalizeText": CapitalizeText,
    "RearrangeWords": RearrangeWords,
    "ShowUselessText": ShowUselessText,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "LoadUselessText": "Load Useless Text 📝",
    "CapitalizeText": "CAPITALIZE 🔠",
    "RearrangeWords": "Rearrange Words 🔀",
    "ShowUselessText": "Show Text 👀",
}
