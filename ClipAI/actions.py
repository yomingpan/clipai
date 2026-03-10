
import logging
import os
import yaml

logger = logging.getLogger(__name__)


def load_config(path: str):
    """Load the main configuration file (provider, app, tts settings)."""
    with open(path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    return cfg or {}


def _resolve_prompt_files(actions, base_dir: str):
    """Resolve ``prompt_file`` / ``system_prompt_file`` references in actions.

    For each action that has a ``prompt_file`` or ``system_prompt_file`` key,
    read the referenced text file (relative to *base_dir*) and store the
    content under the corresponding ``prompt`` or ``system_prompt`` key.
    The ``*_file`` key is removed after resolution so downstream consumers
    see only the standard ``prompt`` / ``system_prompt`` keys.

    If the referenced file does not exist, a warning is logged and the
    ``prompt`` / ``system_prompt`` key is set to an empty string.
    """
    for action in actions or []:
        for file_key, content_key in [
            ("prompt_file", "prompt"),
            ("system_prompt_file", "system_prompt"),
        ]:
            file_ref = action.get(file_key)
            if not file_ref:
                continue
            full_path = os.path.join(base_dir, file_ref)
            if os.path.isfile(full_path):
                try:
                    with open(full_path, "r", encoding="utf-8") as f:
                        action[content_key] = f.read()
                except Exception as exc:
                    logger.warning(
                        "Failed to read prompt file %s: %s", full_path, exc
                    )
                    action[content_key] = ""
            else:
                logger.warning(
                    "Prompt file not found: %s (referenced by action '%s')",
                    full_path,
                    action.get("id", "unknown"),
                )
                action[content_key] = ""
            del action[file_key]
    return actions


def load_actions(config_path: str):
    """Load action definitions from actions.yaml (or fall back to config.yaml).

    Looks for ``actions.yaml`` in the same directory as *config_path*.
    If the file exists and contains an ``actions`` key, those definitions are
    returned.  Otherwise, falls back to reading the ``actions`` key from
    *config_path* itself (backward compatibility).

    After loading, any ``prompt_file`` / ``system_prompt_file`` references are
    resolved by reading the corresponding text files.

    Returns:
        list: A list of action definition dicts.
    """
    config_dir = os.path.dirname(os.path.abspath(config_path))
    actions_path = os.path.join(config_dir, "actions.yaml")

    # Primary: load from dedicated actions.yaml
    if os.path.isfile(actions_path):
        with open(actions_path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        actions = data.get("actions")
        if actions is not None:
            return _resolve_prompt_files(actions, config_dir)

    # Fallback: load from config.yaml (backward compatibility)
    cfg = load_config(config_path)
    actions = cfg.get("actions", [])
    return _resolve_prompt_files(actions, config_dir)


def build_action_map(actions):
    out = {}
    for a in actions or []:
        action_id = a.get("id")
        if not action_id:
            continue
        out[action_id] = a
    return out



