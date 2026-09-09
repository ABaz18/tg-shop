from html import escape as html_escape

from aiogram.types import InputRichMessage


def e(value: object) -> str:
    return html_escape(str(value), quote=True)


def rich(html: str) -> InputRichMessage:
    return InputRichMessage(html=html)


def h1(text: str) -> str:
    return f"<h1>{e(text)}</h1>"


def h2(text: str) -> str:
    return f"<h2>{e(text)}</h2>"


def p(text: str) -> str:
    return f"<p>{e(text)}</p>"


def raw_p(html_inner: str) -> str:
    return f"<p>{html_inner}</p>"


def divider() -> str:
    return "<hr>"


def details(title: str, body_html: str) -> str:
    return f"<details><summary>{e(title)}</summary>{body_html}</details>"


def table(headers: list[str], rows: list[list[str]], compact: bool = True) -> str:
    attrs = ' class="compact striped"' if compact else ' class="striped"'
    head = "".join(f"<th align='left'>{e(h)}</th>" for h in headers)
    body = []
    for row in rows:
        cells = "".join(f"<td>{e(c)}</td>" for c in row)
        body.append(f"<tr>{cells}</tr>")
    return f"<table{attrs}><tr>{head}</tr>{''.join(body)}</table>"


def join(*parts: str) -> str:
    return "".join(parts)
