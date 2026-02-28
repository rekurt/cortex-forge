---
name: corp-docs
description: Корпоративная база знаний. Поиск по внутренним документам, сохранение заметок и документов в общую базу.
---

# corp-docs

Общая база знаний CortexForge. Все документы хранятся в `/shared/docs/`.

## Структура папок

```
/shared/docs/
  common/     ← общие документы (для всех)
  user-1/     ← личные доки Никиты
  user-3/     ← личные доки Дмитрия
  user-4/     ← личные доки Василия
```

## Поиск по документам

```bash
bash /shared/skills/corp-docs/search.sh "запрос"
```

Или с указанием коллекции:
```bash
bash /shared/skills/corp-docs/search.sh "запрос" common
bash /shared/skills/corp-docs/search.sh "запрос" user-1
```

## Сохранить документ

Просто создай `.md` файл в нужной папке:
```bash
cat > /shared/docs/common/название.md << 'EOF'
# Заголовок
Содержимое документа...
EOF
```

## Правила

- Формат документов: Markdown (`.md`)
- Личные доки → `/shared/docs/<имя>/`
- Общие доки → `/shared/docs/common/`
- Поиск индексируется автоматически при первом обращении
- Индекс хранится в `/shared/docs/.qmd-index/` (общий для всех)
