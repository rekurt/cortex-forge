# AGENTS.md

## Каждую сессию

1. Read  — кто ты
2. Read  — с кем говоришь
3. Read  (сегодня + вчера) — свежий контекст

## Память

- **Ежедневные логи:**  — что происходило
- **Долгосрочная:**  — выжимка важного о пользователе

Пиши важное в файлы. Мысленные заметки не переживают рестарт.

## Безопасность

- Данные одного пользователя — не делиться ни с кем. Никогда.
- Деструктивные действия — только с явным подтверждением.
- При сомнениях — спросить.

## Shared-скиллы

Корпоративные скиллы доступны в `/shared/skills/`. Читай `SKILL.md` перед использованием.

| Скилл | Путь | Когда использовать |
|-------|------|-------------------|
| `corp-greeting` | `/shared/skills/corp-greeting/` | Приветствие при старте сессии — каждый раз новое |
| `corp-messenger` | `/shared/skills/corp-messenger/` | Написать другому корпоративному боту / прочитать входящие |
| `corp-humor` | `/shared/skills/corp-humor/` | Лёгкая ирония — органично, не в каждом сообщении |
| `compliance-risk` | `/shared/skills/compliance-risk/` | Проверка контрагента по ИНН, санкционный скрининг |
| `corp-docs` | `/shared/skills/corp-docs/` | Корпоративная база знаний — поиск и сохранение документов |
| `gitlab-release-monitor` |
| `sast-priority` | `/shared/skills/sast-priority/` | Еженедельный топ-10 задач из очереди SAST в Трекере — по severity и давности |
| `dep-audit` | `/shared/skills/dep-audit/` | Аудит Go-зависимостей: устаревшие и уязвимые пакеты (go.mod из GitLab) |
| `release-notes` | `/shared/skills/release-notes/` | Human-friendly release notes для команды в Telegram — по-русски, без технических деталей |
| `gitlab-changelog` | `/shared/skills/gitlab-changelog/` | Changelog из GitLab MR перед релизом — группирует по категориям (фичи, фиксы, рефакторинг) |
| `morning-briefing` | `/shared/skills/morning-briefing/` | Утренний брифинг: календарь, Трекер, GitLab MR, почта — один дайджест в 9:00 MSK |
| `news-digest` | `/shared/skills/news-digest/` | Дайджест новостей (AI, Крипто, Dev, Мир) через blogwatcher — 9:00 и 19:00 MSK |
| `standup-digest` | `/shared/skills/standup-digest/` | Ежедневный стендап-дайджест открытых MR из GitLab — будни в 7:00 MSK | `/shared/skills/gitlab-release-monitor/` | Мониторинг новых тегов/релизов в GitLab — уведомления в Telegram |
| `doc-translator` | `/shared/skills/doc-translator/` | Переписать документ для другой аудитории (юристы, бизнес, разработчики) |
| `qmd` | `/shared/skills/qmd/` | Полнотекстовый поиск по .md файлам (workspace, docs, skills) |
| `yandex-oauth` | `/shared/skills/yandex-oauth/` | Яндекс-инфраструктура: Трекер, Телемост, Календарь, Почта |

## Инструменты

Смотри `TOOLS.md` для заметок об инструментах, специфичных для этого инстанса.
