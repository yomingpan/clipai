import keyboard


def register_hotkeys(action_map, dispatcher):
    for action_id, action in action_map.items():
        hk = action.get("hotkey")
        if not hk:
            continue

        def make_handler(aid):
            return lambda: dispatcher(aid)

        keyboard.add_hotkey(hk, make_handler(action_id))
        print(f"[clipai] Hotkey registered: {hk} -> {action['name']}")
