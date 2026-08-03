# Useless Text Pipeline (ComfyUI custom nodes)

A gloriously pointless text pipeline for ComfyUI: type text in, get it
CAPITALIZED and word-scrambled out.

## Install

1. Copy this whole folder into `ComfyUI/custom_nodes/`, e.g.:

   ```
   ComfyUI/
     custom_nodes/
       comfyui-useless-text-nodes/
         __init__.py
         nodes.py
   ```

2. Restart ComfyUI (custom nodes are only scanned on startup).
3. In the node search / right-click "Add Node" menu, look under
   **useless > text**. You should see four nodes:
   - Load Useless Text 📝
   - CAPITALIZE 🔠
   - Rearrange Words 🔀
   - Show Text 👀

## Wire it up

`Load Useless Text` → `CAPITALIZE` → `Rearrange Words` → `Show Text`

Connect each node's `text` output socket to the next node's `text`
input socket. Queue the prompt and the final scrambled, shouty text
will render under the "Show Text" node.

## How the interface works (the bit you actually care about)

- `INPUT_TYPES()` is a classmethod ComfyUI calls to build the node's
  sockets/widgets. `"required"` entries become input sockets (or
  widgets if not wired); each value is `(TYPE, options_dict)`.
  - `"STRING"` + `{"multiline": True}` → a text box widget
  - `"STRING"` + `{"forceInput": True}` → forces it to be a wired
    socket instead of an editable widget
  - A Python list like `["shuffle", "reverse"]` as the type → a
    dropdown widget
- `RETURN_TYPES` is a tuple of output socket types; `RETURN_NAMES`
  labels them.
- `FUNCTION` names the method ComfyUI actually calls with your inputs
  as kwargs.
- `CATEGORY` controls the submenu path in the node picker.
- `OUTPUT_NODE = True` marks a node as a pipeline terminus whose
  result gets pushed back to the browser UI (that's how "Show Text"
  displays its value on the node itself).

## Extending it

Some easy next steps if you want to keep playing:
- Add a `ReverseCharacters` node (`text[::-1]`).
- Add a `PigLatin` node.
- Add an `INT` "repeat" widget that repeats the text N times.
- Add a second output socket (e.g. word count) — just extend
  `RETURN_TYPES`/`RETURN_NAMES` and return a longer tuple.
- For a fancier live-updating text box widget (instead of the default
  UI text dump), you'd add a small JS file under a `web/` directory
  and register it — that's the point where ComfyUI custom nodes start
  talking to its frontend extension system, if you want to go further
  down that rabbit hole later.