# Установка AdMarket на свой хостинг

Проект не имеет внешних зависимостей — нужен только **Python 3.8+** и файл `app.py`.
Данные хранятся в SQLite-файле `sites.db` (создаётся автоматически при первом запуске).

Минимальный набор файлов для загрузки на сервер:
```
app.py       — само приложение (сервер + база + фронтенд в одном файле)
sites.db     — (опционально) если хотите перенести уже существующие данные
```

---

## Вариант 1. VPS / выделенный сервер (рекомендуется)

Подойдёт любой VPS с Ubuntu/Debian (от $3–5/мес: Hetzner, DigitalOcean, Timeweb, Selectel и т.п.).

### 1. Загрузите файлы на сервер
```bash
scp app.py user@ваш-сервер:/opt/admarket/
ssh user@ваш-сервер
sudo mkdir -p /opt/admarket && sudo mv app.py /opt/admarket/ 2>/dev/null || true
```

### 2. Проверьте Python и запустите вручную (для теста)
```bash
python3 --version          # должно быть 3.8+
cd /opt/admarket
PORT=8000 python3 app.py   # проверьте: curl http://localhost:8000
```

### 3. Автозапуск через systemd (чтобы сайт работал всегда)
Создайте файл `/etc/systemd/system/admarket.service`:
```ini
[Unit]
Description=AdMarket
After=network.target

[Service]
WorkingDirectory=/opt/admarket
ExecStart=/usr/bin/python3 /opt/admarket/app.py
Environment=PORT=8000
Restart=always
User=www-data

[Install]
WantedBy=multi-user.target
```

Включите и запустите:
```bash
sudo systemctl daemon-reload
sudo systemctl enable --now admarket
sudo systemctl status admarket
```

### 4. Домен + HTTPS через nginx
`/etc/nginx/sites-available/admarket`:
```nginx
server {
    listen 80;
    server_name yourdomain.com;

    location / {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
    }
}
```
```bash
sudo ln -s /etc/nginx/sites-available/admarket /etc/nginx/sites-enabled/
sudo nginx -t && sudo systemctl reload nginx

# Бесплатный сертификат Let's Encrypt:
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d yourdomain.com
```

Готово — сайт доступен по `https://yourdomain.com`.

---

## Вариант 2. Docker (любой хостинг с поддержкой контейнеров)

Создайте `Dockerfile` рядом с `app.py`:
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY app.py .
EXPOSE 8000
CMD ["python3", "app.py"]
```

Запуск:
```bash
docker build -t admarket .
docker run -d --restart always -p 8000:8000 \
  -v $(pwd)/data:/app/data admarket
```
> Примечание: чтобы база не терялась при пересборке образа, можно смонтировать
> том и указать путь к ней, либо просто копировать `sites.db` в `/app/data`.

Подходит для Render, Railway, Fly.io, а также любого VPS с Docker.

---

## Вариант 3. Shared-хостинг (cPanel / Plesk, без root-доступа)

На таких хостингах нельзя держать постоянный процесс, но приложение можно
запустить как **CGI-скрипт**:

1. Переименуйте `app.py` → `admarket.cgi` и положите в папку `cgi-bin/`.
2. В самом начале файла добавьте shebang:
   ```python
   #!/usr/bin/env python3
   ```
3. Дайте права на исполнение: `chmod 755 admarket.cgi`.
4. В коде заменьте `ThreadingHTTPServer(...)` на CGI-обработчик одного запроса
   (например, через модуль `cgitb` + `os.environ['REQUEST_METHOD']`) — либо
   выберите хостинг с поддержкой Python-приложений.

**Проще:** многие cPanel-хостинги имеют раздел **«Setup Python App»**
(Passenger). Там достаточно:
- создать Python-приложение в cPanel;
- указать точку входа (нужен небольшой WSGI-совместимый wrapper);
- приложение само получит домен и будет перезапускаться.

Если на хостинге есть **SSH + Python**, самый быстрый путь:
```bash
nohup python3 app.py > admarket.log 2>&1 &
```
(но после перезагрузки сервера процесс нужно будет запускать заново).

---

## Вариант 4. Бесплатные платформы (за пару минут)

| Платформа | Как |
|---|---|
| **PythonAnywhere** | Аккаунт → Files → загрузить `app.py` → Bash-консоль: `python3 app.py` работает только как веб-приложение через Flask… Для данного проекта проще всего выбрать «Flask» и обернуть обработчики (см. ниже) |
| **Render.com** | Create → Web Service → подключить GitHub-репозиторий → Build: `pip install -r requirements.txt` (пустой) → Start: `python3 app.py`, Free plan |
| **Railway.app** | New Project → Deploy from GitHub → переменная `PORT` подставляется автоматически |
| **Vercel/Netlify** | Не подойдут: это статические/serverless-платформы, а нужен постоянный процесс с базой |

Для Render/Railway создайте `requirements.txt` (можно пустой) и `Procfile`/start-command:
```
python3 app.py
```
Обязательно читайте пункт «Порт» ниже!

---

## Важные замечания

### 📌 Порт
Хостинги (Render, Railway, Fly) сами назначают порт через переменную окружения
`PORT`. Проект её уже поддерживает: `port = int(os.environ.get("PORT", 8000))` —
ничего менять не нужно.

### 📌 База данных
- Данные лежат в файле `sites.db` в той же папке, что и `app.py`.
- На контейнерных платформах с «эфемерной» ФС (Render Free, Heroku) файл
  перезаписывается при каждом деплое. Решения:
  - использовать постоянный диск/том (`fly volumes`, Railway Volume);
  - или перенести хранение в PostgreSQL (потребуется небольшая правка функции `db()`).
- Сделайте резервную копию: `cp sites.db sites-backup.db` или скачайте по SCP.

### 📌 Безопасность
- Сейчас удаление объявлений доступно любому (нет авторизации). Для публичного
  хостинга рекомендуется добавить простой пароль/токен на `POST /api/sites`
  и `DELETE /api/sites/{id}`.
- Ставьте HTTPS (certbot из Варианта 1) — форма добавления сайтов передаёт данные по сети.

### 📌 Обновление сайта
```bash
# VPS:
sudo scp app.py user@server:/opt/admarket/
sudo systemctl restart admarket
```
Файл `sites.db` при этом не трогайте — данные сохранятся.

### 📌 Проверка после установки
```bash
curl -s https://yourdomain.com/api/meta | head    # список категорий/рейтингов
curl -s https://yourdomain.com/api/sites | head   # список сайтов
```
