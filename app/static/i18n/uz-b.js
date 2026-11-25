// Uzbek (Latin) texts: Russian source text -> Uzbek. See tools/uz-glossary.md for the terms.
// Worker B: forecast, control table, reports (list, card, history, edit dialog, delete dialog).
Object.assign(window.UZ, {
  // ---------- shared small words used by these pages
  "Загрузка…": "Yuklanmoqda…",
  "Дата": "Sana",
  "Регион": "Hudud",
  "Район": "Tuman",
  "Учреждение": "Muassasa",
  "Ответственный": "Mas’ul shaxs",
  "Статус": "Holat",
  "Время": "Vaqt",
  "Все": "Barchasi",
  "Версия": "Versiya",
  "Кто": "Kim tomonidan",
  "Причина": "Sabab",
  "Сохранить": "Saqlash",
  "Отмена": "Bekor qilish",
  "Проверить": "Tekshirish",
  "Готово": "Tayyor",
  "Сохранено": "Saqlandi",
  "поздно": "kechikkan",

  // ---------- forecast
  "Прогноз на 3 и 7 дней": "3 va 7 kunlik prognoz",
  "Это инструмент оперативного планирования, а не эпидемиологический вывод. Метод: {method}. Серая зона — 90% интервал.": "Bu operativ rejalashtirish vositasi bo‘lib, epidemiologik xulosa hisoblanmaydi. Usul: {method}. Kulrang zona — 90% ishonch oralig‘i.",
  "Обращения": "Murojaatlar",
  "Тяжёлые": "Og‘ir",
  "Крайне тяжёлые": "O‘ta og‘ir",
  "Госпитализации": "Yotqizilganlar",
  "Выписки": "Chiqarilganlar",
  "Последнее значение {cur} ({date}). Через 3 дня: <b>{v3}</b> ({l3}–{h3}); через 7 дней: <b>{v7}</b> ({l7}–{h7}). Надёжность: {rel}": "Oxirgi qiymat: {cur} ({date}). 3 kundan keyin: <b>{v3}</b> ({l3}–{h3}); 7 kundan keyin: <b>{v7}</b> ({l7}–{h7}). Ishonchlilik: {rel}",
  "Прогноз загрузки коек": "O‘rinlar bandligi prognozi",
  "Сейчас занято {occ} из {flu} ({date}). Надёжность: {rel}": "Hozir {flu} o‘rindan {occ} tasi band ({date}). Ishonchlilik: {rel}",
  "Занято коек": "Band o‘rinlar",
  "Коек для гриппа и ОРВИ": "Gripp va ORVI uchun o‘rinlar",
  "Занято": "Band",
  "Свободно": "Bo‘sh",
  "Загрузка": "Bandlik",
  "Дефицит": "Tanqislik",
  "Прогноз коек недоступен: нужны данные о госпитализациях, выписках и коечном фонде.": "O‘rinlar prognozi mavjud emas: yotqizilganlar, chiqarilganlar va o‘rinlar fondi bo‘yicha ma’lumotlar kerak.",
  "Предупреждения": "Ogohlantirishlar",
  "Предупреждений нет.": "Ogohlantirishlar yo‘q.",
  // texts of the server shown on the forecast page
  "Линейный тренд (метод наименьших квадратов) по последним дням с данными; значения не ниже нуля": "Ma’lumotlari bor so‘nggi kunlar bo‘yicha chiziqli trend (eng kichik kvadratlar usuli); qiymatlar noldan past emas",
  "Занятые койки сегодня + прогноз госпитализаций − прогноз выписок за каждый следующий день": "Bugungi band o‘rinlar + yotqizilganlar prognozi − keyingi har bir kun uchun chiqarilganlar prognozi",
  "Низкая: данных меньше 5 дней": "Past: ma’lumotlar 5 kundan kam",
  "Низкая: данных недостаточно для прогноза": "Past: prognoz uchun ma’lumot yetarli emas",

  // ---------- control table
  "🔔 Напомнить не сдавшим": "🔔 Topshirmaganlarga eslatish",
  "Срок сдачи: <b>{deadline}</b>. Всего {total}; сдали {sent} (из них исправлено {corrected}); возвращено {returned}; не сдали {notsent}; без ответственного: {noresp}.": "Topshirish muddati: <b>{deadline}</b>. Jami {total}; topshirgan {sent} (shundan tuzatilgan {corrected}); qaytarilgan {returned}; topshirmagan {notsent}; mas’ul shaxssiz: {noresp}.",
  "не назначен": "tayinlanmagan",
  "Сдали": "Topshirganlar",
  "Исправлены": "Tuzatilganlar",
  "Возвращены": "Qaytarilganlar",
  "Не сдали": "Topshirmaganlar",
  "Просрочены": "Muddati o‘tganlar",
  "Без ответственного": "Mas’ul shaxssiz",

  // ---------- reports: the list
  "Отчёты": "Hisobotlar",
  "Отправленные": "Yuborilganlar",
  "Возвращённые": "Qaytarilganlar",
  "Исправленные": "Tuzatilganlar",
  "С опозданием": "Kechikib topshirilganlar",
  "Поиск по учреждению": "Muassasa bo‘yicha qidirish",
  "🗑 Удалить выбранные": "🗑 Tanlanganlarni o‘chirish",
  "🗑 Удалить выбранные ({n})": "🗑 Tanlanganlarni o‘chirish ({n})",
  "+ Внести отчёт": "+ Hisobot kiritish",
  "Найдено: {n}": "Topildi: {n}",
  "Выбрать все": "Barchasini tanlash",

  // ---------- reports: delete dialog
  "🗑 Удалить отчёты": "🗑 Hisobotlarni o‘chirish",
  "Будет удалено отчётов: <b>{n}</b> вместе с историей версий. Это нельзя отменить. В журнале действий останется запись о каждом удалённом отчёте (учреждение, дата, цифры, причина).": "O‘chiriladigan hisobotlar soni: <b>{n}</b>, versiyalar tarixi bilan birga. Bu amalni bekor qilib bo‘lmaydi. Harakatlar jurnalida har bir o‘chirilgan hisobot bo‘yicha yozuv (muassasa, sana, raqamlar, sabab) saqlanib qoladi.",
  "Учреждение снова будет считаться не сдавшим за эту дату, отчёт можно внести заново.": "Muassasa shu sana uchun yana hisobot topshirmagan hisoblanadi, hisobotni qaytadan kiritish mumkin.",
  "Удалить безвозвратно": "Butunlay o‘chirish",
  "Удалено отчётов: {n}": "O‘chirilgan hisobotlar soni: {n}",

  // ---------- reports: the card and the history
  "за {date}": "{date} sanasi uchun",
  "версия {n}": "{n}-versiya",
  "закрыт": "yopilgan",
  "Возвращён: {reason}": "Qaytarilgan: {reason}",
  "Исправить": "Tuzatish",
  "Вернуть на исправление": "Tuzatish uchun qaytarish",
  "Открыть для правок": "Tahrirlash uchun ochish",
  "Закрыть для правок": "Tahrirlash uchun yopish",
  "🗑 Удалить отчёт": "🗑 Hisobotni o‘chirish",
  "Закрыть окно": "Oynani yopish",
  "История версий": "Versiyalar tarixi",
  "Когда": "Qachon",
  "Действие": "Amal",
  "Что изменено": "Nima o‘zgargan",
  "Вернуть": "Tiklash",
  "Причина возврата:": "Qaytarish sababi:",
  "Отчёт возвращён": "Hisobot qaytarildi",
  "Причина восстановления версии {n}:": "{n}-versiyani tiklash sababi:",
  "Версия восстановлена (создана новая)": "Versiya tiklandi (yangisi yaratildi)",

  // ---------- reports: the edit dialog
  "Исправление отчёта": "Hisobotni tuzatish",
  "Внести отчёт": "Hisobot kiritish",
  "Причина изменения (обязательно для журнала)": "O‘zgartirish sababi (jurnal uchun majburiy)",
});

// Messages of the server shown on these pages (the forecast, the alerts, the validation of the figures): patterns [RegExp, replacement].
(function () {
  const rx = s => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const regionOf = v => typeof rname === "function" ? rname(v) : v;
  // a Russian template with {name} placeholders and its Uzbek twin; a placeholder called reg* is a region name, rel* a level of reliability
  const REL = { "низкая": "past", "средняя": "o‘rtacha", "высокая": "yuqori" };
  const add = (ru, uz) => {
    const names = [];
    const re = new RegExp("^" + rx(ru).replace(/\\\{(\w+)\\\}/g, (m, k) => { names.push(k); return "(.+?)"; }) + "$");
    UZP.push([re, (m0, ...g) => uz.replace(/\{(\w+)\}/g, (mm, k) => {
      const v = g[names.indexOf(k)];
      return k.startsWith("reg") ? regionOf(v) : k === "rel" ? (REL[v] || v) : v;
    })]);
  };
  // reliability of the forecast
  add("Высокая: {n} дней данных, тренд устойчив (R² = {r})", "Yuqori: {n} kunlik ma’lumot, trend barqaror (R² = {r})");
  add("Средняя: {n} дней данных, R² = {r}", "O‘rtacha: {n} kunlik ma’lumot, R² = {r}");
  // alerts
  const WHAT = { "обращений": "murojaatlar", "тяжёлых пациентов": "og‘ir ahvoldagi bemorlar", "крайне тяжёлых пациентов": "o‘ta og‘ir ahvoldagi bemorlar", "госпитализаций": "yotqizilganlar" };
  for (const [ru, uz] of Object.entries(WHAT)) {
    add(`Внимание! В регионе «{reg}» за последние 3 дня отмечается увеличение количества ${ru} на {g}% относительно предыдущего сопоставимого периода ({a} → {b}).`, `Diqqat! «{reg}» hududida so‘nggi 3 kun ichida ${uz} soni oldingi taqqoslanadigan davrga nisbatan {g}% ga oshgani qayd etilmoqda ({a} → {b}).`);
    add(`Тревога! В регионе «{reg}» за последние 3 дня отмечается увеличение количества ${ru} на {g}% относительно предыдущего сопоставимого периода ({a} → {b}).`, `Xavf signali! «{reg}» hududida so‘nggi 3 kun ichida ${uz} soni oldingi taqqoslanadigan davrga nisbatan {g}% ga oshgani qayd etilmoqda ({a} → {b}).`);
  }
  add("Критическая загрузка коек: в регионе «{reg}» занято {x}% коек для больных гриппом (на {d}).", "Kritik bandlik: «{reg}» hududida gripp bilan kasallangan bemorlar uchun ajratilgan o‘rinlarning {x}% band ({d} holatiga).");
  add("Повышенная нагрузка: в регионе «{reg}» занято {x}% коек для больных гриппом (на {d}).", "Oshgan yuklama: «{reg}» hududida gripp bilan kasallangan bemorlar uchun ajratilgan o‘rinlarning {x}% band ({d} holatiga).");
  add("Риск нехватки коек: в регионе «{reg}» через 3 дня ожидается потребность {x} коек при {y} выделенных. Надёжность прогноза: {rel}.", "O‘rinlar yetishmasligi xavfi: «{reg}» hududida 3 kundan keyin {x} o‘ringa ehtiyoj kutilmoqda, ajratilgan o‘rinlar soni {y}. Prognoz ishonchliligi: {rel}.");
  add("Предупреждение! В учреждении «{f}» ({reg}) занято {x}% коек, выделенных для госпитализации больных гриппом.", "Ogohlantirish! «{f}» muassasasida ({reg}) gripp bilan kasallangan bemorlarni yotqizish uchun ajratilgan o‘rinlarning {x}% band.");
  add("Нет отчёта за {d} от {n} учреждений региона «{reg}».", "{d} sanasi uchun «{reg}» hududida {n} muassasa hisobot topshirmagan.");
  // validation of the figures (the messages of the rules and of the check of a single figure)
  add("Коек для больных гриппом и ОРВИ ({beds_flu}) больше общего числа коек ({beds_total}).", "Gripp va ORVI uchun ajratilgan o‘rinlar ({beds_flu}) jami o‘rinlardan ({beds_total}) ko‘p.");
  add("Тяжёлых пациентов ({severe}) больше, чем обращений ({visits}).", "Og‘ir bemorlar ({severe}) murojaatlardan ({visits}) ko‘p.");
  add("Крайне тяжёлых пациентов ({extreme}) больше, чем обращений ({visits}).", "O‘ta og‘ir bemorlar ({extreme}) murojaatlardan ({visits}) ko‘p.");
  add("Беременных среди занятых коек ({occ_pregnant}) больше, чем занято коек ({beds_occupied}).", "Band o‘rinlardagi homilador ayollar ({occ_pregnant}) band o‘rinlardan ({beds_occupied}) ko‘p.");
  add("Детей среди занятых коек ({occ_children}) больше, чем занято коек ({beds_occupied}).", "Band o‘rinlardagi bolalar ({occ_children}) band o‘rinlardan ({beds_occupied}) ko‘p.");
  add("Беременных в крайне тяжёлом состоянии ({extreme_pregnant}) больше, чем крайне тяжёлых ({extreme}).", "O‘ta og‘ir ahvoldagi homiladorlar ({extreme_pregnant}) o‘ta og‘ir bemorlardan ({extreme}) ko‘p.");
  add("Детей в крайне тяжёлом состоянии ({extreme_children}) больше, чем крайне тяжёлых ({extreme}).", "O‘ta og‘ir ahvoldagi bolalar ({extreme_children}) o‘ta og‘ir bemorlardan ({extreme}) ko‘p.");
  add("Госпитализаций ({hosp}) больше, чем обращений ({visits}). Проверьте данные.", "Yotqizilganlar ({hosp}) murojaatlardan ({visits}) ko‘p. Ma’lumotlarni tekshiring.");
  add("Выписано ({disch}) больше, чем было занято и поступило ({beds_occupied} + {hosp}). Проверьте данные.", "Chiqarilganlar ({disch}) band va yotqizilganlardan ({beds_occupied} + {hosp}) ko‘p. Ma’lumotlarni tekshiring.");
  add("Тяжёлых и крайне тяжёлых вместе ({severe} + {extreme}) больше, чем обращений ({visits}).", "Og‘ir va o‘ta og‘ir bemorlar birgalikda ({severe} + {extreme}) murojaatlardan ({visits}) ko‘p.");
  add("Обращений в 3 и более раз больше, чем в прошлом отчёте ({b} → {a}). Проверьте.", "Murojaatlar oldingi hisobotdagidan 3 baravar va undan ko‘p ({b} → {a}). Tekshiring.");
  add("Госпитализаций в 3 и более раз больше, чем в прошлом отчёте ({b} → {a}). Проверьте.", "Yotqizilganlar oldingi hisobotdagidan 3 baravar va undan ko‘p ({b} → {a}). Tekshiring.");
  add("Общее число коек резко изменилось ({b} → {a}). Проверьте.", "Jami o‘rinlar soni keskin o‘zgargan ({b} → {a}). Tekshiring.");
  const IND = {
    "Общее количество коек": "Jami o‘rinlar soni",
    "Из них выделено для больных гриппом и ОРВИ": "Shundan gripp va ORVI bilan kasallangan bemorlar uchun ajratilgan o‘rinlar soni",
    "Общее количество обращений": "Jami murojaatlar soni",
    "Количество пациентов, госпитализированных за отчётный день": "Hisobot kuni davomida shifoxonaga yotqizilgan bemorlar soni",
    "Количество пациентов, выписанных из стационара за отчётный день": "Hisobot kuni davomida shifoxonadan chiqarilgan bemorlar soni",
    "Количество коек, занятых больными гриппом и ОРВИ на конец отчётного дня": "Hisobot kuni yakunida gripp va ORVI bilan kasallangan bemorlar band qilgan o‘rinlar soni",
    "Из них беременные женщины": "Shundan homilador ayollar",
    "Из них дети": "Shundan bolalar",
    "Количество пациентов в тяжёлом состоянии": "Og‘ir ahvoldagi bemorlar soni",
    "Количество пациентов в крайне тяжёлом состоянии": "O‘ta og‘ir ahvoldagi bemorlar soni",
    "Из них беременные в крайне тяжёлом состоянии": "Shundan o‘ta og‘ir ahvoldagi homilador ayollar",
    "Из них дети в крайне тяжёлом состоянии": "Shundan o‘ta og‘ir ahvoldagi bolalar",
  };
  const indName = v => IND[v] || v;
  for (const [ru, uz] of [["Не заполнено: ", "To‘ldirilmagan: "], ["Нужно целое число: ", "Butun son kerak: "], ["Отрицательные значения запрещены: ", "Manfiy qiymatlar taqiqlanadi: "]])
    UZP.push([new RegExp("^" + rx(ru) + "(.+)$"), (m, name) => uz + indName(name)]);
})();
