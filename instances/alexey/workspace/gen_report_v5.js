'use strict';
/**
 * Capuchin Report v5
 * - СТРОГО 10 страниц через явное размещение с проверкой Y
 * - Контент не переполняет страницы — если не помещается, обрезается
 * - Полная кириллица (Roboto TTF встроен)
 * - Дизайн: RubX corporate style (синий акцент, строгие таблицы)
 * - НЕТ emoji в тексте
 */

const PDFDocument = require('./node_modules/pdfkit');
const fs   = require('fs');
const path = require('path');

const FONTS = path.join(__dirname, 'fonts');
const OUT   = path.join(__dirname, 'capuchin_report_v5.pdf');

const C = {
  coverBg:  '#0D1117',
  navy:     '#0D1B3E',
  blue:     '#1A56DB',
  blueL:    '#EBF2FF',
  heading:  '#0A0E1A',
  body:     '#1F2937',
  muted:    '#6B7280',
  white:    '#FFFFFF',
  light:    '#F9FAFB',
  border:   '#E5E7EB',
  tableAlt: '#F3F4F6',
  green:    '#059669',
  amber:    '#D97706',
};

const PW = 595.28;
const PH = 841.89;
const ML = 52;
const MR = 52;
const CW = PW - ML - MR;  // 491.28

// Y boundaries per page
const Y_START = 46;   // below header
const Y_END   = PH - 42;  // above footer

const doc = new PDFDocument({
  size: 'A4',
  autoFirstPage: false,
  bufferPages: false,
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

let pageCount = 0;
let curY = Y_START;

// ── Создать страницу с хедером и футером ──────────────────────────────────────
function makePage(title, pageNum) {
  pageCount++;
  doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

  // Accent top bar
  doc.save().rect(0, 0, PW, 5).fill(C.blue).restore();

  // Header bg
  doc.save().rect(0, 5, PW, 28).fill(C.light)
     .moveTo(0, 33).lineTo(PW, 33).strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();

  // Header text
  doc.font('RB').fontSize(8).fillColor(C.blue)
     .text('RubX  |  Капуцин', ML, 16, { width: CW / 2, lineBreak: false });
  doc.font('R').fontSize(8).fillColor(C.muted)
     .text(`Стр. ${pageNum} / 10`, ML, 16, { width: CW, align: 'right', lineBreak: false });

  // Footer bg
  doc.save().rect(0, PH - 36, PW, 36).fill(C.light)
     .moveTo(0, PH - 36).lineTo(PW, PH - 36).strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();
  doc.font('R').fontSize(7.5).fillColor(C.muted)
     .text('Корпоративный AI-ассистент', ML, PH - 22, { width: CW / 2, lineBreak: false });
  doc.font('R').fontSize(7.5).fillColor(C.muted)
     .text('Март 2026  |  Конфиденциально', ML, PH - 22, { width: CW, align: 'right', lineBreak: false });

  // Page title bar (if given)
  curY = Y_START + 4;
  if (title) {
    doc.save().rect(ML, curY, CW, 30).fill(C.blueL).restore();
    doc.save().rect(ML, curY, 4, 30).fill(C.blue).restore();
    doc.font('RB').fontSize(14).fillColor(C.heading)
       .text(title, ML + 12, curY + 8, { width: CW - 16, lineBreak: false });
    curY += 38;
  }
}

// ── Проверка: хватает ли места ────────────────────────────────────────────────
function fits(h) {
  return curY + h <= Y_END;
}

// ── Горизонтальная линия ─────────────────────────────────────────────────────
function rule(color, h, mt, mb) {
  color = color || C.border; h = h || 0.5; mt = mt || 6; mb = mb || 8;
  if (!fits(mt + h + mb)) return;
  curY += mt;
  doc.save().moveTo(ML, curY).lineTo(ML + CW, curY)
     .strokeColor(color).lineWidth(h).stroke().restore();
  curY += mb;
}

// ── H2 подзаголовок ──────────────────────────────────────────────────────────
function h2(text) {
  const H = 24;
  if (!fits(H)) return;
  curY += 8;
  doc.font('RB').fontSize(11).fillColor(C.blue)
     .text(text, ML, curY, { width: CW, lineBreak: false });
  curY += 14;
  doc.save().moveTo(ML, curY).lineTo(ML + CW * 0.4, curY)
     .strokeColor(C.blue).lineWidth(1.5).stroke().restore();
  curY += 6;
}

// ── Параграф ─────────────────────────────────────────────────────────────────
function para(text) {
  const h = doc.font('R').fontSize(9.5).heightOfString(text, { width: CW, lineGap: 3 });
  if (!fits(h + 6)) return;
  doc.font('R').fontSize(9.5).fillColor(C.body)
     .text(text, ML, curY, { width: CW, lineGap: 3, align: 'justify' });
  curY += h + 6;
}

// ── Пункт списка ─────────────────────────────────────────────────────────────
function listItem(text) {
  const h = doc.font('R').fontSize(9.5).heightOfString(text, { width: CW - 16, lineGap: 2.5 });
  const totalH = h + 4;
  if (!fits(totalH)) return;
  doc.save().rect(ML + 4, curY + 4.5, 5, 5).fill(C.blue).restore();
  doc.font('R').fontSize(9.5).fillColor(C.body)
     .text(text, ML + 16, curY, { width: CW - 16, lineGap: 2.5 });
  curY += totalH;
}

function list(items) {
  items.forEach(t => listItem(t));
  curY += 2;
}

// ── Строка таблицы KV ────────────────────────────────────────────────────────
function kvRow(key, val, shade) {
  const H = 22;
  if (!fits(H)) return;
  const y = curY;
  if (shade) doc.save().rect(ML, y, CW, H).fill(C.tableAlt).restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();
  doc.font('RB').fontSize(8.5).fillColor(C.muted)
     .text(key, ML + 8, y + 6, { width: 145, lineBreak: false });
  doc.font('R').fontSize(9).fillColor(C.body)
     .text(val, ML + 162, y + 6, { width: CW - 166, lineBreak: false });
  curY = y + H;
}

// ── Строка таблицы NAME|DESC ─────────────────────────────────────────────────
function tRow(name, desc, shade) {
  const H = 22;
  if (!fits(H)) return;
  const y = curY;
  if (shade) doc.save().rect(ML, y, CW, H).fill(C.tableAlt).restore();
  doc.save().rect(ML, y + 3, 3, H - 6).fill(C.blue).restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();
  doc.font('RB').fontSize(9).fillColor(C.heading)
     .text(name, ML + 10, y + 6, { width: 148, lineBreak: false });
  doc.font('R').fontSize(9).fillColor(C.muted)
     .text(desc, ML + 165, y + 6, { width: CW - 169, lineBreak: false });
  curY = y + H;
}

// ── Chips ────────────────────────────────────────────────────────────────────
function chips(items) {
  const H = 18, PAD = 9, GAP = 5;
  let x = ML, y = curY;
  items.forEach(item => {
    const w = doc.font('RB').fontSize(8).widthOfString(item) + PAD * 2;
    if (x + w > ML + CW) { x = ML; y += H + GAP; }
    if (y + H > Y_END) return;
    doc.save().roundedRect(x, y, w, H, 3).fill(C.navy).restore();
    doc.font('RB').fontSize(8).fillColor(C.white)
       .text(item, x + PAD, y + 4.5, { width: w - PAD * 2, lineBreak: false });
    x += w + GAP;
  });
  curY = y + H + 10;
}

// ── Info box ─────────────────────────────────────────────────────────────────
function infoBox(text, color) {
  color = color || C.blue;
  const tw = CW - 14;
  const h = doc.font('RI').fontSize(9.5).heightOfString(text, { width: tw - 8 }) + 16;
  if (!fits(h + 6)) return;
  curY += 4;
  const y = curY;
  doc.save().rect(ML, y, CW, h).fill(C.blueL).restore();
  doc.save().rect(ML, y, 3, h).fill(color).restore();
  doc.font('RI').fontSize(9.5).fillColor(C.body)
     .text(text, ML + 14, y + 8, { width: tw, lineGap: 3 });
  curY = y + h + 8;
}

// ── Example row ──────────────────────────────────────────────────────────────
function exRow(text, i) {
  const H = 21;
  if (!fits(H)) return;
  const y = curY;
  doc.save().rect(ML, y, CW, H).fill(i % 2 === 0 ? C.tableAlt : C.white).restore();
  doc.save().rect(ML, y, 3, H).fill(C.blue).restore();
  doc.font('RI').fontSize(9).fillColor(C.body)
     .text(text, ML + 12, y + 6, { width: CW - 16, lineBreak: false });
  curY = y + H;
}

// ── Capability card ───────────────────────────────────────────────────────────
function capCard(x, y, w, title, items) {
  const iH = 15;
  const H  = 10 + 16 + items.length * iH + 10;
  if (y + H > Y_END) return 0;
  doc.save().rect(x, y, w, H).fill(C.light).restore();
  doc.save().rect(x, y, w, 3).fill(C.blue).restore();
  doc.save().rect(x, y, w, H).undash()
     .moveTo(x, y).lineTo(x + w, y).lineTo(x + w, y + H)
     .lineTo(x, y + H).lineTo(x, y)
     .strokeColor(C.border).lineWidth(0.5).stroke().restore();
  doc.font('RB').fontSize(9.5).fillColor(C.heading)
     .text(title, x + 10, y + 9, { width: w - 20, lineBreak: false });
  let iy = y + 25;
  items.forEach(item => {
    doc.save().rect(x + 10, iy + 3.5, 4, 4).fill(C.blue).restore();
    doc.font('R').fontSize(8.5).fillColor(C.body)
       .text(item, x + 20, iy, { width: w - 28, lineBreak: false });
    iy += iH;
  });
  return H;
}

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 1 — ОБЛОЖКА
// ══════════════════════════════════════════════════════════════════════════════
pageCount++;
doc.addPage({ size: 'A4', margins: { top: 0, bottom: 0, left: 0, right: 0 } });

// Фон
doc.rect(0, 0, PW, PH).fill(C.coverBg);

// Левая полоса
doc.rect(0, 0, 5, PH).fill(C.blue);

// Тонкая сетка (декор)
doc.save().opacity(0.04);
for (let gx = 0; gx < PW; gx += 32)
  doc.moveTo(gx, 0).lineTo(gx, PH).strokeColor('#FFFFFF').lineWidth(0.5).stroke();
for (let gy = 0; gy < PH; gy += 32)
  doc.moveTo(0, gy).lineTo(PW, gy).strokeColor('#FFFFFF').lineWidth(0.5).stroke();
doc.restore().opacity(1);

// Декоративный прямоугольник
doc.save().opacity(0.06).rect(PW - 180, 0, 180, PH).fill(C.blue).restore().opacity(1);

// Верхняя строка
doc.save().rect(0, 0, PW, 40).fill('#080C14').restore();
doc.save().moveTo(0, 40).lineTo(PW, 40).strokeColor(C.blue).lineWidth(0.8).stroke().restore();
doc.font('RB').fontSize(9).fillColor(C.blue).text('RubX', 20, 14, { lineBreak: false });
doc.font('R').fontSize(9).fillColor('#4B5563').text('Корпоративный AI-ассистент', 60, 14, { lineBreak: false });

// Главный заголовок
doc.font('RB').fontSize(56).fillColor('#FFFFFF')
   .text('КАПУЦИН', 0, 200, { width: PW, align: 'center', characterSpacing: 4, lineBreak: false });

// Линия под заголовком
const ulX1 = (PW - 300) / 2, ulX2 = ulX1 + 300;
doc.save().moveTo(ulX1, 270).lineTo(ulX2, 270).strokeColor(C.blue).lineWidth(2).stroke().restore();

// Подзаголовок
doc.font('R').fontSize(13).fillColor('#9CA3AF')
   .text('Детальный отчёт о возможностях', 0, 283, { width: PW, align: 'center', lineBreak: false });

// Мета-карточки
const mCards = [['Платформа','OpenClaw'],['Модель','Claude Sonnet 4.6'],['Версия','2.0'],['Дата','Март 2026']];
let mcX = (PW - 4 * 120 - 3 * 8) / 2;
mCards.forEach(([label, val]) => {
  doc.save().rect(mcX, 345, 120, 52).fill('#0D1B3E').restore();
  doc.save().rect(mcX, 345, 120, 2).fill(C.blue).restore();
  doc.font('R').fontSize(7.5).fillColor('#6B7280')
     .text(label.toUpperCase(), mcX + 8, 355, { width: 104, align: 'center', lineBreak: false });
  doc.font('RB').fontSize(10).fillColor('#FFFFFF')
     .text(val, mcX + 8, 372, { width: 104, align: 'center', lineBreak: false });
  mcX += 128;
});

// Нижняя полоса
doc.save().rect(0, PH - 56, PW, 56).fill('#060A14').restore();
doc.save().moveTo(0, PH - 56).lineTo(PW, PH - 56).strokeColor(C.blue).lineWidth(0.5).stroke().restore();
doc.font('R').fontSize(8).fillColor('#374151')
   .text('КОНФИДЕНЦИАЛЬНО  |  АО РУБX  |  2026', 0, PH - 32, { width: PW, align: 'center', lineBreak: false });

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 2 — СОДЕРЖАНИЕ
// ══════════════════════════════════════════════════════════════════════════════
makePage('Содержание', 2);

const toc = [
  ['01', 'Идентичность и миссия',        '3'],
  ['02', 'Базовые возможности',           '4'],
  ['03', 'Скиллы и инструменты',          '5'],
  ['04', 'Автоматизация и агенты',        '6'],
  ['05', 'Интеграции',                    '7'],
  ['06', 'Память и контекст',             '8'],
  ['07', 'Безопасность и ограничения',    '9'],
  ['08', 'Как работать с Капуцином',     '10'],
  ['09', 'О компании RubX',             '10'],
];

curY += 4;
toc.forEach(([num, title, pg], i) => {
  const H = 30;
  if (!fits(H)) return;
  const y = curY;
  if (i % 2 === 0) doc.save().rect(ML, y, CW, H).fill(C.tableAlt).restore();
  doc.save().rect(ML, y, 3, H).fill(i % 2 === 0 ? C.blue : '#CBD5E0').restore();
  doc.save().moveTo(ML, y + H).lineTo(ML + CW, y + H)
     .strokeColor(C.border).lineWidth(0.4).stroke().restore();
  doc.font('RB').fontSize(8.5).fillColor(C.blue)
     .text(num, ML + 10, y + 10, { width: 25, lineBreak: false });
  doc.font('R').fontSize(10).fillColor(C.body)
     .text(title, ML + 38, y + 9, { width: CW - 85, lineBreak: false });
  doc.font('RB').fontSize(10).fillColor(C.blue)
     .text(pg, ML, y + 9, { width: CW - 8, align: 'right', lineBreak: false });
  curY = y + H;
});

curY += 18;
infoBox('Документ описывает возможности корпоративного AI-ассистента Капуцин, разработанного компанией RubX. Актуально на март 2026 года.');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 3 — ИДЕНТИЧНОСТЬ
// ══════════════════════════════════════════════════════════════════════════════
makePage('01.  Идентичность и миссия', 3);

h2('Паспорт системы');
[
  ['Наименование',     'Капуцин'],
  ['Компания',         'RubX (АО «Руб Икс»)'],
  ['Назначение',       'Корпоративный AI-ассистент'],
  ['Платформа',        'OpenClaw'],
  ['Языковая модель',  'Anthropic Claude Sonnet 4.6'],
  ['Контекст',         '200 000 токенов (около 150 000 слов)'],
  ['Основной канал',   'Telegram'],
  ['Язык',             'Русский (+ English)'],
  ['Версия',           '2.0  |  Март 2026'],
].forEach(([k, v], i) => kvRow(k, v, i % 2 === 0));

curY += 8;
h2('Миссия');
para('Капуцин — инструмент повышения эффективности команды RubX. Ассистент обрабатывает рутинные задачи, находит решения в нестандартных ситуациях и обеспечивает информационную поддержку в режиме реального времени. Принцип: не просто отвечать, а решать.');

h2('Операционные принципы');
list([
  'Прямота — ответ начинается с сути, без вводных конструкций',
  'Workaround-мышление — невозможное прямо решается обходным путём',
  'Ориентированность на результат — задача выполнена только при достижении цели',
  'Честность — если решение неоптимально, сообщает об этом один раз',
]);

infoBox('"Банана нет. Есть задачи. И всегда есть способ их решить." — Капуцин');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 4 — ВОЗМОЖНОСТИ
// ══════════════════════════════════════════════════════════════════════════════
makePage('02.  Базовые возможности', 4);

const caps = [
  { title: 'Поиск и анализ',    items: ['Веб-поиск (Brave Search API)', 'Чтение страниц по URL', 'Анализ документов', 'Выжимки и сравнения'] },
  { title: 'Документы',         items: ['Письма, отчёты, договоры', 'Редактирование текстов', 'Переводы документов', 'Суммаризация встреч'] },
  { title: 'Разработка',        items: ['JS, Python, Bash, SQL', 'Отладка и code review', 'Shell в sandbox', 'Автоматизация задач'] },
  { title: 'Файлы и данные',    items: ['Чтение / запись файлов', 'PDF, HTML, JSON, CSV', 'Работа с большими файлами', 'Форматирование данных'] },
  { title: 'Браузер',           items: ['Навигация и клики', 'Заполнение форм', 'Скриншоты и сбор данных', 'Chrome Extension Relay'] },
  { title: 'Расписание',        items: ['Разовые напоминания', 'Повторяющиеся cron-задачи', 'Периодические отчёты', 'Heartbeat-мониторинг'] },
];

const C2W = (CW - 12) / 2;
for (let i = 0; i < caps.length; i += 2) {
  const rowY = curY;
  const lH = capCard(ML,         rowY, C2W, caps[i].title,   caps[i].items);
  const rH = caps[i+1] ? capCard(ML + C2W + 12, rowY, C2W, caps[i+1].title, caps[i+1].items) : 0;
  curY = rowY + Math.max(lH, rH) + 8;
}

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 5 — СКИЛЛЫ
// ══════════════════════════════════════════════════════════════════════════════
makePage('03.  Скиллы и инструменты', 5);

h2('Корпоративные скиллы RubX  (/shared/skills/)');
para('Специализированные инструменты для всей команды:');
[
  ['capuchin-mcp',    'Подключение к MCP-серверам'],
  ['compliance-risk', 'Комплаенс и управление рисками'],
  ['corp-docs',       'Работа с корпоративными документами'],
  ['corp-greeting',   'Корпоративные приветствия и этикет'],
  ['corp-humor',      'Корпоративный юмор'],
  ['corp-messenger',  'Корпоративные мессенджеры'],
  ['doc-translator',  'Перевод документов'],
  ['qmd',             'QMD-формат документов'],
  ['yandex-oauth',    'Авторизация через Yandex OAuth'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

curY += 12;
h2('Системные скиллы платформы  (/app/skills/)');
[
  ['weather',            'Погода (wttr.in / Open-Meteo)'],
  ['openai-image-gen',   'Генерация изображений (DALL-E)'],
  ['openai-whisper-api', 'Транскрипция аудио (Whisper)'],
  ['healthcheck',        'Аудит безопасности хоста'],
  ['skill-creator',      'Создание новых скиллов'],
  ['video-frames',       'Кадры из видео (ffmpeg)'],
  ['mcporter',           'Прямая работа с MCP'],
  ['nano-pdf',           'Редактирование PDF'],
  ['github',             'GitHub: issues, PRs'],
  ['notion',             'Notion: базы данных'],
  ['trello',             'Trello: доски и карточки'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 6 — АВТОМАТИЗАЦИЯ
// ══════════════════════════════════════════════════════════════════════════════
makePage('04.  Автоматизация и агенты', 6);

h2('Планировщик задач (Cron)');
para('Капуцин поддерживает полноценное планирование: разовые напоминания, повторяющиеся по расписанию и сложные cron-выражения.');
list([
  'Разовые: «напомни в 15:00 про звонок» — срабатывает один раз',
  'Регулярные: «каждый понедельник в 9:00 — стендап»',
  'Cron: «первый рабочий день каждого месяца»',
  'Автономные задачи без участия человека',
]);

h2('Sub-agents — изолированные задачи');
para('Для длительных операций порождает под-агентов, не блокируя основной диалог. По завершении — push-уведомление.');
list([
  'Изолированные сессии для длительных операций',
  'ACP-сессии (кодинг-агенты) для технических задач',
  'Параллельное выполнение независимых задач',
]);

h2('Управление браузером');
list([
  'Навигация, клики, скроллинг, заполнение форм',
  'Снимки DOM-дерева для точных действий',
  'Скриншоты и сбор данных со страниц',
  'Chrome Extension Relay — реальный браузер пользователя',
]);

h2('Heartbeat-мониторинг');
para('HEARTBEAT.md содержит периодические задачи. При каждом опросе Капуцин выполняет их автоматически: мониторинг, уведомления, регулярные проверки.');

infoBox('Пример: «Каждую пятницу в 18:00 — проверить задачи в Trello и отправить сводку в Telegram»');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 7 — ИНТЕГРАЦИИ
// ══════════════════════════════════════════════════════════════════════════════
makePage('05.  Интеграции', 7);

h2('Каналы коммуникации');
para('Работает через несколько платформ одновременно:');
chips(['Telegram','WhatsApp','Discord','Slack','Signal','iMessage','IRC','Google Chat']);

h2('Внешние сервисы');
[
  ['Brave Search',    'Веб-поиск с фильтрами по региону и языку'],
  ['GitHub',          'Issues, PRs, репозитории'],
  ['Notion',          'Базы данных, страницы, блоки'],
  ['Trello',          'Доски, списки, карточки задач'],
  ['Yandex OAuth',    'Корпоративная авторизация'],
  ['OpenAI APIs',     'DALL-E (изображения), Whisper (аудио), Embeddings'],
  ['Anthropic',       'Claude Sonnet 4.6 — языковая модель'],
  ['Spotify',         'Управление воспроизведением'],
  ['Philips Hue',     'Умное освещение'],
  ['Nodes',           'Устройства: камера, экран, геолокация'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

curY += 10;
h2('MCP — Model Context Protocol');
para('Открытый протокол для подключения внешних систем. Через capuchin-mcp и mcporter Капуцин подключается к CRM, ERP, внутренним API и базам данных без изменения кода.');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 8 — ПАМЯТЬ
// ══════════════════════════════════════════════════════════════════════════════
makePage('06.  Память и контекст', 8);

h2('Файловая память');
para('Языковые модели не сохраняют состояние между сессиями. Капуцин решает это через файловую систему: важное записывается в файлы и читается при каждом старте.');
[
  ['SOUL.md',      'Характер, принципы, тон — определяет поведение'],
  ['USER.md',      'Данные о пользователе: роль, предпочтения'],
  ['IDENTITY.md',  'Имя, компания, роль ассистента'],
  ['HEARTBEAT.md', 'Периодические задачи для автономной работы'],
  ['TOOLS.md',     'Заметки об инструментах'],
  ['memory/',      'Ежедневные логи и долгосрочные выжимки'],
].forEach(([n, d], i) => tRow(n, d, i % 2 === 0));

curY += 10;
h2('Семантический поиск');
para('memory_search выполняет векторный поиск по файлам памяти на основе OpenAI Embeddings. Находит релевантные записи даже при несовпадении формулировок.');

h2('Контекстное окно: 200 000 токенов');

// Полоска контекста
const bY = curY + 4;
doc.save().roundedRect(ML, bY, CW, 24, 4).fill(C.light).restore();
doc.save().roundedRect(ML, bY, CW * 0.08, 24, 4).fill(C.blue).restore();
doc.save().moveTo(ML, bY).lineTo(ML + CW, bY).lineTo(ML + CW, bY + 24)
   .lineTo(ML, bY + 24).lineTo(ML, bY)
   .strokeColor(C.border).lineWidth(0.5).stroke().restore();
doc.font('R').fontSize(8).fillColor('#FFFFFF').text('8%', ML + 4, bY + 8, { lineBreak: false });
doc.font('R').fontSize(8).fillColor(C.muted).text('Использовано в сессии', ML + CW * 0.08 + 8, bY + 8, { lineBreak: false });
curY = bY + 32;

list([
  '200 000 токенов = около 150 000 слов = около 300 страниц A4',
  'Средний роман (70–100 тыс. слов) полностью помещается в контекст',
  'При исчерпании — автоматическая компактизация',
]);

infoBox('Изоляция данных: данные одного пользователя никогда не передаются другим. Деструктивные действия — только с явным подтверждением.');

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 9 — БЕЗОПАСНОСТЬ
// ══════════════════════════════════════════════════════════════════════════════
makePage('07.  Безопасность и ограничения', 9);

h2('Принципы безопасности');
list([
  'Нет самостоятельных целей вне задач пользователя',
  'Нет самосохранения, репликации или накопления ресурсов',
  'При конфликте инструкций — пауза и уточняющий вопрос',
  'Немедленная реакция на запросы остановки или аудита',
  'Не обходит защитные меры',
  'Повышенные права — только по явному разрешению',
]);

h2('Sandbox-среда');
para('Работает в изолированном Linux-контейнере (Node.js). Shell-команды с ограниченными правами. Нет доступа к хост-системе без явного разрешения. Рабочая директория — только workspace.');

h2('Авторизованный доступ');
para('Система работает со списком авторизованных отправителей. Несанкционированные запросы игнорируются.');

h2('Известные ограничения');
list([
  'Нет прямого интернета — только через web_search и web_fetch',
  'Нет памяти между сессиями без явной записи в файлы',
  'Нет доступа к закрытым системам без настройки MCP',
  'База знаний ограничена датой обучения + актуальный поиск',
  'Не заменяет юридическую или финансовую консультацию',
]);

infoBox('При обнаружении потенциально ошибочного решения — предупреждает один раз, затем действует согласно инструкции.', C.amber);

// ══════════════════════════════════════════════════════════════════════════════
// СТРАНИЦА 10 — ПРАКТИКА + RUBX
// ══════════════════════════════════════════════════════════════════════════════
makePage('08–09.  Практика и RubX', 10);

h2('Эффективные запросы');
[
  'Найди последние новости о конкурентах X и сделай краткое саммери',
  'Напиши коммерческое предложение по следующим параметрам: ...',
  'Напомни в 15:00 про звонок с клиентом Ивановым',
  'Каждый понедельник в 9:00 напоминай про командный стендап',
  'Открой сайт rubx.ru, найди актуальные тарифы и сохрани в таблицу',
  'Проверь Python-скрипт на ошибки и предложи оптимизацию',
  'Переведи договор на английский и сохрани как PDF',
  'Каждую пятницу в 17:30 напоминай написать недельный отчёт',
].forEach((ex, i) => exRow(ex, i));

curY += 12;
h2('О компании RubX');
para('RubX (АО «Руб Икс») — компания в области финансовых технологий. Разрабатывает инструменты для финансовой независимости российского бизнеса: от цифровых активов до AI-ассистентов. Капуцин — флагманский AI-продукт для внутренней автоматизации.');

// Заключительный блок-цитата
if (fits(72)) {
  const qY = curY + 8;
  doc.save().rect(ML, qY, CW, 66).fill(C.navy).restore();
  doc.save().rect(ML, qY, 4, 66).fill(C.blue).restore();
  doc.font('RB').fontSize(13).fillColor('#FFFFFF')
     .text('"Банана нет. Есть задачи.', ML + 16, qY + 11, { width: CW - 24, lineBreak: false });
  doc.font('RB').fontSize(13).fillColor('#FFFFFF')
     .text('И всегда есть способ их решить."', ML + 16, qY + 30, { width: CW - 24, lineBreak: false });
  doc.font('R').fontSize(8.5).fillColor('#6B7280')
     .text('— Капуцин  |  RubX  |  2026', ML + 16, qY + 50, { width: CW - 24, lineBreak: false });
  curY = qY + 74;
}

// Финальная строка
if (fits(16)) {
  doc.save()
     .moveTo(ML, curY).lineTo(ML + CW, curY)
     .strokeColor(C.border).lineWidth(0.5).stroke()
     .restore();
  doc.font('R').fontSize(7.5).fillColor(C.muted)
     .text('Капуцин v2.0  |  RubX  |  Март 2026  |  Все права защищены',
           ML, curY + 5, { width: CW, align: 'center', lineBreak: false });
}

// ── Финализация ───────────────────────────────────────────────────────────────
doc.end();

output.on('finish', () => {
  const sz = fs.statSync(OUT).size;
  // Verify page count via PDF object scan
  const buf = fs.readFileSync(OUT);
  const str = buf.toString('latin1');
  const pgCount = (str.match(/\/Count\s+(\d+)/)||['','?'])[1];
  console.log(`PDF: capuchin_report_v5.pdf  |  ${(sz/1024).toFixed(1)} KB  |  Страниц по счётчику: ${pgCount}  |  Страниц создано: ${pageCount}`);
});
output.on('error', err => {
  console.error('Ошибка:', err.message);
  process.exit(1);
});
