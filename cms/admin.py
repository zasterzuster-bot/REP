"""Админ-панель CMS. Рендерится напрямую (без тем), защищена паролем."""

import html
import json
from urllib.parse import quote

import storage as db


def e(s) -> str:
    return html.escape(str(s if s is not None else ""))


# ---------- Каркас страницы админки ----------

LAYOUT = """<!DOCTYPE html><html lang="ru"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title} — Админка</title>
<link rel="stylesheet" href="/admin/style.css"></head><body>
<header class="topbar"><b><a href="/admin/">FileBlog · Админка</a></b>
<nav>
  <a href="/admin/posts">Посты</a>
  <a href="/admin/categories">Категории</a>
  <a href="/admin/home">Главная</a>
  <a href="/admin/themes">Темы</a>
  <a href="/admin/settings">Настройки</a>
  <a href="/" target="_blank">Смотреть сайт ↗</a>
  {logout}
</nav></header>
<main>{flash}{content}</main>
</body></html>"""

STYLE = """*{box-sizing:border-box}body{margin:0;font-family:system-ui,sans-serif;background:#f4f5f7;color:#222}
.topbar{background:#1e293b;color:#fff;padding:.6rem 1rem;display:flex;flex-wrap:wrap;gap:.5rem 1.5rem;align-items:center}
.topbar a{color:#cbd5e1;text-decoration:none}.topbar b a{color:#fff}
.topbar nav{display:flex;gap:1rem;flex-wrap:wrap}.topbar nav a:hover{color:#fff}
main{max-width:980px;margin:1.5rem auto;padding:0 1rem}
h1{font-size:1.4rem}
.card{background:#fff;border-radius:8px;padding:1rem 1.2rem;margin-bottom:1rem;box-shadow:0 1px 3px rgba(0,0,0,.1)}
table{width:100%;border-collapse:collapse}th,td{text-align:left;padding:.5rem .6rem;border-bottom:1px solid #eee;font-size:.95rem}
.btn{display:inline-block;background:#2563eb;color:#fff;border:0;border-radius:6px;padding:.45rem .9rem;font-size:.9rem;cursor:pointer;text-decoration:none}
.btn.secondary{background:#64748b}.btn.danger{background:#dc2626}.btn.small{padding:.2rem .55rem;font-size:.8rem}
input[type=text],input[type=password],input[type=number],select,textarea{width:100%;padding:.5rem;border:1px solid #cbd5e1;border-radius:6px;font:inherit}
label{display:block;margin:.7rem 0 .25rem;font-weight:600;font-size:.9rem}
.flash{padding:.7rem 1rem;border-radius:6px;margin-bottom:1rem;background:#dcfce7;color:#166534}
.flash.err{background:#fee2e2;color:#991b1b}
.tree ul{list-style:none;margin:.2rem 0 0;padding-left:1.3rem;border-left:1px dashed #bbb}
.badge{font-size:.75rem;padding:.1rem .5rem;border-radius:99px;background:#e2e8f0}.badge.pub{background:#bbf7d0;color:#14532d}
.muted{color:#64748b;font-size:.85rem}.row{display:flex;gap:.6rem;align-items:center;flex-wrap:wrap}
.grid2{display:grid;grid-template-columns:1fr 1fr;gap:1rem}
@media(max-width:700px){.grid2{grid-template-columns:1fr}}"""


def page(handler, title: str, content: str, code=200, flash: str = "", err=False):
    logout = '<a href="/admin/logout">Выйти</a>' if handler.is_admin() else ""
    fl = f'<div class="flash{" err" if err else ""}">{e(flash)}</div>' if flash else ""
    body = LAYOUT.format(title=e(title), content=content, logout=logout, flash=fl)
    handler.send_html(body, code)


# ---------- Маршруты GET ----------

def handle_get(handler, path, q):
    if path == "/admin/style.css":
        handler._send(STYLE.encode(), ctype="text/css; charset=utf-8")
        return
    if path in ("/admin/login", "/admin/logout"):
        return view_login(handler, path)
    if not handler.is_admin():
        return view_login(handler, "/admin/login", next_path=path)
    if path in ("/admin", "/admin/"):
        return dashboard(handler)
    if path == "/admin/posts":
        return posts_list(handler)
    if path.startswith("/admin/posts/new"):
        return post_edit(handler, None)
    if path.startswith("/admin/posts/edit/"):
        return post_edit(handler, path[len("/admin/posts/edit/"):])
    if path.startswith("/admin/posts/export/"):
        p = db.load_post(path[len("/admin/posts/export/"):])
        if p:
            import app
            data = app.post_to_markdown(p).encode()
            handler._send(data, ctype="text/markdown; charset=utf-8",
                          headers={"Content-Disposition": f'attachment; filename="{p["slug"]}.md"'})
            return
    if path == "/admin/categories":
        return categories_page(handler, q)
    if path.startswith("/admin/categories/edit/"):
        return category_edit(handler, path[len("/admin/categories/edit/"):])
    if path == "/admin/home":
        return home_editor(handler)
    if path == "/admin/themes":
        return themes_page(handler)
    if path == "/admin/settings":
        return settings_page(handler)
    page(handler, "404", "<p>Страница не найдена.</p>", 404)


# ---------- Маршруты POST ----------

def handle_post(handler, path, form):
    if path == "/admin/login":
        return do_login(handler, form)
    if not handler.is_admin():
        return view_login(handler, "/admin/login", err="Требуется вход")
    if path.startswith("/admin/posts/save"):
        return do_save_post(handler, form)
    if path.startswith("/admin/posts/delete/"):
        db.delete_post(path[len("/admin/posts/delete/"):])
        return back(handler, "/admin/posts", "Пост удалён.")
    if path.startswith("/admin/posts/publish/"):
        slug = path[len("/admin/posts/publish/"):]
        p = db.load_post(slug)
        if p:
            db.save_post(slug, {"status": "published" if p.get("status") != "published" else "draft"})
        return back(handler, "/admin/posts", "Статус изменён.")
    if path == "/admin/categories/save":
        return do_save_category(handler, form)
    if path.startswith("/admin/categories/delete/"):
        db.delete_category(path[len("/admin/categories/delete/"):])
        return back(handler, "/admin/categories", "Категория и подкатегории удалены.")
    if path == "/admin/home/save":
        return do_save_home(handler, form)
    if path == "/admin/themes/activate":
        name = form.get("theme", "")
        names = [t["name"] for t in db.list_themes()]
        if name in names:
            db.save_settings({"theme": name})
            return back(handler, "/admin/themes", f"Тема «{name}» активирована.")
        return back(handler, "/admin/themes", "Такой темы нет.", True)
    if path == "/admin/settings/save":
        return do_save_settings(handler, form)
    page(handler, "404", "<p>Не найдено.</p>", 404)


def back(handler, location, msg="", err=False):
    # flash через query-параметр
    sep = "&" if "?" in location else "?"
    handler.redirect(location + sep + "msg=" + quote(msg) + ("&err=1" if err else ""))


def get_msg(q):
    return (q.get("msg") or [""])[0], bool(q.get("err"))


# ---------- Вход ----------

def view_login(handler, path, next_path="/admin/", err=None):
    if path == "/admin/logout":
        handler.redirect("/", cookie="cms_session=; Max-Age=0; Path=/")
        return
    nxt = quote(next_path)
    msg = f'<div class="flash err">{e(err)}</div>' if err else ""
    content = f"""{msg}<div class="card" style="max-width:380px;margin:3rem auto">
<h1>Вход в админку</h1>
<form method="post" action="/admin/login?next={nxt}">
<label>Логин</label><input type="text" name="login" value="admin">
<label>Пароль</label><input type="password" name="password">
<div style="margin-top:1rem"><button class="btn">Войти</button></div>
</form><p class="muted">Пароль по умолчанию: <code>admin</code></p></div>"""
    page(handler, "Вход", content)


def do_login(handler, form):
    import app
    nxt = (handler.headers.get("Referer", "").split("next=") + [""])[-1]
    from urllib.parse import unquote
    nxt = unquote(nxt.split("&")[0]) if nxt else "/admin/"
    pw_hash = app.get_or_create_admin_password_hash()
    if form.get("login") == "admin" and app.password_hash(form.get("password", "")) == pw_hash:
        cookie = f"cms_session={app.sign('admin')}; Path=/; HttpOnly; SameSite=Lax"
        handler.redirect(nxt or "/admin/", cookie=cookie)
    else:
        view_login(handler, "/admin/login", err="Неверный логин или пароль")


# ---------- Дашборд ----------

def dashboard(handler):
    msg, err = get_msg(handler._q_cache if hasattr(handler, "_q_cache") else {})
    posts = db.load_posts()
    published = [p for p in posts if p.get("status") == "published"]
    cats = db.load_categories()["items"]
    theme = db.load_settings().get("theme", "default")
    content = f"""<h1>Панель управления</h1>
<div class="grid2">
<div class="card"><h3>Контент</h3><p>Постов: <b>{len(posts)}</b> (опубликовано {len(published)}, черновиков {len(posts)-len(published)})<br>
Категорий: <b>{len(cats)}</b></p></div>
<div class="card"><h3>Быстрые действия</h3>
<p><a class="btn" href="/admin/posts/new">+ Новый пост</a>
<a class="btn secondary" href="/admin/categories">Категории</a>
<a class="btn secondary" href="/admin/home">Главная</a></p>
<p class="muted">Активная тема: {e(theme)}</p></div></div>"""
    page(handler, "Панель", content)


# ---------- Посты ----------

def cat_options(selected_ids, none_label="— без категории —"):
    opts = []
    if none_label:
        opts.append(f'<option value="">{none_label}</option>')
    def walk(nodes, depth):
        for n in nodes:
            sel = " selected" if n["id"] in selected_ids else ""
            opts.append(f'<option value="{n["id"]}"{sel}>{"— "*depth}{e(n["title"])}</option>')
            walk(n["children"], depth + 1)
    walk(db.get_category_tree(), 0)
    return "\n".join(opts)


def posts_list(handler):
    msg, err = get_msg(handler._q_cache if hasattr(handler, "_q_cache") else {})
    rows = []
    for p in db.load_posts():
        cats_titles = ", ".join(
            db.find_category(c)["title"] for c in p.get("category_ids", []) if db.find_category(c))
        pub = p.get("status") == "published"
        toggle_txt = "В черновик" if pub else "Опубликовать"
        rows.append(f"""<tr><td><a href="/post/{p['slug']}" target="_blank">{e(p['title'])}</a><br>
<span class="muted">{e(p.get('published_at','')[:10])} · {e(cats_titles) or 'нет категории'}</span></td>
<td><span class="badge{' pub' if pub else ''}">{'опубликован' if pub else 'черновик'}</span></td>
<td class="row">
<a class="btn small" href="/admin/posts/edit/{p['slug']}">Ред.</a>
<form method="post" action="/admin/posts/publish/{p['slug']}" style="display:inline"><button class="btn small secondary">{toggle_txt}</button></form>
<a class="btn small secondary" href="/admin/posts/export/{p['slug']}">.md</a>
<form method="post" action="/admin/posts/delete/{p['slug']}" style="display:inline" onsubmit="return confirm('Удалить пост?')"><button class="btn small danger">Удалить</button></form>
</td></tr>""")
    content = f"""<div class="row" style="justify-content:space-between"><h1>Посты ({len(rows)})</h1>
<a class="btn" href="/admin/posts/new">+ Новый пост</a></div>
<div class="card"><table><tr><th>Заголовок</th><th>Статус</th><th>Действия</th></tr>{''.join(rows) or '<tr><td colspan=3>Пока пусто</td></tr>'}</table></div>"""
    page(handler, "Посты", content)


def post_edit(handler, slug):
    p = db.load_post(slug) if slug else None
    title = "Редактирование поста" if p else "Новый пост"
    body_val = e(p["body"]) if p else ""
    form = f"""<h1>{title}</h1>
<div class="card"><form method="post" action="/admin/posts/save">
<input type="hidden" name="slug" value="{e(slug or '')}">
<label>Заголовок</label><input type="text" name="title" required value="{e(p['title']) if p else ''}">
<div class="grid2">
<div><label>Категории (Ctrl/Cmd — несколько)</label><select name="cats" multiple size="8">{cat_options(set(p.get('category_ids', [])) if p else set())}</select>
<p class="muted">Можно выбрать несколько категорий любого уровня вложенности.</p></div>
<div><label>Теги (через запятую)</label><input type="text" name="tags" value="{e(', '.join(p.get('tags', [])))if p else ''}">
<label>Статус</label><select name="status">
<option value="draft"{' selected' if p and p.get('status')!='published' else ''}>Черновик</option>
<option value="published"{' selected' if p and p.get('status')=='published' else ''}>Опубликован</option></select>
<label>Slug (URL)</label><input type="text" name="slug_keep" value="{e(slug or '')}" placeholder="сгенерировать автоматически"></div></div>
<label>Краткое описание (для главной/списков)</label><input type="text" name="excerpt" value="{e(p.get('excerpt','')) if p else ''}">
<label>Текст поста (Markdown: # заголовки, **жирный**, списки, ссылки, ```код```)</label>
<textarea name="body" rows="16">{body_val}</textarea>
<div class="row" style="margin-top:1rem">
<button class="btn" name="go" value="save" formaction="/admin/posts/save">Сохранить</button>
<a class="btn secondary" href="/admin/posts">Отмена</a></div>
</form></div>"""
    page(handler, title, form)


def do_save_post(handler, form):
    title = form.get("title", "").strip()
    if not title:
        return back(handler, "/admin/posts", "Заголовок обязателен.", True)
    cats = form.getlist("cats") if hasattr(form, "getlist") else _multi(form, "cats")
    tags = [t.strip() for t in form.get("tags", "").split(",") if t.strip()]
    fields = {
        "title": title,
        "body": form.get("body", ""),
        "excerpt": form.get("excerpt", "").strip(),
        "category_ids": cats,
        "tags": tags,
        "status": "published" if form.get("status") == "published" else "draft",
    }
    slug = form.get("slug", "")
    keep = form.get("slug_keep", "").strip()
    if slug:  # редактирование
        if keep and keep != slug and not db.load_post(keep):
            db.delete_post(slug)
            slug = keep
        db.save_post(slug, fields)
    else:
        import app
        p = db.create_post(title, fields["body"], cats, tags, fields["status"], fields["excerpt"])
        slug = p["slug"]
    return back(handler, "/admin/posts", "Пост сохранён.")


def _multi(form, key):
    """read_form возвращает список для полей с несколькими значениями (select multiple)."""
    val = form.get(key, "")
    if isinstance(val, list):
        return [v for v in val if v]
    return [val] if val else []


# ---------- Категории ----------

def render_tree(nodes):
    if not nodes:
        return ""
    lis = []
    for n in nodes:
        cnt = len(db.posts_for_category(n["id"], include_children=False))
        lis.append(
            f"<li><div class='row'><b>{e(n['title'])}</b> "
            f"<span class='muted'>/{e(db.category_full_slug(n['id']))} · постов: {cnt}</span> "
            f"<span class='row' style='margin-left:auto'>"
            f"<a class='btn small' href='/admin/categories/edit/{n['id']}'>Ред.</a>"
            f"<a class='btn small secondary' href='/admin/categories?parent={n['id']}'>+ подкатегория</a>"
            f"<form method='post' action='/admin/categories/delete/{n['id']}' style='display:inline' "
            f"onsubmit=\"return confirm('Удалить категорию со всеми подкатегориями?')\">"
            f"<button class='btn small danger'>×</button></form></div></div>"
            f"{render_tree(n['children'])}</li>")
    return "<ul>" + "".join(lis) + "</ul>"


def categories_page(handler, q=None):
    q = q or {}
    preselect = (q.get("parent") or [""])[0] if isinstance(q, dict) else ""
    tree_html = render_tree(db.get_category_tree()) or "<p class='muted'>Категорий пока нет.</p>"
    content = f"""<h1>Категории</h1>
<div class="card"><h3>Дерево категорий (вложенность не ограничена)</h3>
<div class="tree">{tree_html}</div></div>
<div class="card"><h3>Добавить категорию</h3>
<form method="post" action="/admin/categories/save">
<label>Название</label><input type="text" name="title" required>
<label>Родительская категория</label>
<select name="parent_id"><option value="">— корневая —</option>{cat_options({preselect}, none_label='')}</select>
<label>Описание (необязательно)</label><input type="text" name="description">
<div style="margin-top:.8rem"><button class="btn">Добавить</button></div>
</form></div>"""
    page(handler, "Категории", content)


def category_edit(handler, cat_id):
    cat = db.find_category(cat_id)
    if not cat:
        return back(handler, "/admin/categories", "Категория не найдена.", True)
    others = []
    def walk(nodes, depth, skip_subtree=True):
        for n in nodes:
            if n["id"] == cat_id:
                continue
            others.append((n, depth))
            walk(n["children"], depth + 1)
    flat = []
    def flatten(nodes, depth):
        for n in nodes:
            # исключаем само дерево редактируемой категории из родителей
            def in_subtree(x):
                cur = x
                by = {c["id"]: c for c in db.load_categories()["items"]}
                g = 0
                while cur and g < 50:
                    if cur["id"] == cat_id:
                        return True
                    cur = by.get(cur.get("parent_id")); g += 1
                return False
            node = {**n}
            if not in_subtree(node):
                flat.append((node, depth))
            flatten(n["children"], depth + 1)
    flatten(db.get_category_tree(), 0)
    opts = "".join(f'<option value="{n["id"]}"{" selected" if n["id"]==cat.get("parent_id") else ""}>{"— "*d}{e(n["title"])}</option>' for n, d in flat)
    content = f"""<h1>Категория: {e(cat['title'])}</h1>
<div class="card"><form method="post" action="/admin/categories/save">
<input type="hidden" name="cat_id" value="{cat['id']}">
<label>Название</label><input type="text" name="title" value="{e(cat['title'])}" required>
<label>Slug</label><input type="text" name="slug" value="{e(cat['slug'])}">
<label>Родитель</label><select name="parent_id"><option value="">— корневая —</option>{opts}</select>
<label>Описание</label><input type="text" name="description" value="{e(cat.get('description',''))}">
<div style="margin-top:.8rem"><button class="btn">Сохранить</button>
<a class="btn secondary" href="/admin/categories">Отмена</a></div></form></div>"""
    page(handler, "Категория", content)


def do_save_category(handler, form):
    title = form.get("title", "").strip()
    if not title:
        return back(handler, "/admin/categories", "Название обязательно.", True)
    parent = form.get("parent_id") or None
    cat_id = form.get("cat_id", "")
    if cat_id:
        fields = {"title": title, "parent_id": parent, "description": form.get("description", ""),
                  "slug": form.get("slug", "")}
        # защита от циклов: нельзя сделать родителем самого себя/потомка
        db.update_category(cat_id, fields)
        return back(handler, "/admin/categories", "Категория обновлена.")
    db.add_category(title, parent, form.get("description", ""))
    return back(handler, "/admin/categories", "Категория добавлена.")


# ---------- Главная страница ----------

def home_editor(handler):
    home = db.load_home()
    sections = home.get("sections", [])
    sec_rows = []
    for i, s in enumerate(sections):
        typ = s.get("type", "text")
        sec_rows.append(f"""<div class="card"><div class="row">
<select name="sec_type_{i}">
<option value="latest_posts"{' selected' if typ=='latest_posts' else ''}>Последние посты</option>
<option value="text"{' selected' if typ=='text' else ''}>Текстовый блок (HTML)</option>
<option value="remove">— удалить —</option></select>
<input type="text" name="sec_title_{i}" placeholder="Заголовок блока" value="{e(s.get('title',''))}">
</div>
<textarea name="sec_html_{i}" rows="3" placeholder="HTML-содержимое (для текстового блока)">{e(s.get('html',''))}</textarea></div>""")
    new_idx = len(sections)
    content = f"""<h1>Редактирование главной страницы</h1>
<form method="post" action="/admin/home/save">
<div class="card"><h3>Hero-блок</h3>
<label>Заголовок</label><input type="text" name="hero_title" value="{e(home.get('hero_title',''))}">
<label>Текст</label><textarea name="hero_text" rows="3">{e(home.get('hero_text',''))}</textarea></div>
<h2 style="font-size:1.1rem">Блоки страницы</h2>
{"".join(sec_rows)}
<div class="card"><h3>Добавить новый блок</h3><div class="row">
<select name="new_sec_type"><option value="latest_posts">Последние посты</option><option value="text">Текстовый блок</option></select>
<input type="text" name="new_sec_title" placeholder="Заголовок">
<input type="text" name="new_sec_html" placeholder="HTML (для текстового)">
</div></div>
<button class="btn">Сохранить главную</button>
</form>"""
    page(handler, "Главная", content)


def do_save_home(handler, form):
    old = db.load_home().get("sections", [])
    sections = []
    for i in range(len(old)):
        typ = form.get(f"sec_type_{i}", "text")
        if typ == "remove":
            continue
        s = {"type": typ, "title": form.get(f"sec_title_{i}", "")}
        if typ == "text":
            s["html"] = form.get(f"sec_html_{i}", "")
        sections.append(s)
    if form.get("new_sec_type"):
        s = {"type": form["new_sec_type"], "title": form.get("new_sec_title", "")}
        if s["type"] == "text":
            s["html"] = form.get("new_sec_html", "")
        sections.append(s)
    db.save_home({"hero_title": form.get("hero_title", ""),
                  "hero_text": form.get("hero_text", ""),
                  "sections": sections})
    return back(handler, "/admin/home", "Главная страница сохранена.")


# ---------- Темы ----------

THEME_HELP = """<h3>Как добавить свою тему</h3>
<ol>
<li>Создайте папку <code>templates/&lt;имя_темы&gt;/</code> рядом с app.py.</li>
<li>Обязателен файл <code>base.html</code> — каркас страницы с блоками:<br>
<code>{% block title %}{% endblock %}</code>, <code>{% block content %}{% endblock %}</code>.</li>
<li>Добавьте шаблоны страниц, каждый начинается с <code>{% extends \"base.html\" %}</code>:
<ul><li><code>index.html</code> — главная (переменные: <code>home.hero_title</code>, <code>home.hero_text</code>, <code>posts</code>, <code>page</code>, <code>total_pages</code>)</li>
<li><code>post.html</code> — пост (<code>post.title</code>, <code>post.body</code>, <code>cats</code>, <code>related</code>)</li>
<li><code>category.html</code> — категория (<code>cat</code>, <code>trail</code>, <code>posts</code>, <code>subcats</code>)</li>
<li><code>tag.html</code>, <code>about.html</code>, <code>404.html</code> — необязательны (фолбэк на index/base)</li></ul></li>
<li>CSS положите в <code>&lt;имя_темы&gt;/style.css</code> и подключите <code>/static/style.css</code>.</li>
<li>Синтаксис: <code>{{ переменная }}</code>, <code>{% for x in posts %}…{% endfor %}</code>,
<code>{% if условие %}…{% endif %}</code>. Функции: <code>{{ f('url_post', p) }}</code>,
<code>{{ f('url_cat', c) }}</code>, <code>{{ f('md', post.body) }}</code> (markdown→HTML),
<code>{{ f('raw', s) }}</code> (вставить HTML как есть), <code>{{ f('date', iso) }}</code>.</li>
<li>Переменные контекста: <code>site.site_title</code>, <code>site.tagline</code>, <code>nav</code> (дерево категорий).</li>
</ol>"""


def themes_page(handler):
    active = db.load_settings().get("theme", "default")
    cards = []
    for t in db.list_themes():
        is_active = t["name"] == active
        btn = ("<span class='badge pub'>активна</span>" if is_active else
               f"<form method='post' action='/admin/themes/activate'><input type='hidden' name='theme' value='{t['name']}'>"
               f"<button class='btn small'>Активировать</button></form>")
        cards.append(f"""<div class="card row" style="justify-content:space-between">
<div><b>{e(t['name'])}</b><br><span class="muted">{e(t['description'])}</span></div>{btn}</div>""")
    content = f"""<h1>Темы оформления</h1>{''.join(cards)}
<div class="card">{THEME_HELP}</div>"""
    page(handler, "Темы", content)


# ---------- Настройки ----------

def settings_page(handler):
    st = db.load_settings()
    content = f"""<h1>Настройки сайта</h1>
<div class="card"><form method="post" action="/admin/settings/save">
<label>Название сайта</label><input type="text" name="site_title" value="{e(st.get('site_title',''))}">
<label>Девиз / tagline</label><input type="text" name="tagline" value="{e(st.get('tagline',''))}">
<label>Постов на страницу</label><input type="number" name="posts_per_page" min="1" max="50" value="{e(st.get('posts_per_page',5))}">
<label>Текст страницы «О сайте» (HTML)</label><textarea name="about_html" rows="4">{e(st.get('about_html',''))}</textarea>
<hr style="margin:1rem 0;border:none;border-top:1px solid #eee">
<h3>Сменить пароль администратора</h3>
<label>Текущий пароль</label><input type="password" name="current_password">
<label>Новый пароль</label><input type="password" name="new_password">
<div style="margin-top:1rem"><button class="btn">Сохранить настройки</button></div>
</form></div>"""
    page(handler, "Настройки", content)


def do_save_settings(handler, form):
    import app
    updates = {
        "site_title": form.get("site_title", "Блог"),
        "tagline": form.get("tagline", ""),
        "about_html": form.get("about_html", ""),
    }
    try:
        per = int(form.get("posts_per_page", "5"))
        updates["posts_per_page"] = max(1, min(50, per))
    except ValueError:
        pass
    db.save_settings(updates)
    new_pw = form.get("new_password", "")
    if new_pw:
        cur = app.password_hash(form.get("current_password", ""))
        if cur == db.load_settings().get("admin_password_hash"):
            db.save_settings({"admin_password_hash": app.password_hash(new_pw)})
            return back(handler, "/admin/settings", "Настройки сохранены, пароль изменён.")
        return back(handler, "/admin/settings", "Пароль НЕ изменён: неверный текущий пароль.", True)
    return back(handler, "/admin/settings", "Настройки сохранены.")
