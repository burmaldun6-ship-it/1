# Black Russia Complaint Bot

Telegram-бот на Python + aiogram 3 для подготовки жалоб по скриншотам Black Russia.

## Возможности

- /start — инструкция по использованию.
- Принимаются только фото с подписью из 3 строк: `Ваш ник:...`, `Ссылка на фото:https://...`, `На какого игрока писать жалобу(ник):...`.
- Строгая проверка Nickname: `^[A-Z][a-z]*_[A-Z][a-z]*$`.
- По умолчанию максимум 5 **успешных** жалоб в календарные сутки.
- Лимит хранится в SQLite.
- Администратор из `ADMIN_ID` не ограничен лимитом.
- /admin_panel — защищённая админ-панель.
- В панели есть статус, изменение лимита конкретного пользователя, изменение общего лимита и выгрузка полного журнала AI в Markdown.
- Все попытки обращения к AI записываются в SQLite, включая ошибки API.
- API задаётся через `OPENAI_API_KEY`, `OPENAI_BASE_URL`, `OPENAI_MODEL`.

## Установка

Python 3.11+:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
python bot.py
```

На Windows PowerShell:

```powershell
py -m venv .venv
.venv\\Scripts\\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
python bot.py
```

## Переменные окружения

Обязательные:

- `BOT_TOKEN`
- `ADMIN_ID`
- `OPENAI_API_KEY`

Необязательные:

- `OPENAI_BASE_URL` — по умолчанию `https://api.openai.com/v1`.
- `OPENAI_MODEL` — модель vision, совместимая с Chat Completions.
- `DATABASE_PATH` — путь к SQLite.
- `DEFAULT_DAILY_LIMIT` — начальный общий лимит, по умолчанию 5.

## Формат API

Используется OpenAI-compatible Chat Completions:

- system message загружается из `prompt.md` и содержит строгие правила проверки именно целевого игрока;
- user message содержит `Ваш ник`, целевой ник, ссылку на доказательство и изображение как data URL;
- `temperature=0`.

Это позволяет использовать OpenAI или совместимый endpoint через `OPENAI_BASE_URL`.

## Админ-панель

Доступ разрешён только если `Telegram user_id == ADMIN_ID`.

### Лимит пользователя

Кнопка «Лимит пользователя» ожидает:

```
123456789 10
```

### Общий лимит

Кнопка «Общий лимит» ожидает одно целое число.

Лимит 0 означает запрет новых пользовательских запросов. Администратор всё равно остаётся без ограничений.

### Экспорт

Кнопка «Экспорт .md» отправляет файл `ai_logs.md` со всеми обращениями к ИИ в формате:

```markdown
## дата — имя_в_telegram|telegram_id
**Ник:** Abc_Dfs
**Link:** https://...

**Запрос:**
...

**Что ему ответила ИИ:**
...
```

## WispByte

Создай Python-сервер, загрузите репозиторий/файлы и задайте environment variables в панели хостинга. Startup command:

```bash
python bot.py
```

Для SQLite важно, чтобы каталог с базой находился на постоянном диске/volume, если выбранный тип сервера очищает рабочую файловую систему при пересоздании.

## Безопасность

- `.env` не коммитится.
- Токены и API key не находятся в исходниках.
- Админ проверяется по Telegram user ID из `ADMIN_ID`.
- SQLite-файл исключён из Git.

## Лицензия

MIT.
