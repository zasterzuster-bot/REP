"""Слой хранения данных CMS. Без базы данных: JSON-файлы на диске."""

import json
import os
import re
import uuid
from datetime import datetime, timezone
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
POSTS_DIR = DATA_DIR / "posts"
CATEGORIES_FILE = DATA_DIR / "categories" / "categories.json"
SETTINGS_FILE = DATA_DIR / "settings" / "site.json"
HOME_FILE = DATA_DIR / "settings" / "home.json"
TEMPLATES_DIR = BASE_DIR / "templates"


def _ensure_dirs():
    POSTS_DIR.mkdir(parents=True, exist_ok=True)
    CATEGORIES_FILE.parent.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)


def slugify(text: str) -> str:
    """Транслитерация + формирование URL-слага (поддерживает кириллицу)."""
    translit = {
        "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "yo",
        "ж": "zh", "з": "z", "и": "i", "й": "y", "к": "k", "л": "l", "м": "m",
        "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t", "у": "u",
        "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sch",
        "ъ": "", "ы": "y", "ь": "", "э": "e", "ю": "yu", "я": "ya",
    }
    text = text.lower()
    text = "".join(translit.get(ch, ch) for ch in text)
    text = re.sub(r"[^a-z0-9]+", "-", text)
    return text.strip("-") or uuid.uuid4().hex[:8]


def unique_slug(base: str, taken: set) -> str:
    slug, i = base, 1
    while slug in taken:
        i += 1
        slug = f"{base}-{i}"
    return slug


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S")


# ---------- Категории (древовидная структура, любая вложенность) ----------

def load_categories() -> dict:
    _ensure_dirs()
    if not CATEGORIES_FILE.exists():
        _save({"items": []})
    with open(CATEGORIES_FILE, encoding="utf-8") as f:
        return json.load(f)


def _save(data: dict):
    _ensure_dirs()
    tmp = CATEGORIES_FILE.with_suffix(".tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    os.replace(tmp, CATEGORIES_FILE)


def get_category_tree() -> list:
    """Возвращает список корневых категорий, у каждой children — рекурсивно."""
    items = load_categories()["items"]
    by_id = {c["id"]: {**c, "children": []} for c in items}
    roots = []
    for c in by_id.values():
        parent = by_id.get(c.get("parent_id"))
        if parent is not None:
            parent["children"].append(c)
        else:
            roots.append(c)
    def sort_rec(nodes):
        nodes.sort(key=lambda n: (n.get("order", 0), n["title"]))
        for n in nodes:
            sort_rec(n["children"])
    sort_rec(roots)
    return roots


def find_category(cat_id: str, tree=None):
    if tree is None:
        tree = [get_category_tree()]  # обёртка, чтобы не мутировать
        tree = tree[0]
    for c in tree:
        if c["id"] == cat_id:
            return c
        found = find_category(cat_id, c["children"])
        if found:
            return found
    return None


def find_category_by_slug(slug: str, tree=None):
    if tree is None:
        tree = get_category_tree()
    for c in tree:
        if c["slug"] == slug:
            return c
        found = find_category_by_slug(slug, c["children"])
        if found:
            return found
    return None


def category_path(slug: str) -> list:
    """Цепочка категорий от корня до категории с указанным полным путью-slug."""
    def walk(nodes, trail):
        for n in nodes:
            cur = trail + [n]
            full = "/".join(x["slug"] for x in cur)
            if full == slug:
                return cur
            found = walk(n["children"], cur)
            if found:
                return found
        return None
    return walk(get_category_tree(), []) or []


def category_depth(cat_id: str) -> int:
    """Уровень вложенности категории (корень = 0)."""
    items = load_categories()["items"]
    by_id = {c["id"]: c for c in items}
    d, cur = 0, by_id.get(cat_id)
    while cur and cur.get("parent_id") and guard_ok(d):
        cur = by_id.get(cur["parent_id"])
        d += 1
    return d


def guard_ok(d):
    return d < 50


def add_category(title: str, parent_id: str = None, description: str = "") -> dict:
    data = load_categories()
    slugs = {c["slug"] for c in data["items"]}
    cat = {
        "id": uuid.uuid4().hex[:12],
        "title": title.strip(),
        "slug": unique_slug(slugify(title), slugs),
        "parent_id": parent_id or None,
        "description": description.strip(),
        "order": len([c for c in data["items"] if (c.get("parent_id") or None) == (parent_id or None)]),
        "created_at": now_iso(),
    }
    data["items"].append(cat)
    _save(data)
    return cat


def update_category(cat_id: str, fields: dict):
    data = load_categories()
    for c in data["items"]:
        if c["id"] == cat_id:
            for k in ("title", "description", "parent_id", "order"):
                if k in fields:
                    c[k] = fields[k]
            if "slug" in fields and fields["slug"]:
                slugs = {x["slug"] for x in data["items"] if x["id"] != cat_id}
                c["slug"] = unique_slug(slugify(fields["slug"]), slugs)
            break
    _save(data)


def delete_category(cat_id: str):
    """Удаляет категорию и все подкатегории; посты отвязываются."""
    data = load_categories()
    ids = {cat_id}
    changed = True
    while changed:  # собираем всё поддерево
        changed = False
        for c in data["items"]:
            if c.get("parent_id") in ids and c["id"] not in ids:
                ids.add(c["id"])
                changed = True
    data["items"] = [c for c in data["items"] if c["id"] not in ids]
    _save(data)
    for p in load_posts():
        if p.get("category_id") in ids:
            remove_post_category(p["slug"], cat_id)
            for i in ids:
                p2 = load_post(p["slug"])
                if p2 and i in (p2.get("category_ids") or []):
                    upd = {"category_ids": [x for x in p2["category_ids"] if x != i]}
                    save_post(p2["slug"], upd)


def category_full_slug(cat_id: str) -> str:
    """Полный путь slug через все уровни вложенности: tech/web/frontend."""
    items = load_categories()["items"]
    by_id = {c["id"]: c for c in items}
    parts = []
    cur = by_id.get(cat_id)
    guard = 0
    while cur and guard < 50:
        parts.append(cur["slug"])
        cur = by_id.get(cur.get("parent_id"))
        guard += 1
    return "/".join(reversed(parts))


# ---------- Посты ----------

def load_posts() -> list:
    _ensure_dirs()
    posts = []
    for fp in sorted(POSTS_DIR.glob("*.json")):
        try:
            with open(fp, encoding="utf-8") as f:
                posts.append(json.load(f))
        except (json.JSONDecodeError, OSError):
            continue
    posts.sort(key=lambda p: p.get("published_at", ""), reverse=True)
    return posts


def load_post(slug: str):
    fp = POSTS_DIR / f"{slug}.json"
    if not fp.exists():
        return None
    try:
        with open(fp, encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return None


def save_post(slug: str, fields: dict) -> dict:
    _ensure_dirs()
    post = load_post(slug) or {}
    post.update(fields)
    post["slug"] = slug
    post.setdefault("id", uuid.uuid4().hex[:12])
    post.setdefault("created_at", now_iso())
    post["updated_at"] = now_iso()
    with open(POSTS_DIR / f"{slug}.json", "w", encoding="utf-8") as f:
        json.dump(post, f, ensure_ascii=False, indent=2)
    return post


def create_post(title: str, body: str, category_ids: list, tags: list,
                status: str = "draft", excerpt: str = "") -> dict:
    existing = {p["slug"] for p in load_posts()}
    slug = unique_slug(slugify(title), existing)
    return save_post(slug, {
        "title": title.strip(),
        "body": body,
        "excerpt": excerpt.strip(),
        "category_ids": category_ids,
        "tags": tags,
        "status": status,  # draft | published
        "published_at": now_iso(),
    })


def delete_post(slug: str):
    fp = POSTS_DIR / f"{slug}.json"
    if fp.exists():
        fp.unlink()


def remove_post_category(slug: str, cat_id: str):
    p = load_post(slug)
    if p and cat_id in (p.get("category_ids") or []):
        save_post(slug, {"category_ids": [c for c in p["category_ids"] if c != cat_id]})


def posts_for_category(cat_id: str, include_children: bool = True) -> list:
    ids = {cat_id}
    if include_children:
        def collect(node):
            ids.add(node["id"])
            for ch in node["children"]:
                collect(ch)
        node = find_category(cat_id)
        if node:
            ids.discard(cat_id)
            collect(node)
            ids.add(cat_id)
    result = []
    for p in load_posts():
        if p.get("status") != "published":
            continue
        if ids & set(p.get("category_ids") or []):
            result.append(p)
    return result


# ---------- Настройки сайта / главная страница / активная тема ----------

def load_settings() -> dict:
    _ensure_dirs()
    defaults = {
        "site_title": "My Blog CMS",
        "tagline": "Блог без базы данных",
        "theme": "default",
        "posts_per_page": 5,
    }
    if SETTINGS_FILE.exists():
        try:
            with open(SETTINGS_FILE, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def save_settings(fields: dict):
    s = load_settings()
    s.update(fields)
    SETTINGS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(SETTINGS_FILE, "w", encoding="utf-8") as f:
        json.dump(s, f, ensure_ascii=False, indent=2)


def load_home() -> dict:
    defaults = {
        "hero_title": "Добро пожаловать!",
        "hero_text": "Это главная страница вашего блога. Отредактируйте её в админке.",
        "sections": [],  # [{"type":"text","title":...,"html":...}, {"type":"latest_posts","title":"Свежие записи"}]
    }
    if HOME_FILE.exists():
        try:
            with open(HOME_FILE, encoding="utf-8") as f:
                defaults.update(json.load(f))
        except (json.JSONDecodeError, OSError):
            pass
    return defaults


def save_home(data: dict):
    HOME_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(HOME_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


# ---------- Темы ----------

def list_themes() -> list:
    themes = []
    if TEMPLATES_DIR.exists():
        for d in sorted(TEMPLATES_DIR.iterdir()):
            if d.is_dir() and (d / "base.html").exists():
                desc = ""
                meta = d / "theme.json"
                if meta.exists():
                    try:
                        desc = json.loads(meta.read_text(encoding="utf-8")).get("description", "")
                    except (json.JSONDecodeError, OSError):
                        pass
                themes.append({"name": d.name, "description": desc})
    return themes
