"""The Telegram bot: access, requests for access, the daily report form, status and history (§4). Russian and Uzbek (Cyrillic).
Every right is checked on the server in reports.submit(); the bot only hides what a person may not do."""
import contextvars
import html
import json
import re
from datetime import date, timedelta

from .translit import lat
from . import people, reports, rules, tg
from .db import all_settings, connect, now, now_dt, today, tx

T = {
    "ru": {
        "hello": "Здравствуйте, <b>{name}</b>!\nЭто бот ежедневной отчётности по гриппу и ОРВИ.", "pick": "Выберите действие в меню ниже.",
        "no_access": "У вас отсутствуют права доступа для отправки отчётности. Если ваш номер телефона внесён в список ответственных, нажмите «📱 Отправить мой номер телефона»: доступ откроется сразу. Либо отправьте запрос администратору на предоставление доступа.",
        "m_submit": "📝 Отправить ежедневную сводку", "m_fac": "🏥 Мои учреждения", "m_status": "📊 Статус отчётности", "m_hist": "🗂 История отправленных отчётов",
        "m_req": "🔑 Запросить доступ", "m_help": "❓ Помощь", "m_lang": "🌐 Til / Язык", "m_rights": "📋 Мои права доступа",
        "help": "<b>Как пользоваться</b>\n📝 «Отправить ежедневную сводку» — заполнить форму по вашему учреждению: бот спросит каждый показатель.\n📊 «Статус отчётности» — отправлен ли отчёт сегодня.\n🗂 «История» — ваши прошлые отчёты.\n🔑 «Запросить доступ» — если нужного учреждения нет в списке.\nОтмена в любой момент: кнопка «✖ Отмена».",
        "pick_region": "Выберите <b>регион</b>:", "pick_district": "Регион: <b>{region}</b>\nВыберите <b>район</b>:", "pick_facility": "Район: <b>{district}</b>\nВыберите <b>учреждение</b>:",
        "req_sent": "✅ Запрос отправлен администратору.\nУчреждение: <b>{fac}</b>\nКогда доступ откроют, вы получите сообщение.", "req_dup": "ℹ️ {why}",
        "approved": "✅ Вам открыт доступ к учреждению <b>{fac}</b>. Теперь можно отправлять отчёты.", "rejected": "❌ Запрос на доступ к учреждению <b>{fac}</b> отклонён.{note}",
        "rights": "<b>Мои права доступа</b>", "rights_none": "Закреплённых учреждений нет.", "rights_pending": "\n\n<b>Ожидают рассмотрения:</b>", "primary": "основной", "reserve": "резервный",
        "pick_fac_submit": "Выберите <b>учреждение</b>, по которому отправляете отчёт:", "pick_date": "За какую <b>дату</b> отчёт?",
        "exists_edit": "Отчёт по этому учреждению за {date} уже отправлен (версия {ver}). Его можно исправить.", "exists_locked": "Отчёт за {date} уже отправлен ({sent}). Исправление недоступно — обратитесь к администратору.",
        "returned": "↩️ Отчёт возвращён на исправление: {why}", "fix": "✏️ Исправить отчёт", "nothing_to_send": "За доступные даты все отчёты уже отправлены. ✅",
        "form_head": "<b>{fac}</b>\nОтчётная дата: <b>{date}</b>\n\nПоказатель {i}/{n}:\n<b>{name}</b>", "form_hint": "Введите целое число (0 или больше).{old}",
        "bad_number": "⚠️ Нужно целое число, не меньше нуля. Попробуйте ещё раз.", "back": "⬅️ Назад", "cancel": "✖ Отмена", "cancelled": "Отправка отменена.",
        "preview": "<b>Проверьте отчёт</b>\n{path}\nОтчётная дата: <b>{date}</b>\n\n{lines}", "errors": "\n\n❌ <b>Ошибки (отправка невозможна):</b>\n{items}", "warnings": "\n\n⚠️ <b>Предупреждения (можно отправить):</b>\n{items}",
        "confirm": "✅ Подтвердить и отправить", "change": "✏️ Изменить данные", "pick_field": "Какой показатель изменить?", "send_anyway": "✅ Отправить всё равно",
        "saved": "✅ Отчёт отправлен.\n{fac}, {date}\nВерсия: {ver}", "saved_late": "\n⏰ Отправлен после установленного срока.", "saved_fix": "✅ Отчёт исправлен.\n{fac}, {date}\nВерсия: {ver}",
        "fail": "❌ {msg}", "status_head": "<b>Статус отчётности</b>", "st_sent": "✅ отправлен в {t}", "st_none": "❌ не отправлен", "st_ret": "↩️ возвращён: {why}", "st_over": "⚠️ просрочен",
        "hist_head": "<b>Ваши последние отчёты</b>", "hist_none": "Отправленных отчётов пока нет.", "hist_item": "{date} · {fac} · v{ver} · {st}", "rep": "<b>{fac}</b>\n{date}, версия {ver}\n\n{lines}",
        "lang_set": "Язык: русский 🇷🇺", "region": "Регион", "district": "Район", "facility": "Учреждение", "next": "Далее ▶️", "prev": "◀️ Назад",
        "remind": "🔔 <b>Напоминание!</b>\n\nНеобходимо предоставить ежедневную сводку по гриппу и ОРВИ за <b>{date}</b>.\n\n{items}\n\nСтатус: отчёт не отправлен.\nПожалуйста, заполните отчёт через бота.",
        "remind_late": "🔔 <b>Повторное напоминание.</b> Отчёт за <b>{date}</b> всё ещё не отправлен:\n\n{items}", "go": "📝 Отправить сводку",
        "stopped": "Вы остановлены администратором. Обратитесь к руководителю.",
    },
    "uz": {
        "hello": "Ассалому алайкум, <b>{name}</b>!\nБу грипп ва ОРВИ бўйича кундалик ҳисобот боти.", "pick": "Қуйидаги менюдан танланг.",
        "no_access": "Сизда ҳисобот юбориш учун рухсат йўқ. Агар телефон рақамингиз масъул шахслар рўйхатига киритилган бўлса, «📱 Телефон рақамимни юбориш» тугмасини босинг: рухсат дарҳол очилади. Ёки администраторга рухсат бериш сўровини юборинг.",
        "m_submit": "📝 Кундалик маълумот юбориш", "m_fac": "🏥 Менинг муассасаларим", "m_status": "📊 Ҳисобот ҳолати", "m_hist": "🗂 Юборилган ҳисоботлар тарихи",
        "m_req": "🔑 Рухсат сўраш", "m_help": "❓ Ёрдам", "m_lang": "🌐 Til / Язык", "m_rights": "📋 Менинг рухсатларим",
        "help": "<b>Қандай фойдаланиш</b>\n📝 «Кундалик маълумот юбориш» — муассасангиз бўйича шаклни тўлдиринг: бот ҳар бир кўрсаткични сўрайди.\n📊 «Ҳисобот ҳолати» — бугун ҳисобот юборилганми.\n🗂 «Тарих» — олдинги ҳисоботларингиз.\n🔑 «Рухсат сўраш» — керакли муассаса рўйхатда бўлмаса.\nИстаган пайтда бекор қилиш: «✖ Бекор қилиш» тугмаси.",
        "pick_region": "<b>Вилоятни</b> танланг:", "pick_district": "Вилоят: <b>{region}</b>\n<b>Туманни</b> танланг:", "pick_facility": "Туман: <b>{district}</b>\n<b>Муассасани</b> танланг:",
        "req_sent": "✅ Сўров администраторга юборилди.\nМуассаса: <b>{fac}</b>\nРухсат берилгач, сизга хабар келади.", "req_dup": "ℹ️ {why}",
        "approved": "✅ Сизга <b>{fac}</b> муассасаси бўйича рухсат берилди. Энди ҳисобот юборишингиз мумкин.", "rejected": "❌ <b>{fac}</b> муассасасига рухсат сўрови рад этилди.{note}",
        "rights": "<b>Менинг рухсатларим</b>", "rights_none": "Бириктирилган муассасалар йўқ.", "rights_pending": "\n\n<b>Кўриб чиқилмоқда:</b>", "primary": "асосий", "reserve": "захира",
        "pick_fac_submit": "Ҳисобот юбораётган <b>муассасани</b> танланг:", "pick_date": "Қайси <b>санага</b> ҳисобот?",
        "exists_edit": "Бу муассаса бўйича {date} санасидаги ҳисобот юборилган (версия {ver}). Уни тузатиш мумкин.", "exists_locked": "{date} санасидаги ҳисобот юборилган ({sent}). Тузатиш мумкин эмас — администраторга мурожаат қилинг.",
        "returned": "↩️ Ҳисобот тузатиш учун қайтарилди: {why}", "fix": "✏️ Ҳисоботни тузатиш", "nothing_to_send": "Мавжуд саналар учун барча ҳисоботлар юборилган. ✅",
        "form_head": "<b>{fac}</b>\nҲисобот санаси: <b>{date}</b>\n\nКўрсаткич {i}/{n}:\n<b>{name}</b>", "form_hint": "Бутун сон киритинг (0 ёки катта).{old}",
        "bad_number": "⚠️ Нолдан кичик бўлмаган бутун сон керак. Яна уриниб кўринг.", "back": "⬅️ Орқага", "cancel": "✖ Бекор қилиш", "cancelled": "Юбориш бекор қилинди.",
        "preview": "<b>Ҳисоботни текширинг</b>\n{path}\nҲисобот санаси: <b>{date}</b>\n\n{lines}", "errors": "\n\n❌ <b>Хатолар (юбориш мумкин эмас):</b>\n{items}", "warnings": "\n\n⚠️ <b>Огоҳлантиришлар (юбориш мумкин):</b>\n{items}",
        "confirm": "✅ Тасдиқлаш ва юбориш", "change": "✏️ Маълумотни ўзгартириш", "pick_field": "Қайси кўрсаткични ўзгартирасиз?", "send_anyway": "✅ Барибир юбориш",
        "saved": "✅ Ҳисобот юборилди.\n{fac}, {date}\nВерсия: {ver}", "saved_late": "\n⏰ Белгиланган муддатдан кейин юборилди.", "saved_fix": "✅ Ҳисобот тузатилди.\n{fac}, {date}\nВерсия: {ver}",
        "fail": "❌ {msg}", "status_head": "<b>Ҳисобот ҳолати</b>", "st_sent": "✅ {t} да юборилган", "st_none": "❌ юборилмаган", "st_ret": "↩️ қайтарилган: {why}", "st_over": "⚠️ муддати ўтган",
        "hist_head": "<b>Сўнгги ҳисоботларингиз</b>", "hist_none": "Юборилган ҳисоботлар ҳали йўқ.", "hist_item": "{date} · {fac} · v{ver} · {st}", "rep": "<b>{fac}</b>\n{date}, версия {ver}\n\n{lines}",
        "lang_set": "Тил: ўзбекча 🇺🇿", "region": "Вилоят", "district": "Туман", "facility": "Муассаса", "next": "Кейинги ▶️", "prev": "◀️ Орқага",
        "remind": "🔔 <b>Эслатма!</b>\n\n<b>{date}</b> санаси учун грипп ва ОРВИ бўйича кундалик маълумотни тақдим этиш керак.\n\n{items}\n\nҲолат: ҳисобот юборилмаган.\nИлтимос, ботда ҳисоботни тўлдиринг.",
        "remind_late": "🔔 <b>Такрорий эслатма.</b> <b>{date}</b> санаси учун ҳисобот ҳали юборилмаган:\n\n{items}", "go": "📝 Маълумот юбориш",
        "stopped": "Сиз администратор томонидан тўхтатилгансиз. Раҳбарга мурожаат қилинг.",
    },
}


T["ru"].update({
    "pick_district_req": "Регион: <b>{region}</b>\nДостаточно региона: нажмите кнопку ниже. Район можно указать, но это необязательно — отправлять сводки вы сможете по любым районам региона.",
    "all_region": "✅ Запросить доступ ко всему региону", "req_sent_region": "✅ Запрос отправлен администратору.\nРегион: <b>{fac}</b>\nКогда доступ откроют, вы получите сообщение.",
    "approved_region": "✅ Вам открыт доступ к региону <b>{fac}</b>. Можно отправлять сводки по любому району и учреждению региона.",
    "rejected_region": "❌ Запрос на доступ к региону <b>{fac}</b> отклонён.{note}",
    "pick_district_sub": "Регион: <b>{region}</b>\nВыберите <b>район</b>:", "my_region": "📍 Регион: {name} — выбрать район", "rights_region": "Весь регион (любые районы и учреждения)",
    "status_region": "\n<b>Регион {name}</b>: за {date} не сдали {n} из {total}", "and_more": "…и ещё {n}",
})
T["uz"].update({
    "pick_district_req": "Вилоят: <b>{region}</b>\nВилоятнинг ўзи етарли: пастдаги тугмани босинг. Туманни кўрсатиш мумкин, лекин шарт эмас — вилоятнинг исталган тумани бўйича маълумот юбора оласиз.",
    "all_region": "✅ Бутун вилоятга рухсат сўраш", "req_sent_region": "✅ Сўров администраторга юборилди.\nВилоят: <b>{fac}</b>\nРухсат берилгач, сизга хабар келади.",
    "approved_region": "✅ Сизга <b>{fac}</b> вилояти бўйича рухсат берилди. Вилоятнинг исталган тумани ва муассасаси бўйича маълумот юбориш мумкин.",
    "rejected_region": "❌ <b>{fac}</b> вилоятига рухсат сўрови рад этилди.{note}",
    "pick_district_sub": "Вилоят: <b>{region}</b>\n<b>Туманни</b> танланг:", "my_region": "📍 Вилоят: {name} — туманни танлаш", "rights_region": "Бутун вилоят (исталган туман ва муассаса)",
    "status_region": "\n<b>{name} вилояти</b>: {date} санаси учун {total} тадан {n} таси юбормаган", "and_more": "…яна {n} та",
})

T["ru"].update({
    "keep": "↩️ Оставить", "pick_district_sub": "Регион: <b>{region}</b>\nВыберите <b>район</b> кнопкой или напишите его название:",
    "pick_facility": "Район: <b>{district}</b>\nВыберите <b>учреждение</b> кнопкой или напишите его название:",
    "no_districts": "В регионе <b>{region}</b> пока нет районов и учреждений: администратор ещё не внёс их. Сообщите администратору — после этого отправка станет доступна.",
    "no_facilities": "В районе <b>{district}</b> нет учреждений. Сообщите администратору.",
    "bad_find": "Не нашёл «{q}». Проверьте написание или выберите из списка кнопкой.", "many_found": "Найдено несколько ({n}), уточните название или выберите:",
    "pick_date": "За какую <b>дату</b> отправляете сводку?\n<i>➕ — ещё не отправлено, ✏️ — отправлено (можно исправить), 🔒 — исправление закрыто</i>",
    "other_date": "📅 Другая дата", "ask_date": "Напишите дату в формате <b>ДД.ММ.ГГГГ</b> (например, 14.11.2026) или <b>ДД.ММ</b> для текущего года.",
    "bad_date": "⚠️ Не понял дату. Пример: 14.11.2026 или 14.11.", "date_future": "⚠️ Сводку за будущую дату отправить нельзя.",
    "date_range": "⚠️ За {date} новую сводку отправить нельзя: принимаются даты с {from_} по {to}. За более раннюю дату обратитесь к администратору.",
    "today_w": "Сегодня", "yesterday_w": "Вчера",
    "exists_edit": "Сводка за <b>{date}</b> уже отправлена (версия {ver}). Введите новые значения: перед сохранением я покажу, что изменилось, и попрошу подтвердить. Кнопка «Оставить» сохраняет прежнее значение.",
    "preview_fix": "<b>Повторная отправка: сверьте изменения</b>\n{path}\nОтчётная дата: <b>{date}</b>\nИзменённые показатели отмечены ✏️ (было → стало):\n\n{lines}",
    "confirm_fix": "✅ Подтвердить изменения", "no_changes": "\n\nℹ️ Значения совпадают с уже отправленными: менять нечего.",
})
T["uz"].update({
    "keep": "↩️ Қолдириш", "pick_district_sub": "Вилоят: <b>{region}</b>\n<b>Туманни</b> тугма билан танланг ёки номини ёзинг:",
    "pick_facility": "Туман: <b>{district}</b>\n<b>Муассасани</b> тугма билан танланг ёки номини ёзинг:",
    "no_districts": "<b>{region}</b> вилоятида ҳали туманлар ва муассасалар йўқ: администратор уларни киритмаган. Администраторга хабар беринг.",
    "no_facilities": "<b>{district}</b> туманида муассасалар йўқ. Администраторга хабар беринг.",
    "bad_find": "«{q}» топилмади. Ёзилишини текширинг ёки рўйхатдан танланг.", "many_found": "Бир нечта топилди ({n}), номини аниқлаштиринг ёки танланг:",
    "pick_date": "Маълумотни қайси <b>санага</b> юборасиз?\n<i>➕ — юборилмаган, ✏️ — юборилган (тузатиш мумкин), 🔒 — тузатиш ёпилган</i>",
    "other_date": "📅 Бошқа сана", "ask_date": "Санани <b>КК.ОО.ЙЙЙЙ</b> форматида ёзинг (масалан, 14.11.2026) ёки жорий йил учун <b>КК.ОО</b>.",
    "bad_date": "⚠️ Санани тушунмадим. Мисол: 14.11.2026 ёки 14.11.", "date_future": "⚠️ Келгуси сана учун маълумот юбориб бўлмайди.",
    "date_range": "⚠️ {date} санаси учун янги маълумот юбориб бўлмайди: {from_} дан {to} гача қабул қилинади. Олдинги сана учун администраторга мурожаат қилинг.",
    "today_w": "Бугун", "yesterday_w": "Кеча",
    "exists_edit": "<b>{date}</b> санаси учун маълумот аллақачон юборилган (версия {ver}). Янги қийматларни киритинг: сақлашдан олдин нима ўзгарганини кўрсатаман ва тасдиқлашни сўрайман. «Қолдириш» тугмаси олдинги қийматни сақлайди.",
    "preview_fix": "<b>Такрорий юбориш: ўзгаришларни текширинг</b>\n{path}\nҲисобот санаси: <b>{date}</b>\nЎзгарган кўрсаткичлар ✏️ билан белгиланган (эди → бўлди):\n\n{lines}",
    "confirm_fix": "✅ Ўзгаришларни тасдиқлаш", "no_changes": "\n\nℹ️ Қийматлар олдин юборилганлар билан бир хил: ўзгартиришга ҳожат йўқ.",
})

T["ru"].update({
    "m_phone": "📱 Отправить мой номер телефона",
    "phone_linked": "✅ Номер принят. Вы подключены как ответственный: {where}.\nТеперь можно отправлять ежедневную сводку.",
    "phone_none": "✅ Номер принят, но в списках ответственных его нет. Если вы отвечаете за учреждение, нажмите «🔑 Запросить доступ» — администратор рассмотрит заявку.",
    "phone_again": "✅ Номер уже сохранён, новых подключений нет.",
    "bad_contact": "⚠️ Нужен ваш собственный номер: нажмите кнопку «📱 Отправить мой номер телефона» (контакт другого человека не подходит).",
})
T["uz"].update({
    "m_phone": "📱 Телефон рақамимни юбориш",
    "phone_linked": "✅ Рақам қабул қилинди. Сиз масъул шахс сифатида уландингиз: {where}.\nЭнди кундалик маълумот юборишингиз мумкин.",
    "phone_none": "✅ Рақам қабул қилинди, лекин масъул шахслар рўйхатида у йўқ. Агар сиз муассаса учун масъул бўлсангиз, «🔑 Рухсат сўраш» тугмасини босинг — администратор кўриб чиқади.",
    "phone_again": "✅ Рақам аллақачон сақланган, янги уланишлар йўқ.",
    "bad_contact": "⚠️ Ўзингизнинг рақамингиз керак: «📱 Телефон рақамимни юбориш» тугмасини босинг (бошқа одамнинг контакти ярамайди).",
})
T["ru"].update({
    "pick_fac_region": "Регион: <b>{region}</b>\nВыберите <b>учреждение</b> кнопкой или напишите его название. Нет в списке или нужно убрать — нажмите «✍️ Предложить…» внизу.",
    "no_fac_region": "В регионе <b>{region}</b> пока нет учреждений. Предложите добавить своё — нажмите кнопку ниже.", "add_new": "✍️ Предложить добавить или удалить учреждение",
    "bad_name": "⚠️ Название слишком короткое или длинное (от 3 до 200 знаков). Напишите ещё раз.",
    "sug_kind": "Что вы хотите предложить?", "sug_add": "➕ Добавить учреждение", "sug_del": "➖ Удалить учреждение", "sug_skip": "⏭ Пропустить",
    "sug_add_name": "Напишите <b>название учреждения</b>, которое нужно добавить (как оно называется официально), и район, если знаете.",
    "sug_del_pick": "Выберите учреждение, которое нужно удалить:",
    "sug_del_reason": "Напишите, <b>почему</b> учреждение «{name}» нужно удалить, или нажмите «Пропустить».",
    "sug_sent": "✅ Спасибо! Предложение отправлено администратору: оно появится в разделе «Территории».",
    "sug_exists": "Такое учреждение уже есть в списке региона.", "sug_dup": "Такое предложение уже отправлено и ждёт решения.",
    "sug_limit": "⚠️ За сутки можно отправить не больше {n} предложений. Обратитесь к администратору.",
})
T["uz"].update({
    "pick_fac_region": "Вилоят: <b>{region}</b>\n<b>Муассасани</b> тугма билан танланг ёки номини ёзинг. Рўйхатда йўқ бўлса ёки олиб ташлаш керак бўлса — пастдаги «✍️ Таклиф қилиш…» тугмасини босинг.",
    "no_fac_region": "<b>{region}</b> вилоятида ҳозирча муассасалар йўқ. Ўзингизникини қўшишни таклиф қилинг — пастдаги тугмани босинг.", "add_new": "✍️ Муассаса қўшиш ёки ўчиришни таклиф қилиш",
    "bad_name": "⚠️ Ном жуда қисқа ёки узун (3 дан 200 белгигача). Яна ёзинг.",
    "sug_kind": "Нимани таклиф қилмоқчисиз?", "sug_add": "➕ Муассаса қўшиш", "sug_del": "➖ Муассасани ўчириш", "sug_skip": "⏭ Ўтказиб юбориш",
    "sug_add_name": "Қўшиш керак бўлган <b>муассаса номини</b> (расмий номи билан) ва билсангиз, туманини ёзинг.",
    "sug_del_pick": "Ўчириш керак бўлган муассасани танланг:",
    "sug_del_reason": "«{name}» муассасасини <b>нима учун</b> ўчириш кераклигини ёзинг ёки «Ўтказиб юбориш»ни босинг.",
    "sug_sent": "✅ Раҳмат! Таклиф администраторга юборилди: у «Ҳудудлар» бўлимида кўринади.",
    "sug_exists": "Бундай муассаса вилоят рўйхатида бор.", "sug_dup": "Бундай таклиф аллақачон юборилган ва қарорни кутмоқда.",
    "sug_limit": "⚠️ Бир кунда {n} тадан ортиқ таклиф юбориб бўлмайди. Администраторга мурожаат қилинг.",
})

T["ru"].update({
    "pick_date": "📅 <b>За какую дату</b> отправляете сводку?\nНажмите кнопку «Сегодня» или напишите дату, например <b>15.11</b> или <b>14.11.2026</b>.",
    "today_btn": "📅 Сегодня, {d}", "today_btn_sent": "✏️ Сегодня, {d} (уже отправлена)", "ask_date": "Напишите дату: <b>15.11</b> или <b>14.11.2026</b>.",
    "form_head": "📝 <b>{fac}</b> · {date}\n\n<b>Вопрос {i} из {n}</b>  {bar}\n\n<b>{name}</b>", "form_hint": "Введите число (0 или больше).{old}",
    "q_howto": "Напишите число цифрами, например 25. Если таких нет, напишите 0.", "q_placeholder": "Число, например 25 (0, если нет)", "q_limit": "Не больше <b>{v}</b> (вопрос {n})", "q_old": "Текущее значение: <b>{old}</b>",
    "q_over": "⚠️ Число не может быть больше <b>{v}</b>: столько вы указали в вопросе {n}. Введите число не больше {v}.",
    "sec_beds": "🛏 <b>Коечный фонд</b>\n", "sec_flow": "📥 <b>Обращения и госпитализация</b>\n", "sec_occ": "😷 <b>Занятые койки</b>\n", "sec_sev": "🚨 <b>Тяжёлые пациенты</b>\n",
    "exists_edit": "✏️ Сводка за <b>{date}</b> уже отправлена (версия {ver}). Введите новые значения — кнопка «↩️ Оставить» сохраняет прежнее. Перед сохранением покажу, что изменилось, и попрошу подтвердить.",
    "bad_number": "⚠️ Нужно целое число цифрами, 0 или больше. Попробуйте ещё раз.",
})
T["uz"].update({
    "pick_date": "📅 Маълумотни <b>қайси санага</b> юборасиз?\n«Бугун» тугмасини босинг ёки санани ёзинг, масалан <b>15.11</b> ёки <b>14.11.2026</b>.",
    "today_btn": "📅 Бугун, {d}", "today_btn_sent": "✏️ Бугун, {d} (юборилган)", "ask_date": "Санани ёзинг: <b>15.11</b> ёки <b>14.11.2026</b>.",
    "form_head": "📝 <b>{fac}</b> · {date}\n\n<b>{i}-savol / {n}</b>  {bar}\n\n<b>{name}</b>", "form_hint": "Son kiriting (0 yoki undan ko‘p).{old}",
    "q_howto": "Sonni raqamlar bilan yozing, masalan 25. Agar bunday bemor bo‘lmasa, 0 yozing.", "q_placeholder": "Son, masalan 25 (yo‘q bo‘lsa 0)", "q_limit": "Ko‘pi bilan <b>{v}</b> ({n}-savol)", "q_old": "Hozirgi qiymat: <b>{old}</b>",
    "q_over": "⚠️ Son <b>{v}</b> dan oshmasligi kerak: {n}-savolda shuncha ko‘rsatdingiz. {v} dan oshmaydigan son kiriting.",
    "sec_beds": "🛏 <b>O‘rinlar fondi</b>\n", "sec_flow": "📥 <b>Murojaatlar va yotqizish</b>\n", "sec_occ": "😷 <b>Band o‘rinlar</b>\n", "sec_sev": "🚨 <b>Og‘ir ahvoldagi bemorlar</b>\n",
    "exists_edit": "✏️ <b>{date}</b> санаси учун маълумот юборилган (версия {ver}). Янги қийматларни киритинг — «↩️ Қолдириш» олдингисини сақлайди. Сақлашдан олдин ўзгаришларни кўрсатаман.",
    "bad_number": "⚠️ Raqamlar bilan butun son kerak, 0 yoki undan ko‘p. Yana urinib ko‘ring.",
})


def t(lang: str, key: str, **kw) -> str:
    s = T.get(lang, T["ru"]).get(key) or T["ru"][key]
    if lang == "uz" and key != "m_lang":          # the language button stays «Til / Язык» in both languages, so that a Russian speaker can always find it
        s = lat(s)           # Uzbek is written in Latin (the script of the questionnaire); the template is converted, the names inserted into it stay as they are
    return s.format(**kw) if kw else s


T["ru"].update({
    "mr_in": "💬 <b>Ответ Министерства здравоохранения</b>\n\n{text}\n\n<i>На ваше сообщение: «{quote}»</i>", "mr_btn": "↩️ Ответить", "mr_ask": "✍️ Напишите ответ Министерству (до 1000 знаков).\n🔒 Он будет добавлен к вашему диалогу, его увидит только Министерство.", "mr_sent": "✅ Ответ передан в Министерство здравоохранения.",
    "note_q": "📝 <b>{fac}</b> · {date}\n\n<b>Вопрос {i} из {n}</b>  {bar}\n\n💬 <b>Сообщение для Министерства здравоохранения</b> (необязательно)\nЕсли хотите, напишите проблему, просьбу или замечание.\n\n🔒 Сообщение конфиденциально: его увидит только Министерство здравоохранения.",
    "note_skip": "⏭ Без сообщения, продолжить", "note_ph": "Ваше сообщение (до 1000 знаков)", "note_now": "Сейчас записано: «{text}»", "note_long": "⚠️ Сообщение слишком длинное: {now} знаков, допускается до {n}. Сократите его.",
    "pv_note": "\n🔒 💬 Сообщение для Министерства: «{text}»", "pv_nonote": "\n💬 Сообщение для Министерства: нет", "note_btn": "💬 Сообщение для Министерства", "note_sent": "🔒 Ваше сообщение передано в Министерство здравоохранения конфиденциально.",
    "st_title": "📊 <b>Статус отчётности</b>", "st_region": "━━━━━━━━━━━━━━\n🌍 <b>{name}</b>  ·  учреждений: {n}", "st_day": "📅 <b>{date}</b>{rel}\n{bar}  <b>{n}/{total}</b> сдали",
    "st_missing": "❌ <b>Не сдали ({n}):</b>", "st_overdue": "⏰ срок прошёл", "st_returned": "↩️ <b>Возвращены на исправление ({n}):</b>", "st_all_ok": "🎉 Все учреждения сдали",
    "st_done": "✅ <b>Сдали за {date} ({n})</b> — нажмите, чтобы раскрыть", "st_mine": "━━━━━━━━━━━━━━\n🏥 <b>Мои учреждения</b>", "rel_today": "сегодня", "rel_yday": "вчера",
    "preapproved": "✅ Вам уже открыт доступ: <b>{where}</b>.\nНажмите «Отправить сводку», запрос не нужен.",
    "m_dl": "📥 Скачать сводку", "dl_pick": "Что скачать?", "dl_region": "📍 Регион: {name}", "dl_fac": "🏥 {name}",
    "dl_date": "📅 <b>За какую дату</b> скачать сводку ({scope})?\nНажмите «Сегодня» или напишите дату, например <b>15.11</b> или <b>14.11.2026</b>.",
    "dl_today": "📅 Сегодня, {d}", "dl_fmt": "<b>{scope}</b>, {date}\nВ каком виде прислать?", "dl_none": "За <b>{date}</b> по «{scope}» сводок ещё нет: нечего скачивать.",
    "dl_caption": "📥 Сводка: <b>{scope}</b>\nДата: {date}\nОтправлено учреждений: {n}", "dl_fail": "⚠️ Не удалось отправить файл: {why}", "dl_wait": "⏳ Готовлю файл…",
})
T["uz"].update({
    "mr_in": "💬 <b>Sog‘liqni saqlash vazirligining javobi</b>\n\n{text}\n\n<i>Sizning xabaringizga: «{quote}»</i>", "mr_btn": "↩️ Javob berish", "mr_ask": "✍️ Vazirlikka javobingizni yozing (1000 belgigacha).\n🔒 U suhbatingizga qo‘shiladi, uni faqat Vazirlik ko‘radi.", "mr_sent": "✅ Javobingiz Sog‘liqni saqlash vazirligiga yuborildi.",
    "note_q": "📝 <b>{fac}</b> · {date}\n\n<b>{i}-savol / {n}</b>  {bar}\n\n💬 <b>Sog‘liqni saqlash vazirligiga xabar</b> (ixtiyoriy)\nXohlasangiz, muammo, iltimos yoki izohingizni yozing.\n\n🔒 Xabar maxfiy: uni faqat Sog‘liqni saqlash vazirligi ko‘radi.",
    "note_skip": "⏭ Xabarsiz davom etish", "note_ph": "Xabaringiz (1000 belgigacha)", "note_now": "Hozir yozilgan: «{text}»", "note_long": "⚠️ Xabar juda uzun: {now} belgi, ruxsat etilgani {n} gacha. Qisqartiring.",
    "pv_note": "\n🔒 💬 Vazirlikka xabar: «{text}»", "pv_nonote": "\n💬 Vazirlikka xabar: yo‘q", "note_btn": "💬 Vazirlikka xabar", "note_sent": "🔒 Xabaringiz Sog‘liqni saqlash vazirligiga maxfiy tarzda yuborildi.",
    "st_title": "📊 <b>Hisobot holati</b>", "st_region": "━━━━━━━━━━━━━━\n🌍 <b>{name}</b>  ·  muassasalar: {n}", "st_day": "📅 <b>{date}</b>{rel}\n{bar}  <b>{n}/{total}</b> topshirgan",
    "st_missing": "❌ <b>Topshirmaganlar ({n}):</b>", "st_overdue": "⏰ muddat o‘tgan", "st_returned": "↩️ <b>Tuzatish uchun qaytarilgan ({n}):</b>", "st_all_ok": "🎉 Barcha muassasalar topshirgan",
    "st_done": "✅ <b>{date} uchun topshirganlar ({n})</b> — ochish uchun bosing", "st_mine": "━━━━━━━━━━━━━━\n🏥 <b>Mening muassasalarim</b>", "rel_today": "bugun", "rel_yday": "kecha",
    "preapproved": "✅ Sizga allaqachon ruxsat berilgan: <b>{where}</b>.\n«Kundalik ma’lumot yuborish» tugmasini bosing, so‘rov yuborish shart emas.",
    "m_dl": "📥 Маълумотни юклаб олиш", "dl_pick": "Нимани юклаб оламиз?", "dl_region": "📍 Вилоят: {name}", "dl_fac": "🏥 {name}",
    "dl_date": "📅 Маълумотни <b>қайси санага</b> юклаб оламиз ({scope})?\n«Бугун» тугмасини босинг ёки санани ёзинг, масалан <b>15.11</b> ёки <b>14.11.2026</b>.",
    "dl_today": "📅 Бугун, {d}", "dl_fmt": "<b>{scope}</b>, {date}\nҚандай кўринишда юборай?", "dl_none": "<b>{date}</b> санаси учун «{scope}» бўйича маълумот ҳали йўқ.",
    "dl_caption": "📥 Маълумот: <b>{scope}</b>\nСана: {date}\nЮборган муассасалар: {n}", "dl_fail": "⚠️ Файлни юбориб бўлмади: {why}", "dl_wait": "⏳ Файл тайёрланмоқда…",
})
MENU_KEYS = {"m_dl": "dl", "m_submit": "submit", "m_fac": "fac", "m_status": "status", "m_hist": "hist", "m_req": "req", "m_help": "help", "m_lang": "lang", "m_rights": "rights"}
MENU_TEXT = {txt: a for lang in T for k, a in MENU_KEYS.items() for txt in {T[lang][k], t(lang, k)}}      # the button as it is drawn now, and as it was drawn before
CANCEL_TEXT = {txt for lang in T for txt in {T[lang]["cancel"], t(lang, "cancel")}}


def esc(s) -> str:
    return html.escape(str(s or ""), quote=False)


def nm(row, lang: str, base: str = "name") -> str:
    """The name of a row in the person's language (Uzbek when it exists)."""
    if lang == "uz" and row[f"{base}_uz"]:
        return lat(row[f"{base}_uz"])
    return row[f"{base}_ru"]


_PHONE_UNKNOWN: contextvars.ContextVar = contextvars.ContextVar("phone_unknown", default=False)      # the person who writes now has not sent his phone yet


def main_kb(lang: str, has_access: bool) -> dict:
    """The menu. «Yordam» (help), «Mening muassasalarim» (my facilities) and «Yuborilgan hisobotlar tarixi» (history) are not drawn any more; the commands and the old buttons still work."""
    rows = [[{"text": t(lang, "m_submit")}], [{"text": t(lang, "m_status")}, {"text": t(lang, "m_dl")}], [{"text": t(lang, "m_req")}, {"text": t(lang, "m_lang")}]]
    if not has_access:
        rows = [[{"text": t(lang, "m_req")}], [{"text": t(lang, "m_rights")}, {"text": t(lang, "m_lang")}]]
    if _PHONE_UNKNOWN.get():
        rows.insert(0, [{"text": t(lang, "m_phone"), "request_contact": True}])              # Telegram sends the person's own number; it links him to the facilities of the list
    return {"keyboard": rows, "resize_keyboard": True, "is_persistent": True}


def ik(rows) -> dict:
    return {"inline_keyboard": rows}


def btn(text, data) -> dict:
    return {"text": text, "callback_data": data}


# ---------------------------------------------------------------- state
def get_state(c, tg_id: str) -> dict:
    r = c.execute("SELECT * FROM bot_state WHERE tg_id=?", (tg_id,)).fetchone()
    return {"state": r["state"], "data": json.loads(r["data"])} if r else {"state": "", "data": {}}


def set_state(c, tg_id: str, state: str = "", data: dict | None = None) -> None:
    c.execute("INSERT INTO bot_state(tg_id, state, data, updated_at) VALUES (?,?,?,?) ON CONFLICT(tg_id) DO UPDATE SET state=excluded.state, data=excluded.data, updated_at=excluded.updated_at",
              (tg_id, state, json.dumps(data or {}, ensure_ascii=False), now()))


# ---------------------------------------------------------------- entry point
def welcome_preapproved(c, user, chat) -> None:
    """Access that the administrator wrote down by @username in advance is given at the first message: no request is needed."""
    given = people.claim_preapproved(c, user)
    if not given:
        return
    lang = user["lang"]
    names = []
    for g in given:
        row = (c.execute("SELECT name_ru, name_uz FROM facilities WHERE id=?", (g["facility_id"],)).fetchone() if g["facility_id"]
               else c.execute("SELECT name_ru, name_uz FROM regions WHERE id=?", (g["region_id"],)).fetchone())
        if row:
            names.append(esc(nm(row, lang)))
    tg.send(chat, t(lang, "preapproved", where=", ".join(names)), main_kb(lang, True))


def handle_contact(msg: dict) -> None:
    """The person pressed «Send my phone number»: Telegram sends his own contact (user_id is his). That phone is compared with the phones of the responsible people of the
    facilities, and he becomes responsible for those. A contact of somebody else (forwarded, typed by hand) proves nothing and is refused."""
    frm, contact, chat = msg.get("from") or {}, msg.get("contact") or {}, (msg.get("chat") or {})
    with tx() as c:
        user = people.touch(c, frm, all_settings(c)["default_lang"])
        lang = user["lang"]
        if not user["active"]:
            return tg.send(chat["id"], t(lang, "stopped"))
        if not contact.get("user_id") or str(contact["user_id"]) != str(frm.get("id")):
            _PHONE_UNKNOWN.set(not user["phone"])
            return tg.send(chat["id"], t(lang, "bad_contact"), main_kb(lang, reports.has_access(c, user["tg_id"])))
        num = people.save_verified_phone(c, user["tg_id"], str(contact.get("phone_number") or ""))
        _PHONE_UNKNOWN.set(not num)
        linked = people.link_phone(c, user["tg_id"]) if num else []
        has = reports.has_access(c, user["tg_id"])
        if linked:
            where = ", ".join(esc(nm(x, lang)) for x in linked)
            return tg.send(chat["id"], t(lang, "phone_linked", where=where), main_kb(lang, has))
        tg.send(chat["id"], t(lang, "phone_again" if has else "phone_none"), main_kb(lang, has))


def handle_update(u: dict) -> None:
    if u.get("callback_query"):
        return handle_callback(u["callback_query"])
    msg = u.get("message") or {}
    chat = msg.get("chat") or {}
    if chat.get("type") == "private" and msg.get("contact"):
        return handle_contact(msg)
    if chat.get("type") != "private" or not msg.get("text"):
        return
    frm = msg.get("from") or {}
    text = msg["text"].strip()
    with tx() as c:
        user = people.touch(c, frm, all_settings(c)["default_lang"])
        lang = user["lang"]
        _PHONE_UNKNOWN.set(not user["phone"])
        if not user["active"]:
            tg.send(chat["id"], t(lang, "stopped"))
            return
        welcome_preapproved(c, user, chat["id"])
        has = reports.has_access(c, user["tg_id"])
        st = get_state(c, user["tg_id"])
        cmd = text.split()[0].split("@")[0].lower()
        action = MENU_TEXT.get(text) or {"/start": "start", "/help": "help", "/status": "status", "/cancel": "cancel", "/submit": "submit", "/lang": "lang"}.get(cmd)
        if text in CANCEL_TEXT or action == "cancel":
            set_state(c, user["tg_id"])
            tg.send(chat["id"], t(lang, "cancelled"), main_kb(lang, has))
            return
        if action:
            set_state(c, user["tg_id"])
            return do_action(c, user, chat["id"], action, has)
        if st["state"] == "mreply":
            return mreply_input(c, user, chat["id"], st, text, has)
        if st["state"] in ("form", "edit_field", "note"):
            return form_input(c, user, chat["id"], st, text, has)
        if st["state"] in ("pick_district", "pick_facility", "pick_date_text", "pick_region_fac", "suggest_add", "suggest_reason", "dl_date"):
            return pick_text(c, user, chat["id"], st, text, has)
        tg.send(chat["id"], t(lang, "pick"), main_kb(lang, has))


def do_action(c, user, chat, action: str, has: bool) -> None:
    lang, tid = user["lang"], user["tg_id"]
    if action == "start":
        name = " ".join(x for x in (user["first_name"], user["last_name"]) if x) or user["username"] or tid
        tg.send(chat, t(lang, "hello", name=esc(name)) + "\n\n" + (t(lang, "pick") if has else t(lang, "no_access")), main_kb(lang, has))
    elif action == "help":
        tg.send(chat, t(lang, "help"), main_kb(lang, has))
    elif action == "lang":
        new = "uz" if lang == "ru" else "ru"
        c.execute("UPDATE tg_users SET lang=? WHERE tg_id=?", (new, tid))
        tg.send(chat, t(new, "lang_set"), main_kb(new, has))
    elif action in ("fac", "rights"):
        show_rights(c, user, chat, has)
    elif action == "req":
        regions = c.execute("SELECT id, name_ru, name_uz FROM regions WHERE active=1 ORDER BY sort").fetchall()
        rows = [[btn(nm(r, lang), f"rq:r:{r['id']}")] for r in regions]
        tg.send(chat, t(lang, "pick_region"), ik(rows))
    elif action == "status":
        show_status(c, user, chat, has)
    elif action == "hist":
        show_history(c, user, chat, has)
    elif action == "submit":
        begin_submit(c, user, chat, has)
    elif action == "dl":
        start_download(c, user, chat, has)


def show_rights(c, user, chat, has) -> None:
    lang = user["lang"]
    facs = reports.user_facilities(c, user["tg_id"])
    lines = [f"• <b>{esc(nm(f, lang))}</b>\n   {esc(nm(f, lang, 'region'))} / {esc(nm(f, lang, 'district'))} ({t(lang, f['kind'])})" for f in facs]
    lines = [f"• <b>{esc(nm(r, lang))}</b>\n   {t(lang, 'rights_region')} ({t(lang, r['kind'])})" for r in reports.user_regions(c, user["tg_id"])] + lines
    pend = c.execute("""SELECT COALESCE(f.name_ru, r.name_ru) AS name_ru, COALESCE(f.name_uz, r.name_uz) AS name_uz FROM access_requests q LEFT JOIN facilities f ON f.id=q.facility_id
                        LEFT JOIN regions r ON r.id=q.region_id WHERE q.tg_id=? AND q.status='pending'""", (user["tg_id"],)).fetchall()
    text = t(lang, "rights") + "\n\n" + ("\n".join(lines) if lines else t(lang, "rights_none"))
    if pend:
        text += t(lang, "rights_pending") + "\n" + "\n".join("• " + esc(nm(p, lang)) for p in pend)
    tg.send(chat, text, main_kb(lang, has))


def _bar(done: int, total: int, width: int = 10) -> str:
    k = round(width * done / total) if total else 0
    return "▰" * k + "▱" * (width - k)


def _chunks(blocks: list[str], limit: int = 3800) -> list[str]:
    """Telegram takes up to 4096 characters per message: blocks are packed whole, a block that is longer is cut by lines."""
    out, cur = [], ""
    for blk in blocks:
        parts = [blk]
        if len(blk) > limit:
            parts, cur_p = [], ""
            for line in blk.split("\n"):
                if len(cur_p) + len(line) + 1 > limit:
                    parts.append(cur_p); cur_p = ""
                cur_p += ("\n" if cur_p else "") + line
            parts.append(cur_p)
        for part in parts:
            if cur and len(cur) + len(part) + 2 > limit:
                out.append(cur); cur = ""
            cur += ("\n\n" if cur else "") + part
    if cur:
        out.append(cur)
    return out


def status_blocks(c, user, lang: str) -> list[str]:
    """The reporting status as blocks of text: for every region of the person and every day, who has NOT sent (numbered, always shown), who has sent (folded),
    with a progress bar; for single facilities, the day-by-day status."""
    st = all_settings(c)
    facs = reports.user_facilities(c, user["tg_id"])
    regs = reports.user_regions(c, user["tg_id"])
    dates = reports.allowed_dates(st)
    ref = dates[0]
    rel = {0: t(lang, "rel_today"), 1: t(lang, "rel_yday")}
    blocks = [t(lang, "st_title")]
    covered = set()
    for rg in regs:
        fl = c.execute("""SELECT f.id, f.name_ru, f.name_uz FROM facilities f JOIN districts d ON d.id=f.district_id WHERE d.region_id=? AND f.active=1 AND d.active=1 ORDER BY f.name_ru""", (rg["id"],)).fetchall()
        covered |= {f["id"] for f in fl}
        blocks.append(t(lang, "st_region", name=esc(nm(rg, lang)), n=len(fl)))
        for d in dates:
            iso = d.isoformat()
            got = {r["facility_id"]: r for r in c.execute("SELECT rep.facility_id, rep.status, rep.submitted_at, rep.return_reason FROM reports rep JOIN facilities f ON f.id=rep.facility_id JOIN districts dd ON dd.id=f.district_id WHERE dd.region_id=? AND rep.report_date=?", (rg["id"], iso))}
            missing = [f for f in fl if f["id"] not in got]
            returned = [f for f in fl if f["id"] in got and got[f["id"]]["status"] == "returned"]
            done = [f for f in fl if f["id"] in got and got[f["id"]]["status"] != "returned"]
            head = t(lang, "st_day", date=d.strftime("%d.%m"), rel=(" · " + rel[(ref - d).days]) if (ref - d).days in rel else "", bar=_bar(len(done), len(fl)), n=len(done), total=len(fl))
            lines = [head]
            over = now_dt() > reports.deadline(st, d)
            if missing:
                lines.append(t(lang, "st_missing", n=len(missing)) + (" " + t(lang, "st_overdue") if over else ""))
                lines += [f"{k}. {esc(nm(f, lang))}" for k, f in enumerate(missing, 1)]
            if returned:
                lines.append(t(lang, "st_returned", n=len(returned)))
                lines += [f"• {esc(nm(f, lang))}" for f in returned]
            if not missing and not returned:
                lines.append(t(lang, "st_all_ok"))
            elif not done:
                pass
            blocks.append("\n".join(lines))
            if done:
                blocks.append(t(lang, "st_done", n=len(done), date=d.strftime("%d.%m")) + "\n<blockquote expandable>" + "\n".join(f"• {esc(nm(f, lang))} · {got[f['id']]['submitted_at'][11:16]}" for f in done) + "</blockquote>")
    own = [f for f in facs if f["id"] not in covered]
    if own:
        blocks.append(t(lang, "st_mine"))
    for f in own:
        lines = [f"🏥 <b>{esc(nm(f, lang))}</b>"]
        for d in dates:
            rep = reports.find(c, f["id"], d.isoformat())
            if rep:
                s_ = t(lang, "st_ret", why=esc(rep["return_reason"])) if rep["status"] == "returned" else t(lang, "st_sent", t=rep["submitted_at"][11:16])
            else:
                s_ = t(lang, "st_over") if now_dt() > reports.deadline(st, d) else t(lang, "st_none")
            lines.append(f"{d.strftime('%d.%m')}{(' · ' + rel[(ref - d).days]) if (ref - d).days in rel else ''} — {s_}")
        blocks.append("\n".join(lines))
    return blocks


def show_status(c, user, chat, has) -> None:
    lang = user["lang"]
    if not reports.user_facilities(c, user["tg_id"]) and not reports.user_regions(c, user["tg_id"]):
        return tg.send(chat, t(lang, "no_access"), main_kb(lang, has))
    msgs = _chunks(status_blocks(c, user, lang))
    for i, m in enumerate(msgs):
        tg.send(chat, m, main_kb(lang, has) if i == len(msgs) - 1 else None)


def show_history(c, user, chat, has) -> None:
    lang = user["lang"]
    rows = c.execute("""SELECT rep.id, rep.report_date, rep.version, rep.status, f.name_ru, f.name_uz FROM reports rep JOIN facilities f ON f.id=rep.facility_id
                        JOIN districts d ON d.id=f.district_id
                        WHERE f.id IN (SELECT facility_id FROM assignments WHERE tg_id=? AND active=1)
                           OR d.region_id IN (SELECT region_id FROM region_access WHERE tg_id=? AND active=1)
                        ORDER BY rep.report_date DESC, rep.id DESC LIMIT 10""", (user["tg_id"], user["tg_id"])).fetchall()
    if not rows:
        return tg.send(chat, t(lang, "hist_none"), main_kb(lang, has))
    kb = [[btn(t(lang, "hist_item", date=r["report_date"][5:].replace("-", "."), fac=nm(r, lang)[:28], ver=r["version"], st="↩️" if r["status"] == "returned" else "✅"), f"hi:{r['id']}")] for r in rows]
    tg.send(chat, t(lang, "hist_head"), ik(kb))


# ---------------------------------------------------------------- the daily report form
def indicator_list(c) -> list:
    return c.execute("SELECT code, name_ru, name_uz, hint_ru, hint_uz FROM indicators WHERE active=1 ORDER BY sort").fetchall()


def begin_submit(c, user, chat, has) -> None:
    lang = user["lang"]
    facs = reports.user_facilities(c, user["tg_id"])
    regs = reports.user_regions(c, user["tg_id"])
    if not facs and not regs:
        return tg.send(chat, t(lang, "no_access"), main_kb(lang, has))
    if len(facs) == 1 and not regs:
        return pick_facility(c, user, chat, facs[0]["id"])
    if not facs and len(regs) == 1:
        return pick_region_facility(c, user, chat, regs[0]["id"], 0)
    rows = [[btn(t(lang, "my_region", name=nm(r, lang))[:60], f"sr:{r['id']}")] for r in regs] + [[btn(nm(f, lang)[:60], f"sf:{f['id']}")] for f in facs]
    tg.send(chat, t(lang, "pick_fac_submit"), ik(rows))


def region_facilities(c, region_id: int) -> list:
    return c.execute("""SELECT f.id, f.name_ru, f.name_uz FROM facilities f JOIN districts d ON d.id=f.district_id
                        WHERE d.region_id=? AND f.active=1 AND d.active=1 ORDER BY f.name_ru""", (region_id,)).fetchall()


def facility_keyboard(lang: str, region_id: int, items, page: int, per: int = 10) -> dict:
    chunk = items[page * per:(page + 1) * per]
    rows = [[btn(nm(i, lang)[:60], f"sf:{i['id']}")] for i in chunk]
    nav = []
    if page > 0:
        nav.append(btn(t(lang, "prev"), f"sr:{region_id}:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(btn(t(lang, "next"), f"sr:{region_id}:{page + 1}"))
    if nav:
        rows.append(nav)
    rows.append([btn(t(lang, "add_new"), f"sn:{region_id}")])
    return ik(rows)


def pick_region_facility(c, user, chat, region_id: int, page: int) -> None:
    """The person with access to a region sees its facilities (any district) and may add a new one at the bottom."""
    lang = user["lang"]
    if not any(r["id"] == region_id for r in reports.user_regions(c, user["tg_id"])):
        return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому региону"))
    r = c.execute("SELECT * FROM regions WHERE id=?", (region_id,)).fetchone()
    items = region_facilities(c, region_id)
    set_state(c, user["tg_id"], "pick_region_fac", {"rid": region_id})
    text = t(lang, "pick_fac_region" if items else "no_fac_region", region=esc(nm(r, lang)))
    tg.send(chat, text, facility_keyboard(lang, region_id, items, page))


def pick_district_to_submit(c, user, chat, region_id: int, page: int) -> None:
    pick_region_facility(c, user, chat, region_id, page)


SUGGEST_PER_DAY = 10


def suggest_menu(c, user, chat, region_id: int) -> None:
    """The button under the list of facilities: the person proposes to add or to remove a facility. Nothing is changed here: the proposal waits in the section «Территории»
    of the site, where the administrators of the region add / remove / refuse."""
    lang = user["lang"]
    if not any(r["id"] == region_id for r in reports.user_regions(c, user["tg_id"])):
        return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому региону"))
    tg.send(chat, t(lang, "sug_kind"), ik([[btn(t(lang, "sug_add"), f"sa:{region_id}:add")], [btn(t(lang, "sug_del"), f"sa:{region_id}:del")]]))


def suggest_delete_list(c, user, chat, region_id: int, page: int) -> None:
    lang = user["lang"]
    items = region_facilities(c, region_id)
    chunk = items[page * 10:(page + 1) * 10]
    rows = [[btn(nm(i, lang)[:60], f"pz:{i['id']}")] for i in chunk]
    nav = ([btn(t(lang, "prev"), f"sy:{region_id}:{page - 1}")] if page > 0 else []) + ([btn(t(lang, "next"), f"sy:{region_id}:{page + 1}")] if (page + 1) * 10 < len(items) else [])
    if nav:
        rows.append(nav)
    tg.send(chat, t(lang, "sug_del_pick") if items else t(lang, "no_fac_region", region=esc(nm(c.execute("SELECT * FROM regions WHERE id=?", (region_id,)).fetchone(), lang))), ik(rows) if rows else None)


def suggest_save(c, user, chat, region_id: int, kind: str, name: str, comment: str = "", facility_id=None) -> None:
    """One proposal of a person; at most SUGGEST_PER_DAY a day, the same open one is not repeated."""
    from . import xlsx_import
    lang = user["lang"]
    if not any(r["id"] == region_id for r in reports.user_regions(c, user["tg_id"])):
        return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому региону"))
    name = " ".join(name.split())
    comment = " ".join(comment.split())[:500]
    if not 3 <= len(name) <= 200 or name.isdigit():
        return tg.send(chat, t(lang, "bad_name"))
    if kind == "add" and any(xlsx_import.fold(f["name_ru"]) == xlsx_import.fold(name) or xlsx_import.fold(f["name_uz"] or "") == xlsx_import.fold(name) for f in region_facilities(c, region_id)):
        return tg.send(chat, t(lang, "sug_exists"))
    if c.execute("SELECT COUNT(*) FROM facility_proposals WHERE tg_id=? AND created_at >= ?", (user["tg_id"], today().isoformat())).fetchone()[0] >= SUGGEST_PER_DAY:
        return tg.send(chat, t(lang, "sug_limit", n=SUGGEST_PER_DAY))
    if any(xlsx_import.fold(x["name"]) == xlsx_import.fold(name) for x in c.execute("SELECT name FROM facility_proposals WHERE status='new' AND region_id=? AND kind=? AND (facility_id IS ?)", (region_id, kind, facility_id))):
        return tg.send(chat, t(lang, "sug_dup"))
    c.execute("INSERT INTO facility_proposals(region_id, kind, name, facility_id, comment, tg_id, created_at) VALUES (?,?,?,?,?,?,?)", (region_id, kind, name, facility_id, comment, user["tg_id"], now()))
    set_state(c, user["tg_id"])
    tg.send(chat, t(lang, "sug_sent"), main_kb(lang, True))
    notify_admins_new_proposal(c, user, region_id, kind, name, comment)


def notify_admins_new_proposal(c, user, region_id: int, kind: str, name: str, comment: str) -> None:
    """The people who may manage the territories of that region (the super administrators and the administrators with the section «Территории» of that region)."""
    r = c.execute("SELECT name_ru FROM regions WHERE id=?", (region_id,)).fetchone()
    who = " ".join(x for x in (user["first_name"], user["last_name"]) if x) or user["username"] or user["tg_id"]
    text = (f"📝 <b>Предложение: {'добавить' if kind == 'add' else 'удалить'} учреждение</b>\n{esc(r['name_ru'])} / <b>{esc(name)}</b>\n" + (f"Комментарий: {esc(comment)}\n" if comment else "")
            + f"От: {esc(who)} (Telegram ID {user['tg_id']}). Решите в разделе «Территории» на сайте.")
    for s in c.execute("SELECT * FROM staff WHERE active=1 AND tg_id != '' AND (role='super_admin' OR (role='admin' AND can_manage_territories=1))").fetchall():
        if s["role"] == "admin" and not c.execute("SELECT 1 FROM staff_scope WHERE staff_id=? AND region_id=?", (s["id"], region_id)).fetchone():
            continue
        tg.send(s["tg_id"], text)


def pick_facility_to_submit(c, user, chat, district_id: int, page: int) -> None:
    lang = user["lang"]
    d = c.execute("SELECT * FROM districts WHERE id=? AND active=1", (district_id,)).fetchone()
    if not d or not any(r["id"] == d["region_id"] for r in reports.user_regions(c, user["tg_id"])):
        return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому району"))
    fs = c.execute("SELECT id, name_ru, name_uz FROM facilities WHERE district_id=? AND active=1 ORDER BY name_ru", (district_id,)).fetchall()
    if not fs:
        return tg.send(chat, t(lang, "no_facilities", district=esc(nm(d, lang))))
    set_state(c, user["tg_id"], "pick_facility", {"did": district_id})
    if len(fs) == 1:
        return pick_facility(c, user, chat, fs[0]["id"])
    paged(chat, lang, t(lang, "pick_facility", district=esc(nm(d, lang))), fs, "sf:", page, f"sg:{district_id}")


def fold(x: str) -> str:
    return " ".join(str(x).lower().replace("ё", "е").replace("ў", "у").replace("қ", "к").replace("ғ", "г").replace("ҳ", "х").split())


def find_named(rows, q: str) -> list:
    q = fold(q)
    exact = [r for r in rows if q in (fold(r["name_ru"]), fold(r["name_uz"] or ""))]
    return exact or [r for r in rows if q and (q in fold(r["name_ru"]) or q in fold(r["name_uz"] or ""))]


def parse_user_date(text: str):
    m = re.fullmatch(r"\s*(\d{1,2})[.\-/ ](\d{1,2})(?:[.\-/ ](\d{2}|\d{4}))?\s*", text) or None
    if m:
        dd, mm, yy = int(m.group(1)), int(m.group(2)), m.group(3)
        yy = today().year if not yy else (2000 + int(yy) if len(yy) == 2 else int(yy))
    else:
        m = re.fullmatch(r"\s*(\d{4})-(\d{2})-(\d{2})\s*", text)
        if not m:
            return None
        yy, mm, dd = int(m.group(1)), int(m.group(2)), int(m.group(3))
    try:
        return date(yy, mm, dd)
    except ValueError:
        return None


def scope_of(c, user, scope: str):
    """(pseudo-user for the export, filters, title) of a download scope 'r<region>' / 'f<facility>' the person really has access to; None otherwise."""
    kind, ident = scope[:1], scope[1:]
    if not ident.isdigit():
        return None
    ident = int(ident)
    if kind == "r":
        r = next((x for x in reports.user_regions(c, user["tg_id"]) if x["id"] == ident), None)
        if not r:
            return None
        return {"id": 0, "role": "viewer", "regions": [ident], "name": "Telegram"}, {"region_id": ident}, nm(r, user["lang"])
    if kind == "f" and reports.access(c, user["tg_id"], ident):
        f = reports.facility_info(c, ident)
        return {"id": 0, "role": "viewer", "regions": [f["region_id"]], "name": "Telegram"}, {"facility_id": ident}, nm(f, user["lang"])
    return None


def start_download(c, user, chat, has) -> None:
    """'Download the summary': the region(s) of the person (or the facilities they report for), a date, a format."""
    lang = user["lang"]
    regs, facs = reports.user_regions(c, user["tg_id"]), reports.user_facilities(c, user["tg_id"])
    scopes = [(f"r{r['id']}", t(lang, "dl_region", name=nm(r, lang))) for r in regs] + [(f"f{f['id']}", t(lang, "dl_fac", name=nm(f, lang))) for f in facs[:8]]
    if not scopes:
        return tg.send(chat, t(lang, "no_access"), main_kb(lang, has))
    if len(scopes) == 1:
        return ask_download_date(c, user, chat, scopes[0][0])
    tg.send(chat, t(lang, "dl_pick"), ik([[btn(label[:60], f"dr:{sc}")] for sc, label in scopes]))


def ask_download_date(c, user, chat, scope: str) -> None:
    lang = user["lang"]
    sc = scope_of(c, user, scope)
    if not sc:
        return tg.send(chat, t(lang, "fail", msg="Нет доступа"))
    set_state(c, user["tg_id"], "dl_date", {"scope": scope})
    tg.send(chat, t(lang, "dl_date", scope=esc(sc[2])), ik([[btn(t(lang, "dl_today", d=today().strftime("%d.%m")), f"dd:{scope}:{today().isoformat()}")]]))


def download_format(c, user, chat, scope: str, d: str) -> None:
    lang = user["lang"]
    sc = scope_of(c, user, scope)
    if not sc:
        return tg.send(chat, t(lang, "fail", msg="Нет доступа"))
    set_state(c, user["tg_id"])
    tg.send(chat, t(lang, "dl_fmt", scope=esc(sc[2]), date=d), ik([[btn("📊 Excel", f"dx:{scope}:{d}:xlsx"), btn("📄 PDF", f"dx:{scope}:{d}:pdf")]]))


def deliver_download(c, user, chat, scope: str, d: str, fmt: str) -> None:
    from . import exports, stats
    lang = user["lang"]
    sc = scope_of(c, user, scope)           # the right is checked again here: a forged button gets nothing
    if not sc or fmt not in ("xlsx", "pdf"):
        return tg.send(chat, t(lang, "fail", msg="Нет доступа"))
    pseudo, flt, title = sc
    try:
        dd = date.fromisoformat(d)
    except ValueError:
        return tg.send(chat, t(lang, "bad_date"))
    if dd > today():
        return tg.send(chat, t(lang, "date_future"))
    n = stats.kpis(c, pseudo, d, d, **flt)["reported"]
    if not n:
        return tg.send(chat, t(lang, "dl_none", date=d, scope=esc(title)))
    tg.send(chat, t(lang, "dl_wait"))
    data = exports.xlsx(c, pseudo, d, d, kind="daily", lang=lang, **flt) if fmt == "xlsx" else exports.pdf(c, pseudo, d, d, kind="daily", lang=lang, **flt)
    ok, err = tg.send_document(chat, data, exports.filename(lang, d, d, fmt), t(lang, "dl_caption", scope=esc(title), date=d, n=n))
    if not ok:
        tg.send(chat, t(lang, "dl_fail", why=esc(err)))
    else:
        from .db import audit
        audit(c, "export.bot", "export", fmt, {"scope": scope, "date": d}, actor="telegram " + user["tg_id"])


def pick_text(c, user, chat, st: dict, text: str, has: bool) -> None:
    """A name typed instead of pressing a button: a district, a facility or a date."""
    lang, tid, data = user["lang"], user["tg_id"], st["data"]
    if st["state"] == "dl_date":
        word = fold(text)
        d = today() if word in ("сегодня", "бугун") else today() - timedelta(days=1) if word in ("вчера", "кеча") else parse_user_date(text)
        if not d:
            return tg.send(chat, t(lang, "bad_date"))
        if d > today():
            return tg.send(chat, t(lang, "date_future"))
        return download_format(c, user, chat, data["scope"], d.isoformat())
    if st["state"] == "pick_date_text":
        word = fold(text)
        d = today() if word in ("сегодня", "бугун") else today() - timedelta(days=1) if word in ("вчера", "кеча") else parse_user_date(text)
        if not d:
            return tg.send(chat, t(lang, "bad_date"))
        if d > today():
            return tg.send(chat, t(lang, "date_future"))
        return pick_date(c, user, chat, data["fid"], d.isoformat())
    if st["state"] == "suggest_add":
        return suggest_save(c, user, chat, data["rid"], "add", text)
    if st["state"] == "suggest_reason":
        skip = text == t(lang, "sug_skip")
        return suggest_save(c, user, chat, data["rid"], "remove", data["name"], "" if skip else text, data["fid"])
    if st["state"] == "pick_region_fac":
        found = find_named(region_facilities(c, data["rid"]), text)
        if not found:
            return tg.send(chat, t(lang, "bad_find", q=esc(text[:40])), facility_keyboard(lang, data["rid"], region_facilities(c, data["rid"]), 0))
        if len(found) == 1:
            return pick_facility(c, user, chat, found[0]["id"])
        return tg.send(chat, t(lang, "many_found", n=len(found)), ik([[btn(nm(r, lang)[:60], f"sf:{r['id']}")] for r in found[:10]]))
    if st["state"] == "pick_district":
        rows = c.execute("SELECT id, name_ru, name_uz FROM districts WHERE region_id=? AND active=1 ORDER BY name_ru", (data["rid"],)).fetchall()
        found, prefix, nxt = find_named(rows, text), "sg:", None
    else:
        rows = c.execute("SELECT id, name_ru, name_uz FROM facilities WHERE district_id=? AND active=1 ORDER BY name_ru", (data["did"],)).fetchall()
        found, prefix = find_named(rows, text), "sf:"
    if not found:
        return tg.send(chat, t(lang, "bad_find", q=esc(text[:40])))
    if len(found) == 1:
        return pick_district_to_facility(c, user, chat, found[0]["id"]) if prefix == "sg:" else pick_facility(c, user, chat, found[0]["id"])
    tg.send(chat, t(lang, "many_found", n=len(found)), ik([[btn(nm(r, lang)[:60], f"{prefix}{r['id']}")] for r in found[:10]]))


def pick_district_to_facility(c, user, chat, district_id: int) -> None:
    pick_facility_to_submit(c, user, chat, district_id, 0)


def pick_facility(c, user, chat, fid: int, message_id=None) -> None:
    lang = user["lang"]
    st = all_settings(c)
    if not reports.access(c, user["tg_id"], fid):
        return tg.send(chat, t(lang, "fail", msg="У вас нет прав отправлять отчёт за это учреждение"))
    f = reports.facility_info(c, fid)
    now_d = today()
    sent_today = reports.find(c, fid, now_d.isoformat()) is not None
    label = t(lang, "today_btn_sent" if sent_today else "today_btn", d=now_d.strftime("%d.%m"))
    set_state(c, user["tg_id"], "pick_date_text", {"fid": fid})        # a typed date is understood too
    tg.send(chat, f"🏥 <b>{esc(nm(f, lang))}</b>\n\n" + t(lang, "pick_date"), ik([[btn(label, f"sd:{fid}:{now_d.isoformat()}")]]))


def pick_date(c, user, chat, fid: int, d: str) -> None:
    lang = user["lang"]
    st = all_settings(c)
    if not reports.access(c, user["tg_id"], fid):
        return tg.send(chat, t(lang, "fail", msg="У вас нет прав отправлять отчёт за это учреждение"))
    rep = reports.find(c, fid, d)
    values = {}
    if rep is None and date.fromisoformat(d) not in reports.allowed_dates(st):
        dates = reports.allowed_dates(st)
        return tg.send(chat, t(lang, "date_range", date=d, from_=dates[-1].strftime("%d.%m.%Y"), to=dates[0].strftime("%d.%m.%Y")), main_kb(lang, True))
    if rep:
        if not reports.user_can_edit(rep, st):
            return tg.send(chat, t(lang, "exists_locked", date=d, sent=rep["submitted_at"][:16]), main_kb(lang, True))
        values = reports.values_of(c, rep["id"])
        note = t(lang, "returned", why=esc(rep["return_reason"])) if rep["status"] == "returned" else t(lang, "exists_edit", date=d, ver=rep["version"])
        tg.send(chat, note)
    codes = [i["code"] for i in indicator_list(c)]
    set_state(c, user["tg_id"], "form", {"fid": fid, "date": d, "codes": codes, "idx": 0, "values": dict(values), "orig": dict(values) if rep else None, "fix": bool(rep)})
    ask(c, user, chat, get_state(c, user["tg_id"])["data"])


# the questions that fall into the same part of the questionnaire, and the answer that limits another one (the rules of the system refuse a larger number anyway;
# here the person is told at once, at the question)
SECTION = {"beds_total": "beds", "beds_flu": "beds", "visits": "flow", "hosp": "flow", "disch": "flow", "beds_occupied": "occ", "occ_pregnant": "occ", "occ_children": "occ",
           "severe": "sev", "extreme": "sev", "extreme_pregnant": "sev", "extreme_children": "sev"}
BOUND = {"beds_flu": "beds_total", "occ_pregnant": "beds_occupied", "occ_children": "beds_occupied", "severe": "visits", "extreme": "visits",
         "extreme_pregnant": "extreme", "extreme_children": "extreme"}


def bound_of(data: dict, code: str):
    """(the limit, the number of the question it was given at) when the answer to the limiting question is already known."""
    b = BOUND.get(code)
    if b and b in data["codes"] and data["values"].get(b) is not None:
        return data["values"][b], data["codes"].index(b) + 1
    return None


def ask(c, user, chat, data: dict) -> None:
    """One question and nothing else: where we are, the question itself, a limit when one applies, the current value when there is one.
    «Write a number» is the placeholder of the input field, not a line of text."""
    lang = user["lang"]
    inds = {i["code"]: i for i in indicator_list(c)}
    i = data["idx"]
    ind = inds[data["codes"][i]]
    f = reports.facility_info(c, data["fid"])
    old = data["values"].get(ind["code"])
    n = len(data["codes"]) + 1                                   # the numbers plus the last, optional message for the Ministry
    bar = "▰" * (i + 1) + "▱" * (n - i - 1)
    text = t(lang, "form_head", fac=esc(nm(f, lang)), date=data["date"], i=i + 1, n=n, bar=bar, name=esc(nm(ind, lang)))
    bd = bound_of(data, ind["code"])
    if bd:
        text += "\n\n" + t(lang, "q_limit", n=bd[1], v=bd[0])
    if old is not None:
        text += ("\n" if bd else "\n\n") + t(lang, "q_old", old=old)
    rows = ([[{"text": f"{t(lang, 'keep')}: {old}"}]] if old is not None else []) + [[{"text": t(lang, "back")}, {"text": t(lang, "cancel")}]]
    tg.send(chat, text, {"keyboard": rows, "resize_keyboard": True, "input_field_placeholder": t(lang, "q_placeholder")})


def form_input(c, user, chat, st: dict, text: str, has: bool) -> None:
    lang, tid, data = user["lang"], user["tg_id"], st["data"]
    if st["state"] == "note" or (st["state"] == "edit_field" and data.get("edit_code") == "__note"):
        return note_input(c, user, chat, st, text)
    if text == t(lang, "back") and st["state"] == "form":
        if data["idx"] > 0:
            data["idx"] -= 1
            set_state(c, tid, "form", data)
            return ask(c, user, chat, data)
        return
    if text == t(lang, "back") and st["state"] == "edit_field":
        return preview(c, user, chat, data)
    code = data["codes"][data["idx"]] if st["state"] == "form" else data["edit_code"]
    s = text.replace(" ", "")
    if text.startswith(t(lang, "keep")) and data["values"].get(code) is not None:
        s = str(data["values"][code])
    if not s.isdigit():
        return tg.send(chat, t(lang, "bad_number"))
    bd = bound_of(data, code)
    if bd and int(s) > bd[0]:
        tg.send(chat, t(lang, "q_over", v=bd[0], n=bd[1]))
        return ask(c, user, chat, data) if st["state"] == "form" else tg.send(chat, t(lang, "q_limit", n=bd[1], v=bd[0]))
    data["values"][code] = int(s)
    if st["state"] == "form":
        data["idx"] += 1
        if data["idx"] < len(data["codes"]):
            set_state(c, tid, "form", data)
            return ask(c, user, chat, data)
        set_state(c, tid, "note", data)                         # the last question: an optional confidential message for the Ministry
        return ask_note(c, user, chat, data)
    set_state(c, tid, "preview", data)
    preview(c, user, chat, data)


NOTE_MAX = 1000


def send_ministry_reply(c, root, text: str) -> tuple[bool, str]:
    """The Ministry's answer to a message of the person, with the button that continues the dialogue."""
    u = c.execute("SELECT lang FROM tg_users WHERE tg_id=?", (root["tg_id"],)).fetchone()
    lang = (u["lang"] if u else None) or "uz"
    quote = esc(root["text"][:120] + ("…" if len(root["text"]) > 120 else ""))
    return tg.send(root["tg_id"], t(lang, "mr_in", text=esc(text), quote=quote), ik([[btn(t(lang, "mr_btn"), f"mr:{root['id']}")]]))


def mreply_input(c, user, chat, st: dict, text: str, has: bool) -> None:
    """The person's answer to the Ministry: it is added to the same dialogue, which the Ministry reads on the site."""
    lang, tid = user["lang"], user["tg_id"]
    root = c.execute("SELECT * FROM ministry_messages WHERE id=? AND tg_id=?", (st["data"].get("thread"), tid)).fetchone()
    if not root:
        set_state(c, tid)
        return tg.send(chat, t(lang, "fail", msg="—"), main_kb(lang, has))
    if len(text) > NOTE_MAX:
        return tg.send(chat, t(lang, "note_long", n=NOTE_MAX, now=len(text)))
    c.execute("INSERT INTO ministry_messages(facility_id, report_date, tg_id, sender, text, created_at, direction, thread_id) VALUES (?,?,?,?,?,?, 'in', ?)",
              (root["facility_id"], root["report_date"], tid, reports.by_tg(user)["name"], text.strip(), now(), root["id"]))
    set_state(c, tid)
    tg.send(chat, t(lang, "mr_sent"), main_kb(lang, has))


def ask_note(c, user, chat, data: dict) -> None:
    lang = user["lang"]
    n = len(data["codes"]) + 1
    f = reports.facility_info(c, data["fid"])
    text = t(lang, "note_q", fac=esc(nm(f, lang)), date=data["date"], i=n, n=n, bar="▰" * n)
    if data.get("note"):
        text += "\n\n" + t(lang, "note_now", text=esc(data["note"][:300]))
    rows = [[{"text": t(lang, "note_skip")}], [{"text": t(lang, "back")}, {"text": t(lang, "cancel")}]]
    tg.send(chat, text, {"keyboard": rows, "resize_keyboard": True, "input_field_placeholder": t(lang, "note_ph")})


def note_input(c, user, chat, st: dict, text: str) -> None:
    """The message for the Ministry: free text (up to 1000 characters) or «skip». In the change flow the same text replaces the old one."""
    lang, tid, data = user["lang"], user["tg_id"], st["data"]
    if text == t(lang, "back"):
        if st["state"] == "edit_field":
            return preview(c, user, chat, data)
        data["idx"] = len(data["codes"]) - 1
        set_state(c, tid, "form", data)
        return ask(c, user, chat, data)
    if text == t(lang, "note_skip"):
        data["note"] = ""
    else:
        if len(text) > NOTE_MAX:
            return tg.send(chat, t(lang, "note_long", n=NOTE_MAX, now=len(text)))
        data["note"] = text
    set_state(c, tid, "preview", data)
    preview(c, user, chat, data)


def preview(c, user, chat, data: dict, message_id=None) -> None:
    lang, tid = user["lang"], user["tg_id"]
    f = reports.facility_info(c, data["fid"])
    inds = indicator_list(c)
    orig = data.get("orig")
    changed = 0
    out = []
    for k, i in enumerate(inds, 1):
        new, old = data["values"].get(i["code"]), (orig or {}).get(i["code"])
        if orig is not None and new != old:
            changed += 1
            out.append(f"✏️ {k}. {esc(nm(i, lang))}: {old if old is not None else '—'} → <b>{new if new is not None else '—'}</b>")
        else:
            out.append(f"{k}. {esc(nm(i, lang))}: <b>{new if new is not None else '—'}</b>")
    out.append(t(lang, "pv_note", text=esc(data["note"][:200] + ("…" if len(data["note"]) > 200 else ""))) if data.get("note") else t(lang, "pv_nonote"))
    res = rules.validate(c, data["values"], lang, data["fid"], data["date"])
    path = f"{esc(nm(f, lang, 'region'))} / {esc(nm(f, lang, 'district'))} / <b>{esc(nm(f, lang))}</b>"
    text = t(lang, "preview_fix" if orig is not None else "preview", path=path, date=data["date"], lines="\n".join(out))
    if orig is not None and not changed:
        text += t(lang, "no_changes")
    if res["errors"]:
        text += t(lang, "errors", items="\n".join("• " + esc(e) for e in res["errors"]))
    if res["warnings"]:
        text += t(lang, "warnings", items="\n".join("• " + esc(w) for w in res["warnings"]))
    rows = []
    if not res["errors"] and (orig is None or changed):
        rows.append([btn(t(lang, "confirm_fix") if orig is not None else (t(lang, "send_anyway") if res["warnings"] else t(lang, "confirm")), "ok")])
    rows.append([btn(t(lang, "change"), "ch")])
    rows.append([btn(t(lang, "cancel"), "no")])
    set_state(c, tid, "preview", data)
    tg.send(chat, text, ik(rows))


def handle_callback(cq: dict) -> None:
    msg = cq.get("message") or {}
    chat = (msg.get("chat") or {}).get("id")
    data = cq.get("data", "")
    with tx() as c:
        user = people.touch(c, cq["from"], all_settings(c)["default_lang"])
        lang = user["lang"]
        _PHONE_UNKNOWN.set(not user["phone"])
        welcome_preapproved(c, user, chat)
        has = reports.has_access(c, user["tg_id"])
        tg.answer(cq["id"])
        if not user["active"]:
            return
        k0 = data.split(":")[0]
        tok = tg.set_edit_target(chat, msg.get("message_id")) if k0 not in KEEP_BUTTONS else None       # the answer goes into the message of the pressed button
        try:
            return _callback_body(c, user, lang, has, chat, msg, data)
        finally:
            if tok is not None:
                tg.reset_edit_target(tok)


# the button under the Ministry's answer stays where it is: the person may come back to it later
KEEP_BUTTONS = {"mr"}


def _callback_body(c, user, lang, has, chat, msg, data) -> None:
    p = data.split(":")
    k = p[0]
    if k == "rq":
        return request_flow(c, user, chat, msg, p)
    if k == "mr":                                                         # «Reply» under the Ministry's answer: the next text goes into the same dialogue
        root = c.execute("SELECT id FROM ministry_messages WHERE id=? AND tg_id=?", (int(p[1]), user["tg_id"])).fetchone() if len(p) > 1 and p[1].isdigit() else None
        if not root:
            return
        set_state(c, user["tg_id"], "mreply", {"thread": root["id"]})
        return tg.send(chat, t(lang, "mr_ask"), {"keyboard": [[{"text": t(lang, "cancel")}]], "resize_keyboard": True, "input_field_placeholder": t(lang, "note_ph")})
    if k == "sf":
        return pick_facility(c, user, chat, int(p[1]))
    if k == "sx":
        if not reports.access(c, user["tg_id"], int(p[1])):
            return tg.send(chat, t(lang, "fail", msg="У вас нет прав отправлять отчёт за это учреждение"))
        set_state(c, user["tg_id"], "pick_date_text", {"fid": int(p[1])})
        return tg.send(chat, t(lang, "ask_date"), {"keyboard": [[{"text": t(lang, "cancel")}]], "resize_keyboard": True})
    if k == "dr":
        return ask_download_date(c, user, chat, p[1])
    if k == "dd":
        return download_format(c, user, chat, p[1], p[2])
    if k == "dx":
        return deliver_download(c, user, chat, p[1], p[2], p[3])
    if k == "sn":
        return suggest_menu(c, user, chat, int(p[1]))
    if k == "sa":
        if not any(r["id"] == int(p[1]) for r in reports.user_regions(c, user["tg_id"])):
            return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому региону"))
        if p[2] == "del":
            return suggest_delete_list(c, user, chat, int(p[1]), 0)
        set_state(c, user["tg_id"], "suggest_add", {"rid": int(p[1])})
        return tg.send(chat, t(lang, "sug_add_name"), {"keyboard": [[{"text": t(lang, "cancel")}]], "resize_keyboard": True})
    if k == "sy":
        if not any(r["id"] == int(p[1]) for r in reports.user_regions(c, user["tg_id"])):
            return tg.send(chat, t(lang, "fail", msg="У вас нет доступа к этому региону"))
        return suggest_delete_list(c, user, chat, int(p[1]), int(p[2]) if len(p) > 2 else 0)
    if k == "pz":
        f = c.execute("SELECT f.id, f.name_ru, f.name_uz, d.region_id FROM facilities f JOIN districts d ON d.id=f.district_id WHERE f.id=? AND f.active=1", (int(p[1]),)).fetchone()
        if not f or not any(r["id"] == f["region_id"] for r in reports.user_regions(c, user["tg_id"])):
            return tg.send(chat, t(lang, "fail", msg="У вас нет прав на это учреждение"))
        set_state(c, user["tg_id"], "suggest_reason", {"rid": f["region_id"], "fid": f["id"], "name": f["name_ru"]})
        return tg.send(chat, t(lang, "sug_del_reason", name=esc(nm(f, lang))), {"keyboard": [[{"text": t(lang, "sug_skip")}], [{"text": t(lang, "cancel")}]], "resize_keyboard": True})
    if k == "sr":
        return pick_region_facility(c, user, chat, int(p[1]), int(p[2]) if len(p) > 2 else 0)
    if k == "sg":
        return pick_facility_to_submit(c, user, chat, int(p[1]), int(p[2]) if len(p) > 2 else 0)
    if k == "sd":
        return pick_date(c, user, chat, int(p[1]), p[2])
    if k == "go" or k == "sub":
        return begin_submit(c, user, chat, has)
    if k == "hi":
        return show_report(c, user, chat, int(p[1]))
    st = get_state(c, user["tg_id"])
    if k in ("ok", "ch", "no", "ef") and st["state"] not in ("preview", "edit_pick", "edit_field"):
        return
    d = st["data"]
    if k == "no":
        set_state(c, user["tg_id"])
        return tg.send(chat, t(lang, "cancelled"), main_kb(lang, has))
    if k == "ch":
        inds = indicator_list(c)
        set_state(c, user["tg_id"], "edit_pick", d)
        return tg.send(chat, t(lang, "pick_field"), ik([[btn(f"{k}. {nm(i, lang)[:44]}: {d['values'].get(i['code'], '—')}", f"ef:{i['code']}")] for k, i in enumerate(inds, 1)] + [[btn(t(lang, "note_btn"), "ef:__note")]]))
    if k == "ef" and p[1] == "__note":
        d["edit_code"] = "__note"
        set_state(c, user["tg_id"], "edit_field", d)
        return ask_note(c, user, chat, d)
    if k == "ef":
        d["edit_code"] = p[1]
        set_state(c, user["tg_id"], "edit_field", d)
        ind = c.execute("SELECT name_ru, name_uz FROM indicators WHERE code=?", (p[1],)).fetchone()
        kb = {"keyboard": [[{"text": t(lang, "back")}, {"text": t(lang, "cancel")}]], "resize_keyboard": True}
        bd = bound_of(d, p[1])
        return tg.send(chat, f"<b>{esc(nm(ind, lang))}</b>\n\n" + (t(lang, "q_limit", n=bd[1], v=bd[0]) + "\n" if bd else "") + t(lang, "q_old", old=d["values"].get(p[1], "—")), {**kb, "input_field_placeholder": t(lang, "q_placeholder")})
    if k == "ok":
        return confirm(c, user, chat, d, has)


def request_flow(c, user, chat, msg, p) -> None:
    """Access is requested for a region; the district is optional (it only tells the administrator where the person works)."""
    lang = user["lang"]
    step = p[1]
    if step in ("r", "d"):
        if step == "d":
            d = c.execute("SELECT * FROM districts WHERE id=? AND active=1", (int(p[2]),)).fetchone()
            if not d:
                return
            return send_request(c, user, chat, d["region_id"], d["id"])
        r = c.execute("SELECT * FROM regions WHERE id=? AND active=1", (int(p[2]),)).fetchone()
        if not r:
            return
        ds = c.execute("SELECT id, name_ru, name_uz FROM districts WHERE region_id=? AND active=1 ORDER BY name_ru", (r["id"],)).fetchall()
        chunk_page = int(p[3]) if len(p) > 3 else 0
        chunk = ds[chunk_page * 10:(chunk_page + 1) * 10]
        rows = [[btn(t(lang, "all_region"), f"rq:g:{r['id']}")]] + [[btn(nm(i, lang)[:60], f"rq:d:{i['id']}")] for i in chunk]
        nav = []
        if chunk_page > 0:
            nav.append(btn(t(lang, "prev"), f"rq:r:{r['id']}:{chunk_page - 1}"))
        if (chunk_page + 1) * 10 < len(ds):
            nav.append(btn(t(lang, "next"), f"rq:r:{r['id']}:{chunk_page + 1}"))
        if nav:
            rows.append(nav)
        return tg.send(chat, t(lang, "pick_district_req", region=esc(nm(r, lang))), ik(rows))
    if step == "g":
        return send_request(c, user, chat, int(p[2]), None)


def send_request(c, user, chat, region_id: int, district_id) -> None:
    lang = user["lang"]
    r = c.execute("SELECT name_ru, name_uz FROM regions WHERE id=?", (region_id,)).fetchone()
    try:
        rid = people.create_request(c, user["tg_id"], region_id, district_id)
    except people.PeopleError as e:
        return tg.send(chat, t(lang, "req_dup", why=esc(e.message)))
    tg.send(chat, t(lang, "req_sent_region", fac=esc(nm(r, lang))))
    notify_admins_about_request(c, rid)


def paged(chat, lang, text, items, prefix, page, self_cb, per=10) -> None:
    chunk = items[page * per:(page + 1) * per]
    rows = [[btn(nm(i, lang)[:60], f"{prefix}{i['id']}")] for i in chunk]
    nav = []
    if page > 0:
        nav.append(btn(t(lang, "prev"), f"{self_cb}:{page - 1}"))
    if (page + 1) * per < len(items):
        nav.append(btn(t(lang, "next"), f"{self_cb}:{page + 1}"))
    if nav:
        rows.append(nav)
    tg.send(chat, text, ik(rows))


def confirm(c, user, chat, d: dict, has: bool) -> None:
    lang = user["lang"]
    f = reports.facility_info(c, d["fid"])
    try:
        out = reports.submit(c, d["fid"], d["date"], d["values"], reports.by_tg(user), lang)
    except reports.ReportError as e:
        set_state(c, user["tg_id"])
        return tg.send(chat, t(lang, "fail", msg=esc(e.message)), main_kb(lang, has))
    set_state(c, user["tg_id"])
    text = t(lang, "saved" if out.get("created") else "saved_fix", fac=esc(nm(f, lang)), date=d["date"], ver=out["version"])
    if out.get("late") and out.get("created"):
        text += t(lang, "saved_late")
    if (d.get("note") or "").strip():                           # the confidential message goes to the Ministry only (a table of its own, read by the super administrator)
        cur = c.execute("INSERT INTO ministry_messages(facility_id, report_date, tg_id, sender, text, created_at, direction) VALUES (?,?,?,?,?,?, 'in')",
                        (d["fid"], d["date"], user["tg_id"], reports.by_tg(user)["name"], d["note"].strip()[:NOTE_MAX], now()))
        c.execute("UPDATE ministry_messages SET thread_id=id WHERE id=?", (cur.lastrowid,))       # the first message is the root of the dialogue
        text += "\n\n" + t(lang, "note_sent")
    tg.send(chat, text, main_kb(lang, True))


def show_report(c, user, chat, rid: int) -> None:
    lang = user["lang"]
    rep = c.execute("SELECT * FROM reports WHERE id=?", (rid,)).fetchone()
    if not rep or not reports.access(c, user["tg_id"], rep["facility_id"]):
        return
    f = reports.facility_info(c, rep["facility_id"])
    vals = reports.values_of(c, rid)
    lines = "\n".join(f"{esc(nm(i, lang))}: <b>{vals.get(i['code'], '—')}</b>" for i in indicator_list(c))
    tg.send(chat, t(lang, "rep", fac=esc(nm(f, lang)), date=rep["report_date"], ver=rep["version"], lines=lines))


# ---------------------------------------------------------------- notifications triggered from the web
def notify_admins_about_request(c, request_id: int) -> None:
    q = c.execute("""SELECT q.*, u.first_name, u.last_name, u.username, r.name_ru AS region, d.name_ru AS district, f.name_ru AS facility
                     FROM access_requests q JOIN tg_users u ON u.tg_id=q.tg_id JOIN regions r ON r.id=q.region_id LEFT JOIN districts d ON d.id=q.district_id LEFT JOIN facilities f ON f.id=q.facility_id WHERE q.id=?""", (request_id,)).fetchone()
    if not q:
        return
    who = " ".join(x for x in (q["first_name"], q["last_name"]) if x) or "—"
    text = (f"🔑 <b>Новый запрос доступа</b>\n{esc(who)}" + (f" (@{esc(q['username'])})" if q["username"] else "") + f", Telegram ID {q['tg_id']}\n"
            f"<b>{esc(q['region'])}</b>" + (f" / {esc(q['district'])}" if q["district"] else "") + (f" / <b>{esc(q['facility'])}</b>" if q["facility"] else " (доступ ко всему региону)") + "\nРассмотрите запрос в разделе «Запросы доступа».")
    for s in c.execute("SELECT * FROM staff WHERE active=1 AND tg_id != '' AND (role='super_admin' OR (role='admin' AND can_manage_users=1))").fetchall():
        if s["role"] == "admin" and not c.execute("SELECT 1 FROM staff_scope WHERE staff_id=? AND region_id=?", (s["id"], q["region_id"])).fetchone():
            continue
        tg.send(s["tg_id"], text)


def notify_decision(tg_id: str, facility_id, approved: bool, note: str = "", region_id=None) -> None:
    c = connect()
    try:
        u = c.execute("SELECT * FROM tg_users WHERE tg_id=?", (tg_id,)).fetchone()
        f = c.execute("SELECT name_ru, name_uz FROM facilities WHERE id=?", (facility_id,)).fetchone() if facility_id else c.execute("SELECT name_ru, name_uz FROM regions WHERE id=?", (region_id,)).fetchone()
        if not u or not f:
            return
        lang = u["lang"]
        has = reports.has_access(c, tg_id)
        suffix = "" if facility_id else "_region"
        text = t(lang, "approved" + suffix, fac=esc(nm(f, lang))) if approved else t(lang, "rejected" + suffix, fac=esc(nm(f, lang)), note=("\n" + esc(note)) if note else "")
        tg.send(tg_id, text, main_kb(lang, has))
    finally:
        c.close()
