import yaml


DEFAULTS = {
    "app": {
        "auto_paste_default": False,
        "add_result_header": False,
    },
    "safety": {
        "mode": "block",
    },
}


def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def build_action_map(actions):
    out = {}
    for a in actions or []:
        action_id = a.get("id")
        if not action_id:
            continue
        out[action_id] = a
    return out
