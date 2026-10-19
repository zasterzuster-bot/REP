"""Блог-CMS без базы данных. Точка входа: python app.py -> http://localhost:8000

Структура:
  storage.py         — хранение в JSON-файлах (posts/, categories/, settings/)
  template_engine.py — шаблонизатор (extends/block/for/if) для тем
  md.py              — Markdown -> HTML
  templates/<тема>/  — темы оформления (default + пример "dark")
  admin.py           — админ-панель (вход по паролю, посты, категории, главная, темы)
"""

import html
import json
import mimetypes
from http.cookies import SimpleCookie
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlparse

import storage as db
from md import md_to_html
from template_engine import Engine, TemplateError

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
PORT = 8000


# ---------- Тема и контекст ----------

def get_theme_name() -> str:
    return db.load_settings().get("theme", "default")


def get_engine() -> Engine:
    theme_dir = TEMPLATES_DIR / get_theme_name()
    if not (theme_dir / "base.html").exists():
        theme_dir = TEMPLATES_DIR / "default"
    return Engine(theme_dir)


def nav_tree():
    """Дерево категорий для меню/сайдбара."""
    return db.get_category_tree()


def make_context(**extra) -> dict:
    settings = db.load_settings()
    ctx = {
        "site": settings,
        "nav": nav_tree(),
        "year": "2026",
        "_funcs": {
            "url_post": lambda p: f"/post/{p['slug']}",
            "url_cat": lambda c: f"/category/{db.category_full_slug(c['id'])}",
            "md": md_to_html,
            "raw": lambda s: s,  # вставить HTML как есть
            "date": lambda iso: (iso or "")[:10],
            "cat_by_id": lambda cid: db.find_category(cid),
            "excerpt_of": lambda p: p.get("excerpt") or (p.get("body", "")[:160] + "..."),
            "join_path": lambda trail: "/".join(x["slug"] for x in trail),
        },
    }
    ctx.update(extra)
    return ctx


def render(template: str, **extra) -> str:
    engine = get_engine()
    try:
        return engine.render(template, make_context(**extra))
    except TemplateError as e:
        return f"<h1>Ошибка шаблона</h1><pre>{html.escape(str(e))}</pre>"


# ---------- Простая markdown-сериализация для импорта/экспорта ----------

def post_to_markdown(p: dict) -> str:
    cats = [db.find_category(c)["title"] for c in p.get("category_ids", []) if db.find_category(c)]
    lines = [f"# {p['title']}", ""]
    meta = {"categories": cats, "tags": p.get("tags", []),
            "status": p.get("status", "draft"), "excerpt": p.get("excerpt", "")}
    lines.append("<!--meta\n" + json.dumps(meta, ensure_ascii=False, indent=2) + "\n-->")
    lines += ["", p.get("body", "")]
    return "\n".join(lines)


def markdown_to_post(text: str) -> dict:
    m = text.replace("\r\n", "\n")
    fields = {"title": "Без названия", "body": m, "category_ids": [], "tags": [], "status": "draft", "excerpt": ""}
    hm = re_meta = None
    hm = __import__("re").search(r"^#\s+(.+)$", m, __import__("re").M)
    if hm:
        fields["title"] = hm.group(1).strip()
    mm = __import__("re").search(r"<!--meta\s*(\{.*?\})\s*-->", m, __import__("re").S)
    if mm:
        try:
            meta = json.loads(mm.group(1))
            fields["tags"] = meta.get("tags", [])
            fields["status"] = meta.get("status", "draft")
            fields["excerpt"] = meta.get("excerpt", "")
            names = meta.get("categories", [])
            tree = db.get_category_tree()
            for name in names:
                def find(nodes):
                    for n in nodes:
                        if n["title"].lower() == name.lower():
                            return n["id"]
                        r = find(n["children"])
                        if r:
                            return r
                cid = find(tree)
                if cid:
                    fields["category_ids"].append(cid)
        except json.JSONDecodeError:
            pass
    return fields


# ---------- Сессии админки (подпись через hashlib, без внешних библиотек) ----------

import hashlib
import hmac
import os
import secrets

SECRET_FILE = db.DATA_DIR / "settings" / ".secret"


def _secret_key() -> bytes:
    SECRET_FILE.parent.mkdir(parents=True, exist_ok=True)
    if SECRET_FILE.exists():
        return SECRET_FILE.read_bytes()
    key = secrets.token_bytes(32)
    SECRET_FILE.write_bytes(key)
    os.chmod(SECRET_FILE, 0o600)
    return key


def sign(value: str) -> str:
    sig = hmac.new(_secret_key(), value.encode(), hashlib.sha256).hexdigest()[:32]
    return f"{value}.{sig}"


def unsign(signed: str):
    if not signed or "." not in signed:
        return None
    value, sig = signed.rsplit(".", 1)
    expect = hmac.new(_secret_key(), value.encode(), hashlib.sha256).hexdigest()[:32]
    return value if hmac.compare_digest(sig, expect) else None


def password_hash(password: str) -> str:
    salt = SECRET_FILE.parent / ".salt"
    if salt.exists():
        salt_bytes = salt.read_bytes()
    else:
        salt_bytes = secrets.token_bytes(16)
        salt.write_bytes(salt_bytes)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt_bytes, 100_000)
    return dk.hex()


def get_or_create_admin_password_hash() -> str:
    st = db.load_settings()
    if "admin_password_hash" not in st:
        st["admin_password_hash"] = password_hash("admin")
        db.save_settings({"admin_password_hash": st["admin_password_hash"]})
        print("[CMS] Пароль администратора по умолчанию: admin  (измените в /admin/settings)")
    return st["admin_password_hash"]


# ---------- HTTP ----------

PAGINATION = {}  # не используется глобально; пагинация считается в хендлерах


class Handler(BaseHTTPRequestHandler):
    server_version = "MiniCMS/1.0"

    # --- утилиты ---
    def _send(self, body: bytes, code=200, ctype="text/html; charset=utf-8", headers=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def send_html(self, html_str: str, code=200, headers=None):
        self._send(html_str.encode("utf-8"), code, headers=headers)

    def redirect(self, location: str, cookie: str = None):
        self.send_response(302)
        self.send_header("Location", location)
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()

    def read_form(self) -> dict:
        length = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(length).decode("utf-8") if length else ""
        qs = parse_qs(raw, keep_blank_values=True)
        # многонзначные поля (select multiple) сохраняем списком под тем же ключом
        form = {}
        for k, v in qs.items():
            form[k] = v if len(v) > 1 else v[-1]
        return form

    def is_admin(self) -> bool:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        sess = cookie.get("cms_session")
        return bool(sess and unsign(sess.value) == "admin")

    def log_message(self, fmt, *args):  # тише логи
        pass

    # --- маршрутизация ---
    def do_GET(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        q = parse_qs(parsed.query)

        if path.startswith("/admin"):
            import admin as admin_mod
            self._q_cache = q
            return admin_mod.handle_get(self, path, q)

        if path.startswith("/static/"):
            return self.serve_static(path)

        if path == "/":
            return self.page_home(q)
        if path.startswith("/post/"):
            return self.page_post(path[len("/post/"):])
        if path.startswith("/category/"):
            return self.page_category(path[len("/category/"):].rstrip("/"), q)
        if path.startswith("/tag/"):
            return self.page_tag(unquote(path[len("/tag/"):]), q)
        if path == "/about":
            return self.page_about()
        if path == "/sitemap.xml":
            return self.sitemap()
        self.send_html(render("404.html", title="Страница не найдена"), 404)

    def do_POST(self):
        parsed = urlparse(self.path)
        path = unquote(parsed.path)
        if path.startswith("/admin"):
            import admin as admin_mod
            return admin_mod.handle_post(self, path, self.read_form())
        self.send_html("405 Method Not Allowed", 405)

    # --- публичные страницы ---
    def page_home(self, q):
        home = db.load_home()
        settings = db.load_settings()
        per = int(settings.get("posts_per_page", 5))
        page = max(1, int((q.get("page") or ["1"])[0]))
        published = [p for p in db.load_posts() if p.get("status") == "published"]
        total_pages = max(1, (len(published) + per - 1) // per)
        page_posts = published[(page - 1) * per: page * per]
        body = render("index.html", home=home, posts=page_posts,
                      page=page, total_pages=total_pages,
                      prev_page=max(1, page-1), next_page=min(total_pages, page+1),
                      title=home.get("hero_title", ""), page_url="/")
        self.send_html(body)

    def page_post(self, slug):
        p = db.load_post(slug)
        if not p or p.get("status") != "published":
            self.send_html(render("404.html", title="Пост не найден"), 404)
            return
        cats = [db.find_category(c) for c in p.get("category_ids", [])]
        cats = [c for c in cats if c]
        related = [x for x in db.load_posts()
                   if x["slug"] != slug and x.get("status") == "published"
                   and set(x.get("category_ids", [])) & {c["id"] for c in cats}][:3]
        self.send_html(render("post.html", post=p, cats=cats, related=related,
                              title=p["title"], page_url=f"/post/{slug}"))

    def page_category(self, full_slug, q):
        trail = db.category_path(full_slug)
        if not trail:
            self.send_html(render("404.html", title="Категория не найдена"), 404)
            return
        cat = trail[-1]
        posts = db.posts_for_category(cat["id"], include_children=True)
        settings = db.load_settings()
        per = int(settings.get("posts_per_page", 5))
        page = max(1, int((q.get("page") or ["1"])[0]))
        total_pages = max(1, (len(posts) + per - 1) // per)
        page_posts = posts[(page - 1) * per: page * per]
        subcats = cat["children"]
        self.send_html(render("category.html", cat=cat, trail=trail, posts=page_posts,
                              subcats=subcats, page=page, total_pages=total_pages,
                              prev_page=max(1, page-1), next_page=min(total_pages, page+1),
                              title=cat["title"], page_url=f"/category/{full_slug}"))

    def page_tag(self, tag, q):
        posts = [p for p in db.load_posts()
                 if p.get("status") == "published" and tag in (p.get("tags") or [])]
        self.send_html(render("tag.html", tag=tag, posts=posts, title=f"Тег: {tag}"))

    def page_about(self):
        st = db.load_settings()
        self.send_html(render("about.html", about=st.get("about_html", ""),
                              title="О сайте"))

    def sitemap(self):
        urls = ["<url><loc>/</loc></url>"]
        for p in db.load_posts():
            if p.get("status") == "published":
                urls.append(f"<url><loc>/post/{p['slug']}</loc></url>")
        def walk(nodes):
            for n in nodes:
                urls.append(f"<url><loc>/category/{db.category_full_slug(n['id'])}</loc></url>")
                walk(n["children"])
        walk(db.get_category_tree())
        xml = ('<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
               + "".join(urls) + "</urlset>")
        self._send(xml.encode(), ctype="application/xml")

    def serve_static(self, path):
        # файлы темы: /static/style.css -> templates/<тема>/style.css, плюс общий static/
        rel = path[len("/static/"):]
        candidates = [TEMPLATES_DIR / get_theme_name() / rel, STATIC_DIR / rel]
        for fp in candidates:
            try:
                fp = fp.resolve()
                if str(fp).startswith(str((TEMPLATES_DIR / get_theme_name()).resolve())) or \
                   str(fp).startswith(str(STATIC_DIR.resolve())):
                    if fp.is_file():
                        ctype = mimetypes.guess_type(str(fp))[0] or "application/octet-stream"
                        self._send(fp.read_bytes(), ctype=ctype)
                        return
            except OSError:
                continue
        self.send_html("Not found", 404)


def seed_demo_content():
    """Наполняет CMS демо-данными при первом запуске."""
    if db.load_categories()["items"] or db.load_posts():
        return
    tech = db.add_category("Технологии", description="Всё о технологиях")
    web = db.add_category("Веб-разработка", parent_id=tech["id"])
    fe = db.add_category("Фронтенд", parent_id=web["id"])
    be = db.add_category("Бэкенд", parent_id=web["id"])
    db.add_category("Python", parent_id=be["id"])
    life = db.add_category("Жизнь", description="Заметки о жизни")
    db.add_category("Путешествия", parent_id=life["id"])

    db.create_post(
        "Как я сделал CMS без базы данных",
        "## Введение\n\nЭта система управления контентом хранит всё в **JSON-файлах**.\n\n"
        "- Древовидные категории с любой вложенностью\n- Посты с тегами\n- Админка\n\n"
        "```python\nimport json\ndata = {'hello': 'world'}\nprint(json.dumps(data))\n```\n\n"
        "> Никакого сервера БД — просто файлы на диске.",
        [fe["id"], be["id"]], ["cms", "json", "python"], status="published",
        excerpt="Обзор файловой CMS: хранение, темы, админка.")
    db.create_post(
        "Фронтенд в 2026 году: краткий обзор",
        "Фреймворки приходят и уходят, но *HTML, CSS и JavaScript* остаются.\n\n"
        "1. Компонентные фреймворки\n2. Сборщики\n3. SSR и островная архитектура",
        [fe["id"]], ["frontend", "javascript"], status="published")
    db.create_post(
        "Python vs остальной мир",
        "Python прост, читаем и универсален:\n\n- веб (FastAPI, Django)\n- анализ данных\n- автоматизация\n\n"
        "`print('Привет, мир!')`",
        [db.find_category_by_slug("python", db.get_category_tree())["id"]],
        ["python"], status="published")
    db.create_post(
        "Черновик будущей статьи",
        "Здесь будет что-то интересное... скоро.",
        [tech["id"]], [], status="draft")

    db.save_home({
        "hero_title": "Файловый блог без базы данных",
        "hero_text": "Посты, древовидные категории, админка и подключаемые темы — всё хранится в файлах JSON.",
        "sections": [
            {"type": "latest_posts", "title": "Свежие записи"},
        ],
    })
    db.save_settings({
        "site_title": "FileBlog CMS",
        "tagline": "Блог без базы данных",
        "about_html": "<p>Это демонстрационный блог на самодельной файловой CMS.</p>",
    })


def main():
    db._ensure_dirs()
    get_or_create_admin_password_hash()
    seed_demo_content()
    server = ThreadingHTTPServer(("0.0.0.0", PORT), Handler)
    print(f"[CMS] Сайт:      http://localhost:{PORT}/")
    print(f"[CMS] Админка:   http://localhost:{PORT}/admin/  (логин: admin/admin по умолчанию)")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[CMS] Остановлено.")


if __name__ == "__main__":
    main()
