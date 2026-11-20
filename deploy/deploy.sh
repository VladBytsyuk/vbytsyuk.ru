#!/usr/bin/env bash
set -Eeuo pipefail

site_root="/var/www/vbytsyuk.ru"
repository="VladBytsyuk/vbytsyuk.ru"
ref="${1:-main}"
workspace=""

fail() {
    printf 'Ошибка: %s\n' "$*" >&2
    exit 1
}

[[ $# -le 1 ]] || fail "Использование: bash deploy.sh [ветка|тег|SHA|--rollback]"
command -v flock >/dev/null || fail "Установите util-linux (команда flock)."
mkdir -p "$site_root/releases"
chmod 755 "$site_root" "$site_root/releases"
exec 9>"$site_root/.deploy.lock"
flock -n 9 || fail "Другой деплой уже выполняется."

cleanup() {
    if [[ -n "$workspace" ]]; then
        rm -rf -- "$workspace"
    fi
    rm -f -- "$site_root/.current-$$" "$site_root/.previous-$$"
}
trap cleanup EXIT

valid_release() {
    [[ "$1" == releases/* && "$1" != *..* && -s "$site_root/$1/index.html" ]]
}

switch_link() {
    local name="$1" target="$2"
    ln -s -- "$target" "$site_root/.$name-$$"
    mv -Tf -- "$site_root/.$name-$$" "$site_root/$name"
}

current=""
if [[ -e "$site_root/current" || -L "$site_root/current" ]]; then
    [[ -L "$site_root/current" ]] || fail "Каталог current уже существует и не является ссылкой."
    current="$(readlink "$site_root/current")"
    valid_release "$current" || fail "Ссылка current не указывает на корректный релиз."
fi
if [[ -e "$site_root/previous" && ! -L "$site_root/previous" ]]; then
    fail "Путь previous уже существует и не является ссылкой."
fi

if [[ "$ref" == --rollback ]]; then
    [[ -n "$current" && -L "$site_root/previous" ]] || fail "Предыдущего релиза для отката нет."
    previous="$(readlink "$site_root/previous")"
    valid_release "$previous" || fail "Предыдущий релиз отсутствует или повреждён."
    switch_link current "$previous"
    switch_link previous "$current"
    printf 'Откат выполнен: %s\n' "$previous"
    exit 0
fi

[[ "$ref" =~ ^[a-zA-Z0-9][a-zA-Z0-9._/-]*$ ]] || fail "Некорректная ветка, тег или SHA."
command -v curl >/dev/null || fail "Установите curl."
command -v tar >/dev/null || fail "Установите tar."
workspace="$(mktemp -d)"
mkdir "$workspace/source"

printf 'Загрузка %s (%s)…\n' "$repository" "$ref"
curl --fail --location --retry 2 --connect-timeout 15 --max-time 180 \
    "https://codeload.github.com/$repository/tar.gz/$ref" \
    --output "$workspace/source.tar.gz"
tar -xzf "$workspace/source.tar.gz" --strip-components=1 -C "$workspace/source"

for file in index.html styles.css script.js assets/favicon.svg assets/portrait.jpg \
    assets/onest.ttf assets/OFL-Onest.txt assets/vladislav-bytsyuk-resume.pdf; do
    [[ -s "$workspace/source/release/$file" ]] || fail "В архиве нет release/$file. Текущий сайт сохранён."
done

release_path="$(mktemp -d "$site_root/releases/$(date -u +%Y%m%dT%H%M%SZ)-XXXXXX")"
cp -R "$workspace/source/release/." "$release_path/"
find "$release_path" -type d -exec chmod 755 {} +
find "$release_path" -type f -exec chmod 644 {} +
target="releases/${release_path##*/}"

if [[ -n "$current" ]]; then
    switch_link previous "$current"
fi
switch_link current "$target"
printf 'Деплой завершён: %s (%s)\n' "$target" "$ref"
printf 'Проверьте https://vbytsyuk.ru и логи Nginx.\n'
