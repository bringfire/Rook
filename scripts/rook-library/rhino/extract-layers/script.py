#! python 3
import json

import scriptcontext as sc


def _layer_to_dict(layer):
    color = layer.Color
    return {
        "name": layer.FullPath,
        "index": layer.Index,
        "id": str(layer.Id),
        "is_visible": bool(layer.IsVisible),
        "is_locked": bool(layer.IsLocked),
        "color": {
            "r": int(color.R),
            "g": int(color.G),
            "b": int(color.B),
        },
    }


layers = [_layer_to_dict(layer) for layer in sc.doc.Layers if layer is not None]
print(json.dumps({"layers": layers}, sort_keys=True))
