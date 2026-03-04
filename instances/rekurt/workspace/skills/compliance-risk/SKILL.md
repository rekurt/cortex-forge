---
name: compliance-risk
description: Расширение shared/compliance-risk. Проверка контрагента по ИНН, ОГРН или названию компании/ИП — с автоматическим поиском. Используй check.py вместо enrich.py когда у пользователя нет ИНН.
---

# Личное расширение compliance-risk

Расширяет `/shared/skills/compliance-risk` — добавляет умный поиск по названию.

## Когда использовать

- Пользователь называет компанию/ИП по имени (без ИНН)
- Нужно проверить контрагента "найди и проверь"

## Скрипт: check.py

```bash
# По названию — найдёт и сразу проверит:
python3 ~/workspace/skills/compliance-risk/scripts/check.py "АО Рубикс"
python3 ~/workspace/skills/compliance-risk/scripts/check.py "ИП Алдаев Никита"

# Показать список совпадений:
python3 ~/workspace/skills/compliance-risk/scripts/check.py "Сбер" --list

# Выбрать конкретный из топ-5:
python3 ~/workspace/skills/compliance-risk/scripts/check.py "Рубикс" --pick 2

# По ИНН — то же самое что enrich.py:
python3 ~/workspace/skills/compliance-risk/scripts/check.py 9703208834

# С форматом для Telegram:
python3 ~/workspace/skills/compliance-risk/scripts/check.py "Рубикс" --format telegram
```

## Логика

1. Если аргумент — 10/12/13/15 цифр → сразу `enrich.py <ИНН>`
2. Иначе → поиск через DaData → показать список → выбрать → `enrich.py <ИНН>`
3. Если один результат — проверяет без вопросов
4. Если несколько — спрашивает (или берёт первый при `--pick 1`)

## Примечание

Базовый скилл: `/shared/skills/compliance-risk/scripts/enrich.py`
Личный скрипт: `~/workspace/skills/compliance-risk/scripts/check.py`
