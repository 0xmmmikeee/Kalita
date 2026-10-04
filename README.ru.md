# Wallet Lab — отбор кошельков для копитрейдинга (Robinhood Chain · Pons v2)

Отдельный продукт рядом со `scout-bot`. Считает «паспорта» сигналов (первая покупка кошелька на
кривой Pons), оценивает кошельки с усадкой к рыночной базе и проверкой вне выборки, ведёт активный
список, лог изменений и базу брака, экспортирует список в формат движка (`wallets.txt`).

## Структура
```
src/build_passports.py   паспорта сигналов из launchpad-cache.json (или полного потока)
src/score_wallets.py     скоринг: 2 профиля (fast / picker), усадка, кластеры, отбор/проверка
src/server.js            веб-интерфейс + API (Node 18+, без зависимостей), порт 8830
src/ui.html              страница
deploy/                  установка на VPS (Caddy + systemd)
data/                    signals.csv, scores/            (не в git)
state/                   active.json, rejected.json, log.jsonl, rules.json   (не в git)
```

## Запуск локально
```bash
python3 src/build_passports.py ../scout-bot/data/launchpad-cache.json data/signals.csv
python3 src/score_wallets.py data/signals.csv data/scores
node src/server.js          # http://localhost:8830
```
Нужны python3 + pandas + numpy, node ≥ 18.

## Методология (коротко)
- Сигнал — первая покупка кошелька на кривой; вход симулируется через 2 с (измеренная медиана
  живых сделок), также считается для 0/5/10 с.
- Паспорт сигнала: ATH и время до него на горизонтах 1м…30д (горизонт считается только если
  полностью наблюдён), минимум за 10 мин, откат до первого +50%/x2/x5, графуация, первая продажа.
- Профиль **fast**: hit = x2 за 1 ч. Профиль **picker**: hit = дошёл до пула или x5 за 24 ч.
- База рынка считается по корзинам «сколько ETH уже собрала кривая» — кошелёк сравнивается с
  равными по позиции, а не с рынком в целом.
- Оценка: нижняя граница Уилсона (80%) минус ожидаемая база = «превышение»; ранг = превышение·√n.
- Кластеры: кошельки с ≥50% общих токенов и совпадением блоков покупки считаются одним хозяином.
- Отбор на одном периоде, проверка на другом; плацебо — случайный список того же размера.
- Правила добавления/удаления с гистерезисом — вкладка «Правила».

## Правила списка (вкладка «Правила»)
Пороги: мин. сигналов, мин. превышение над рынком, мин. нижняя граница, макс. руги, размер списка.
Гистерезис: добавление после `enter_days` подряд дней прохождения порогов, удаление после `exit_days`
подряд дней ниже `exit_excess`; удалённый попадает в брак на `recheck_days`. Серии — `state/streak.json`.

## Внешние списки (вкладка «Списки»)
`lists/*.txt` — любые списки адресов (исходные 1132 из Telegram-бота, Wallets-B). Панель показывает их
хит против ожидаемого рынка на тех же позициях кривой, долю с положительным превышением и место в рейтинге.

## Ограничения данных
`launchpad-cache.json` (стартовые данные) содержит только токены, где сработал сигнал от исходных 1132
кошельков, и перекошен к мигрировавшим (63% против 1,1% по рынку) — профиль picker на нём не
интерпретируется. Полный поток снимает это ограничение.

## Полный поток Pons v2 (`src/fetch_stream.py`)
Читает четыре события по topic0 (TokenLaunched, CurveBuy, CurveSell, PoolGraduated) без привязки к адресам
кривых. Покупки, где получатель — универсальный роутер (45% всех покупок), разрешаются точечным запросом
Transfer(router → user) по адресам токенов в той же транзакции (проверено: 100% найдено).
Хранение — **каталог** `data/stream/`: `tokens.json` (метаданные), `series.csv` (сделки построчно),
`state.json` (последний блок). Инкрементально и с чекпоинтами: перезапуск продолжает с места обрыва.
```bash
HYPERSYNC_TOKEN=... python3 src/fetch_stream.py --out data/stream --days 30 [--max-blocks N]
python3 src/build_passports.py data/stream data/signals.csv     # внешняя сортировка, по одному токену в памяти
python3 src/score_wallets.py data/signals.csv data/scores        # проверка = последние 7 дней (--val-days)
python3 src/check_contracts.py data/scores state/contracts.json  # eth_getCode пачками → flag=contract
python3 src/compare_lists.py data/signals.csv data/scores lists data/scores/lists.json
```
Позиция на кривой — в долях порога графуации (`curve_frac_before`, нетто: покупки − продажи).
Скорость с VPS ≈ 100 тыс. блоков за 3–4 мин (gzip); 30 дней ≈ 16 ч. С платным HyperSync быстрее в разы.

## Автопилот (сервер ↔ GitHub)
`deploy/agent-setup.sh` ставит на VPS таймер (раз в минуту, `deploy/agent-tick.sh`): подтянуть `main`,
обновить приложение, запустить новые задания `jobs/*.sh` (каждое — один раз, отдельным transient-юнитом
systemd), опубликовать логи в ветку `agent-logs` (`logs/_status.txt`, `logs/<job>.log`).
Так изменения и задания доходят до сервера без ручного rsync/ssh.

## Деплой на VPS (Caddy уже стоит)
```bash
# с Mac
rsync -a --exclude data --exclude state --exclude .git ~/Desktop/"SIGNAL ANALYSYS"/wallet-lab/ root@SERVER:/opt/wallet-lab-src/
rsync -a ~/Desktop/"SIGNAL ANALYSYS"/scout-bot/data/launchpad-cache.json root@SERVER:/opt/wallet-lab/data/   # стартовые данные до первой выгрузки
# на сервере
bash /opt/wallet-lab-src/deploy/setup.sh wallets.SERVER-IP-DASHED.sslip.io   # спросит логин/пароль панели
cp /opt/wallet-lab/.env.example /opt/wallet-lab/.env && nano /opt/wallet-lab/.env   # вписать HYPERSYNC_TOKEN
bash /opt/wallet-lab/deploy/daily.sh     # первая выгрузка + пересчёт (несколько часов на 30 дней)
```
Дальше `wallet-lab-daily.timer` запускает `deploy/daily.sh` каждую ночь: дозагрузка потока →
паспорта → скоринг → применение правил → экспорт `data/export_fast.txt` / `data/export_picker.txt`.
