# API Quality Monitor

Учебный проект QA Automation на Python: сервис запускает проверки REST API,
сохраняет историю в SQLite и формирует HTML-отчёты с причинами падений.

## Что умеет

- Проверяет HTTP-статусы, заголовки, JSON Schema (Draft 2020-12) и время ответа.
- Выполняет позитивные, негативные и авторизационные проверки.
- Превращает сетевые ошибки и таймауты в результаты упавших проверок.
- Хранит наборы проверок и историю запусков между перезапусками.
- Предоставляет Swagger UI по адресу `/docs` и отчёт `/runs/{id}/report`.

Стек: Python 3.11+, FastAPI, Pydantic, httpx, jsonschema, SQLite, pytest, Docker, GitHub Actions.
SQLite используется через стандартный модуль Python; ORM для такого объёма не требуется.

## Быстрый запуск с Docker

```sh
docker compose up --build -d
```

Откройте http://localhost:8000/docs. Для загрузки десяти демонстрационных проверок:

```sh
python -m venv .venv
# Windows PowerShell:
.venv\Scripts\Activate.ps1
# Linux/macOS: source .venv/bin/activate
python -m pip install -e ".[test]"
python scripts/demo.py
```

Ожидаемый результат: **7 PASS, 3 FAIL**. Ошибки намеренные: неправильный статус,
отсутствующий `id`, ответ дольше 100 мс. Отчёт сохраняется в `reports/run-<id>.html`.
Первый запрос выполняйте после готовности `/health` монитора.

## Запуск без Docker

Установите зависимости как выше. В двух терминалах запустите:

```sh
python -m uvicorn monitor.demo:app --port 8001
python -m uvicorn monitor.app:create_app --factory --port 8000
```

В третьем терминале (PowerShell):

```powershell
$env:TARGET_URL = "http://localhost:8001"
python scripts/demo.py
```

Для Linux/macOS: `TARGET_URL=http://localhost:8001 python scripts/demo.py`.
`MONITOR_URL` меняет адрес монитора, `MONITOR_DB` — путь к SQLite.

## REST API

| Метод | Путь | Назначение |
|---|---|---|
| POST / GET | `/suites` | Создать / получить наборы |
| POST / GET | `/suites/{id}/checks` | Добавить / получить проверки |
| POST | `/suites/{id}/runs` | Выполнить проверки и сохранить результат |
| GET | `/suites/{id}/runs` | История запусков |
| GET | `/runs/{id}` | Результат в JSON |
| GET | `/runs/{id}/report` | HTML-отчёт |

Пример тела создания набора:

```json
{"name": "Shop regression", "base_url": "http://localhost:8001"}
```

Пример тела проверки:

```json
{
  "name": "Create user",
  "method": "POST",
  "path": "/users",
  "body": {"name": "Alice"},
  "expected_status": 201,
  "json_schema": {"type": "object", "required": ["id", "name"]},
  "max_response_ms": 500,
  "timeout_seconds": 5
}
```

## Проверка проекта

```sh
python -m pytest -q
```

Тесты выполняют полный цикл через ASGI без внешнего интернета: создание набора,
10 проверок, отчёт, экранирование HTML, сохранение истории после повторного открытия
БД, изоляцию наборов, невалидные входные данные, сетевые ошибки и таймауты.
CI выполняет их на Python 3.11–3.13.

## Устройство и границы первой версии

`monitor/models.py` — валидация; `runner.py` — исполнение; `app.py` — REST API,
SQLite и отчёты; `demo.py` — учебный API; `tests/` — тесты самого сервиса.

Запуск синхронный с точки зрения клиента: POST возвращает готовый отчёт после
последовательного выполнения всех проверок. Фоновой очереди и планировщика пока нет.
Демо `/users` возвращает фиксированный ID и не хранит пользователей.

Сервис предназначен для локального использования доверенным пользователем:
аутентификации нет, он может отправлять запросы на заданные пользователем адреса,
включая локальную сеть. Docker публикует порт только на loopback.
Не открывайте его в интернет без авторизации, ограничений исходящих адресов и лимитов.
Тела запросов и заголовки сохраняются в SQLite открытым текстом — используйте тестовые
токены. JSON Schema может включить значения ответа в текст ошибки.
Внешние ссылки JSON Schema запрещены; перенаправления HTTP не выполняются.

Дальнейшее развитие: цепочки запросов с передачей ID, импорт OpenAPI,
фоновые задания, пагинация истории, секреты через переменные окружения.
