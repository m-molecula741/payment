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

В базе есть `payments`, `outbox` и `alembic_version`. В RabbitMQ — очереди `payments.new` и `payments.dlq`.

## Почему не использован паттерн репозиторий

Запросов к базе четыре: создать платёж, прочитать его, обновить статус и забрать события outbox. Они стоят в сервисе, который и открывает транзакцию. Отдельный репозиторий повторил бы те же вызовы под другим именем.

Платёж и строка outbox сохраняются одним коммитом. Если спрятать базу в слой, который сам открывает сессию и пишет только платёж, событие может не попасть в ту же транзакцию. Тогда API уже ответил бы `202`, а в очередь ничего не ушло бы.

## Пример платежа

`Idempotency-Key` обязателен. Повтор с тем же ключом возвращает уже созданный платёж.

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

Результат уходит POST-ом на `webhook_url`. Если адрес не отвечает, отправка повторяется три раза с паузой 1 с, 2 с и 4 с. После этого сообщение оказывается в очереди `payments.dlq`.
