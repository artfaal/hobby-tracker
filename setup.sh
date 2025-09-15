#!/usr/bin/env bash
set -e

if [ ! -f ".env" ]; then
  echo "Создаю .env…"
  cp .env.example .env
fi

read -rp "Вставьте TELEGRAM_BOT_TOKEN: " BOT
read -rp "Вставьте SPREADSHEET_ID: " SID
read -rp "Имя листа (по умолчанию 'Данные'): " SNAME

SNAME=${SNAME:-Данные}

# Экранируем слэши для sed
BOT_ESCAPED=$(printf '%s\n' "$BOT" | sed -e 's/[\/&]/\\&/g')
SID_ESCAPED=$(printf '%s\n' "$SID" | sed -e 's/[\/&]/\\&/g')
SNAME_ESCAPED=$(printf '%s\n' "$SNAME" | sed -e 's/[\/&]/\\&/g')

sed -i.bak "s/^TELEGRAM_BOT_TOKEN=.*/TELEGRAM_BOT_TOKEN=$BOT_ESCAPED/" .env
sed -i.bak "s/^SPREADSHEET_ID=.*/SPREADSHEET_ID=$SID_ESCAPED/" .env
sed -i.bak "s/^SHEET_NAME=.*/SHEET_NAME=$SNAME_ESCAPED/" .env

echo "Готово. Проверьте .env"

