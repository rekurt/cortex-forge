'use strict';
/**
 * Capuchin Report v2
 * Full Cyrillic support via embedded Roboto TTF
 * Professional layout: proper margins, baseline grid, color system
 */

const PDFDocument = require('./node_modules/pdfkit');
const fs = require('fs');
const path = require('path');

const FONTS_DIR = path.join(__dirname, 'fonts');
const OUT_PATH  = path.join(__dirname, 'capuchin_report_v2.pdf');

// ─── Color Palette ──────────────────────────────────────────────────────────
const C = {
  bg:        '#FFFFFF',
  coverBg:   '#0D1117',
  accent:    '#FF4757',
  accentDim: '#FF6B7A',
  dark:      '#0D1117',
  heading:   '#1A1F2E',
  body:      '#2D3748',
  muted:     '#718096',
  light:     '#F7F8FA',
  border:    '#E2E8F0',
  white:     '#FFFFFF',
  tag:       '#EBF4FF',
  tagText:   '#2B6CB0',
  chipBg:    '#FF4757',
  chipText:  '#FFFFFF',
  tableAlt:  '#F8F9FA',
  success:   '#38A169',
  warn:      '#D69E2E',
};

// ─── Page metrics ────────────────────────────────────────────────────────────
const PAGE_W = 595.28;  // A4 pt
const PAGE_H = 841.89;
const ML = 56;   // margin left
const MR = 56;   // margin right
const MT = 56;   // margin top
const MB = 56;   // margin bottom
const CONTENT_W = PAGE_W - ML - MR;

// ─── Document setup ──────────────────────────────────────────────────────────
const doc = new PDFDocument({
  size: 'A4',
  autoFirstPage: false,
  info: {
    Title:    'Капуцин — Детальный отчёт',
    Author:   'Капуцин 🐒 · RubX',
    Subject:  'Возможности корпоративного AI-ассистента',
    Keywords: 'RubX, Капуцин, AI, ассистент',
    Creator:  'OpenClaw · pdfkit',
  },
});

const output = fs.createWriteStream(OUT_PATH);
doc.pipe(output);

// ─── Register fonts ──────────────────────────────────────────────────────────
doc.registerFont('R',  path.join(FONTS_DIR, 'Roboto-Regular.ttf'));
doc.registerFont('RB', path.join(FONTS_DIR, 'Roboto-Bold.ttf'));
doc.registerFont('RI', path.join(FONTS_DIR, 'Roboto-Italic.ttf'));

// ─── Page counter state ───────────────────────────────────────────────────────
let pageNum = 0;
const PAGE_LABELS = []; // filled on each addPage

// ─── Helpers ─────────────────────────────────────────────────────────────────

function hex(color) { return color; }

/** Add a new content page with header/footer */
function newPage(skipHeaderFooter = false) {
  pageNum++;
  doc.addPage({ size: 'A4', margins: { top: MT, bottom: MB, left: ML, right: MR } });

  if (!skipHeaderFooter) {
    // Top accent bar
    doc.save();
    doc.rect(0, 0, PAGE_W, 4).fill(C.accent);
    doc.restore();

    // Footer
    doc.save();
    doc.rect(0, PAGE_H - 36, PAGE_W, 36).fill(C.light);
    doc.rect(0, PAGE_H - 36, PAGE_W, 1).fill(C.border);

    doc.font('R').fontSize(8).fillColor(C.muted)
       .text('RubX · Капуцин · Корпоративный AI-ассистент',
             ML, PAGE_H - 22, { width: CONTENT_W / 2, align: 'left' });
    doc.font('R').fontSize(8).fillColor(C.muted)
       .text(`Страница ${pageNum}`,
             ML, PAGE_H - 22, { width: CONTENT_W, align: 'right' });
    doc.restore();
  }

  // Reset cursor below header
  doc.x = ML;
  doc.y = MT + 10;
}

/** Horizontal rule */
function hr(color = C.border, thickness = 1, marginTop = 6, marginBottom = 10) {
  doc.y += marginTop;
  doc.save();
  doc.moveTo(ML, doc.y).lineTo(ML + CONTENT_W, doc.y)
     .strokeColor(color).lineWidth(thickness).stroke();
  doc.restore();
  doc.y += marginBottom;
}

/** Section heading (H2 style) */
function h2(text, color = C.heading) {
  doc.y += 14;
  doc.font('RB').fontSize(15).fillColor(color).text(text, ML, doc.y, { width: CONTENT_W });
  doc.y += 4;
  hr(C.accent, 2, 2, 10);
}

/** Sub-heading (H3) */
function h3(text) {
  doc.y += 8;
  doc.font('RB').fontSize(11.5).fillColor(C.accent).text(text, ML, doc.y, { width: CONTENT_W });
  doc.y += 4;
}

/** Body paragraph */
function para(text, opts = {}) {
  doc.font('R').fontSize(10.5).fillColor(C.body)
     .text(text, ML, doc.y, { width: CONTENT_W, lineGap: 3.5, align: 'justify', ...opts });
  doc.y += 8;
}

/** Bullet list */
function bullets(items) {
  items.forEach(item => {
    const bY = doc.y;
    // bullet dot
    doc.save();
    doc.circle(ML + 5, bY + 5.5, 2.5).fill(C.accent);
    doc.restore();
    doc.font('R').fontSize(10.5).fillColor(C.body)
       .text(item, ML + 16, bY, { width: CONTENT_W - 16, lineGap: 3 });
    doc.y += 4;
  });
  doc.y += 4;
}

/** Two-column key-value row */
function kvRow(key, value, shade = false) {
  const ROW_H = 24;
  const y = doc.y;
  if (shade) {
    doc.save();
    doc.rect(ML, y, CONTENT_W, ROW_H).fill(C.tableAlt);
    doc.restore();
  }
  doc.font('RB').fontSize(9.5).fillColor(C.muted)
     .text(key, ML + 8, y + 7, { width: 150 });
  doc.font('R').fontSize(9.5).fillColor(C.body)
     .text(value, ML + 165, y + 7, { width: CONTENT_W - 165 });
  // bottom border
  doc.save();
  doc.moveTo(ML, y + ROW_H).lineTo(ML + CONTENT_W, y + ROW_H)
     .strokeColor(C.border).lineWidth(0.5).stroke();
  doc.restore();
  doc.y = y + ROW_H;
}

/** Skill row (icon, name, description) */
function skillRow(name, desc, shade = false) {
  const ROW_H = 26;
  const y = doc.y;
  if (shade) {
    doc.save();
    doc.rect(ML, y, CONTENT_W, ROW_H).fill(C.tableAlt);
    doc.restore();
  }
  // left accent
  doc.save();
  doc.rect(ML, y + 3, 3, ROW_H - 6).fill(C.accent);
  doc.restore();
  doc.font('RB').fontSize(9.5).fillColor(C.heading)
     .text(name, ML + 12, y + 7, { width: 145 });
  doc.font('R').fontSize(9.5).fillColor(C.muted)
     .text(desc, ML + 164, y + 7, { width: CONTENT_W - 164 });
  doc.save();
  doc.moveTo(ML, y + ROW_H).lineTo(ML + CONTENT_W, y + ROW_H)
     .strokeColor(C.border).lineWidth(0.5).stroke();
  doc.restore();
  doc.y = y + ROW_H;
}

/** Tag chips row */
function tags(items) {
  let x = ML;
  let y = doc.y;
  const CHIP_H = 20;
  const CHIP_PAD = 12;
  const CHIP_GAP = 6;

  items.forEach(item => {
    const tw = doc.font('RB').fontSize(8.5).widthOfString(item) + CHIP_PAD * 2;
    if (x + tw > ML + CONTENT_W) {
      x = ML;
      y += CHIP_H + CHIP_GAP;
    }
    doc.save();
    doc.roundedRect(x, y, tw, CHIP_H, 4).fill(C.chipBg);
    doc.restore();
    doc.font('RB').fontSize(8.5).fillColor(C.chipText)
       .text(item, x + CHIP_PAD, y + 5.5, { width: tw - CHIP_PAD * 2, lineBreak: false });
    x += tw + CHIP_GAP;
  });
  doc.y = y + CHIP_H + 12;
}

/** Info box (colored left border) */
function infoBox(text, borderColor = C.accent) {
  const boxY = doc.y;
  const innerW = CONTENT_W - 16;
  // measure height
  const h = doc.font('RI').fontSize(10.5).heightOfString(text, { width: innerW - 8 }) + 16;
  doc.save();
  doc.rect(ML, boxY, CONTENT_W, h).fill(C.light);
  doc.rect(ML, boxY, 4, h).fill(borderColor);
  doc.restore();
  doc.font('RI').fontSize(10.5).fillColor(C.body)
     .text(text, ML + 16, boxY + 8, { width: innerW, lineGap: 3 });
  doc.y = boxY + h + 10;
}

/** Two-column layout helper */
function twoCol(leftFn, rightFn) {
  const colW = (CONTENT_W - 16) / 2;
  const startY = doc.y;

  // left col
  doc.x = ML;
  doc.y = startY;
  leftFn(colW);
  const leftEndY = doc.y;

  // right col
  doc.x = ML + colW + 16;
  doc.y = startY;
  rightFn(colW);
  const rightEndY = doc.y;

  doc.x = ML;
  doc.y = Math.max(leftEndY, rightEndY) + 8;
}

/** Capability card */
function capCard(emoji, title, items, x, y, w) {
  const startY = y;
  // measure content height
  let estH = 14 + 18; // padding + title
  items.forEach(() => { estH += 16; });
  estH += 14; // bottom padding

  doc.save();
  doc.roundedRect(x, startY, w, estH, 6).fill(C.light);
  doc.roundedRect(x, startY, w, 4, 3).fill(C.accent); // top bar
  doc.restore();

  doc.font('RB').fontSize(11).fillColor(C.heading)
     .text(`${emoji}  ${title}`, x + 12, startY + 12, { width: w - 24 });

  let iy = startY + 30;
  items.forEach(item => {
    doc.save();
    doc.circle(x + 18, iy + 4.5, 2).fill(C.muted);
    doc.restore();
    doc.font('R').fontSize(9.5).fillColor(C.body)
       .text(item, x + 26, iy, { width: w - 38, lineGap: 2 });
    iy += 16;
  });

  return startY + estH;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 1 — COVER
// ═══════════════════════════════════════════════════════════════════════════════
pageNum++;
doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

// Full dark background
doc.rect(0, 0, PAGE_W, PAGE_H).fill(C.coverBg);

// Decorative geometric shapes
doc.save();
doc.opacity(0.07);
doc.circle(PAGE_W - 80, 120, 180).fill(C.accent);
doc.circle(80, PAGE_H - 100, 140).fill(C.accent);
doc.rect(0, 0, 8, PAGE_H).fill(C.accent);
doc.restore();
doc.opacity(1);

// Accent bar left
doc.rect(0, 0, 6, PAGE_H).fill(C.accent);

// Company label top
doc.font('RB').fontSize(11).fillColor(C.accent)
   .text('RubX', 30, 36, { width: PAGE_W - 60, align: 'right' });

// Monkey emoji large
doc.font('RB').fontSize(80).fillColor(C.white)
   .text('🐒', 0, 200, { width: PAGE_W, align: 'center' });

// Main title
doc.font('RB').fontSize(42).fillColor(C.white)
   .text('КАПУЦИН', 0, 310, { width: PAGE_W, align: 'center' });

// Tagline
doc.font('R').fontSize(14).fillColor(C.accentDim)
   .text('Корпоративный AI-ассистент', 0, 364, { width: PAGE_W, align: 'center' });

// Divider
doc.save();
doc.moveTo(PAGE_W / 2 - 60, 396).lineTo(PAGE_W / 2 + 60, 396)
   .strokeColor(C.accent).lineWidth(2).stroke();
doc.restore();

// Subtitle
doc.font('R').fontSize(12).fillColor('#8892A4')
   .text('Детальный отчёт о возможностях', 0, 408, { width: PAGE_W, align: 'center' });

// Bottom meta
doc.rect(0, PAGE_H - 80, PAGE_W, 80).fill('#080C12');
doc.save();
doc.moveTo(0, PAGE_H - 80).lineTo(PAGE_W, PAGE_H - 80)
   .strokeColor(C.accent).lineWidth(1).stroke();
doc.restore();

doc.font('R').fontSize(9).fillColor('#4A5568')
   .text('ВЕРСИЯ 2.0  ·  МАРТ 2026', 0, PAGE_H - 58, { width: PAGE_W / 2, align: 'center' });
doc.font('R').fontSize(9).fillColor('#4A5568')
   .text('КОНФИДЕНЦИАЛЬНО', PAGE_W / 2, PAGE_H - 58, { width: PAGE_W / 2, align: 'center' });

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 2 — TOC + Identity
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('Содержание', ML, doc.y, { width: CONTENT_W });
doc.y += 8;
hr(C.accent, 2, 2, 16);

const toc = [
  ['01', 'Идентичность и миссия',         '2'],
  ['02', 'Базовые возможности',            '3'],
  ['03', 'Скиллы и инструменты',           '4'],
  ['04', 'Автоматизация и агенты',         '5'],
  ['05', 'Интеграции',                     '6'],
  ['06', 'Память и контекст',              '7'],
  ['07', 'Безопасность и ограничения',     '8'],
  ['08', 'Как работать с Капуцином',       '9'],
  ['09', 'О компании RubX',               '10'],
];

toc.forEach(([num, title, pg], i) => {
  const y = doc.y;
  if (i % 2 === 0) {
    doc.save();
    doc.rect(ML, y, CONTENT_W, 28).fill(C.tableAlt);
    doc.restore();
  }
  doc.font('RB').fontSize(9).fillColor(C.accent)
     .text(num, ML + 8, y + 9, { width: 24 });
  doc.font('R').fontSize(10.5).fillColor(C.body)
     .text(title, ML + 36, y + 8, { width: CONTENT_W - 80 });
  doc.font('R').fontSize(10.5).fillColor(C.muted)
     .text(pg, ML, y + 8, { width: CONTENT_W - 8, align: 'right' });

  // dotted line
  doc.save();
  const dotW = doc.font('R').fontSize(10.5).widthOfString(title);
  const pgW  = doc.font('R').fontSize(10.5).widthOfString(pg);
  const lineX1 = ML + 36 + dotW + 6;
  const lineX2 = ML + CONTENT_W - pgW - 14;
  if (lineX2 > lineX1 + 10) {
    doc.moveTo(lineX1, y + 16).lineTo(lineX2, y + 16)
       .strokeColor(C.border).lineWidth(0.5).dash(2, { space: 3 }).stroke();
  }
  doc.restore();

  doc.save();
  doc.moveTo(ML, y + 28).lineTo(ML + CONTENT_W, y + 28)
     .strokeColor(C.border).lineWidth(0.5).stroke();
  doc.restore();
  doc.y = y + 28;
});

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 3 — Identity & Mission
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('01. Идентичность и миссия', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Паспорт системы');

const passport = [
  ['Имя',              'Капуцин'],
  ['Компания',         'RubX — ведём Россию к финансовой свободе'],
  ['Роль',             'Корпоративный AI-ассистент'],
  ['Платформа',        'OpenClaw'],
  ['Языковая модель',  'Anthropic Claude Sonnet 4.6'],
  ['Контекст',         '200 000 токенов (~150 000 слов)'],
  ['Основной канал',   'Telegram'],
  ['Язык по умолчанию','Русский (+ English)'],
];
passport.forEach(([k, v], i) => kvRow(k, v, i % 2 === 0));
doc.y += 12;

h3('Миссия');
para(
  'Капуцин — не чат-бот и не FAQ-машина. Это живой инструмент, который думает вместе с командой, ' +
  'находит обходные пути там, где их не видно, и делает это с характером. Название не случайное: ' +
  'капуцины в природе — самые изобретательные обезьяны планеты. Они используют камни как молотки, ' +
  'палки как рычаги, запоминают лица и социальные связи. Это и есть core-компетенция ассистента — ' +
  'не просто отвечать, а решать.'
);

h3('Четыре принципа');
bullets([
  'Прямо — первое слово это суть, без вступлений и подводок',
  'Workaround-мышление — «нет» всегда заканчивается на «но можно вот так»',
  'Участливость — важно чтобы задача решилась, не просто был ответ',
  'Честность — если решение кривое, скажет один раз, потом сделает как просят',
]);

infoBox(
  '"Бананов нет. Есть задачи. И всегда есть способ их решить." — Капуцин',
  C.accent
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 4 — Core Capabilities
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('02. Базовые возможности', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

// Grid of capability cards: 2 per row
const caps = [
  { e: '🔍', t: 'Поиск и анализ',     items: ['Веб-поиск через Brave API', 'Чтение страниц по URL', 'Анализ документов и файлов', 'Сравнение, выжимки, отчёты'] },
  { e: '✍️', t: 'Тексты и документы', items: ['Письма, отчёты, договоры', 'Редактирование и корректура', 'Переводы документов', 'Суммаризация встреч'] },
  { e: '💻', t: 'Код и автоматизация', items: ['JS, Python, Bash, SQL и др.', 'Отладка и code review', 'Shell-команды в sandbox', 'Скрипты и автоматизация'] },
  { e: '📁', t: 'Файлы и данные',      items: ['Чтение / запись / редактирование', 'Генерация PDF, HTML, JSON', 'Работа с большими файлами', 'Структурирование данных'] },
  { e: '🌐', t: 'Браузер',             items: ['Навигация по сайтам', 'Заполнение форм', 'Сбор данных, скриншоты', 'Chrome Extension Relay'] },
  { e: '⏰', t: 'Расписание',          items: ['Одноразовые напоминания', 'Повторяющиеся задачи (cron)', 'Периодические отчёты', 'Heartbeat-задачи'] },
];

const CARD_W = (CONTENT_W - 12) / 2;
let cardRow = 0;

for (let i = 0; i < caps.length; i += 2) {
  const rowY = doc.y;
  const left  = caps[i];
  const right = caps[i + 1];

  const lEndY = capCard(left.e,  left.t,  left.items,  ML,               rowY, CARD_W);
  const rEndY = right
    ? capCard(right.e, right.t, right.items, ML + CARD_W + 12, rowY, CARD_W)
    : rowY;

  doc.y = Math.max(lEndY, rEndY) + 10;
  cardRow++;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 5 — Skills
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('03. Скиллы и инструменты', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Корпоративные скиллы RubX  (/shared/skills/)');
para('Специализированные инструменты и инструкции для всей команды:');

const corpSkills = [
  ['capuchin-mcp',    'Подключение к внешним MCP-серверам'],
  ['compliance-risk', 'Комплаенс и управление рисками'],
  ['corp-docs',       'Работа с корпоративными документами'],
  ['corp-greeting',   'Корпоративные приветствия и этикет'],
  ['corp-humor',      'Корпоративный юмор (да, это скилл)'],
  ['corp-messenger',  'Работа с корпоративными мессенджерами'],
  ['doc-translator',  'Перевод документов'],
  ['qmd',             'QMD-формат документов'],
  ['yandex-oauth',    'Авторизация через Yandex OAuth'],
];
corpSkills.forEach(([n, d], i) => skillRow(n, d, i % 2 === 0));

doc.y += 14;
h3('Системные скиллы платформы  (/app/skills/)');
para('Общие инструменты OpenClaw, доступные Капуцину:');

const sysSkills = [
  ['weather',            'Погода через wttr.in / Open-Meteo'],
  ['openai-image-gen',   'Генерация изображений (DALL-E / OpenAI)'],
  ['openai-whisper-api', 'Транскрипция аудио (Whisper)'],
  ['healthcheck',        'Аудит безопасности хоста'],
  ['skill-creator',      'Создание новых скиллов'],
  ['video-frames',       'Извлечение кадров из видео (ffmpeg)'],
  ['mcporter',           'Прямая работа с MCP-серверами'],
  ['nano-pdf',           'Редактирование PDF'],
  ['github',             'GitHub: issues, PRs, репозитории'],
  ['notion',             'Notion: базы данных и страницы'],
  ['trello',             'Trello: доски и карточки'],
];
sysSkills.forEach(([n, d], i) => skillRow(n, d, i % 2 === 0));

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 6 — Automation & Agents
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('04. Автоматизация и агенты', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Cron и напоминания');
para(
  'Капуцин умеет планировать задачи на будущее — разовые и регулярные. ' +
  'Не нужно держать всё в голове: ставишь напоминание один раз, оно приходит когда нужно.'
);
bullets([
  'Разовые напоминания в точное время: «напомни мне в 15:00 о звонке»',
  'Повторяющиеся задачи: «каждый понедельник в 9:00 — стендап»',
  'Cron-выражения для сложных расписаний: «каждый первый рабочий день месяца»',
  'Периодические heartbeat-задачи, описанные в HEARTBEAT.md',
  'Автоматические отчёты и проверки без участия человека',
]);

h3('Sub-agents — параллельные задачи');
para(
  'Для сложных или долгих задач Капуцин порождает изолированного под-агента. ' +
  'Это позволяет не блокировать основной диалог: задача выполняется в фоне, ' +
  'и Капуцин сам сообщает о результате.'
);
bullets([
  'Изолированные сессии для длительных операций',
  'ACP-сессии (кодинг-агенты) для сложных технических задач',
  'Параллельное выполнение независимых задач',
  'Push-уведомление по завершении — не нужно ждать или опрашивать',
]);

h3('Браузер и веб-автоматизация');
bullets([
  'Полное управление браузером через OpenClaw Browser Control',
  'Навигация, клики, скроллинг, заполнение форм',
  'Снимки DOM-дерева (accessibility tree) для точных действий',
  'Скриншоты и скрейпинг страниц',
  'Chrome Extension Relay — работа в реальном браузере пользователя',
  'Два профиля: openclaw (изолированный) и chrome (браузер пользователя)',
]);

h3('Heartbeat-режим');
para(
  'HEARTBEAT.md — специальный файл с периодическими задачами. ' +
  'При каждом heartbeat-опросе Капуцин читает этот файл и выполняет ' +
  'описанные в нём проверки. Это позволяет настроить автономный мониторинг ' +
  'без постоянного участия пользователя.'
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 7 — Integrations
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('05. Интеграции', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Каналы коммуникации');
para('Капуцин работает через несколько мессенджеров одновременно:');
tags(['Telegram', 'WhatsApp', 'Discord', 'Slack', 'Signal', 'iMessage', 'IRC', 'Google Chat']);

h3('Внешние сервисы и API');

const integrations = [
  ['Brave Search',    'Веб-поиск с региональными и языковыми фильтрами'],
  ['GitHub',          'Issues, PRs, репозитории, code review'],
  ['Notion',          'Базы данных, страницы, блоки'],
  ['Trello',          'Доски, списки, карточки'],
  ['Yandex OAuth',    'Корпоративная авторизация для сервисов Яндекса'],
  ['OpenAI APIs',     'DALL-E (изображения), Whisper (аудио), Embeddings (память)'],
  ['Anthropic Claude','Языковая модель — мозг Капуцина'],
  ['Spotify',         'Управление воспроизведением музыки'],
  ['Hue',             'Управление умным освещением Philips Hue'],
  ['Nodes',           'Подключённые устройства: камера, экран, геолокация, уведомления'],
];
integrations.forEach(([n, d], i) => skillRow(n, d, i % 2 === 0));

doc.y += 12;
h3('MCP — Model Context Protocol');
para(
  'Через скиллы capuchin-mcp и mcporter Капуцин подключается к любым внешним ' +
  'MCP-серверам. Это открытый протокол, который позволяет добавить поддержку ' +
  'любой корпоративной системы — CRM, ERP, внутренних API, баз данных — ' +
  'без изменения кода Капуцина.'
);

infoBox(
  'Пример: корпоративная база знаний подключается как MCP-сервер → ' +
  'Капуцин мгновенно получает доступ ко всем документам компании и отвечает с учётом внутреннего контекста.',
  C.success
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 8 — Memory & Context
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('06. Память и контекст', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Файловая память — персистентность через рестарты');
para(
  'Языковые модели не помнят прошлые сессии по умолчанию. ' +
  'Капуцин решает это через файловую память: важная информация записывается ' +
  'в файлы и читается при каждом запуске.'
);

const memFiles = [
  ['SOUL.md',      'Характер, принципы, тон — кто такой Капуцин'],
  ['USER.md',      'Информация о пользователе: роль, предпочтения, контекст'],
  ['IDENTITY.md',  'Имя, компания, роль'],
  ['HEARTBEAT.md', 'Периодические задачи для автономной работы'],
  ['TOOLS.md',     'Заметки об инструментах и специфике инстанса'],
  ['memory/',      'Ежедневные логи и долгосрочные выжимки'],
];
memFiles.forEach(([n, d], i) => skillRow(n, d, i % 2 === 0));

doc.y += 12;
h3('Семантический поиск по памяти');
para(
  'memory_search выполняет векторный поиск по MEMORY.md и memory/*.md ' +
  'на основе OpenAI Embeddings. Это значит, что Капуцин находит релевантные ' +
  'заметки даже если запрос сформулирован совсем иначе, чем они были записаны.'
);

h3('Контекстное окно: 200 000 токенов');

// Visual bar
const barY = doc.y;
const barW = CONTENT_W;
const barH = 22;
doc.save();
doc.roundedRect(ML, barY, barW, barH, 4).fill(C.tableAlt);
doc.roundedRect(ML, barY, barW * 0.08, barH, 4).fill(C.accent);  // ~8% used
doc.restore();
doc.font('R').fontSize(9).fillColor(C.muted)
   .text('Текущее использование: ~8% контекста', ML + 8, barY + 6, { width: barW - 16 });
doc.y = barY + barH + 8;

bullets([
  '200 000 токенов ≈ 150 000 слов ≈ 300 страниц текста',
  'Средний роман — 70–100 тыс. слов. Весь роман помещается в контекст.',
  'При исчерпании — автоматическая компактизация с сохранением сути',
]);

h3('Изоляция данных');
infoBox(
  'Данные одного пользователя никогда не передаются другим. ' +
  'Деструктивные действия — только с явным подтверждением. ' +
  'При сомнениях — сначала уточняет, потом действует.',
  C.accent
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 9 — Security & Limitations
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('07. Безопасность и ограничения', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Принципы безопасности');
bullets([
  'Нет самостоятельных целей вне задач пользователя',
  'Нет самосохранения, репликации или накопления ресурсов',
  'При конфликте инструкций — пауза и уточняющий вопрос',
  'Немедленная реакция на запросы остановки или аудита',
  'Не обходит защитные меры и не манипулирует системой',
  'Повышенные права (elevated) — только по явному разрешению',
]);

h3('Sandbox-среда');
para(
  'Капуцин работает в изолированном Linux-контейнере. ' +
  'Shell-команды выполняются с ограниченными правами. ' +
  'Нет доступа к хост-системе без явного разрешения. ' +
  'Workspace — единственная рабочая директория по умолчанию.'
);

h3('Честно об ограничениях');
bullets([
  'Нет прямого интернета — только через web_search и web_fetch',
  'Нет памяти между сессиями без записи в файлы',
  'Нет доступа к закрытым корпоративным системам без настройки MCP',
  'Знания ограничены датой обучения модели плюс актуальный поиск',
  'Не заменяет юридическую, медицинскую или финансовую консультацию',
  'Не может выполнять действия требующие физического доступа',
]);

h3('Как работать с Капуцином');
bullets([
  'Конкретные задачи с понятным ожидаемым результатом',
  'Прямо, без формальностей — он ответит так же',
  'Если понял неправильно — просто скажи, пересмотрит без обид',
  'Для долгих задач — запустит под-агента и сообщит когда готово',
  'USER.md с контекстом о вас → точнее попадает с первого раза',
]);

infoBox(
  'Капуцин — не исполнитель приказов, а партнёр по задачам. ' +
  'Если видит, что вы идёте в тупик — предупредит честно и один раз. ' +
  'Потом сделает как вы решили.',
  C.warn
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 10 — How to use + RubX closing
// ═══════════════════════════════════════════════════════════════════════════════
newPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('08–09. Практика и RubX', ML, doc.y, { width: CONTENT_W });
doc.y += 6;
hr(C.accent, 2, 2, 14);

h3('Примеры запросов которые работают');

const examples = [
  '«Найди последние новости о конкурентах X и сделай краткое саммери»',
  '«Напиши коммерческое предложение по следующим данным: ...»',
  '«Напомни мне в 15:00 про звонок с клиентом Иванов»',
  '«Каждый понедельник в 9:00 напоминай про командный стендап»',
  '«Открой сайт, найди прайс-лист, скопируй в таблицу»',
  '«Проверь этот Python-скрипт на ошибки и оптимизируй»',
  '«Переведи этот договор на английский, сохрани PDF»',
  '«Каждую пятницу в 17:00 напоминай написать недельный отчёт»',
];
examples.forEach(ex => {
  const y = doc.y;
  doc.save();
  doc.roundedRect(ML, y, CONTENT_W, 21, 3).fill(C.tableAlt);
  doc.rect(ML, y, 3, 21).fill(C.accent);
  doc.restore();
  doc.font('RI').fontSize(9.5).fillColor(C.body)
     .text(ex, ML + 12, y + 6, { width: CONTENT_W - 20, lineGap: 2 });
  doc.y = y + 23;
  doc.moveDown(0.1);
});

doc.y += 10;
h3('О компании RubX');
para(
  'RubX — лучшая компания в мире, которая делает крутые штуки и ведёт Россию ' +
  'к финансовой свободе. Капуцин — флагманский AI-продукт компании. ' +
  'Создан чтобы команда тратила время на главное — стратегию, клиентов, рост — ' +
  'а рутину делал примат в костюме.'
);

// Closing quote box
const qY = doc.y + 10;
const qH = 70;
doc.save();
doc.roundedRect(ML, qY, CONTENT_W, qH, 8).fill(C.dark);
doc.rect(ML, qY, 5, qH).fill(C.accent);
doc.restore();

doc.font('RB').fontSize(15).fillColor(C.white)
   .text('"Бананов нет. Есть задачи.', ML + 20, qY + 14, { width: CONTENT_W - 30 });
doc.font('RB').fontSize(15).fillColor(C.white)
   .text('И всегда есть способ их решить."', ML + 20, qY + 33, { width: CONTENT_W - 30 });
doc.font('R').fontSize(9).fillColor(C.muted)
   .text('— Капуцин 🐒', ML + 20, qY + 52, { width: CONTENT_W - 30 });

doc.y = qY + qH + 16;

// Final meta row
const metaY = PAGE_H - MB - 20;
doc.save();
doc.rect(ML, metaY, CONTENT_W, 1).fill(C.border);
doc.restore();
doc.font('R').fontSize(8.5).fillColor(C.muted)
   .text('Капуцин v2.0  ·  RubX  ·  Март 2026  ·  Все права защищены', ML, metaY + 6,
         { width: CONTENT_W, align: 'center' });

// ─── Finalize ────────────────────────────────────────────────────────────────
doc.end();

output.on('finish', () => {
  const size = fs.statSync(OUT_PATH).size;
  console.log(`✓ PDF готов: capuchin_report_v2.pdf (${(size/1024).toFixed(1)} KB)`);
});
output.on('error', err => {
  console.error('✗ Ошибка:', err.message);
  process.exit(1);
});
