import yaml


def load_config(path: str):
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def build_action_map(actions):
    out = {}
    for a in actions:
        out[a["id"]] = a
    return out
