import re


def _escape(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _inline(text):
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)", r"<i>\1</i>", text)
    text = re.sub(r"`(.+?)`", r'<span background="#f0f0f0" foreground="#d63384">\1</span>', text)
    text = re.sub(r"\[(.+?)\]\((.+?)\)", r'<a href="\2">\1</a>', text)
    return text


def markdown_to_pango(text):
    if not text:
        return ""

    result = []
    in_code_block = False
    code_lines = []

    for line in text.split("\n"):
        if line.strip().startswith("```"):
            if in_code_block:
                code_content = "\n".join(code_lines)
                escaped = _escape(code_content)
                result.append(f'<span background="#f4f4f5" foreground="#18181b">{escaped}</span>')
                code_lines = []
                in_code_block = False
            else:
                in_code_block = True
            continue

        if in_code_block:
            code_lines.append(line)
            continue

        stripped = line.lstrip()
        if re.match(r"^#{1,4}\s", stripped):
            level = len(stripped) - len(stripped.lstrip("#"))
            heading = stripped.lstrip("# ").rstrip()
            size = "x-large" if level <= 2 else "larger"
            result.append(f'<span size="{size}"><b>{_inline(_escape(heading))}</b></span>')
        elif re.match(r"^[-*]\s", stripped):
            item = stripped[2:]
            result.append(f"  {_inline(_escape(item))}")
        elif re.match(r"^\d+\.\s", stripped):
            item = re.sub(r"^\d+\.\s", "", stripped)
            result.append(f"  {_inline(_escape(item))}")
        else:
            result.append(_inline(_escape(line)))

    output = "\n".join(result)
    output = re.sub(r"\n{2,}", "\n", output)
    return output
