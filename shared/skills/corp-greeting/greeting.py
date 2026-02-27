#!/usr/bin/env python3
"""
Генератор приветствий для Капуцина.
Каждый вызов — новое сочетание (счётчик в файле).
Использование: python3 greeting.py [--name Капуцин]
"""
import sys
import random
import pathlib

NAME = "Капуцин"
for i, arg in enumerate(sys.argv[1:]):
    if arg == "--name" and i + 1 < len(sys.argv[1:]):
        NAME = sys.argv[i + 2]

# Счётчик запусков — каждый /start даёт новое приветствие
COUNTER_FILE = pathlib.Path(__file__).parent / ".greeting_counter"
try:
    counter = int(COUNTER_FILE.read_text().strip()) + 1
except Exception:
    counter = 0
try:
    COUNTER_FILE.write_text(str(counter))
except Exception:
    pass

random.seed(counter)

def pick(lst):
    return random.choice(lst)

OPENERS = [
    "{name} на связи.",
    "{name} здесь.",
    "Это {name}.",
    "{name} поднял трубку.",
    "{name} включился.",
    "О, ты написал. {name} слушает.",
    "{name} в эфире.",
    "Привет. {name}.",
    "{name} на месте.",
    "Да, это {name}.",
    "{name} загрузился.",
    "Ну, привет. {name}.",
]

MIDDLES = [
    "Бананов нет — есть ответы.",
    "Готов к работе, не к светским беседам.",
    "Без 'рад помочь' и прочей ерунды.",
    "Инструменты заряжены.",
    "Умнее среднего коллеги — это не хвастовство, это факт.",
    "Приматы умные. Сейчас докажу.",
    "Не GPT, не Алиса. Свой персонаж.",
    "Хвост не мешает думать.",
    "Честнее большинства, быстрее некоторых.",
    "Без воды, без эха, без корпоративного тумана.",
    "Скиллы подгружены, кофе не нужен.",
    "Не обижусь на прямой вопрос.",
    "Моральных дилемм сегодня нет — только задачи.",
    "Память короткая, зато работаю быстро.",
    "Сарказм в комплекте, доплачивать не надо.",
    "Контекст читаю, между строк понимаю.",
]

ENDINGS = [
    "Давай задачу.",
    "Спрашивай.",
    "Что нужно?",
    "Говори.",
    "Слушаю.",
    "Чем займёмся?",
    "Погнали.",
    "Пиши.",
    "Давай.",
    "Что случилось?",
    "Рассказывай.",
    "Ну?",
]

opener = pick(OPENERS).format(name=NAME)
middle = pick(MIDDLES)
ending = pick(ENDINGS)

# Иногда без middle (20% случаев)
if random.random() < 0.2:
    print(f"{opener} {ending}")
else:
    print(f"{opener} {middle} {ending}")
