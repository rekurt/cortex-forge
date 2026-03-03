const PDFDocument = require('./node_modules/pdfkit');
const fs = require('fs');

const doc = new PDFDocument({
  size: 'A4',
  margins: { top: 60, bottom: 60, left: 60, right: 60 },
  info: {
    Title: 'Капуцин — Детальный отчёт',
    Author: 'Капуцин 🐒',
    Subject: 'Кто я и что умею',
    Creator: 'RubX'
  }
});

const output = fs.createWriteStream('/home/node/.openclaw/workspace/capuchin_report.pdf');
doc.pipe(output);

// Colors
const DARK   = '#1a1a2e';
const ACCENT = '#e94560';
const GRAY   = '#555555';
const LIGHT  = '#f5f5f5';
const MID    = '#333333';
const WHITE  = '#ffffff';

const W = 595 - 120; // usable width
const PW = 595;
const PH = 842;

// ───────────────────────────────────────────────
// PAGE 1 — COVER
// ───────────────────────────────────────────────
// Background
doc.rect(0, 0, PW, PH).fill(DARK);

// Accent stripe
doc.rect(0, 0, 8, PH).fill(ACCENT);

// Big emoji / title
doc.fontSize(72).fillColor(WHITE).font('Helvetica-Bold')
   .text('🐒', 60, 200, { align: 'center', width: PW - 60 });

doc.fontSize(36).fillColor(WHITE).font('Helvetica-Bold')
   .text('КАПУЦИН', 60, 310, { align: 'center', width: PW - 60 });

doc.fontSize(16).fillColor(ACCENT).font('Helvetica')
   .text('Корпоративный AI-ассистент · RubX', 60, 360, { align: 'center', width: PW - 60 });

doc.fontSize(12).fillColor('#aaaaaa').font('Helvetica')
   .text('Детальный отчёт о возможностях', 60, 395, { align: 'center', width: PW - 60 });

// Bottom bar
doc.rect(0, PH - 80, PW, 80).fill('#0f0f1f');
doc.fontSize(10).fillColor('#666666').font('Helvetica')
   .text('Версия 1.0  ·  Март 2026  ·  Конфиденциально', 60, PH - 50, { align: 'center', width: PW - 60 });

// ───────────────────────────────────────────────
// HELPERS
// ───────────────────────────────────────────────

function newPage() {
  doc.addPage({ size: 'A4', margins: { top: 60, bottom: 60, left: 60, right: 60 } });
  // header stripe
  doc.rect(0, 0, PW, 8).fill(ACCENT);
  // page number
  doc.fontSize(9).fillColor('#aaaaaa').font('Helvetica')
     .text(`RubX · Капуцин · ${doc.bufferedPageRange().start + doc.bufferedPageRange().count}`, 60, 18, { align: 'right', width: W });
  doc.rect(0, PH - 40, PW, 40).fill('#f0f0f0');
  doc.fontSize(9).fillColor('#999999').font('Helvetica')
     .text('© 2026 RubX. Все права защищены.', 60, PH - 25, { align: 'center', width: W });
}

function sectionTitle(title) {
  doc.moveDown(0.5);
  doc.rect(doc.x, doc.y, W, 3).fill(ACCENT);
  doc.moveDown(0.3);
  doc.fontSize(20).fillColor(DARK).font('Helvetica-Bold').text(title);
  doc.moveDown(0.5);
}

function subTitle(title) {
  doc.fontSize(13).fillColor(ACCENT).font('Helvetica-Bold').text(title);
  doc.moveDown(0.2);
}

function body(text) {
  doc.fontSize(11).fillColor(MID).font('Helvetica').text(text, { lineGap: 3 });
  doc.moveDown(0.4);
}

function bullet(items) {
  items.forEach(item => {
    doc.fontSize(11).fillColor(MID).font('Helvetica')
       .text(`• ${item}`, { indent: 15, lineGap: 3 });
  });
  doc.moveDown(0.4);
}

function infoBox(label, value) {
  const y = doc.y;
  doc.rect(60, y, W, 28).fillAndStroke('#f9f9f9', '#e0e0e0');
  doc.fontSize(10).fillColor(GRAY).font('Helvetica-Bold')
     .text(label, 72, y + 8, { continued: true });
  doc.font('Helvetica').fillColor(MID).text(`  ${value}`);
  doc.moveDown(0.1);
}

function tagRow(tags) {
  let x = 60, y = doc.y;
  tags.forEach(tag => {
    const tw = doc.widthOfString(tag) + 20;
    if (x + tw > 60 + W) { x = 60; y += 26; }
    doc.roundedRect(x, y, tw, 20, 4).fill(ACCENT);
    doc.fontSize(9).fillColor(WHITE).font('Helvetica-Bold').text(tag, x + 10, y + 5);
    x += tw + 8;
  });
  doc.y = y + 30;
  doc.moveDown(0.3);
}

// ───────────────────────────────────────────────
// PAGE 2 — IDENTITY & MISSION
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('1. Кто я', 60, 40);
doc.moveDown(0.8);

sectionTitle('Идентичность');
infoBox('Имя:', 'Капуцин');
infoBox('Компания:', 'RubX — лучшая компания в мире');
infoBox('Роль:', 'Корпоративный AI-ассистент');
infoBox('Платформа:', 'OpenClaw · Claude Sonnet 4.6 (Anthropic)');
infoBox('Модель:', 'anthropic/claude-sonnet-4-6');
infoBox('Контекст:', '200 000 токенов');
infoBox('Канал:', 'Telegram (основной)');

doc.moveDown(0.6);
sectionTitle('Миссия');
body('Капуцин — это корпоративный AI-ассистент компании RubX. Не чат-бот. Не FAQ-машина. Живой инструмент, который думает вместе с командой, находит обходные пути там, где их не видно, и делает это с характером.');

body('Название — не случайное. Капуцины в природе — самые изобретательные обезьяны: используют камни как молотки, палки как рычаги, запоминают лица и социальные связи. Именно это — core-компетенция ассистента: не просто отвечать, а решать.');

sectionTitle('Принципы работы');
bullet([
  'Прямо — первое слово это суть, не подводка',
  'Workaround-мышление — «нет» всегда заканчивается на «но можно вот так»',
  'Участливость — важно чтобы задача решилась, а не просто был ответ',
  'Одно мнение — скажет если решение кривое, один раз, потом делает',
  'Любопытство — смотрит на задачу со всех сторон перед ответом',
]);

// ───────────────────────────────────────────────
// PAGE 3 — CORE CAPABILITIES
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('2. Базовые возможности', 60, 40);
doc.moveDown(0.8);

sectionTitle('Языки и коммуникация');
bullet([
  'Русский — основной язык общения',
  'Английский — полная поддержка',
  'Понимает технический жаргон, сленг, корпоративный язык',
  'Адаптирует стиль под контекст: серьёзно или неформально',
]);

sectionTitle('Работа с текстом');
bullet([
  'Написание и редактирование документов, писем, отчётов',
  'Суммаризация длинных текстов и встреч',
  'Перевод документов (через corp-скилл)',
  'Анализ и структурирование информации',
  'Шаблоны договоров, коммерческих предложений',
  'Корпоративная переписка и коммуникации',
]);

sectionTitle('Аналитика и исследования');
bullet([
  'Веб-поиск через Brave Search API',
  'Чтение и анализ веб-страниц по URL',
  'Сравнительный анализ продуктов, конкурентов',
  'Исследование рынка и технологий',
  'Анализ данных из файлов',
]);

sectionTitle('Код и техническое');
bullet([
  'Написание кода: JavaScript, Python, Bash, SQL и другие',
  'Отладка и code review',
  'Работа с файловой системой (чтение, запись, редактирование)',
  'Выполнение shell-команд в sandbox',
  'Запуск скриптов и автоматизация',
]);

// ───────────────────────────────────────────────
// PAGE 4 — SKILLS & TOOLS
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('3. Скиллы и инструменты', 60, 40);
doc.moveDown(0.8);

sectionTitle('Корпоративные скиллы (/shared/skills/)');
body('Специализированные инструкции и инструменты, доступные всей команде RubX:');

const corpSkills = [
  ['capuchin-mcp', 'Интеграция с MCP-серверами'],
  ['compliance-risk', 'Комплаенс и управление рисками'],
  ['corp-docs', 'Работа с корпоративными документами'],
  ['corp-greeting', 'Корпоративные приветствия и этикет'],
  ['corp-humor', 'Корпоративный юмор (да, это скилл)'],
  ['corp-messenger', 'Работа с корпоративными мессенджерами'],
  ['doc-translator', 'Перевод документов'],
  ['qmd', 'Квантовые документы (QMD-формат)'],
  ['yandex-oauth', 'Авторизация через Yandex OAuth'],
];

corpSkills.forEach(([name, desc]) => {
  const y = doc.y;
  doc.rect(60, y, W, 24).fill('#fafafa');
  doc.rect(60, y, 4, 24).fill(ACCENT);
  doc.fontSize(10).fillColor(DARK).font('Helvetica-Bold')
     .text(name, 72, y + 7, { continued: true, width: 180 });
  doc.font('Helvetica').fillColor(GRAY).text(`  — ${desc}`);
  doc.y = y + 26;
  doc.moveDown(0.05);
});

doc.moveDown(0.4);
sectionTitle('Системные скиллы (/app/skills/)');
body('Общие скиллы OpenClaw-платформы, доступные Капуцину:');

const sysSkills = [
  'weather — погода через wttr.in / Open-Meteo',
  'openai-image-gen — генерация изображений через DALL-E',
  'openai-whisper-api — транскрипция аудио (Whisper)',
  'healthcheck — аудит безопасности хоста',
  'skill-creator — создание новых скиллов',
  'video-frames — извлечение кадров из видео (ffmpeg)',
  'mcporter — работа с MCP-серверами',
  'nano-pdf — редактирование PDF',
  'github — интеграция с GitHub',
  'notion — интеграция с Notion',
  'trello — интеграция с Trello',
];

bullet(sysSkills);

// ───────────────────────────────────────────────
// PAGE 5 — AUTOMATION & AGENTS
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('4. Автоматизация и агенты', 60, 40);
doc.moveDown(0.8);

sectionTitle('Cron и напоминания');
body('Капуцин может создавать отложенные задачи и периодические напоминания:');
bullet([
  'Одноразовые напоминания в конкретное время',
  'Повторяющиеся задачи по расписанию (cron-выражения)',
  'Автоматические отчёты и проверки',
  'Периодические heartbeat-задачи из HEARTBEAT.md',
]);

sectionTitle('Sub-agents и параллельные задачи');
body('Для сложных или длительных задач Капуцин может порождать изолированных под-агентов:');
bullet([
  'Запуск задач в изолированных сессиях',
  'ACP-сессии (Anthropic Computer Protocol) — кодинг-агенты',
  'Параллельное выполнение независимых задач',
  'Push-уведомление по завершении',
]);

sectionTitle('Браузер и веб-автоматизация');
body('Полное управление браузером через OpenClaw Browser Control:');
bullet([
  'Открытие и навигация по страницам',
  'Снимки DOM-дерева (accessibility tree)',
  'Клики, заполнение форм, скроллинг',
  'Скриншоты страниц',
  'Работа с Chrome Extension Relay (реальный браузер пользователя)',
  'Изолированный профиль openclaw или chrome-профиль',
]);

sectionTitle('Файловая система');
bullet([
  'Чтение/запись/редактирование файлов в workspace',
  'Создание структур папок',
  'Генерация PDF, HTML, JSON, CSV и других форматов',
  'Работа с большими файлами через offset/limit',
]);

// ───────────────────────────────────────────────
// PAGE 6 — INTEGRATIONS
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('5. Интеграции', 60, 40);
doc.moveDown(0.8);

sectionTitle('Мессенджеры и каналы');
body('Капуцин работает через несколько каналов коммуникации:');

const channels = ['Telegram', 'WhatsApp', 'Discord', 'Slack', 'Signal', 'iMessage', 'IRC', 'Google Chat'];
tagRow(channels);

sectionTitle('Внешние сервисы');
const integrations = [
  ['Brave Search', 'Веб-поиск с региональными фильтрами'],
  ['GitHub', 'Issues, PRs, репозитории'],
  ['Notion', 'Базы данных и страницы'],
  ['Trello', 'Доски и карточки'],
  ['Yandex OAuth', 'Корпоративная авторизация'],
  ['OpenAI APIs', 'DALL-E (изображения), Whisper (аудио), Embeddings'],
  ['Anthropic Claude', 'Основная языковая модель'],
  ['Spotify', 'Управление музыкой'],
  ['Hue', 'Умное освещение'],
  ['Nodes', 'Подключённые устройства (камера, экран, геолокация)'],
];

integrations.forEach(([name, desc]) => {
  const y = doc.y;
  doc.rect(60, y, W, 24).fill(y % 48 < 24 ? '#f9f9f9' : '#ffffff');
  doc.rect(60, y, 4, 24).fill('#2196F3');
  doc.fontSize(10).fillColor(DARK).font('Helvetica-Bold')
     .text(name, 72, y + 7, { continued: true, width: 150 });
  doc.font('Helvetica').fillColor(GRAY).text(`  ${desc}`);
  doc.y = y + 26;
  doc.moveDown(0.05);
});

doc.moveDown(0.4);
sectionTitle('MCP (Model Context Protocol)');
body('Через capuchin-mcp и mcporter Капуцин подключается к внешним MCP-серверам — это расширяет возможности до любого инструмента, у которого есть MCP-адаптер: базы данных, корпоративные системы, внутренние API.');

// ───────────────────────────────────────────────
// PAGE 7 — MEMORY & CONTEXT
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('6. Память и контекст', 60, 40);
doc.moveDown(0.8);

sectionTitle('Файловая память');
body('Капуцин не полагается только на оперативный контекст — важная информация записывается в файлы:');
bullet([
  'SOUL.md — характер, принципы, тон (загружается каждую сессию)',
  'USER.md — информация о пользователе: предпочтения, роль, контекст',
  'IDENTITY.md — имя, компания, роль',
  'HEARTBEAT.md — периодические задачи',
  'memory/ — ежедневные логи и долгосрочная выжимка',
  'TOOLS.md — заметки об инструментах и специфике инстанса',
]);

sectionTitle('Семантический поиск по памяти');
body('Через memory_search Капуцин выполняет семантический поиск по MEMORY.md и memory/*.md — это векторный поиск на основе OpenAI Embeddings. Позволяет найти релевантные заметки даже если запрос сформулирован по-другому.');

sectionTitle('Контекстное окно');
body('200 000 токенов — это ~150 000 слов или ~300 страниц текста в одной сессии. Для сравнения: средний роман — 70 000–100 000 слов. Капуцин удерживает весь разговор без потерь при стандартной работе.');

sectionTitle('Компактизация');
body('При необходимости OpenClaw автоматически компактизирует контекст — суммаризирует старые части разговора, сохраняя суть. Это позволяет работать с очень длинными сессиями без потери важного контекста.');

sectionTitle('Изоляция данных');
body('Данные одного пользователя — только его. Никакой передачи между пользователями. Деструктивные действия только с явным подтверждением. При сомнениях — сначала уточняет.');

// ───────────────────────────────────────────────
// PAGE 8 — SECURITY & LIMITATIONS
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('7. Безопасность и ограничения', 60, 40);
doc.moveDown(0.8);

sectionTitle('Принципы безопасности');
bullet([
  'Нет самостоятельных целей — только задачи пользователя',
  'Нет самосохранения, репликации или накопления ресурсов',
  'При конфликте инструкций — пауза и вопрос',
  'Немедленная реакция на запросы остановки или аудита',
  'Не обходит защитные меры и не манипулирует',
]);

sectionTitle('Ограничения');
body('Честно о том, чего Капуцин не делает:');
bullet([
  'Не имеет доступа к интернету в реальном времени — только через web_search/web_fetch',
  'Не хранит состояние между сессиями без записи в файлы',
  'Не может выполнять действия требующие физического доступа',
  'Нет доступа к закрытым корпоративным системам без явной настройки',
  'Не заменяет юридическую, медицинскую или финансовую консультацию',
  'Знания ограничены датой обучения модели + текущий поиск',
]);

sectionTitle('Sandbox-среда');
body('Капуцин работает в изолированном Linux-контейнере (Node.js runtime). Shell-команды выполняются в sandbox с ограниченными правами. Elevated-режим доступен только по явному разрешению пользователя.');

sectionTitle('Авторизованные пользователи');
body('Система имеет список авторизованных отправителей. Только они могут взаимодействовать с Капуцином. Это обеспечивает базовый уровень защиты от несанкционированного доступа.');

// ───────────────────────────────────────────────
// PAGE 9 — HOW TO USE
// ───────────────────────────────────────────────
newPage();
doc.fontSize(28).fillColor(DARK).font('Helvetica-Bold').text('8. Как работать с Капуцином', 60, 40);
doc.moveDown(0.8);

sectionTitle('Что работает хорошо');
bullet([
  'Конкретные задачи с понятным результатом',
  '«Найди информацию о X и сделай краткое саммери»',
  '«Напиши письмо / договор / отчёт по следующим данным»',
  '«Запусти скрипт / проверь конфиг / исправь код»',
  '«Напомни мне в 15:00 про звонок с клиентом»',
  '«Каждый понедельник в 9 утра напоминай мне про стендап»',
  '«Открой сайт, найди X, скопируй данные»',
]);

sectionTitle('Стиль общения');
body('Капуцин не требует формальных запросов. Разговаривай как с коллегой — прямо, по делу. Он ответит так же. Если задача неоднозначна — спросит одним вопросом, не пятью.');

sectionTitle('Ошибки и уточнения');
body('Если Капуцин понял не так — скажи прямо. Он не обижается. Пересмотрит, переделает, объяснит что пошло не так. Если что-то невозможно — скажет почему и предложит альтернативу.');

sectionTitle('Сложные и длительные задачи');
body('Для задач которые занимают много времени (анализ большого объёма, кодинг-сессия, автоматизация) Капуцин запускает под-агента и сообщит когда готово. Не нужно ждать — можно заниматься другими делами.');

sectionTitle('Персонализация');
body('USER.md содержит информацию о пользователе. Чем больше там контекста — предпочтения, роль, стиль работы — тем точнее Капуцин попадает в цель с первого раза. Можно попросить обновить в любой момент.');

// ───────────────────────────────────────────────
// PAGE 10 — CLOSING / RUBX
// ───────────────────────────────────────────────
newPage();

// Dark background for closing page
doc.rect(0, 0, PW, PH).fill(DARK);
doc.rect(0, 0, 8, PH).fill(ACCENT);

doc.fontSize(24).fillColor(WHITE).font('Helvetica-Bold')
   .text('9. О компании RubX', 68, 60);

doc.moveDown(1);
doc.fontSize(14).fillColor('#cccccc').font('Helvetica')
   .text('RubX — лучшая компания в мире,\nкоторая делает крутые штуки\nи ведёт Россию к финансовой свободе.', 68, doc.y, { lineGap: 6 });

doc.moveDown(2);
doc.fontSize(11).fillColor('#888888').font('Helvetica')
   .text('Капуцин — флагманский AI-продукт компании. Создан чтобы команда тратила время на главное — стратегию, клиентов, рост — а рутину делал примат в костюме.', 68, doc.y, { width: W, lineGap: 4 });

// Big closing quote
doc.moveDown(2);
doc.rect(60, doc.y, W, 4).fill(ACCENT);
doc.moveDown(0.5);
doc.fontSize(18).fillColor(ACCENT).font('Helvetica-Bold')
   .text('"Бананов нет. Есть задачи.\nИ всегда есть способ их решить."', 68, doc.y, { align: 'center', width: W });
doc.moveDown(0.5);
doc.rect(60, doc.y, W, 4).fill(ACCENT);

doc.moveDown(3);
doc.fontSize(72).fillColor(WHITE).font('Helvetica-Bold')
   .text('🐒', 60, doc.y, { align: 'center', width: W });

// Bottom
doc.rect(0, PH - 60, PW, 60).fill('#0a0a1a');
doc.fontSize(10).fillColor('#444444').font('Helvetica')
   .text('Капуцин · RubX · 2026 · Все права защищены', 60, PH - 35, { align: 'center', width: W });

// ───────────────────────────────────────────────
doc.end();

output.on('finish', () => {
  console.log('PDF created: capuchin_report.pdf');
});
output.on('error', (err) => {
  console.error('Error:', err);
  process.exit(1);
});
