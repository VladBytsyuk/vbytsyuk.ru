# Владислав Быцюк — сайт-визитка

Статический сайт на HTML/CSS/JavaScript. Сборка, npm, база данных и сервер приложения не нужны. Фото, резюме и шрифт размещены локально; внешних запросов и аналитики нет.

## Структура

- `release/` — готовые файлы сайта, единственный источник для публикации. Редактируйте их напрямую: отдельного шага сборки нет.
- `deploy/deploy.sh` — деплой из публичного GitHub-репозитория и откат.
- `.github/workflows/deploy.yml` — проверки и автодеплой после push в `main`.
- `deploy/nginx.conf` — начальная HTTP-конфигурация Nginx.
- `tests/test_deploy.py` — проверка сценариев деплоя во временных каталогах.

Контент перенесён из предоставленного резюме. В PDF есть две версии: даты работы взяты из первой, подробности проектов — из второй. Статус работы в Magnit Tech указан по резюме. Иллюстрации проектов не являются скриншотами продуктов. Для скачивания доступен оригинальный PDF с обеими версиями.

## Локальный запуск

Из корня репозитория:

```sh
python3 -m http.server 4173 --directory release
```

Откройте http://localhost:4173. Остановить сервер: Ctrl+C. Можно также открыть `release/index.html` напрямую.

## Как устроен деплой

Все команды установки и обновления ниже выполняются **на VPS**. Скрипт скачивает архив публичного репозитория https://github.com/VladBytsyuk/vbytsyuk.ru, проверяет файлы в `release/`, создаёт новый каталог и атомарно переключает на него ссылку `current`. Git, rsync, GitHub-токены и SSH-ключи для GitHub на сервере не нужны.

```text
/var/www/vbytsyuk.ru/
├── current -> releases/20261120T160000Z-XXXXXX
├── previous -> releases/20261120T150000Z-XXXXXX
└── releases/
    ├── 20261120T150000Z-XXXXXX/
    └── 20261120T160000Z-XXXXXX/
```

Nginx отдаёт только содержимое `current`, без README и скриптов. Сбой скачивания или проверки архива не затронет текущий сайт. Одновременные деплои блокируются. Предыдущие релизы сохраняются для отката.

Локальные изменения не участвуют в деплое: сначала выполните commit и push в GitHub. После настройки SSH и GitHub Secrets push в `main` запускает проверки и автоматический деплой через GitHub Actions. Ручной запуск на VPS также доступен.

## Первая установка на VPS

Пример рассчитан на Ubuntu/Debian и пользователя с sudo. Под `root` уберите `sudo`. Скрипт использует права root для записи в `/var/www/vbytsyuk.ru`: скачивайте его из своего доверенного репозитория.

### 1. Установите пакеты

```sh
sudo apt update
sudo apt install nginx curl ca-certificates tar util-linux
```

### 2. Скачайте и запустите скрипт

```sh
curl -fL https://raw.githubusercontent.com/VladBytsyuk/vbytsyuk.ru/main/deploy/deploy.sh -o deploy-vbytsyuk.sh
less deploy-vbytsyuk.sh
sudo bash deploy-vbytsyuk.sh
```

`less` позволяет проверить скрипт перед запуском, выход — клавиша `q`.

Проверьте размещение файлов перед настройкой Nginx:

```sh
readlink /var/www/vbytsyuk.ru/current
test -s /var/www/vbytsyuk.ru/current/index.html && echo 'Файлы сайта готовы'
```

### 3. Подключите Nginx

**Если сайт уже настроен, особенно с HTTPS**, не заменяйте конфигурацию начальным HTTP-шаблоном. В действующем блоке домена замените только `root`:

```nginx
root /var/www/vbytsyuk.ru/current;
```

Затем проверьте конфигурацию и примените её только при успешной проверке:

```sh
sudo nginx -t && sudo systemctl reload nginx
```

Прежние файлы, загруженные прямо в `/var/www/vbytsyuk.ru/`, скрипт не удаляет. До изменения `root` старый сайт продолжает работать. После изменения эти файлы больше не используются; автоматический откат на старую ручную установку не предусмотрен. Для возврата к ней восстановите прежнюю строку `root` и проверьте/перезагрузите Nginx.

**Если домен ещё не настроен в Nginx**, используйте шаблон:

```sh
curl -fL https://raw.githubusercontent.com/VladBytsyuk/vbytsyuk.ru/main/deploy/nginx.conf -o vbytsyuk.ru.nginx.conf
sudo cp vbytsyuk.ru.nginx.conf /etc/nginx/sites-available/vbytsyuk.ru
sudo ln -s /etc/nginx/sites-available/vbytsyuk.ru /etc/nginx/sites-enabled/vbytsyuk.ru
sudo nginx -t && sudo systemctl reload nginx
```

Ссылку создайте только при первом подключении конфигурации. Не создавайте дублирующий блок домена и не отключайте другие сайты на VPS.

### 4. Настройте DNS и HTTPS, если это ещё не сделано

Направьте DNS A-записи `vbytsyuk.ru` и `www.vbytsyuk.ru` на IPv4 VPS. Добавляйте AAAA только при настроенном IPv6. В используемом firewall разрешите TCP 80 и 443, сохранив доступ по SSH.

После обновления DNS:

```sh
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d vbytsyuk.ru -d www.vbytsyuk.ru --redirect
sudo certbot renew --dry-run
```

Для другого домена замените его в конфигурации и командах. Если `www` не используется, удалите его из `server_name` и команды Certbot. Не перезаписывайте конфигурацию, дополненную Certbot, HTTP-шаблоном из репозитория.

## Автодеплой через GitHub Actions

Workflow `.github/workflows/deploy.yml` запускается после каждого push в `main`. Сначала он проверяет синтаксис Bash и тесты деплоя. Затем по SSH передаёт проверенный `deploy/deploy.sh` и SHA коммита на VPS. Сервер скачивает сайт именно из этого коммита, а не из изменившейся ветки.

Запуски выполняются последовательно, работающий деплой не прерывается новым push. Повторный запуск старого коммита пропускается, если `main` уже обновилась. После установки workflow загружает страницу по HTTPS и сравнивает её с HTML релиза. Ошибки видны во вкладке Actions; при сбое после переключения выполните ручной откат. При недоступности сайта автоматического отката нет: сетевой сбой не доказывает поломку релиза.

Перед включением автодеплоя настройте сайт и HTTPS по инструкции выше. SSH-порт VPS должен быть доступен GitHub-hosted runner. Nginx должен обслуживать `/var/www/vbytsyuk.ru/current`.

### 1. Создайте отдельный ключ на своём компьютере

Этот ключ предназначен только для Actions и отличается от вашего личного ключа VPS:

```sh
ssh-keygen -t ed25519 -a 100 -N '' -f ~/.ssh/vbytsyuk_actions_vps -C 'github-actions-vbytsyuk.ru'
cat ~/.ssh/vbytsyuk_actions_vps.pub
```

Для автоматического запуска используется ключ без passphrase. Закрытый ключ `~/.ssh/vbytsyuk_actions_vps` передайте только в GitHub Secret `VPS_SSH_KEY`, не в репозиторий и не в чат. Содержимое `.pub` установите на VPS.

### 2. Подготовьте пользователя на VPS

Рекомендуется отдельный пользователь `site-deploy` без sudo. Выполните команды из административной сессии (если пользователь уже существует, пропустите `adduser`):

```sh
sudo adduser --disabled-password --gecos '' site-deploy
sudo mkdir -p /var/www/vbytsyuk.ru
sudo chown -R site-deploy:site-deploy /var/www/vbytsyuk.ru
sudo chmod 755 /var/www/vbytsyuk.ru
sudo install -d -m 700 -o site-deploy -g site-deploy /home/site-deploy/.ssh
```

Замените `ПОЛНЫЙ_ПУБЛИЧНЫЙ_КЛЮЧ` всей строкой из `.pub`, начиная с `ssh-ed25519`:

```sh
printf '\n%s\n' 'restrict ПОЛНЫЙ_ПУБЛИЧНЫЙ_КЛЮЧ' | sudo tee -a /home/site-deploy/.ssh/authorized_keys > /dev/null
sudo chown site-deploy:site-deploy /home/site-deploy/.ssh/authorized_keys
sudo chmod 600 /home/site-deploy/.ssh/authorized_keys
```

`restrict` отключает проброс портов, агента, X11 и выделение терминала для этого ключа; запуск команды по SSH остаётся доступным. Пользователь получает права на каталог сайта, но не sudo. Существующий пользователь тоже подходит, если он владеет этим каталогом; укажите его имя в `VPS_USER` и установите ключ в его `authorized_keys`.

### 3. Получите ключ самого VPS для проверки подлинности

В доверенной сессии на VPS выполните, заменив `VPS_IP` тем же адресом или именем, которое укажете в `VPS_HOST`:

```sh
printf '%s ' 'VPS_IP'
cat /etc/ssh/ssh_host_ed25519_key.pub
```

Получится одна строка вида `VPS_IP ssh-ed25519 AAAA...`. Сохраните её в Secret `VPS_KNOWN_HOSTS`. При нестандартном SSH-порте, например 2222, используйте вместо `VPS_IP` строку `[VPS_IP]:2222`. Это публичный ключ **сервера**, он отличается от публичного ключа Actions. Проверка подлинности сервера в workflow обязательна; она не отключается.

### 4. Добавьте GitHub Secrets

Откройте [Settings → Secrets and variables → Actions](https://github.com/VladBytsyuk/vbytsyuk.ru/settings/secrets/actions) и добавьте Repository secrets:

| Имя | Значение |
| --- | --- |
| `VPS_HOST` | IP или имя VPS, без `https://` и без порта. |
| `VPS_USER` | `site-deploy` или подготовленный пользователь. |
| `VPS_SSH_KEY` | Полное содержимое закрытого ключа Actions, включая строки `BEGIN` и `END`. |
| `VPS_KNOWN_HOSTS` | Строка с публичным ключом сервера из предыдущего шага. |
| `VPS_PORT` | SSH-порт; необязателен, по умолчанию `22`. |

GitHub хранит Secrets отдельно от публичных файлов репозитория. В runner ключ создаётся во временном каталоге с закрытыми правами и удаляется при завершении шага. Workflow имеет только `contents: read` для GitHub и не использует сторонние SSH Actions. Подробнее о [GitHub Secrets](https://docs.github.com/en/actions/how-tos/write-workflows/choose-what-workflows-do/use-secrets).

### 5. Запустите и проверьте

В [Actions → Deploy website](https://github.com/VladBytsyuk/vbytsyuk.ru/actions/workflows/deploy.yml) нажмите **Run workflow**, выбрав ветку `main`, либо отправьте следующий commit в `main`.

Задания `Check deployment` и `Deploy to VPS` должны завершиться успешно. Если Secrets ещё не добавлены, деплой завершится ошибкой `Missing repository secret`; сервер при этом не затрагивается. Проверка HTTPS также требует работающих DNS, сертификата и корректного `root` Nginx.

Для отзыва доступа удалите строку ключа Actions из `authorized_keys` пользователя VPS и Secret `VPS_SSH_KEY`. При смене ключа сначала добавьте новый публичный ключ на сервер, обновите Secret и проверьте деплой, затем удалите старый ключ.

## Ручное обновление сайта

После push в `main` выполните на VPS из каталога, где сохранили скрипт:

```sh
sudo bash deploy-vbytsyuk.sh
```

Если менялся сам `deploy/deploy.sh`, предварительно скачайте его заново командой из первой установки и проверьте изменения. Перезапуск Nginx для обновления файлов не нужен.

Для воспроизводимого деплоя можно указать полный SHA коммита или существующий тег вместо ветки `main`:

```sh
sudo bash deploy-vbytsyuk.sh COMMIT_SHA_OR_TAG
```

Замените `COMMIT_SHA_OR_TAG` реальным значением. Этот коммит должен уже содержать каталог `release/`. Каждый запуск создаёт отдельный каталог. Старые версии не удаляются автоматически и занимают место на диске.

## Проверка после деплоя

```sh
curl -fI https://vbytsyuk.ru/
curl -fI https://vbytsyuk.ru/styles.css
curl -fI https://vbytsyuk.ru/assets/vladislav-bytsyuk-resume.pdf
sudo tail -n 30 /var/log/nginx/error.log
```

Ожидается HTTP 200. Если DNS/HTTPS ещё не настроены, проверьте HTTP локально на VPS:

```sh
curl -fI -H 'Host: vbytsyuk.ru' http://127.0.0.1/
```

Откройте сайт в браузере, проверьте оформление, переходы по разделам и скачивание PDF. Сделайте принудительное обновление страницы: CSS, JS и изображения используют прежние имена файлов и могут кэшироваться до семи дней.

Успех скрипта подтверждает размещение файлов; работоспособность DNS, HTTPS и Nginx проверяется отдельно этими командами и в браузере. При ошибках после переключения выполните откат. Секреты и серверная конфигурация в релиз не входят; скрипт не изменяет Nginx, firewall, сертификаты и другие сайты.

## Откат

После как минимум двух успешных деплоев:

```sh
sudo bash deploy-vbytsyuk.sh --rollback
```

Скрипт поменяет местами `current` и `previous`. Повторный откат вернёт более новую версию. Доступ к GitHub и перезапуск Nginx не нужны. После первого деплоя предыдущей версии ещё нет. Откат затрагивает только файлы сайта, не конфигурацию Nginx и сертификаты. Повторите HTTP-проверки и проверку в браузере.

Старые каталоги сохраняются до ручной очистки. Не удаляйте цели ссылок `current` и `previous`.

## Изменение контента и проверка разработки

Редактируйте `release/index.html` и `release/styles.css`. При замене PDF сохраните имя `assets/vladislav-bytsyuk-resume.pdf` либо обновите все три ссылки. Портрет — `release/assets/portrait.jpg`.

В браузере проверьте ширины 360, 390, 768 и 1440 px, отсутствие горизонтального скролла, переходы с клавиатуры и скачивание PDF.

```sh
bash -n deploy/deploy.sh
python3 -m unittest discover -s tests -v
```

Тесты используют временные каталоги и локальный архив вместо GitHub; `/var/www` и реальный VPS не затрагиваются. Настройку Nginx перед применением проверяйте командой `sudo nginx -t` на самом сервере.
