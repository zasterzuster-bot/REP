import json
import os
import re
import sqlite3
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

BASE = os.path.dirname(os.path.abspath(__file__))
DB = os.path.join(BASE, "sites.db")

CATEGORIES = ["Новости", "Технологии", "Финансы", "Здоровье", "Развлечения",
              "Образование", "E-commerce", "Игры", "Авто", "Путешествия"]
RATINGS = ["TLD-AI", "Majestic TF", "Ahrefs DR", "Moz DA", "PR(Google)", "xRank", "CyberMD"]


def db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    with db() as conn:
        conn.execute("""CREATE TABLE IF NOT EXISTS sites(
            id TEXT PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL,
            description TEXT DEFAULT '', category TEXT DEFAULT '',
            price_per_1000 INTEGER DEFAULT 0, currency TEXT DEFAULT 'USD',
            traffic INTEGER DEFAULT 0, region TEXT DEFAULT '', languages TEXT DEFAULT '',
            ratings TEXT DEFAULT '{}', tags TEXT DEFAULT '', contact_email TEXT DEFAULT '',
            created_at TEXT)""")
        if conn.execute("SELECT COUNT(*) c FROM sites").fetchone()["c"] == 0:
            demo = [
                dict(name="TechDaily", url="https://techdaily.example.com",
                     description="Ежедневные новости о технологиях, гаджетах и стартапах. Аудитория — IT-специалисты и энтузиасты.",
                     category="Технологии", price_per_1000=12, currency="USD", traffic=850000,
                     region="СНГ", languages="RU,EN",
                     ratings={"TLD-AI": "78", "Majestic TF": "45", "Ahrefs DR": "62", "Moz DA": "58", "PR(Google)": "5", "xRank": "150k"},
                     tags="технологии,гаджеты,стартапы", contact_email="ads@techdaily.example.com"),
                dict(name="FinWise", url="https://finwise.example.com",
                     description="Финансовый портал: инвестиции, кредиты, вклады, курсы валют. Высокая конверсия на финансовые офферы.",
                     category="Финансы", price_per_1000=25, currency="USD", traffic=420000,
                     region="Россия", languages="RU",
                     ratings={"TLD-AI": "81", "Majestic TF": "52", "Ahrefs DR": "70", "Moz DA": "61", "PR(Google)": "6", "xRank": "300k"},
                     tags="инвестиции,кредиты,финансы", contact_email="promo@finwise.example.com"),
                dict(name="GameZone", url="https://gamezone.example.com",
                     description="Крупнейший игровой журнал: обзоры, гайды, киберспорт. Молодая активная аудитория 18-30.",
                     category="Игры", price_per_1000=8, currency="USD", traffic=1200000,
                     region="Мировой", languages="EN,RU",
                     ratings={"TLD-AI": "74", "Majestic TF": "40", "Ahrefs DR": "55", "Moz DA": "50", "PR(Google)": "5", "xRank": "90k"},
                     tags="игры,киберспорт,обзоры", contact_email="adv@gamezone.example.com"),
                dict(name="HealthPlus", url="https://healthplus.example.com",
                     description="Порт о здоровье и медицине: советы врачей, диеты, фитнес. Доверие аудитории — залог высокой CTR.",
                     category="Здоровье", price_per_1000=15, currency="EUR", traffic=300000,
                     region="Европа", languages="EN,DE",
                     ratings={"TLD-AI": "69", "Majestic TF": "38", "Ahrefs DR": "48", "Moz DA": "44", "PR(Google)": "4", "xRank": "500k"},
                     tags="здоровье,медицина,фитнес", contact_email="media@healthplus.example.com"),
            ]
            for d in demo:
                d["id"] = str(uuid.uuid4())
                d["created_at"] = datetime.now().isoformat()
                d["ratings"] = json.dumps(d["ratings"], ensure_ascii=False)
                cols = ",".join(d.keys())
                marks = ",".join("?" * len(d))
                conn.execute(f"INSERT INTO sites({cols}) VALUES({marks})", list(d.values()))
        conn.commit()


def row_to_dict(r):
    d = dict(r)
    try:
        d["ratings"] = json.loads(d.get("ratings") or "{}")
    except Exception:
        d["ratings"] = {}
    return d


ALLOWED_FIELDS = {"name", "url", "description", "category", "price_per_1000",
                  "currency", "traffic", "region", "languages", "tags", "contact_email"}


PAGE = """<!DOCTYPE html>
<html lang="ru">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AdMarket — биржа прямой рекламы</title>
<style>
:root{--bg:#0f1420;--card:#1a2233;--accent:#4f8cff;--green:#3ecf8e;--text:#e8edf6;--muted:#8b96ab}
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:'Segoe UI',Arial,sans-serif;background:var(--bg);color:var(--text)}
header{background:linear-gradient(135deg,#16203a,#0f1420);padding:28px 20px;text-align:center;border-bottom:1px solid #26314a}
header h1{font-size:30px}
header h1 span{color:var(--accent)}
header p{color:var(--muted);margin-top:6px}
nav{display:flex;gap:10px;justify-content:center;margin-top:16px;flex-wrap:wrap}
nav button{background:var(--card);color:var(--text);border:1px solid #2b3a5a;padding:9px 18px;border-radius:8px;cursor:pointer;font-size:15px}
nav button.active,nav button:hover{background:var(--accent);border-color:var(--accent);color:#fff}
main{max-width:1100px;margin:0 auto;padding:24px 16px}
.filters{display:flex;gap:10px;flex-wrap:wrap;margin-bottom:18px}
.filters input,.filters select{background:var(--card);border:1px solid #2b3a5a;color:var(--text);padding:9px 12px;border-radius:8px;font-size:14px}
.card{background:var(--card);border:1px solid #26314a;border-radius:12px;padding:18px;margin-bottom:16px}
.card h3{font-size:19px}
.card h3 a{color:var(--accent);text-decoration:none}
.badges{display:flex;gap:8px;flex-wrap:wrap;margin:8px 0}
.badge{background:#243352;color:#bcd0ff;padding:3px 10px;border-radius:20px;font-size:12px}
.price{color:var(--green);font-weight:bold;font-size:17px}
.desc{color:var(--muted);margin:8px 0;font-size:14px;line-height:1.5}
.ratings{display:flex;gap:6px;flex-wrap:wrap;margin-top:10px}
.rt{background:#111828;border:1px solid #2b3a5a;border-radius:8px;padding:5px 9px;font-size:12px;color:var(--muted)}
.rt b{color:var(--text);margin-left:4px}
.actions{margin-top:12px;display:flex;gap:8px}
.actions button{background:transparent;border:1px solid #5a2b3a;color:#ff8fa3;padding:6px 14px;border-radius:8px;cursor:pointer;font-size:13px}
.form-grid{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.form-grid label{display:flex;flex-direction:column;font-size:13px;color:var(--muted);gap:5px}
.form-grid input,.form-grid select,.form-grid textarea{background:#111828;border:1px solid #2b3a5a;color:var(--text);padding:9px;border-radius:8px;font-size:14px;font-family:inherit}
.form-grid .full{grid-column:1/-1}
.btn-primary{background:var(--accent);color:#fff;border:none;padding:12px 22px;border-radius:8px;font-size:15px;cursor:pointer;margin-top:14px}
.stats{display:flex;gap:16px;flex-wrap:wrap;margin-bottom:20px}
.stat{background:var(--card);border:1px solid #26314a;border-radius:12px;padding:14px 22px;text-align:center}
.stat .v{font-size:22px;font-weight:bold;color:var(--accent)}
.stat .l{font-size:12px;color:var(--muted)}
.hidden{display:none}
h2{margin-bottom:14px;font-size:22px}
footer{text-align:center;color:var(--muted);padding:24px;font-size:13px}
#msg{margin:10px 0;font-size:14px;color:var(--green)}
@media(max-width:640px){.form-grid{grid-template-columns:1fr}}
</style>
</head>
<body>
<header>
  <h1>Ad<span>Market</span></h1>
  <p>Биржа прямой рекламы: владельцы сайтов размещают свои площадки, рекламодатели выбирают напрямую, без посредников</p>
  <nav>
    <button id="nav-list" class="active" onclick="showView('list')">📋 Каталог сайтов</button>
    <button id="nav-add" onclick="showView('add')">➕ Добавить сайт</button>
  </nav>
</header>
<main>
  <div id="view-list">
    <div class="stats" id="stats"></div>
    <div class="filters">
      <input id="fq" placeholder="🔍 Поиск по названию/описанию" oninput="loadList()">
      <select id="fcat" onchange="loadList()"><option value="">Все категории</option></select>
      <select id="fsort" onchange="loadList()">
        <option value="">Без сортировки</option>
        <option value="price_asc">Цена: по возрастанию</option>
        <option value="price_desc">Цена: по убыванию</option>
        <option value="traffic_desc">Трафик: по убыванию</option>
      </select>
    </div>
    <div id="list"></div>
  </div>

  <div id="view-add" class="hidden">
    <h2>Добавить свой сайт в каталог</h2>
    <div id="msg"></div>
    <div class="card">
      <form id="site-form" onsubmit="return submitSite(event)">
        <div class="form-grid">
          <label>Название сайта *<input name="name" required placeholder="MySite"></label>
          <label>URL сайта *<input name="url" required type="url" placeholder="https://example.com"></label>
          <label>Категория
            <select name="category" id="cat-select"></select>
          </label>
          <label>Цена за 1000 показов (CPM)<input name="price_per_1000" type="number" min="0" placeholder="10"></label>
          <label>Валюта
            <select name="currency"><option>USD</option><option>EUR</option><option>RUB</option><option>UAH</option></select>
          </label>
          <label>Месячный трафик (визитов)<input name="traffic" type="number" min="0" placeholder="100000"></label>
          <label>Регион аудитории<input name="region" placeholder="Россия / СНГ / Мировой"></label>
          <label>Языки<input name="languages" placeholder="RU,EN"></label>
          <label>Контактный e-mail<input name="contact_email" type="email" placeholder="ads@example.com"></label>
          <label>Теги (через запятую)<input name="tags" placeholder="новости,блог"></label>
          <label class="full">Описание сайта<textarea name="description" rows="4" placeholder="Расскажите о сайте: тематика, аудитория, форматы рекламы..."></textarea></label>
          <div class="full"><b style="font-size:14px">Рейтинги и метрики</b>
            <div class="form-grid" style="margin-top:8px" id="ratings-grid"></div>
          </div>
        </div>
        <button class="btn-primary" type="submit">Опубликовать сайт</button>
      </form>
    </div>
  </div>
</main>
<footer>AdMarket © 2026 — прямая реклама между владельцами сайтов и рекламодателями</footer>
<script>
const RATINGS=["TLD-AI","Majestic TF","Ahrefs DR","Moz DA","PR(Google)","xRank","CyberMD"];
let SITES=[],CATS=[];
async function api(path,opts){const r=await fetch(path,opts);return r.json();}
function showView(v){
  document.getElementById('view-list').classList.toggle('hidden',v!=='list');
  document.getElementById('view-add').classList.toggle('hidden',v!=='add');
  document.getElementById('nav-list').classList.toggle('active',v==='list');
  document.getElementById('nav-add').classList.toggle('active',v==='add');
}
function esc(s){return String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));}
function fmt(n){return Number(n||0).toLocaleString('ru-RU');}
async function loadMeta(){
  const m=await api('/api/meta');CATS=m.categories;
  document.getElementById('fcat').innerHTML='<option value="">Все категории</option>'+CATS.map(c=>`<option>${esc(c)}</option>`).join('');
  document.getElementById('cat-select').innerHTML='<option value="">— выберите —</option>'+CATS.map(c=>`<option>${esc(c)}</option>`).join('');
  document.getElementById('ratings-grid').innerHTML=RATINGS.map(r=>`<label>${esc(r)}<input name="rating_${esc(r)}" placeholder="напр. 62"></label>`).join('');
}
async function loadList(){
  const q=document.getElementById('fq').value.trim();
  const cat=document.getElementById('fcat').value;
  const sort=document.getElementById('fsort').value;
  const params=new URLSearchParams();
  if(q)params.set('q',q);if(cat)params.set('category',cat);if(sort)params.set('sort',sort);
  SITES=(await api('/api/sites?'+params)).sites;
  document.getElementById('stats').innerHTML=`
    <div class="stat"><div class="v">${SITES.length}</div><div class="l">сайтов найдено</div></div>
    <div class="stat"><div class="v">${fmt(SITES.reduce((s,x)=>s+(x.traffic||0),0))}</div><div class="l">суммарный трафик</div></div>
    <div class="stat"><div class="v">${SITES.length?Math.round(SITES.reduce((s,x)=>s+(x.price_per_1000||0),0)/SITES.length):0}</div><div class="l">средний CPM</div></div>`;
  document.getElementById('list').innerHTML=SITES.map(s=>`
    <div class="card">
      <h3><a href="${esc(s.url)}" target="_blank" rel="noopener">${esc(s.name)}</a> <span style="color:var(--muted);font-size:13px;font-weight:normal">${esc(s.url.replace(/^https?:\\/\\//,''))}</span></h3>
      <div class="badges">
        ${s.category?`<span class="badge">📁 ${esc(s.category)}</span>`:''}
        <span class="badge price">💰 ${fmt(s.price_per_1000)} ${esc(s.currency)} / 1000 показов</span>
        ${s.traffic?`<span class="badge">👥 ${fmt(s.traffic)} визитов/мес</span>`:''}
        ${s.region?`<span class="badge">🌍 ${esc(s.region)}</span>`:''}
        ${s.languages?`<span class="badge">🗣 ${esc(s.languages)}</span>`:''}
      </div>
      <div class="desc">${esc(s.description)}</div>
      <div class="ratings">${Object.entries(s.ratings||{}).map(([k,v])=>`<span class="rt">${esc(k)}:<b>${esc(v)}</b></span>`).join('')}</div>
      ${s.tags?`<div class="badges" style="margin-top:8px">${s.tags.split(',').filter(Boolean).map(t=>`<span class="badge">#${esc(t.trim())}</span>`).join('')}</div>`:''}
      <div class="actions">
        <button onclick="alert('Контакты владельца: ${esc(s.contact_email||'не указаны')}')">✉ Связаться с владельцем</button>
        <button onclick="delSite('${s.id}')">🗑 Удалить</button>
      </div>
    </div>`).join('')||'<p style="color:var(--muted)">Сайты не найдены. Добавьте первый!</p>';
}
async function submitSite(e){
  e.preventDefault();
  const f=new FormData(e.target);const data={};
  for(const[k,v]of f){
    if(k.startsWith('rating_')){if(v.trim())data.ratings=data.ratings||{},data.ratings[k.slice(7)]=v.trim();}
    else data[k]=v;
  }
  const r=await api('/api/sites',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  if(r.ok){document.getElementById('msg').textContent='✅ Сайт опубликован!';e.target.reset();showView('list');loadList();}
  else document.getElementById('msg').textContent='❌ Ошибка: '+(r.error||'unknown');
  return false;
}
async function delSite(id){
  if(!confirm('Удалить сайт из каталога?'))return;
  await api('/api/sites/'+id,{method:'DELETE'});loadList();
}
loadMeta().then(loadList);
</script>
</body>
</html>"""


class Handler(BaseHTTPRequestHandler):
    def _send(self, code, body, ctype="application/json; charset=utf-8"):
        data = body.encode("utf-8") if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _json_body(self):
        length = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(length) or b"{}")
        except Exception:
            return {}

    def do_GET(self):
        path = self.path.split("?")[0]
        if path in ("/", "/index.html"):
            self._send(200, PAGE, "text/html; charset=utf-8")
        elif path == "/api/meta":
            self._send(200, json.dumps({"categories": CATEGORIES, "ratings": RATINGS}))
        elif path == "/api/sites":
            from urllib.parse import urlparse, parse_qs
            qs = parse_qs(urlparse(self.path).query)
            sql, args = "SELECT * FROM sites", []
            conds, params = [], []
            if qs.get("q", [""])[0]:
                like = "%" + qs["q"][0] + "%"
                conds.append("(name LIKE ? OR description LIKE ? OR tags LIKE ?)")
                params += [like, like, like]
            if qs.get("category", [""])[0]:
                conds.append("category = ?")
                params.append(qs["category"][0])
            sql += (" WHERE " + " AND ".join(conds)) if conds else ""
            sort = qs.get("sort", [""])[0]
            if sort == "price_asc":
                sql += " ORDER BY price_per_1000 ASC"
            elif sort == "price_desc":
                sql += " ORDER BY price_per_1000 DESC"
            elif sort == "traffic_desc":
                sql += " ORDER BY traffic DESC"
            with db() as conn:
                rows = [row_to_dict(r) for r in conn.execute(sql, params)]
            self._send(200, json.dumps({"sites": rows}, ensure_ascii=False))
        else:
            self._send(404, '{"error":"not found"}')

    def do_POST(self):
        if self.path == "/api/sites":
            data = self._json_body()
            name = (data.get("name") or "").strip()
            url = (data.get("url") or "").strip()
            if not name or not re.match(r"^https?://", url):
                self._send(400, json.dumps({"error": "нужны название и корректный URL (http://...)"}))
                return
            ratings = {k: str(v)[:40] for k, v in (data.get("ratings") or {}).items() if str(v).strip()}
            rec = dict(
                id=str(uuid.uuid4()), name=name[:120], url=url[:300],
                description=(data.get("description") or "")[:2000],
                category=data.get("category") if data.get("category") in CATEGORIES else "",
                price_per_1000=max(0, int(data.get("price_per_1000") or 0)),
                currency=(data.get("currency") or "USD")[:8],
                traffic=max(0, int(data.get("traffic") or 0)),
                region=(data.get("region") or "")[:100],
                languages=(data.get("languages") or "")[:100],
                ratings=json.dumps(ratings, ensure_ascii=False),
                tags=(data.get("tags") or "")[:300],
                contact_email=(data.get("contact_email") or "")[:120],
                created_at=datetime.now().isoformat(),
            )
            with db() as conn:
                conn.execute("INSERT INTO sites VALUES(%s)" % ",".join("?" * len(rec)), list(rec.values()))
                conn.commit()
            self._send(200, json.dumps({"ok": True, "id": rec["id"]}))
        else:
            self._send(404, '{"error":"not found"}')

    def do_DELETE(self):
        m = re.match(r"^/api/sites/([\w-]+)$", self.path)
        if m:
            with db() as conn:
                conn.execute("DELETE FROM sites WHERE id=?", (m.group(1),))
                conn.commit()
            self._send(200, '{"ok":true}')
        else:
            self._send(404, '{"error":"not found"}')

    def log_message(self, *a):
        pass


if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 8000))
    print("AdMarket running on http://localhost:%d" % port)
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
