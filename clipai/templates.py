
def render_template(text: str, context: dict) -> str:
    if text is None:
        return ""
    out = text
    for k, v in context.items():
        out = out.replace("{{" + k + "}}", v)
    return out
