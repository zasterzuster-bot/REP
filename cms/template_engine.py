"""Мини-шаблонизатор в стиле Jinja: {% extends %}, {% block %}, {% for %}, {% if %}, {{ var }}.

Позволяет пользователям CMS добавлять свои темы: папка templates/<имя_темы>/
с файлами base.html, index.html, post.html, category.html и т.д.
Функции вызываем как {{ f('post', p) }} — префикс f() зарезервирован для функций.
"""

import re
from pathlib import Path

_expr_re = re.compile(r"\{\{(.*?)\}\}", re.S)
_tag_re = re.compile(r"\{%\s*(.*?)\s*%\}", re.S)


class TemplateError(Exception):
    pass


def _resolve(name: str, ctx: dict):
    """Разрешает 'a.b.c' или 'a[0]' по контексту."""
    name = name.strip()
    if name == "" :
        return ""
    cur = ctx
    for part in re.split(r"\.", name):
        m = re.match(r"^(.*?)\[(\d+)\]$", part)
        if m:
            key, idx = m.group(1), int(m.group(2))
            if key:
                cur = cur[key] if isinstance(cur, dict) else getattr(cur, key)
            cur = cur[idx]
        else:
            if isinstance(cur, dict):
                cur = cur.get(part, "")
            else:
                cur = getattr(cur, part, "")
    return cur


def _eval(expr: str, ctx: dict):
    expr = expr.strip()
    # Литералы
    if expr in ("True", "true"):
        return True
    if expr in ("False", "false"):
        return False
    if (expr.startswith('"') and expr.endswith('"')) or (expr.startswith("'") and expr.endswith("'")):
        return expr[1:-1]
    # Вызов функции: f('name', arg1, arg2)
    m = re.match(r"^f\(\s*['\"]([\w]+)['\"]\s*(,\s*(.*))?\)$", expr, re.S)
    if m:
        fname = m.group(1)
        args = []
        rest = (m.group(3) or "").strip()
        if rest:
            depth, cur_arg, args_list = 0, "", []
            for ch in rest:
                if ch in "([{":
                    depth += 1
                elif ch in ")]}":
                    depth -= 1
                if ch == "," and depth == 0:
                    args_list.append(cur_arg)
                    cur_arg = ""
                else:
                    cur_arg += ch
            args_list.append(cur_arg)
            for a in args_list:
                a = a.strip()
                if not a:
                    continue
                args.append(_eval(a, ctx))
        funcs = ctx.get("_funcs", {})
        if fname not in funcs:
            raise TemplateError(f"Неизвестная функция '{fname}'")
        return funcs[fname](*args)
    # Бинарные операторы сравнения == и != (без цепочек)
    m = re.match(r"^(.+?)\s*(==|!=)\s*(.+)$", expr, re.S)
    if m and "==" not in m.group(3) and "!=" not in m.group(3):
        left = _eval(m.group(1), ctx)
        right = _eval(m.group(3), ctx)
        return (left == right) if m.group(2) == "==" else (left != right)
    m = re.match(r"^(.+?)\s*([<>]=?|<=?)\s*(.+)$", expr, re.S)
    if m and not any(op in m.group(3) for op in ("==","!=", "<", ">")):
        try:
            left, right = _eval(m.group(1), ctx), _eval(m.group(3), ctx)
            op = m.group(2)
            if op == "<": return left < right
            if op == ">": return left > right
            if op == "<=": return left <= right
            if op == ">=": return left >= right
        except TypeError:
            return False
    # Оператор 'in' для проверки принадлежности
    m = re.match(r"^(.+?)\s+in\s+(.+)$", expr, re.S)
    if m:
        left = _eval(m.group(1), ctx)
        right = _eval(m.group(2), ctx)
        try:
            return left in right
        except TypeError:
            return False
    # not X
    m = re.match(r"^not\s+(.+)$", expr, re.S)
    if m:
        return not _eval(m.group(1), ctx)
    return _resolve(expr, ctx)


def _render_vars(text: str, ctx: dict) -> str:
    def repl(m):
        val = _eval(m.group(1), ctx)
        if val is None:
            return ""
        if isinstance(val, bool):
            return "true" if val else "false"
        return str(val)
    return _expr_re.sub(repl, text)


def _tokenize(source: str):
    """Разбивает шаблон на токены (текст и теги)."""
    tokens = []
    pos = 0
    for m in _tag_re.finditer(source):
        if m.start() > pos:
            tokens.append(("text", source[pos:m.start()]))
        tokens.append(("tag", m.group(1)))
        pos = m.end()
    if pos < len(source):
        tokens.append(("text", source[pos:]))
    return tokens


def _parse(tokens, i=0, terminators=()):
    """Рекурсивный парсер токенов в AST-узлы."""
    nodes = []
    while i < len(tokens):
        kind, val = tokens[i]
        if kind == "text":
            nodes.append(("text", val))
            i += 1
            continue
        name = val.split(None, 1)[0] if val else ""
        if name in terminators:
            return nodes, i, val
        if name == "set":
            m = re.match(r"set\s+(\w+)\s*=\s*(.+)$", val, re.S)
            if not m:
                raise TemplateError(f"Неверный синтаксис set: {val}")
            nodes.append(("set", m.group(1), m.group(2)))
            i += 1
            continue
        if name == "for":
            m = re.match(r"for\s+(\w+)\s+in\s+(.+)$", val, re.S)
            if not m:
                raise TemplateError(f"Неверный синтаксис for: {val}")
            body, i, end = _parse(tokens, i + 1, ("endfor",))
            nodes.append(("for", m.group(1), m.group(2), body))
        elif name == "if":
            branches = []
            cond = val[2:].strip()
            body, i, end = _parse(tokens, i + 1, ("endif", "elif", "else"))
            branches.append((cond, body))
            while end.startswith(("elif", "else")):
                if end.startswith("elif"):
                    body, i, end = _parse(tokens, i + 1, ("endif", "elif", "else"))
                    branches.append((end[4:].strip(), body))
                else:  # else
                    body, i, end = _parse(tokens, i + 1, ("endif",))
                    branches.append((None, body))
            nodes.append(("if", branches))
        elif name == "block":
            m = re.match(r"block\s+(\w+)", val)
            bname = m.group(1)
            body, i, end = _parse(tokens, i + 1, ("endblock",))
            nodes.append(("block", bname, body))
        elif name == "include":
            m = re.match(r"include\s+['\"](.+?)['\"]", val)
            if not m:
                raise TemplateError(f"Неверный синтаксис include: {val}")
            nodes.append(("include", m.group(1)))
        elif name in ("endfor", "endif", "endblock"):
            raise TemplateError(f"Неожиданный закрывающий тег: {name}")
        else:
            nodes.append(("raw_tag", val))
        i += 1
    if terminators:
        raise TemplateError("Не закрыт блок в шаблоне")
    return nodes, i, None


def _render_nodes(nodes, ctx, blocks, engine=None):
    out = []
    for node in nodes:
        kind = node[0]
        if kind == "set":
            ctx[node[1]] = _eval(node[2], ctx)
        elif kind == "text":
            out.append(_render_vars(node[1], ctx))
        elif kind == "include":
            if engine is not None:
                src = engine._read(node[1])
                if src is None:
                    raise TemplateError(f"Не найден включаемый шаблон '{node[1]}'")
                iast, _, _ = _parse(_tokenize(src))
                out.append(_render_nodes(iast, ctx, {}, engine))
        elif kind == "for":
            _, var, iterable, body = node
            items = _eval(iterable, ctx) or []
            if not hasattr(items, "__iter__") or isinstance(items, (str, bytes)):
                items = [items] if items else []
            for idx, item in enumerate(items):
                child = dict(ctx)
                child[var] = item
                child["loop"] = {"index": idx + 1, "first": idx == 0,
                                 "last": idx == len(items) - 1}
                out.append(_render_nodes(body, child, blocks, engine))
        elif kind == "if":
            for cond, body in node[1]:
                if cond is None or _eval(cond, ctx):
                    out.append(_render_nodes(body, ctx, blocks, engine))
                    break
        elif kind == "block":
            _, bname, body = node
            if bname in blocks:  # переопределён дочерним шаблоном
                out.append(_render_nodes(blocks[bname], ctx, blocks, engine))
            else:
                out.append(_render_nodes(body, ctx, blocks, engine))
        elif kind == "raw_tag":
            pass  # неизвестные теги игнорируются
    return "".join(out)


class Engine:
    def __init__(self, theme_dir: Path):
        self.theme_dir = Path(theme_dir)

    def _read(self, filename: str):
        fp = self.theme_dir / filename
        if not fp.exists():
            return None
        return fp.read_text(encoding="utf-8")

    def render(self, template_name: str, context: dict) -> str:
        source = self._read(template_name)
        if source is None:
            raise TemplateError(f"Шаблон '{template_name}' не найден в теме '{self.theme_dir.name}'")
        tokens = _tokenize(source)
        ast, _, _ = _parse(tokens)
        # Обработка {% extends %}: собираем блоки потомка, рендерим родителя
        parent_name = None
        own_blocks = {}
        rest = []
        it = iter(ast)
        for node in ast:
            if node[0] == "raw_tag" and node[1].startswith("extends"):
                m = re.match(r"extends\s+['\"](.+?)['\"]", node[1])
                if m:
                    parent_name = m.group(1)
            elif node[0] == "block":
                own_blocks[node[1]] = node[2]
        if parent_name:
            parent_src = self._read(parent_name)
            if parent_src is None:
                raise TemplateError(f"Родительский шаблон '{parent_name}' не найден")
            past, _, _ = _parse(_tokenize(parent_src))
            return _render_nodes(past, context, own_blocks, self)
        return _render_nodes(ast, context, own_blocks, self)
