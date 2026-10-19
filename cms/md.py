"""Простейший Markdown -> HTML (без внешних зависимостей)."""

import html as _html
import re


def _inline(text: str) -> str:
    text = _html.escape(text, quote=False)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"(?<!\*)\*([^*]+)\*(?!\*)", r"<em>\1</em>", text)
    text = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", text)
    text = re.sub(r"\[([^\]]+)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', text)
    return text


def md_to_html(md: str) -> str:
    """Конвертирует Markdown в HTML: заголовки, списки, цитаты, код, ссылки."""
    if not md:
        return ""
    lines = md.splitlines()
    out = []
    i = 0
    para = []

    def flush_para():
        if para:
            out.append("<p>" + "<br>\n".join(_inline(l) for l in para) + "</p>")
            para.clear()

    while i < len(lines):
        line = lines[i]
        stripped = line.strip()

        # fenced code block
        if stripped.startswith("```"):
            flush_para()
            lang = stripped[3:].strip()
            code_lines = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                code_lines.append(lines[i])
                i += 1
            cls = f' class="language-{_html.escape(lang)}"' if lang else ""
            out.append(f"<pre><code{cls}>{_html.escape(chr(10).join(code_lines))}</code></pre>")
            i += 1
            continue

        if not stripped:
            flush_para()
            i += 1
            continue

        m = re.match(r"^(#{1,6})\s+(.*)$", stripped)
        if m:
            flush_para()
            lvl = len(m.group(1))
            out.append(f"<h{lvl}>{_inline(m.group(2))}</h{lvl}>")
            i += 1
            continue

        if stripped in ("---", "***", "___"):
            flush_para()
            out.append("<hr>")
            i += 1
            continue

        if stripped.startswith(">"):
            flush_para()
            quote = []
            while i < len(lines) and lines[i].strip().startswith(">"):
                quote.append(lines[i].strip().lstrip(">").strip())
                i += 1
            out.append("<blockquote><p>" + "<br>".join(_inline(q) for q in quote) + "</p></blockquote>")
            continue

        m = re.match(r"^[-*+]\s+(.*)$", stripped)
        if m:
            flush_para()
            items = []
            while i < len(lines):
                mm = re.match(r"^\s*[-*+]\s+(.*)$", lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(1)))
                i += 1
            out.append("<ul>\n" + "\n".join(f"<li>{it}</li>" for it in items) + "\n</ul>")
            continue

        m = re.match(r"^\d+\.\s+(.*)$", stripped)
        if m:
            flush_para()
            items = []
            while i < len(lines):
                mm = re.match(r"^\s*\d+\.\s+(.*)$", lines[i])
                if not mm:
                    break
                items.append(_inline(mm.group(1)))
                i += 1
            out.append("<ol>\n" + "\n".join(f"<li>{it}</li>" for it in items) + "\n</ol>")
            continue

        para.append(stripped)
        i += 1

    flush_para()
    return "\n".join(out)
