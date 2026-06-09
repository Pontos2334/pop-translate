import sys
from urllib.parse import parse_qs, unquote, urlparse

from .__main__ import main as translate_main


VALID_TABS = {"translate", "explain", "chat", "auto"}


def _tab_from_url(parsed):
    candidate = (parsed.netloc or parsed.path.lstrip("/")).strip().lower()
    return candidate if candidate in VALID_TABS else "explain"


def _text_from_url(parsed):
    query = parse_qs(parsed.query, keep_blank_values=True)
    for key in ("q", "text"):
        value = query.get(key, [""])[0].strip()
        if value:
            return value

    if parsed.fragment:
        return unquote(parsed.fragment).strip()
    return ""


def parse_pop_translate_url(url):
    parsed = urlparse(url)
    if parsed.scheme != "pop-translate":
        raise ValueError("unsupported URL scheme")
    return _tab_from_url(parsed), _text_from_url(parsed)


def main(argv=None):
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv:
        return 0

    try:
        tab, text = parse_pop_translate_url(argv[0])
    except ValueError as e:
        print(f"pop-translate-url: {e}", file=sys.stderr)
        return 2

    if not text:
        return 0

    translate_main(["--text", text, "--tab", tab])
    return 0


if __name__ == "__main__":
    sys.exit(main())
