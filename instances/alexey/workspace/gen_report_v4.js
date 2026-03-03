'use strict';
/**
 * Capuchin Report v4
 * - Строго 10 страниц (контент явно размещается, без авто-overflow)
 * - Дизайн в стиле rubx.ru: строгий корпоративный, синий акцент, таблицы
 * - Только кириллица + Latin, нет emoji
 * - Встроенный Roboto TTF
 */

const PDFDocument = require('./node_modules/pdfkit');
const fs   = require('fs');
const path = require('path');

const FONTS = path.join(__dirname, 'fonts');
const OUT   = path.join(__dirname, 'capuchin_report_v4.pdf');

// ── RubX Color Palette (финансовый/корпоративный стиль) ──────────────────────
const C = {
  // Основные
  black:    '#0A0E1A',   // почти чёрный фон обложки
  navy:     '#0D1B3E',   // тёмно-синий
  blue:     '#1A56DB',   // акцентный синий
  blueD:    '#1240A8',   // тёмный синий
  blueL:    '#EBF2FF',   // светло-синий фон
  // Текст
  heading:  '#0A0E1A',
  body:     '#1F2937',
  muted:    '#6B7280',
  // Нейтральные
  white:    '#FFFFFF',
  bg:       '#FFFFFF',
  light:    '#F9FAFB',
  border:   '#E5E7EB',
  // Акценты
  green:    '#059669',
  red:      '#DC2626',
  amber:    '#D97706',
};

// ── Размеры A4 ────────────────────────────────────────────────────────────────
const PW  = 595.28;
const PH  = 841.89;
const ML  = 52;   // margin left
const MR  = 52;   // margin right
const MT  = 52;   // margin top content (после хедера)
const MB  = 48;   // margin bottom (до футера)
const CW  = PW - ML - MR;   // 491.28

// ── Документ ─────────────────────────────────────────────────────────────────
const doc = new PDFDocument({
  size: 'A4',
  autoFirstPage: false,
  bufferPages: true,
  info: {
    Title:    'Капуцин — Детальный отчёт',
    Author:   'RubX',
    Subject:  'Корпоративный AI-ассистент',
    Creator:  'OpenClaw',
  },
});

const output = fs.createWriteStream(OUT);
doc.pipe(output);

doc.registerFont('R',  path.join(FONTS, 'Roboto-Regular.ttf'));
doc.registerFont('RB', path.join(FONTS, 'Roboto-Bold.ttf'));
doc.registerFont('RI', path.join(FONTS, 'Roboto-Italic.ttf'));

let pageNum = 0;

// ── Утилиты ───────────────────────────────────────────────────────────────────

/** Создать новую страницу с хедером и футером */
function newPage() {
  pageNum++;
  doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

  // Header: синяя полоса сверху
  doc.save()
     .rect(0, 0, PW, 6).fill(C.blue)
     .restore();

  // Header: название компании + номер страницы
  const hY = 14;
  doc.save()
     .rect(0, 6, PW, 26).fill(C.light)
     .moveTo(0, 32).lineTo(PW, 32).strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();
  doc.font('RB').fontSize(8).fillColor(C.blue)
     .text('RubX · Капуцин', ML, hY, { width: CW / 2, align: 'left' });
  doc.font('R').fontSize(8).fillColor(C.muted)
     .text(`Страница ${pageNum} из 10`, ML, hY, { width: CW, align: 'right' });

  // Footer
  const fY = PH - 32;
  doc.save()
     .rect(0, fY, PW, 32).fill(C.light)
     .moveTo(0, fY).lineTo(PW, fY).strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();
  doc.font('R').fontSize(7.5).fillColor(C.muted)
     .text('Корпоративный AI-ассистент', ML, fY + 11, { width: CW / 2, align: 'left' });
  doc.font('R').fontSize(7.5).fillColor(C.muted)
     .text('Март 2026 · Конфиденциально', ML, fY + 11, { width: CW, align: 'right' });

  // Сбросить курсор
  doc.x = ML;
  doc.y = MT;
}

/** Горизонтальный разделитель */
function rule(color = C.border, h = 0.5, my = 8) {
  doc.y += my;
  doc.save().moveTo(ML, doc.y).lineTo(ML + CW, doc.y)
     .strokeColor(color).lineWidth(h).stroke().restore();
  doc.y += my;
}

/** Заголовок страницы H1 */
function pageTitle(num, text) {
  // Синяя полоска + номер
  doc.save().rect(ML, doc.y, CW, 32).fill(C.blueL).restore();
  doc.save().rect(ML, doc.y, 4, 32).fill(C.blue).restore();
  doc.font('RB').fontSize(9).fillColor(C.blue)
     .text(num, ML + 12, doc.y + 6, { width: 30 });
  doc.font('RB').fontSize(14).fillColor(C.heading)
     .text(text, ML + 46, doc.y + 7, { width: CW - 50 });
  doc.y += 40;
}

/** H2 */
function h2(text) {
  doc.y += 10;
  doc.font('RB').fontSize(11).fillColor(C.blue)
     .text(text, ML, doc.y, { width: CW });
  doc.y += 4;
  doc.save().moveTo(ML, doc.y).lineTo(ML + CW * 0.35, doc.y)
     .strokeColor(C.blue).lineWidth(1.5).stroke().restore();
  doc.y += 8;
}

/** Параграф */
function para(text) {
  doc.font('R').fontSize(9.5).fillColor(C.body)
     .text(text, ML, doc.y, { width: CW, lineGap: 3, align: 'justify' });
  doc.y += 8;
}

/** Маркированный список */
function list(items) {
  items.forEach(item => {
    const y = doc.y;
    doc.save().rect(ML + 4, y + 4.5, 5, 5).fill(C.blue).restore();
    doc.font('R').fontSize(9.5).fillColor(C.body)
       .text(item, ML + 16, y, { width: CW - 16, lineGap: 2.5 });
    doc.y += 5;
  });
  doc.y += 4;
}

/** Строка таблицы (ключ–значение) */
function kvRow(key, val, shade) {
  const H = 22;
  const y = doc.y;
  if (shade) doc.save().rect(ML, y, CW, H).fill(C.light).restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();
  doc.font('RB').fontSize(8.5).fillColor(C.muted)
     .text(key, ML + 8, y + 6, { width: 145, lineBreak: false });
  doc.font('R').fontSize(9).fillColor(C.body)
     .text(val, ML + 160, y + 6, { width: CW - 165, lineBreak: false });
  doc.y = y + H;
}

/** Строка таблицы (название–описание) с синей линией слева */
function tRow(name, desc, shade) {
  const H = 22;
  const y = doc.y;
  if (shade) doc.save().rect(ML, y, CW, H).fill(C.light).restore();
  doc.save().rect(ML, y + 3, 3, H - 6).fill(C.blue).restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();
  doc.font('RB').fontSize(9).fillColor(C.heading)
     .text(name, ML + 10, y + 6, { width: 148, lineBreak: false });
  doc.font('R').fontSize(9).fillColor(C.muted)
     .text(desc, ML + 165, y + 6, { width: CW - 170, lineBreak: false });
  doc.y = y + H;
}

/** Чип-тег */
function chips(items) {
  let x = ML, y = doc.y;
  const H = 18, PAD = 9, GAP = 5;
  items.forEach(item => {
    const w = doc.font('RB').fontSize(8).widthOfString(item) + PAD * 2;
    if (x + w > ML + CW) { x = ML; y += H + GAP; }
    doc.save().roundedRect(x, y, w, H, 3).fill(C.navy).restore();
    doc.font('RB').fontSize(8).fillColor(C.white)
       .text(item, x + PAD, y + 4.5, { width: w - PAD * 2, lineBreak: false });
    x += w + GAP;
  });
  doc.y = y + H + 10;
}

/** Информационный блок */
function infoBox(text, color = C.blue) {
  const y = doc.y + 4;
  const tw = CW - 14;
  const h = doc.font('RI').fontSize(9.5).heightOfString(text, { width: tw - 8 }) + 16;
  doc.save().rect(ML, y, CW, h).fill(C.blueL).restore();
  doc.save().rect(ML, y, 3, h).fill(color).restore();
  doc.font('RI').fontSize(9.5).fillColor(C.body)
     .text(text, ML + 14, y + 8, { width: tw, lineGap: 3 });
  doc.y = y + h + 8;
}

/** Карточка возможности */
function capCard(x, y, w, title, items) {
  const itemH = 15;
  const H = 10 + 16 + items.length * itemH + 8;
  doc.save().rect(x, y, w, H).fill(C.light).restore();
  doc.save().rect(x, y, w, 3).fill(C.blue).restore();
  doc.save().rect(x, y, w, H).undash()
     .moveTo(x, y).lineTo(x + w, y).lineTo(x + w, y + H).lineTo(x, y + H).lineTo(x, y)
     .strokeColor(C.border).lineWidth(0.5).stroke().restore();
  doc.font('RB').fontSize(9.5).fillColor(C.heading)
     .text(title, x + 10, y + 9, { width: w - 20 });
  let iy = y + 25;
  items.forEach(item => {
    doc.save().rect(x + 10, iy + 4, 4, 4).fill(C.blue).restore();
    doc.font('R').fontSize(8.5).fillColor(C.body)
       .text(item, x + 20, iy, { width: w - 28, lineGap: 2 });
    iy += itemH;
  });
  return H;
}

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 1 — ОБЛОЖКА
// ══════════════════════════════════════════════════════════════════════════════
pageNum++;
doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

// Тёмный фон
doc.rect(0, 0, PW, PH).fill(C.black);

// Синяя полоса слева
doc.rect(0, 0, 5, PH).fill(C.blue);

// Тонкая сетка
doc.save().opacity(0.04);
for (let gx = 0; gx < PW; gx += 32)
  doc.moveTo(gx, 0).lineTo(gx, PH).strokeColor('#FFFFFF').lineWidth(0.5).stroke();
for (let gy = 0; gy < PH; gy += 32)
  doc.moveTo(0, gy).lineTo(PW, gy).strokeColor('#FFFFFF').lineWidth(0.5).stroke();
doc.restore().opacity(1);

// Декоративный прямоугольник
doc.save().opacity(0.08)
   .rect(PW - 200, 0, 200, PH).fill(C.blue)
   .restore().opacity(1);

// Верхняя строка
doc.save().rect(0, 0, PW, 42).fill('#060A14').restore();
doc.save().moveTo(0, 42).lineTo(PW, 42).strokeColor(C.blue).lineWidth(1).stroke().restore();
doc.font('RB').fontSize(9).fillColor(C.blue)
   .text('RubX', 20, 15, { width: PW - 40, align: 'right' });
doc.font('R').fontSize(9).fillColor('#4B5563')
   .text('Корпоративный AI-ассистент', 20, 15, { width: PW - 100 });

// Основной заголовок
doc.font('RB').fontSize(60).fillColor(C.white)
   .text('КАПУЦИН', 20, 180, { width: PW - 40, align: 'center', characterSpacing: 4 });

// Синяя черта под заголовком
doc.save()
   .moveTo(ML * 3, 268).lineTo(PW - ML * 3, 268)
   .strokeColor(C.blue).lineWidth(2).stroke()
   .restore();

// Подзаголовок
doc.font('R').fontSize(13).fillColor('#9CA3AF')
   .text('Детальный отчёт о возможностях', 0, 280, { width: PW, align: 'center' });

// Карточки-метаданные
const metaCards = [
  ['Платформа',   'OpenClaw'],
  ['Модель',      'Claude Sonnet 4.6'],
  ['Версия',      '2.0'],
  ['Дата',        'Март 2026'],
];
let mcX = (PW - (metaCards.length * 118 + (metaCards.length - 1) * 8)) / 2;
const mcY = 340;
metaCards.forEach(([label, val]) => {
  doc.save().rect(mcX, mcY, 118, 52).fill('#0D1B3E').restore();
  doc.save().rect(mcX, mcY, 118, 2).fill(C.blue).restore();
  doc.font('R').fontSize(7.5).fillColor('#6B7280')
     .text(label.toUpperCase(), mcX + 8, mcY + 10, { width: 102, align: 'center' });
  doc.font('RB').fontSize(10).fillColor(C.white)
     .text(val, mcX + 8, mcY + 26, { width: 102, align: 'center' });
  mcX += 126;
});

// Нижняя полоса
doc.save().rect(0, PH - 60, PW, 60).fill('#060A14').restore();
doc.save().moveTo(0, PH - 60).lineTo(PW, PH - 60)
   .strokeColor(C.blue).lineWidth(0.5).stroke().restore();
doc.font('R').fontSize(8).fillColor('#374151')
   .text('КОНФИДЕНЦИАЛЬНО · АО РУБX · 2026', 0, PH - 36, { width: PW, align: 'center' });

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 2 — СОДЕРЖАНИЕ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('', 'Содержание');

const toc = [
  ['01', 'Идентичность и миссия',         '3'],
  ['02', 'Базовые возможности',            '4'],
  ['03', 'Скиллы и инструменты',           '5'],
  ['04', 'Автоматизация и агенты',         '6'],
  ['05', 'Интеграции',                     '7'],
  ['06', 'Память и контекст',              '8'],
  ['07', 'Безопасность и ограничения',     '9'],
  ['08', 'Как работать с Капуцином',      '10'],
  ['09', 'О компании RubX',              '10'],
];

doc.y += 4;
toc.forEach(([num, title, pg], i) => {
  const y = doc.y;
  const H = 30;
  if (i % 2 === 0) doc.save().rect(ML, y, CW, H).fill(C.light).restore();
  doc.save().rect(ML, y, 3, H).fill(i % 2 === 0 ? C.blue : '#CBD5E0').restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();

  doc.font('RB').fontSize(8.5).fillColor(C.blue)
     .text(num, ML + 10, y + 10, { width: 25, lineBreak: false });
  doc.font('R').fontSize(10).fillColor(C.body)
     .text(title, ML + 38, y + 9, { width: CW - 85, lineBreak: false });
  doc.font('RB').fontSize(10).fillColor(C.blue)
     .text(pg, ML, y + 9, { width: CW - 8, align: 'right' });
  doc.y = y + H;
});

doc.y += 20;
infoBox(
  'Этот документ описывает возможности корпоративного AI-ассистента Капуцин, ' +
  'разработанного компанией RubX. Актуально на март 2026 года.'
);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 3 — ИДЕНТИЧНОСТЬ И МИССИЯ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('01', 'Идентичность и миссия');

h2('Паспорт системы');
[
  ['Наименование',       'Капуцин'],
  ['Компания',           'RubX (АО «Руб Икс»)'],
  ['Назначение',         'Корпоративный AI-ассистент'],
  ['Платформа',          'OpenClaw'],
  ['Языковая модель',    'Anthropic Claude Sonnet 4.6'],
  ['Контекстное окно',   '200 000 токенов (около 150 000 слов)'],
  ['Основной канал',     'Telegram'],
  ['Язык по умолчанию',  'Русский (+ English)'],
  ['Версия',             '2.0 · Март 2026'],
].forEach(([k, v], i) => kvRow(k, v, i % 2 === 0));

doc.y += 8;
h2('Миссия');
para(
  'Капуцин — инструмент повышения эффективности команды RubX. ' +
  'Ассистент обрабатывает рутинные задачи, находит обходные решения в нестандартных ' +
  'ситуациях и обеспечивает информационную поддержку в режиме реального времени. ' +
  'Принцип работы: не просто отвечать, а решать задачи.'
);

h2('Операционные принципы');
list([
  'Прямота — ответ начинается с сути без вводных конструкций',
  'Альтернативное мышление — при невозможности прямого решения предлагается обходной путь',
  'Ориентированность на результат — задача считается выполненной только при достижении цели',
  'Честность — если решение неоптимально, сообщает об этом один раз, затем выполняет',
]);

infoBox('"Банана нет. Есть задачи. И всегда есть способ их решить." — Капуцин');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 4 — БАЗОВЫЕ ВОЗМОЖНОСТИ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('02', 'Базовые возможности');

const capGroups = [
  {
    title: 'Поиск и анализ',
    items: ['Веб-поиск (Brave Search API)', 'Чтение страниц по URL', 'Анализ документов и данных', 'Выжимки и сравнения'],
  },
  {
    title: 'Документы и тексты',
    items: ['Письма, отчёты, договоры, КП', 'Редактирование и корректура', 'Переводы документов', 'Суммаризация встреч'],
  },
  {
    title: 'Разработка',
    items: ['JS, Python, Bash, SQL', 'Отладка и code review', 'Shell в sandbox-среде', 'Автоматизация задач'],
  },
  {
    title: 'Файлы и данные',
    items: ['Чтение / запись / редактирование', 'PDF, HTML, JSON, CSV', 'Работа с большими файлами', 'Форматирование данных'],
  },
  {
    title: 'Браузер',
    items: ['Навигация и клики', 'Заполнение форм', 'Скриншоты и сбор данных', 'Chrome Extension Relay'],
  },
  {
    title: 'Расписание',
    items: ['Разовые напоминания', 'Повторяющиеся cron-задачи', 'Периодические отчёты', 'Heartbeat-мониторинг'],
  },
];

const CW2 = (CW - 12) / 2;
for (let i = 0; i < capGroups.length; i += 2) {
  const rowY = doc.y;
  const lH = capCard(ML,          rowY, CW2, capGroups[i].title,   capGroups[i].items);
  const rH = capGroups[i + 1]
    ? capCard(ML + CW2 + 12, rowY, CW2, capGroups[i+1].title, capGroups[i+1].items)
    : 0;
  doc.y = rowY + Math.max(lH, rH) + 8;
}

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 5 — СКИЛЛЫ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('03', 'Скиллы и инструменты');

h2('Корпоративные скиллы RubX  (/shared/skills/)');
para('Специализированные инструменты для всей команды RubX:');
[
  ['capuchin-mcp',    'Подключение к внешним MCP-серверам'],
  ['compliance-risk', 'Комплаенс и управление рисками'],
  ['corp-docs',       'Работа с корпоративными документами'],
  ['corp-greeting',   'Корпоративные приветствия и этикет'],
  ['corp-humor',      'Корпоративный юмор'],
  ['corp-messenger',  'Корпоративные мессенджеры'],
  ['doc-translator',  'Перевод документов'],
  ['qmd',             'QMD-формат документов'],
  ['yandex-oauth',    'Авторизация через Yandex OAuth'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

doc.y += 12;
h2('Системные скиллы платформы  (/app/skills/)');
para('Общие инструменты OpenClaw-платформы:');
[
  ['weather',            'Погода (wttr.in / Open-Meteo)'],
  ['openai-image-gen',   'Генерация изображений (DALL-E)'],
  ['openai-whisper-api', 'Транскрипция аудио (Whisper)'],
  ['healthcheck',        'Аудит безопасности хоста'],
  ['skill-creator',      'Создание новых скиллов'],
  ['video-frames',       'Извлечение кадров из видео (ffmpeg)'],
  ['mcporter',           'Работа с MCP-серверами'],
  ['nano-pdf',           'Редактирование PDF'],
  ['github',             'GitHub: issues, PRs, репозитории'],
  ['notion',             'Notion: базы данных и страницы'],
  ['trello',             'Trello: доски и карточки'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 6 — АВТОМАТИЗАЦИЯ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('04', 'Автоматизация и агенты');

h2('Планировщик задач (Cron)');
para(
  'Капуцин поддерживает полноценное планирование задач: ' +
  'разовые напоминания, повторяющиеся по расписанию и сложные cron-выражения.'
);
list([
  'Разовые: «напомни в 15:00 про звонок» — срабатывает ровно один раз',
  'Регулярные: «каждый понедельник в 9:00 — командный стендап»',
  'Сложные: «первый рабочий день каждого месяца» — полный синтаксис cron',
  'Автономные: задачи выполняются без участия человека',
]);

h2('Sub-agents — изолированные задачи');
para(
  'Для длительных операций Капуцин порождает под-агентов, ' +
  'не блокируя основной диалог. По завершении приходит уведомление.'
);
list([
  'Изолированные сессии для длительных операций',
  'ACP-сессии (кодинг-агенты) для технических задач',
  'Параллельное выполнение независимых задач',
  'Push-уведомление по завершении',
]);

h2('Управление браузером');
list([
  'Навигация, клики, скроллинг, заполнение форм',
  'Снимки DOM-дерева (accessibility tree)',
  'Скриншоты и сбор данных со страниц',
  'Chrome Extension Relay — реальный браузер пользователя',
  'Изолированный openclaw-профиль для автономной работы',
]);

h2('Heartbeat-мониторинг');
para(
  'HEARTBEAT.md содержит список периодических проверок. ' +
  'При каждом опросе Капуцин выполняет их автоматически: ' +
  'мониторинг, уведомления, регулярные действия без участия человека.'
);

infoBox(
  'Пример: «Каждую пятницу в 18:00 — проверить задачи в Trello ' +
  'и отправить сводку в Telegram»',
  C.blue
);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 7 — ИНТЕГРАЦИИ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('05', 'Интеграции');

h2('Каналы коммуникации');
para('Капуцин работает через несколько платформ одновременно:');
chips(['Telegram', 'WhatsApp', 'Discord', 'Slack', 'Signal', 'iMessage', 'IRC', 'Google Chat']);

h2('Внешние сервисы');
[
  ['Brave Search',    'Веб-поиск с фильтрами по региону и языку'],
  ['GitHub',          'Issues, PRs, репозитории, code review'],
  ['Notion',          'Базы данных, страницы, блоки'],
  ['Trello',          'Доски, списки, карточки задач'],
  ['Yandex OAuth',    'Корпоративная авторизация (сервисы Яндекса)'],
  ['OpenAI APIs',     'DALL-E (изображения), Whisper (аудио), Embeddings'],
  ['Anthropic',       'Claude Sonnet 4.6 — языковая модель'],
  ['Spotify',         'Управление воспроизведением музыки'],
  ['Philips Hue',     'Управление умным освещением'],
  ['Nodes',           'Устройства: камера, экран, геолокация'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

doc.y += 10;
h2('MCP — Model Context Protocol');
para(
  'Открытый протокол для подключения внешних систем. ' +
  'Через capuchin-mcp и mcporter Капуцин подключается к любым MCP-серверам: ' +
  'CRM, ERP, внутренние API, базы данных корпоративной системы.'
);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 8 — ПАМЯТЬ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('06', 'Память и контекст');

h2('Файловая память');
para(
  'Языковые модели не сохраняют состояние между сессиями. ' +
  'Капуцин решает это через файловую систему: ' +
  'важная информация записывается в файлы и читается при каждом старте.'
);
[
  ['SOUL.md',      'Характер, принципы, тон — определяет поведение'],
  ['USER.md',      'Данные о пользователе: роль, предпочтения, контекст'],
  ['IDENTITY.md',  'Имя, компания, роль ассистента'],
  ['HEARTBEAT.md', 'Периодические задачи для автономной работы'],
  ['TOOLS.md',     'Заметки об инструментах и специфике инстанса'],
  ['memory/',      'Ежедневные логи и долгосрочные выжимки'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

doc.y += 10;
h2('Семантический поиск');
para(
  'memory_search выполняет векторный поиск по файлам памяти ' +
  'на основе OpenAI Embeddings. Релевантные записи находятся ' +
  'даже при несовпадении формулировки запроса и содержимого заметки.'
);

h2('Контекстное окно');
// Визуальная шкала
const barY = doc.y + 4;
const barH = 26;
doc.save().rect(ML, barY, CW, barH).fill(C.light).restore();
doc.save().rect(ML, barY, CW * 0.08, barH).fill(C.blue).restore();
doc.save().rect(ML, barY, CW, barH).undash()
   .moveTo(ML, barY).lineTo(ML + CW, barY).lineTo(ML + CW, barY + barH)
   .lineTo(ML, barY + barH).lineTo(ML, barY)
   .strokeColor(C.border).lineWidth(0.5).stroke().restore();
doc.font('R').fontSize(8).fillColor(C.white)
   .text('8%', ML + 4, barY + 8, { lineBreak: false });
doc.font('R').fontSize(8).fillColor(C.muted)
   .text('Использовано в данной сессии', ML + CW * 0.08 + 8, barY + 8, { lineBreak: false });
doc.y = barY + barH + 10;

list([
  '200 000 токенов = около 150 000 слов = около 300 страниц A4',
  'Средний роман (70–100 тыс. слов) полностью помещается в контекст',
  'При исчерпании — автоматическая компактизация с сохранением сути',
]);

infoBox(
  'Изоляция данных: данные одного пользователя никогда не передаются другим. ' +
  'Деструктивные действия — только с явным подтверждением.',
  C.blue
);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 9 — БЕЗОПАСНОСТЬ
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('07', 'Безопасность и ограничения');

h2('Принципы безопасности');
list([
  'Нет самостоятельных целей вне задач пользователя',
  'Нет самосохранения, репликации или накопления ресурсов',
  'При конфликте инструкций — пауза и уточняющий вопрос',
  'Немедленная реакция на запросы остановки или аудита',
  'Не обходит защитные меры и не манипулирует системой',
  'Повышенные права (elevated) — только по явному разрешению',
]);

h2('Изолированная среда исполнения');
para(
  'Капуцин работает в изолированном Linux-контейнере (Node.js runtime). ' +
  'Shell-команды выполняются с ограниченными правами. ' +
  'Нет доступа к хост-системе без явного разрешения администратора. ' +
  'Рабочая директория по умолчанию — только workspace.'
);

h2('Авторизованный доступ');
para(
  'Система работает со списком авторизованных отправителей. ' +
  'Только они могут взаимодействовать с ассистентом. ' +
  'Несанкционированные запросы игнорируются.'
);

h2('Известные ограничения');
list([
  'Нет прямого интернета — только через web_search и web_fetch',
  'Нет памяти между сессиями без явной записи в файлы',
  'Нет доступа к закрытым корпоративным системам без настройки MCP',
  'База знаний ограничена датой обучения модели (+ актуальный поиск)',
  'Не заменяет юридическую, медицинскую или финансовую консультацию',
  'Не выполняет действия, требующие физического доступа',
]);

infoBox(
  'При обнаружении потенциально ошибочного решения Капуцин ' +
  'предупреждает один раз и кратко, затем действует согласно инструкции пользователя.',
  C.amber
);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 10 — КАК РАБОТАТЬ + RUBX
// ══════════════════════════════════════════════════════════════════════════════
newPage();
pageTitle('08–09', 'Практика и RubX');

h2('Примеры эффективных запросов');
[
  'Найди последние новости о конкурентах X и сделай краткое саммери',
  'Напиши коммерческое предложение по следующим параметрам: ...',
  'Напомни в 15:00 про звонок с клиентом Ивановым',
  'Каждый понедельник в 9:00 напоминай про командный стендап',
  'Открой сайт rubx.ru, найди актуальные тарифы и сохрани в таблицу',
  'Проверь этот Python-скрипт на ошибки и предложи оптимизацию',
  'Переведи договор на английский и сохрани как PDF',
  'Каждую пятницу в 17:30 напоминай написать недельный отчёт',
].forEach((ex, i) => {
  const y = doc.y;
  const H = 21;
  if (i % 2 === 0) doc.save().rect(ML, y, CW, H).fill(C.light).restore();
  doc.save().rect(ML, y, 3, H).fill(C.blue).restore();
  doc.font('RI').fontSize(9).fillColor(C.body)
     .text(ex, ML + 12, y + 6, { width: CW - 18, lineBreak: false });
  doc.y = y + H;
});

doc.y += 12;
h2('О компании RubX');
para(
  'RubX (АО «Руб Икс») — компания в области финансовых технологий. ' +
  'Разрабатывает инструменты для обеспечения финансовой независимости ' +
  'российского бизнеса: от цифровых активов до AI-ассистентов. ' +
  'Капуцин — флагманский AI-продукт компании для внутренней автоматизации.'
);

// Итоговый блок-цитата
const qY = doc.y + 8;
const qH = 66;
doc.save().rect(ML, qY, CW, qH).fill(C.navy).restore();
doc.save().rect(ML, qY, 4, qH).fill(C.blue).restore();
doc.font('RB').fontSize(13).fillColor(C.white)
   .text('"Банана нет. Есть задачи.', ML + 16, qY + 12, { width: CW - 24 });
doc.font('RB').fontSize(13).fillColor(C.white)
   .text('И всегда есть способ их решить."', ML + 16, qY + 30, { width: CW - 24 });
doc.font('R').fontSize(8.5).fillColor('#6B7280')
   .text('— Капуцин · RubX · 2026', ML + 16, qY + 50, { width: CW - 24 });

doc.y = qY + qH + 14;

// Нижняя строка
const metaY = PH - MB - 16;
doc.save()
   .moveTo(ML, metaY).lineTo(ML + CW, metaY)
   .strokeColor(C.border).lineWidth(0.5).stroke()
   .restore();
doc.font('R').fontSize(7.5).fillColor(C.muted)
   .text('Капуцин v2.0  |  RubX  |  Март 2026  |  Все права защищены',
         ML, metaY + 5, { width: CW, align: 'center' });

// ── Финализация ───────────────────────────────────────────────────────────────
doc.end();

output.on('finish', () => {
  const sz = fs.statSync(OUT).size;
  console.log(`PDF готов: capuchin_report_v4.pdf  ${(sz / 1024).toFixed(1)} KB  Страниц: ${pageNum}`);
});
output.on('error', err => {
  console.error('Ошибка:', err.message);
  process.exit(1);
});
