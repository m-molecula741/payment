# Запуск

Сервис работает в Linux. Образ API собран на Debian, Postgres и RabbitMQ тоже запускаются как Linux-контейнеры. На хосте нужен Docker Engine и плагин Compose.

## Сборка и запуск

Скопируйте пример настроек и поднимите стек. В `.env.example` уже стоят значения, с которыми всё стартует без правок:

```bash
cp .env.example .env
docker compose up -d --build
docker compose ps
```

Остановка:

```bash
docker compose down
```

Данные Postgres остаются в volume. Чтобы стереть базу вместе с контейнерами: `docker compose down -v`.

## Куда ходить

| Что | Адрес | Вход |
|---|---|---|
| API | http://localhost:8000/docs | заголовок `X-API-Key: dev-api-key` |
| RabbitMQ | http://localhost:15672 | `payment` / `payment` |
| Postgres | `localhost:5432`, база `payment` | `payment` / `payment` |

Проверка, что API живой:

```bash
curl http://localhost:8000/health
```

Ожидается `{"status":"ok"}`.

Таблицы и очереди:

```bash
docker compose exec postgres psql -U payment -d payment -c '\dt'
docker compose exec rabbitmq rabbitmqctl list_queues name
```

В базе есть `payments`, `outbox` и `alembic_version`. В RabbitMQ — очереди `payments.new`, `payments.retry.1000`, `payments.retry.2000` и `payments.dlq`.

Запросы, блокировки, коммит и откат живут в методах `db/repositories`. Сервис их только вызывает. Платёж и строка outbox записываются одним методом репозитория.

## Пример платежа

`Idempotency-Key` обязателен. Повтор с тем же ключом и тем же телом возвращает уже созданный платёж. Другое тело с тем же ключом получает `409`.

```bash
curl -X POST http://localhost:8000/api/v1/payments \
  -H "X-API-Key: dev-api-key" \
  -H "Idempotency-Key: demo-1" \
  -H "content-type: application/json" \
  -d '{"amount":"100.50","currency":"RUB","description":"demo","metadata":{"order":1},"webhook_url":"https://example.com/hook"}'
```

В ответе `202` и `payment_id`. Через несколько секунд статус станет `succeeded` или `failed` (шлюз: около 90% успеха, обработка 2–5 с):

```bash
curl http://localhost:8000/api/v1/payments/PAYMENT_ID -H "X-API-Key: dev-api-key"
```

Результат уходит POST-ом на `webhook_url` один раз: доставка записывается в платёж. Если адрес не отвечает, консьюмер кладёт сообщение в TTL-очередь, и брокер возвращает его в `payments.new` через 1 с, затем через 2 с. После третьей неудачи сообщение оказывается в `payments.dlq`.
