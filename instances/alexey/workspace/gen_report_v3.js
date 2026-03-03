'use strict';
/**
 * Capuchin Report v3 — NO EMOJI, full Cyrillic, embedded Roboto TTF
 */

const PDFDocument = require('./node_modules/pdfkit');
const fs   = require('fs');
const path = require('path');

const FONTS = path.join(__dirname, 'fonts');
const OUT   = path.join(__dirname, 'capuchin_report_v3.pdf');

// Palette
const C = {
  coverBg:  '#0D1117',
  accent:   '#FF4757',
  accentD:  '#CC3344',
  heading:  '#1A1F2E',
  body:     '#2D3748',
  muted:    '#718096',
  light:    '#F7F8FA',
  border:   '#E2E8F0',
  white:    '#FFFFFF',
  tableAlt: '#F8F9FA',
  dark:     '#0D1117',
  green:    '#38A169',
  amber:    '#D69E2E',
};

const PW = 595.28;
const PH = 841.89;
const ML = 56, MR = 56, MT = 60, MB = 56;
const CW = PW - ML - MR;  // content width = 483.28

const doc = new PDFDocument({
  size: 'A4',
  autoFirstPage: false,
  info: {
    Title:    'Капуцин — Детальный отчёт',
    Author:   'Капуцин, RubX',
    Subject:  'Возможности корпоративного AI-ассистента',
    Creator:  'OpenClaw',
  },
});

const output = fs.createWriteStream(OUT);
doc.pipe(output);

doc.registerFont('R',  path.join(FONTS, 'Roboto-Regular.ttf'));
doc.registerFont('RB', path.join(FONTS, 'Roboto-Bold.ttf'));
doc.registerFont('RI', path.join(FONTS, 'Roboto-Italic.ttf'));

let pageNum = 0;

// ── Helpers ──────────────────────────────────────────────────────────────────

function addPage(bare = false) {
  pageNum++;
  doc.addPage({ size: 'A4', margins: { top: MT, bottom: MB, left: ML, right: MR } });

  if (!bare) {
    // top accent bar
    doc.save().rect(0, 0, PW, 5).fill(C.accent).restore();

    // footer
    const fY = PH - 38;
    doc.save()
       .rect(0, fY, PW, 38).fill(C.light)
       .moveTo(0, fY).lineTo(PW, fY).strokeColor(C.border).lineWidth(0.5).stroke()
       .restore();
    doc.font('R').fontSize(8).fillColor(C.muted)
       .text('RubX · Капуцин · Корпоративный AI-ассистент', ML, fY + 13,
             { width: CW / 2, align: 'left' });
    doc.font('R').fontSize(8).fillColor(C.muted)
       .text(`Стр. ${pageNum}`, ML, fY + 13, { width: CW, align: 'right' });
  }

  doc.x = ML;
  doc.y = MT + 8;
}

function hr(color = C.border, h = 1, mt = 8, mb = 12) {
  doc.y += mt;
  doc.save().moveTo(ML, doc.y).lineTo(ML + CW, doc.y)
     .strokeColor(color).lineWidth(h).stroke().restore();
  doc.y += mb;
}

function h1(text) {
  doc.font('RB').fontSize(22).fillColor(C.heading)
     .text(text, ML, doc.y, { width: CW });
  doc.y += 4;
  hr(C.accent, 2.5, 4, 14);
}

function h2(text) {
  doc.y += 10;
  doc.font('RB').fontSize(12).fillColor(C.accent)
     .text(text, ML, doc.y, { width: CW });
  doc.y += 5;
}

function para(text, opts = {}) {
  doc.font('R').fontSize(10.5).fillColor(C.body)
     .text(text, ML, doc.y, { width: CW, lineGap: 3.5, align: 'justify', ...opts });
  doc.y += 8;
}

function bullets(items) {
  items.forEach(item => {
    const y = doc.y;
    doc.save().circle(ML + 5, y + 5.5, 2.5).fill(C.accent).restore();
    doc.font('R').fontSize(10.5).fillColor(C.body)
       .text(item, ML + 16, y, { width: CW - 16, lineGap: 3 });
    doc.y += 4;
  });
  doc.y += 4;
}

function kvRow(key, val, shade) {
  const RH = 26;
  const y  = doc.y;
  if (shade) doc.save().rect(ML, y, CW, RH).fill(C.tableAlt).restore();
  doc.save().moveTo(ML, y + RH).lineTo(ML + CW, y + RH)
     .strokeColor(C.border).lineWidth(0.5).stroke().restore();
  doc.font('RB').fontSize(9.5).fillColor(C.muted)
     .text(key, ML + 8, y + 8, { width: 150 });
  doc.font('R').fontSize(9.5).fillColor(C.body)
     .text(val, ML + 165, y + 8, { width: CW - 170 });
  doc.y = y + RH;
}

function tableRow(name, desc, shade) {
  const RH = 26;
  const y  = doc.y;
  if (shade) doc.save().rect(ML, y, CW, RH).fill(C.tableAlt).restore();
  doc.save().rect(ML, y + 4, 3, RH - 8).fill(C.accent).restore();
  doc.save().moveTo(ML, y + RH).lineTo(ML + CW, y + RH)
     .strokeColor(C.border).lineWidth(0.5).stroke().restore();
  doc.font('RB').fontSize(9.5).fillColor(C.heading)
     .text(name, ML + 12, y + 8, { width: 155 });
  doc.font('R').fontSize(9.5).fillColor(C.muted)
     .text(desc, ML + 174, y + 8, { width: CW - 178 });
  doc.y = y + RH;
}

function infoBox(text, color = C.accent) {
  const y  = doc.y + 6;
  const tw = CW - 16;
  const h  = doc.font('RI').fontSize(10.5).heightOfString(text, { width: tw - 8 }) + 18;
  doc.save().rect(ML, y, CW, h).fill(C.light).restore();
  doc.save().rect(ML, y, 4, h).fill(color).restore();
  doc.font('RI').fontSize(10.5).fillColor(C.body)
     .text(text, ML + 16, y + 9, { width: tw, lineGap: 3.5 });
  doc.y = y + h + 10;
}

function exampleRow(text, i) {
  const RH = 23;
  const y  = doc.y;
  doc.save().rect(ML, y, CW, RH).fill(i % 2 === 0 ? C.tableAlt : C.white).restore();
  doc.save().rect(ML, y, 3, RH).fill(C.accent).restore();
  doc.font('RI').fontSize(9.5).fillColor(C.body)
     .text(text, ML + 12, y + 6, { width: CW - 16, lineGap: 2 });
  doc.y = y + RH + 2;
}

function chipRow(items) {
  let x = ML, y = doc.y;
  const CH = 20, PAD = 10, GAP = 6;
  items.forEach(item => {
    const tw = doc.font('RB').fontSize(8.5).widthOfString(item) + PAD * 2;
    if (x + tw > ML + CW) { x = ML; y += CH + GAP; }
    doc.save().roundedRect(x, y, tw, CH, 4).fill(C.accent).restore();
    doc.font('RB').fontSize(8.5).fillColor(C.white)
       .text(item, x + PAD, y + 5.5, { width: tw - PAD * 2, lineBreak: false });
    x += tw + GAP;
  });
  doc.y = y + CH + 12;
}

// ═══════════════════════════════════════════════════════════════════════════════
// COVER PAGE
// ═══════════════════════════════════════════════════════════════════════════════
pageNum++;
doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

// background
doc.rect(0, 0, PW, PH).fill(C.coverBg);

// subtle grid lines
doc.save().opacity(0.04);
for (let gx = 0; gx < PW; gx += 40)
  doc.moveTo(gx, 0).lineTo(gx, PH).strokeColor(C.white).lineWidth(1).stroke();
for (let gy = 0; gy < PH; gy += 40)
  doc.moveTo(0, gy).lineTo(PW, gy).strokeColor(C.white).lineWidth(1).stroke();
doc.restore().opacity(1);

// left accent stripe
doc.rect(0, 0, 6, PH).fill(C.accent);

// decorative circle (top-right)
doc.save().opacity(0.06)
   .circle(PW - 60, 100, 200).fill(C.accent)
   .restore().opacity(1);

// decorative circle (bottom-left)
doc.save().opacity(0.04)
   .circle(60, PH - 80, 160).fill(C.accent)
   .restore().opacity(1);

// company label
doc.font('RB').fontSize(11).fillColor(C.accent)
   .text('RubX', 24, 32, { width: PW - 48, align: 'right' });

// divider top
doc.save()
   .moveTo(40, 60).lineTo(PW - 40, 60)
   .strokeColor('#1F2937').lineWidth(1).stroke()
   .restore();

// large monospace title block
doc.font('RB').fontSize(11).fillColor('#4A5568')
   .text('[ КОРПОРАТИВНЫЙ AI-АССИСТЕНТ ]', 0, 90, { width: PW, align: 'center' });

// Main title
doc.font('RB').fontSize(56).fillColor(C.white)
   .text('КАПУЦИН', 0, 240, { width: PW, align: 'center', characterSpacing: 6 });

// accent underline
const titleW = doc.font('RB').fontSize(56).widthOfString('КАПУЦИН') + 6 * 6;
const ulX = (PW - titleW) / 2;
doc.save()
   .moveTo(ulX, 316).lineTo(ulX + titleW, 316)
   .strokeColor(C.accent).lineWidth(3).stroke()
   .restore();

// subtitle
doc.font('R').fontSize(14).fillColor('#8892A4')
   .text('Детальный отчёт о возможностях', 0, 330, { width: PW, align: 'center' });

// meta chips row
const chips = ['OpenClaw', 'Claude Sonnet 4.6', 'Март 2026'];
let cx = (PW - 280) / 2;
const cy = 380;
chips.forEach(chip => {
  const cw = doc.font('RB').fontSize(9).widthOfString(chip) + 24;
  doc.save().roundedRect(cx, cy, cw, 22, 4).fill('#1F2937').restore();
  doc.save().roundedRect(cx, cy, 3, 22, 2).fill(C.accent).restore();
  doc.font('RB').fontSize(9).fillColor('#CBD5E0')
     .text(chip, cx + 12, cy + 6.5, { width: cw - 16, lineBreak: false });
  cx += cw + 10;
});

// bottom bar
const bY = PH - 70;
doc.save()
   .rect(0, bY, PW, 70).fill('#080C12')
   .moveTo(0, bY).lineTo(PW, bY).strokeColor(C.accent).lineWidth(1).stroke()
   .restore();
doc.font('R').fontSize(9).fillColor('#4A5568')
   .text('ВЕРСИЯ 2.0', 0, bY + 20, { width: PW / 3, align: 'center' });
doc.font('R').fontSize(9).fillColor('#4A5568')
   .text('МАРТ 2026', PW / 3, bY + 20, { width: PW / 3, align: 'center' });
doc.font('R').fontSize(9).fillColor('#4A5568')
   .text('КОНФИДЕНЦИАЛЬНО', PW * 2 / 3, bY + 20, { width: PW / 3, align: 'center' });

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 2 — CONTENTS
// ═══════════════════════════════════════════════════════════════════════════════
addPage();

doc.font('RB').fontSize(22).fillColor(C.heading)
   .text('Содержание', ML, doc.y, { width: CW });
doc.y += 4;
hr(C.accent, 2.5, 4, 16);

const toc = [
  ['01', 'Идентичность и миссия',           '3'],
  ['02', 'Базовые возможности',              '4'],
  ['03', 'Скиллы и инструменты',             '5'],
  ['04', 'Автоматизация и агенты',           '6'],
  ['05', 'Интеграции',                       '7'],
  ['06', 'Память и контекст',                '8'],
  ['07', 'Безопасность и ограничения',       '9'],
  ['08', 'Как работать с Капуцином',        '10'],
  ['09', 'О компании RubX',                '10'],
];

toc.forEach(([num, title, pg], i) => {
  const y = doc.y;
  if (i % 2 === 0) doc.save().rect(ML, y, CW, 30).fill(C.tableAlt).restore();

  doc.save()
     .moveTo(ML, y + 30).lineTo(ML + CW, y + 30)
     .strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();

  doc.font('RB').fontSize(9).fillColor(C.accent)
     .text(num, ML + 8, y + 10, { width: 28 });

  doc.font('R').fontSize(11).fillColor(C.body)
     .text(title, ML + 40, y + 9, { width: CW - 80 });

  doc.font('R').fontSize(11).fillColor(C.muted)
     .text(pg, ML, y + 9, { width: CW - 8, align: 'right' });

  // dotted separator
  const dotX1 = ML + 40 + doc.font('R').fontSize(11).widthOfString(title) + 8;
  const dotX2 = ML + CW - doc.font('R').fontSize(11).widthOfString(pg) - 14;
  if (dotX2 > dotX1 + 20) {
    doc.save()
       .moveTo(dotX1, y + 18).lineTo(dotX2, y + 18)
       .strokeColor(C.border).lineWidth(0.5).dash(2, { space: 4 }).stroke()
       .restore();
  }

  doc.y = y + 30;
});

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 3 — Identity & Mission
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('01. Идентичность и миссия');

h2('Паспорт системы');
const passport = [
  ['Имя',               'Капуцин'],
  ['Компания',          'RubX — ведём Россию к финансовой свободе'],
  ['Роль',              'Корпоративный AI-ассистент'],
  ['Платформа',         'OpenClaw'],
  ['Языковая модель',   'Anthropic Claude Sonnet 4.6'],
  ['Контекст',          '200 000 токенов (около 150 000 слов)'],
  ['Основной канал',    'Telegram'],
  ['Язык по умолчанию', 'Русский (плюс English)'],
];
passport.forEach(([k, v], i) => kvRow(k, v, i % 2 === 0));
doc.y += 10;

h2('Миссия');
para(
  'Капуцин — не чат-бот и не FAQ-машина. Это живой инструмент, который думает вместе ' +
  'с командой, находит обходные пути там, где их не видно, и делает это с характером. ' +
  'Название не случайное: капуцины в природе — самые изобретательные обезьяны планеты. ' +
  'Они используют камни как молотки, палки как рычаги, запоминают лица и социальные связи. ' +
  'Это и есть core-компетенция ассистента — не просто отвечать, а решать.'
);

h2('Четыре принципа');
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
addPage();
h1('02. Базовые возможности');

const caps = [
  {
    title: 'Поиск и анализ',
    items: [
      'Веб-поиск через Brave Search API',
      'Чтение и разбор страниц по URL',
      'Анализ документов и файлов',
      'Сравнение, выжимки, структурированные отчёты',
    ],
  },
  {
    title: 'Тексты и документы',
    items: [
      'Письма, отчёты, договоры, КП',
      'Редактирование и корректура',
      'Переводы документов',
      'Суммаризация встреч и переписки',
    ],
  },
  {
    title: 'Код и автоматизация',
    items: [
      'JavaScript, Python, Bash, SQL и другие языки',
      'Отладка и code review',
      'Shell-команды в sandbox-среде',
      'Скрипты и автоматизация задач',
    ],
  },
  {
    title: 'Файлы и данные',
    items: [
      'Чтение, запись, редактирование файлов',
      'Генерация PDF, HTML, JSON, CSV',
      'Работа с большими файлами (offset/limit)',
      'Структурирование и форматирование данных',
    ],
  },
  {
    title: 'Браузер',
    items: [
      'Навигация, клики, заполнение форм',
      'Скриншоты и сбор данных',
      'Chrome Extension Relay',
      'Снимки DOM-дерева (accessibility tree)',
    ],
  },
  {
    title: 'Расписание и напоминания',
    items: [
      'Разовые напоминания в точное время',
      'Повторяющиеся cron-задачи',
      'Периодические отчёты без участия человека',
      'Heartbeat-задачи из HEARTBEAT.md',
    ],
  },
];

// 2-column layout
const COL_W = (CW - 14) / 2;
const COL_PAD = 12;

for (let i = 0; i < caps.length; i += 2) {
  const rowY = doc.y;

  // estimate card height
  const card = caps[i];
  const estH = 14 + 18 + card.items.length * 16 + 14;

  // Left card
  const lX = ML, rX = ML + COL_W + 14;
  [caps[i], caps[i + 1]].forEach((cap, col) => {
    if (!cap) return;
    const x   = col === 0 ? lX : rX;
    const cH  = 14 + 18 + cap.items.length * 16 + 14;
    doc.save().roundedRect(x, rowY, COL_W, cH, 6).fill(C.light).restore();
    doc.save().roundedRect(x, rowY, COL_W, 4, 3).fill(C.accent).restore();
    doc.font('RB').fontSize(10.5).fillColor(C.heading)
       .text(cap.title, x + COL_PAD, rowY + 10, { width: COL_W - COL_PAD * 2 });
    let iy = rowY + 28;
    cap.items.forEach(item => {
      doc.save().circle(x + COL_PAD + 6, iy + 4.5, 2).fill(C.muted).restore();
      doc.font('R').fontSize(9.5).fillColor(C.body)
         .text(item, x + COL_PAD + 14, iy, { width: COL_W - COL_PAD * 2 - 14, lineGap: 2 });
      iy += 16;
    });
  });

  const lH = 14 + 18 + caps[i].items.length * 16 + 14;
  const rH = caps[i + 1] ? 14 + 18 + caps[i + 1].items.length * 16 + 14 : 0;
  doc.y = rowY + Math.max(lH, rH) + 10;
}

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 5 — Skills
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('03. Скиллы и инструменты');

h2('Корпоративные скиллы RubX  (/shared/skills/)');
para('Специализированные инструменты и инструкции для всей команды:');

const corpSkills = [
  ['capuchin-mcp',    'Подключение к внешним MCP-серверам'],
  ['compliance-risk', 'Комплаенс и управление рисками'],
  ['corp-docs',       'Работа с корпоративными документами'],
  ['corp-greeting',   'Корпоративные приветствия и этикет'],
  ['corp-humor',      'Корпоративный юмор (да, это реальный скилл)'],
  ['corp-messenger',  'Работа с корпоративными мессенджерами'],
  ['doc-translator',  'Перевод документов'],
  ['qmd',             'QMD-формат документов'],
  ['yandex-oauth',    'Авторизация через Yandex OAuth'],
];
corpSkills.forEach(([n, d], i) => tableRow(n, d, i % 2 === 0));

doc.y += 14;
h2('Системные скиллы платформы  (/app/skills/)');
para('Общие инструменты OpenClaw, доступные Капуцину:');

const sysSkills = [
  ['weather',            'Погода через wttr.in / Open-Meteo'],
  ['openai-image-gen',   'Генерация изображений через OpenAI DALL-E'],
  ['openai-whisper-api', 'Транскрипция аудио (Whisper)'],
  ['healthcheck',        'Аудит безопасности хоста'],
  ['skill-creator',      'Создание новых скиллов'],
  ['video-frames',       'Извлечение кадров из видео через ffmpeg'],
  ['mcporter',           'Прямая работа с MCP-серверами'],
  ['nano-pdf',           'Редактирование PDF'],
  ['github',             'GitHub: issues, PRs, репозитории'],
  ['notion',             'Notion: базы данных и страницы'],
  ['trello',             'Trello: доски и карточки'],
];
sysSkills.forEach(([n, d], i) => tableRow(n, d, i % 2 === 0));

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 6 — Automation
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('04. Автоматизация и агенты');

h2('Cron и напоминания');
para(
  'Капуцин умеет планировать задачи на будущее — разовые и регулярные. ' +
  'Не нужно держать всё в голове: ставишь напоминание один раз, оно приходит когда нужно.'
);
bullets([
  'Разовые напоминания в точное время: «напомни мне в 15:00 о звонке»',
  'Повторяющиеся задачи: «каждый понедельник в 9:00 — стендап»',
  'Cron-выражения для сложных расписаний',
  'Периодические heartbeat-задачи из HEARTBEAT.md',
  'Автоматические отчёты и проверки без участия человека',
]);

h2('Sub-agents — параллельные задачи');
para(
  'Для сложных или долгих задач Капуцин порождает изолированного под-агента. ' +
  'Это позволяет не блокировать основной диалог: задача выполняется в фоне, ' +
  'Капуцин сам сообщает о результате.'
);
bullets([
  'Изолированные сессии для длительных операций',
  'ACP-сессии (кодинг-агенты) для сложных технических задач',
  'Параллельное выполнение независимых задач',
  'Push-уведомление по завершении — не нужно ждать',
]);

h2('Браузер и веб-автоматизация');
bullets([
  'Полное управление браузером через OpenClaw Browser Control',
  'Навигация, клики, скроллинг, заполнение форм',
  'Снимки DOM-дерева (accessibility tree) для точных действий',
  'Скриншоты и скрейпинг страниц',
  'Chrome Extension Relay — работа в реальном браузере пользователя',
  'Два профиля: openclaw (изолированный) и chrome (браузер пользователя)',
]);

h2('Heartbeat-режим');
para(
  'HEARTBEAT.md — специальный файл с периодическими задачами. ' +
  'При каждом heartbeat-опросе Капуцин читает этот файл и выполняет ' +
  'описанные в нём проверки: мониторинг, уведомления, регулярные действия.'
);

infoBox(
  'Пример: «Каждую пятницу в 18:00 — напомни написать недельный отчёт и проверить задачи в Trello»',
  C.accent
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 7 — Integrations
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('05. Интеграции');

h2('Каналы коммуникации');
para('Капуцин работает через несколько мессенджеров одновременно:');
chipRow(['Telegram', 'WhatsApp', 'Discord', 'Slack', 'Signal', 'iMessage', 'IRC', 'Google Chat']);

h2('Внешние сервисы и API');
const integrations = [
  ['Brave Search',    'Веб-поиск с региональными и языковыми фильтрами'],
  ['GitHub',          'Issues, PRs, репозитории, code review'],
  ['Notion',          'Базы данных, страницы, блоки'],
  ['Trello',          'Доски, списки, карточки'],
  ['Yandex OAuth',    'Корпоративная авторизация для сервисов Яндекса'],
  ['OpenAI APIs',     'DALL-E (изображения), Whisper (аудио), Embeddings (память)'],
  ['Anthropic Claude','Языковая модель — основа Капуцина'],
  ['Spotify',         'Управление воспроизведением музыки'],
  ['Philips Hue',     'Управление умным освещением'],
  ['Nodes',           'Устройства: камера, экран, геолокация, уведомления'],
];
integrations.forEach(([n, d], i) => tableRow(n, d, i % 2 === 0));

doc.y += 12;
h2('MCP — Model Context Protocol');
para(
  'Через скиллы capuchin-mcp и mcporter Капуцин подключается к любым внешним ' +
  'MCP-серверам. Открытый протокол позволяет добавить поддержку любой корпоративной ' +
  'системы — CRM, ERP, внутренних API, баз данных — без изменения кода Капуцина.'
);

infoBox(
  'Пример: корпоративная база знаний подключается как MCP-сервер — ' +
  'Капуцин мгновенно получает доступ ко всем документам компании ' +
  'и отвечает с учётом внутреннего контекста.',
  C.green
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 8 — Memory
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('06. Память и контекст');

h2('Файловая память — персистентность через рестарты');
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
memFiles.forEach(([n, d], i) => tableRow(n, d, i % 2 === 0));

doc.y += 12;
h2('Семантический поиск по памяти');
para(
  'memory_search выполняет векторный поиск по файлам памяти на основе OpenAI Embeddings. ' +
  'Капуцин находит релевантные заметки даже если запрос сформулирован совсем иначе, ' +
  'чем они были записаны.'
);

h2('Контекстное окно: 200 000 токенов');

// visual bar
const barY = doc.y + 4;
doc.save().roundedRect(ML, barY, CW, 24, 4).fill(C.light).restore();
doc.save().roundedRect(ML, barY, CW * 0.08, 24, 4).fill(C.accent).restore();
doc.font('R').fontSize(9).fillColor(C.muted)
   .text('Текущее использование сессии: около 8% контекста', ML + 8, barY + 7);
doc.y = barY + 32;

bullets([
  '200 000 токенов — это примерно 150 000 слов или 300 страниц текста',
  'Средний роман — 70–100 тысяч слов. Целиком помещается в контекст.',
  'При исчерпании — автоматическая компактизация с сохранением сути',
]);

h2('Изоляция данных');
infoBox(
  'Данные одного пользователя никогда не передаются другим. ' +
  'Деструктивные действия — только с явным подтверждением. ' +
  'При сомнениях — сначала уточняет, потом действует.',
  C.accent
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 9 — Security
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('07. Безопасность и ограничения');

h2('Принципы безопасности');
bullets([
  'Нет самостоятельных целей вне задач пользователя',
  'Нет самосохранения, репликации или накопления ресурсов',
  'При конфликте инструкций — пауза и уточняющий вопрос',
  'Немедленная реакция на запросы остановки или аудита',
  'Не обходит защитные меры и не манипулирует',
  'Повышенные права (elevated) — только по явному разрешению',
]);

h2('Sandbox-среда');
para(
  'Капуцин работает в изолированном Linux-контейнере (Node.js). ' +
  'Shell-команды выполняются с ограниченными правами. ' +
  'Нет доступа к хост-системе без явного разрешения. ' +
  'Workspace — единственная рабочая директория по умолчанию.'
);

h2('Честно об ограничениях');
bullets([
  'Нет прямого интернета — только через web_search и web_fetch',
  'Нет памяти между сессиями без записи в файлы',
  'Нет доступа к закрытым корпоративным системам без настройки MCP',
  'Знания ограничены датой обучения модели плюс актуальный поиск',
  'Не заменяет юридическую, медицинскую или финансовую консультацию',
  'Не может выполнять действия требующие физического доступа',
]);

h2('Авторизованные пользователи');
para(
  'Система работает со списком авторизованных отправителей. ' +
  'Только они могут взаимодействовать с Капуцином. ' +
  'Это обеспечивает базовый уровень защиты от несанкционированного доступа.'
);

infoBox(
  'Капуцин — не исполнитель приказов, а партнёр по задачам. ' +
  'Если видит, что вы идёте в тупик — предупредит честно и один раз. ' +
  'Потом сделает как вы решили.',
  C.amber
);

// ═══════════════════════════════════════════════════════════════════════════════
// PAGE 10 — How to use + RubX
// ═══════════════════════════════════════════════════════════════════════════════
addPage();
h1('08–09. Практика и RubX');

h2('Запросы, которые работают хорошо');

const examples = [
  'Найди последние новости о конкурентах X и сделай краткое саммери',
  'Напиши коммерческое предложение по следующим данным: ...',
  'Напомни мне в 15:00 про звонок с клиентом Ивановым',
  'Каждый понедельник в 9:00 напоминай про командный стендап',
  'Открой сайт, найди прайс-лист, скопируй данные в таблицу',
  'Проверь этот Python-скрипт на ошибки и оптимизируй',
  'Переведи этот договор на английский и сохрани как PDF',
  'Каждую пятницу в 17:00 напоминай написать недельный отчёт',
];
examples.forEach((ex, i) => exampleRow(ex, i));

doc.y += 10;
h2('О компании RubX');
para(
  'RubX — лучшая компания в мире, которая делает крутые штуки и ведёт Россию ' +
  'к финансовой свободе. Капуцин — флагманский AI-продукт компании. ' +
  'Создан чтобы команда тратила время на главное — стратегию, клиентов, рост — ' +
  'а рутину делал примат в костюме.'
);

// Closing quote block
const qY = doc.y + 8;
const qH = 72;
doc.save().roundedRect(ML, qY, CW, qH, 8).fill(C.dark).restore();
doc.save().roundedRect(ML, qY, 5, qH, 4).fill(C.accent).restore();

doc.font('RB').fontSize(15).fillColor(C.white)
   .text('"Банана нет. Есть задачи.', ML + 20, qY + 13, { width: CW - 30 });
doc.font('RB').fontSize(15).fillColor(C.white)
   .text('И всегда есть способ их решить."', ML + 20, qY + 33, { width: CW - 30 });
doc.font('R').fontSize(9).fillColor(C.muted)
   .text('— Капуцин, RubX', ML + 20, qY + 54, { width: CW - 30 });

doc.y = qY + qH + 16;

// Final bottom line
const metaY = PH - MB - 18;
doc.save()
   .moveTo(ML, metaY).lineTo(ML + CW, metaY)
   .strokeColor(C.border).lineWidth(0.5).stroke()
   .restore();
doc.font('R').fontSize(8).fillColor(C.muted)
   .text('Капуцин v2.0  |  RubX  |  Март 2026  |  Все права защищены',
         ML, metaY + 6, { width: CW, align: 'center' });

// ─── Finalize ────────────────────────────────────────────────────────────────
doc.end();

output.on('finish', () => {
  const sz = fs.statSync(OUT).size;
  console.log(`PDF готов: capuchin_report_v3.pdf (${(sz / 1024).toFixed(1)} KB)`);
});
output.on('error', err => {
  console.error('Ошибка:', err.message);
  process.exit(1);
});
