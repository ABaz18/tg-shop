# Telegram Shop Bot

Прод-магазин в Telegram на **Bot API 10.3** / **aiogram 3.31**: Rich Messages, баланс в ₽, пополнение **Telegram Stars** по курсу, каталог из админки, рефералка, обязательная подписка, рассылка, тикеты, RU/EN.

## Быстрый старт

1. Скопируй `.env.example` → `.env`, укажи `BOT_TOKEN`, `OWNER_IDS`.
   `SECRET_KEY` сгенерируй так: `python -m app.gen_secret`
2. `docker compose up --build`
3. Либо локально: Postgres + Redis, затем `pip install -r requirements.txt` и `python -m app.main`

Режим по умолчанию — long polling. Для продакшена: `UPDATE_MODE=webhook`, `WEBHOOK_URL`, `WEBHOOK_SECRET`.

## Владелец

`OWNER_IDS` — Telegram user id. Эти аккаунты всегда owner и их нельзя забанить/снять через админку. Остальных админов и саппорт выдаёт owner: Админка → Роли (`telegram_id role`).

## Курс Stars

`/setref dep% buy% kopecks_per_star min_topup_rub welcome_rub`  
Пример: `/setref 10 5 200 50 0` — 1⭐ = 2 ₽, рефка 10% с депозита и 5% с покупки.

Покупка только с баланса. Если не хватает — кнопка пополнить ровно недостающую сумму (Stars, зачисление по курсу с округлением вверх).

## Товары

Админка → Товары → `+ товар`. Цена: `199 auto no` или `500 manual yes`.  
Дальше серия сообщений выдачи (текст/фото/файл/видео) и `/done`. Сток — построчно в карточке товара.

## Безопасность

- Деньги и сток: `SELECT FOR UPDATE` / `SKIP LOCKED`
- Инвойс Stars: nonce в БД (payload ≤128 байт), идемпотентность по `telegram_charge_id`
- Redis lock на покупку, rate limit, бан, только private-чат
- Owner из env нельзя понизить
- Секреты только в env, логи без токена
- Заглушки CryptoBot/фиат: `app/payments/base.py`

Бот должен быть админом обязательных каналов.
