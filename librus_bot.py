"""
Bot de Telegram interactivo y monitor para Librus Synergia con SQLite.
Control de acceso mediante clave por clave configurable, aislamiento de alumnos por usuario,
comando /resumen inteligente con auto-borrado de resúmenes anteriores,
traducción al español por defecto, botón 'Ver original' y 'Ver más/menos' para textos largos.
"""

from __future__ import annotations

import asyncio
import aiohttp
import os
import sys
import json
import functools
import urllib.parse
from datetime import datetime, date, timedelta
from typing import Any
from librus_synergia import (
    LibrusApiClient,
    LibrusError,
    LibrusInvalidCredentialsError,
    LibrusCaptchaRequiredError,
)
from librus_synergia.parsers import decode_message_content
from deep_translator import MyMemoryTranslator

from aiohttp import web
import db
import web_panel

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")
print = functools.partial(print, flush=True)

# Límite de caracteres para mostrar botón "Ver más"
TRUNCATE_LIMIT = 180

# Diccionario de traducción de asignaturas polacas
SUBJECT_TRANSLATIONS: dict[str, str] = {
    "Język angielski": "🇬🇧 Inglés",
    "Język polski": "🇵🇱 Polaco",
    "Edukacja wczesnoszkolna": "🏫 Ed. Primaria",
    "Edukacja polonistyczna": "🇵🇱 Lengua Polaca",
    "Edukacja matematyczna": "📐 Matemáticas",
    "Edukacja przyrodnicza": "🌿 Ciencias Naturales",
    "Edukacja społeczna": "👥 Ciencias Sociales",
    "Edukacja muzyczna": "🎵 Música",
    "Edukacja plastyczna": "🎨 Plástica",
    "Edukacja techniczna": "🛠️ Tecnología",
    "Edukacja informatyczna": "💻 Informática",
    "Informatyka": "💻 Informática",
    "Matematyka": "📐 Matemáticas",
    "Plastyka": "🎨 Plástica",
    "Muzyka": "🎵 Música",
    "Wychowanie fizyczne": "🏃 Ed. Física",
    "Religia": "✝️ Religión",
    "Etyka": "📖 Ética",
    "Basen": "🏊 Natación",
    "Historia": "🏛️ Historia",
    "Geografia": "🌍 Geografía",
    "Biologia": "🔬 Biología",
    "Chemia": "🧪 Química",
    "Fizyka": "⚛️ Física",
    "Przyroda": "🌿 C. Naturales",
    "Technika": "🛠️ Tecnología",
    "Język hiszpański": "🇪🇸 Español",
    "Język niemiecki": "🇩🇪 Alemán",
    "WF": "🏃 Ed. Física",
    "W-F": "🏃 Ed. Física",
    "Edukacja zdrowotna": "🍎 Ed. Salud",
    "Zajęcia praktyczno - techniczne": "🛠️ Tec. y Prácticas",
    "Edukacja dla bezpieczeństwa": "🛡️ Seguridad y Prim. Aux.",
    "Język hiszpański 7,8": "🇪🇸 Español",
}


def translate_subject(name: str) -> str:
    return SUBJECT_TRANSLATIONS.get(name, f"📚 {name}")


GRADE_NUMERIC_MAP: dict[str, float] = {
    "6": 6.0, "6-": 5.75,
    "5+": 5.25, "5": 5.0, "5-": 4.75,
    "4+": 4.25, "4": 4.0, "4-": 3.75,
    "3+": 3.25, "3": 3.0, "3-": 2.75,
    "2+": 2.25, "2": 2.0, "2-": 1.75,
    "1+": 1.25, "1": 1.0,
}


DIAS_SEMANA = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def format_calendar_date(d_str: str) -> str:
    try:
        dt = datetime.strptime(d_str, "%Y-%m-%d")
        dia_nom = DIAS_SEMANA[dt.weekday()]
        return f"{dia_nom} {dt.day:02d}/{dt.month:02d}"
    except Exception:
        return d_str


def get_event_icon_and_type(cat_name: str) -> tuple[str, str]:
    c = cat_name.lower()
    if "sprawdzian" in c or "praca klasowa" in c:
        return "🎯", "Examen"
    if "kartkówka" in c or "kartkowka" in c or "test" in c:
        return "⚡", "Control / Test"
    if "lektura" in c:
        return "📖", "Lectura"
    if "wycieczka" in c:
        return "🚌", "Excursión"
    if "projekt" in c:
        return "🎨", "Proyecto"
    if "poprawa" in c:
        return "🔄", "Recuperación"
    if "zadanie" in c:
        return "📝", "Entrega Tarea"
    if "warsztat" in c:
        return "👥", "Taller"
    if "egzamin" in c:
        return "🎯", "Examen"
    if "apel" in c:
        return "📢", "Acto escolar"
    if "konkurs" in c or "olimp" in c:
        return "🏆", "Concurso"
    if "zebranie" in c or "spotkanie" in c:
        return "👨‍👩‍👧", "Reunión"
    if "paszport czytelnika" in c or "czytelnictw" in c:
        return "📚", "Actividad de lectura"
    if "dyskoteka" in c or "bal" in c:
        return "🎉", "Fiesta escolar"
    translated = translate_to_spanish(cat_name)
    return "📌", translated if translated else cat_name


SCHEDULE_EVENT_KEYWORDS = [
    "wycieczk", "wyjść", "wyjsc", "apel", "zielona szkoł", "zielona szkol",
    "teatr", "kino", "rekolekcj", "turniej", "piknik", "uroczysto", "imprez",
    "dyskotek", "bal ", "rozpoczęcie", "rozpoczecie", "zakończenie", "zakonczenie",
    "warsztat", "adwokaci", "planetarium"
]

NON_SCHEDULE_KEYWORDS = [
    "sprawdzian", "kartkówk", "kartkowk", "zadanie domow", "praca domow",
    "dyktando", "lektura", "odpowiedź", "odpowiedz", "poprawa"
]

def is_schedule_event(cat_name: str, ev: dict) -> bool:
    cat_lower = (cat_name or "").lower()
    for kw in SCHEDULE_EVENT_KEYWORDS:
        if kw in cat_lower:
            return True
    for kw in NON_SCHEDULE_KEYWORDS:
        if kw in cat_lower:
            return False
    tf = (ev.get("TimeFrom") or "")[:5]
    tt = (ev.get("TimeTo") or "")[:5]
    if tf and tt:
        try:
            h1, m1 = map(int, tf.split(":"))
            h2, m2 = map(int, tt.split(":"))
            if (h2 * 60 + m2) - (h1 * 60 + m1) > 60:
                return True
        except Exception:
            pass
    return False


def extract_day_schedule(
    tt_dict: dict,
    d_str: str,
    day_events: list[dict[str, Any]] | None = None,
    hw_cats: dict[int, str] | None = None,
    subs: dict[int, str] | None = None
) -> tuple[str | None, str | None, list[dict[str, Any]]]:
    slots = tt_dict.get(d_str, [])
    lessons = []
    active_times_from = []
    active_times_to = []

    for slot in slots:
        for l in slot:
            h_from = l.get("HourFrom")
            h_to = l.get("HourTo")
            if h_from and h_to:
                lessons.append(l)
                if not l.get("IsCanceled"):
                    active_times_from.append(h_from)
                    active_times_to.append(h_to)

    if day_events:
        for ev in day_events:
            cid = ev.get("Category", {}).get("Id") if isinstance(ev.get("Category"), dict) else None
            cat_name = (hw_cats or {}).get(cid, "Evento")
            if not is_schedule_event(cat_name, ev):
                continue

            cat_icon, cat_label = get_event_icon_and_type(cat_name)
            content = (ev.get("Content") or "").strip()
            first_line = content.split("\n")[0].strip() if content else ""
            title_es = translate_to_spanish(first_line) if first_line else cat_label
            if len(title_es) > 50:
                title_es = title_es[:48] + "…"

            time_from = (ev.get("TimeFrom") or "")[:5]
            time_to = (ev.get("TimeTo") or "")[:5]

            if not time_from and active_times_from:
                time_from = min(active_times_from)
            if not time_to and active_times_to:
                time_to = max(active_times_to)

            if time_from and time_to:
                active_times_from.append(time_from)
                active_times_to.append(time_to)

            ev_item = {
                "HourFrom": time_from or "08:30",
                "HourTo": time_to or "14:00",
                "Subject": {"Name": f"{cat_icon} {title_es}"},
                "SubjectName": f"{cat_icon} {title_es}",
                "IsEvent": True,
                "IsCanceled": False,
                "CategoryName": cat_label,
                "CategoryIcon": cat_icon,
                "Content": content,
                "Details": f"{cat_label}: {time_from}-{time_to}" if time_from else cat_label
            }
            lessons.append(ev_item)

    if not lessons:
        return None, None, []

    lessons.sort(key=lambda x: (
        x.get("HourFrom", ""),
        0 if x.get("IsEvent") else (1 if not x.get("IsCanceled") else 2)
    ))
    h_start = min(active_times_from) if active_times_from else None
    h_end = max(active_times_to) if active_times_to else None

    return h_start, h_end, lessons


COMMON_GRADE_CATEGORIES: dict[str, str] = {
    "aktywność": "Participación / Actividad",
    "aktywnosc": "Participación / Actividad",
    "odpowiedź ustna": "Pregunta oral",
    "odpowiedz ustna": "Pregunta oral",
    "odpowiedź": "Pregunta oral",
    "odpowiedz": "Pregunta oral",
    "praca klasowa": "Examen de evaluación",
    "sprawdzian": "Control / Examen",
    "kartkówka": "Prueba corta",
    "kartkowka": "Prueba corta",
    "praca na lekcji": "Trabajo en clase",
    "zadanie domowe": "Deberes",
    "praca domowa": "Deberes",
    "zadanie": "Tarea",
    "praca techniczna": "Trabajo técnico",
    "projekt": "Proyecto",
    "projekty": "Proyectos",
    "dyktando": "Dictado",
    "czytanie": "Lectura",
    "czytanie ze zrozumieniem": "Comprensión lectora",
    "lektura": "Lectura obligatoria",
    "zeszyt": "Cuaderno",
    "prowadzenie zeszytu": "Cuaderno",
    "brak zadania": "Falta de tarea",
    "nieprzygotowanie": "No preparado",
    "przygotowanie do lekcji": "Preparación de la clase",
    "praca pisemna": "Trabajo escrito",
    "wypracowanie": "Redacción",
    "recytacja": "Recitación",
    "recytacja wiersza": "Recitación de poema",
    "wiersz": "Poema",
    "test": "Test",
    "test postępu": "Test de progreso",
    "egzamin": "Examen",
    "egzamin próbny": "Examen de prueba",
    "konkurs": "Concurso",
    "prezentacja": "Presentación",
    "praca w grupie": "Trabajo en grupo",
    "praca dodatkowa": "Trabajo voluntario / extra",
}

TRANSLATION_CACHE: dict[str, str] = {}


def translate_grade_category(cat_name: str) -> str:
    """Traduce categorías de notas de forma instantánea usando mapeo local y caché."""
    if not cat_name or cat_name == "General":
        return "General"
    low = cat_name.lower().strip()
    if low in COMMON_GRADE_CATEGORIES:
        return COMMON_GRADE_CATEGORIES[low]
    for k, v in COMMON_GRADE_CATEGORIES.items():
        if k in low:
            return v
    return translate_to_spanish(cat_name)


def translate_to_spanish(text: str) -> str:
    """Traduce texto de polaco a español utilizando caché en memoria y Google API."""
    if not text or not text.strip():
        return ""

    clean_text = text.strip()
    if clean_text in TRANSLATION_CACHE:
        return TRANSLATION_CACHE[clean_text]

    # 1. Google dict-chrome-ex API (ligera, rápida y sin límites agresivos de 429)
    try:
        url = "https://clients5.google.com/translate_a/t?client=dict-chrome-ex&sl=pl&tl=es&q=" + urllib.parse.quote(clean_text[:1800])
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
        with urllib.request.urlopen(req, timeout=8) as r:
            data = json.loads(r.read().decode("utf-8"))
            res = ""
            if isinstance(data, list) and data and data[0]:
                res = str(data[0]).strip()
            elif isinstance(data, str) and data:
                res = data.strip()
            if res:
                TRANSLATION_CACHE[clean_text] = res
                return res
    except Exception:
        pass

    # 2. Google Translate API (gtx) por párrafos
    try:
        paragraphs = clean_text.split("\n")
        translated_parts = []
        chunk = ""
        for p in paragraphs:
            if len(chunk) + len(p) + 1 < 2500:
                chunk = (chunk + "\n" + p).strip() if chunk else p
            else:
                if chunk:
                    url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=pl&tl=es&dt=t&q=" + urllib.parse.quote(chunk)
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        data = json.loads(r.read().decode())
                        translated_parts.append("".join([s[0] for s in data[0] if s[0]]))
                chunk = p

        if chunk:
            url = "https://translate.googleapis.com/translate_a/single?client=gtx&sl=pl&tl=es&dt=t&q=" + urllib.parse.quote(chunk)
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=8) as r:
                data = json.loads(r.read().decode())
                translated_parts.append("".join([s[0] for s in data[0] if s[0]]))

        result = "\n".join(translated_parts).strip()
        if result:
            TRANSLATION_CACHE[clean_text] = result
            return result
    except Exception:
        pass

    # 3. Fallback: MyMemory
    try:
        from deep_translator import MyMemoryTranslator
        res = MyMemoryTranslator(source="pl-PL", target="es-ES").translate(clean_text[:450])
        if res:
            TRANSLATION_CACHE[clean_text] = res
            return res
    except Exception:
        pass

    TRANSLATION_CACHE[clean_text] = text
    return text


def build_card_content(card_row: dict[str, Any], chat_id: int, lang: str = "es", expanded: bool = False) -> tuple[str, dict]:
    header = json.loads(card_row.get("header_info") or "{}")
    card_type = card_row.get("card_type", "msg")
    cache_id = card_row["id"]
    pupil_user = card_row.get("pupil_username", "")
    item_id = card_row.get("item_id", "")

    tag = header.get("tag", "")
    topic = header.get("topic", "")

    # Seleccionar texto según idioma
    if lang == "es":
        text = card_row.get("translated_text") or card_row.get("original_text", "")
        lang_label = "Español"
    else:
        text = card_row.get("original_text", "")
        lang_label = "Polski"

    text = text.strip()
    is_long = len(text) > TRUNCATE_LIMIT

    if is_long and not expanded:
        display_text = text[:TRUNCATE_LIMIT].rsplit(" ", 1)[0] + "..."
    else:
        display_text = text

    # Construir tarjeta según tipo
    if card_type == "msg":
        sender = header.get("sender", "Profesor/a")
        s_date = header.get("date", "-")
        card_text = (
            f"{tag} ✉️ <b>Mensaje de {sender}</b>\n"
            f"📌 <b>Asunto:</b> {topic}\n"
            f"📅 <b>Fecha:</b> {s_date}\n\n"
            f"💬 <b>Contenido ({lang_label}):</b>\n<i>{display_text}</i>"
        )
    elif card_type == "hw":
        assign_d = header.get("assign_d", "-")
        due_d = header.get("due_d", "-")
        card_text = (
            f"{tag} 📝 <b>Tarea Pendiente</b>\n"
            f"📌 <b>Tema:</b> {topic}\n"
            f"📅 <b>Asignada:</b> {assign_d} | ⏰ <b>Entrega:</b> <b>{due_d}</b>\n\n"
            f"📄 <b>Instrucciones ({lang_label}):</b>\n<i>{display_text}</i>"
        )
    elif card_type in ("cal_ev", "event"):
        cat = header.get("cat", "Examen / Evento")
        subj = header.get("subj", "General")
        date_str = header.get("date", "-")
        time_str = header.get("time", "")
        time_label = f" ({time_str})" if time_str else ""
        card_text = (
            f"{tag} 📋 <b>Detalle: {cat}</b>\n"
            f"📖 <b>Asignatura:</b> {subj}\n"
            f"📅 <b>Fecha:</b> {date_str}{time_label}\n\n"
            f"📝 <b>Instrucciones / Temario ({lang_label}):</b>\n<i>{display_text}</i>"
        )
    elif card_type == "schedule":
        card_text = f"{display_text}"
    else:
        card_text = f"{tag}\n\n<i>{display_text}</i>"

    # Construir botones inline
    row_actions = []
    if card_type != "schedule":
        # 1. Botón Ver más / Ver menos (solo si es texto largo)
        if is_long:
            if not expanded:
                row_actions.append({"text": "📄 Ver más", "callback_data": f"card:{cache_id}:{lang}:1"})
            else:
                row_actions.append({"text": "📄 Ver menos", "callback_data": f"card:{cache_id}:{lang}:0"})

        # 2. Botón Idioma (por defecto 'Ver original', o 'Ver traducido' si está en polaco)
        exp_int = 1 if expanded else 0
        if lang == "es":
            row_actions.append({"text": "🇵🇱 Ver original", "callback_data": f"card:{cache_id}:pl:{exp_int}"})
        else:
            row_actions.append({"text": "🇪🇸 Ver traducido", "callback_data": f"card:{cache_id}:es:{exp_int}"})

    keyboard = []
    if row_actions:
        keyboard.append(row_actions)

    # 3. Si es tarea, botón para marcar como hecha
    if card_type == "hw" and pupil_user and item_id:
        is_done = db.is_task_completed(chat_id, pupil_user, item_id)
        if is_done:
            keyboard.append([{"text": "✔ Hecha por ti (pulsa para desmarcar)", "callback_data": f"undone:{pupil_user}:{item_id}:{cache_id}:{lang}:{exp_int}"}])
        else:
            keyboard.append([{"text": "✅ Marcar como hecha", "callback_data": f"done:{pupil_user}:{item_id}:{cache_id}:{lang}:{exp_int}"}])

    # 4. Si es tarjeta de detalle de calendario o horario, botón para cerrar
    if card_type in ("cal_ev", "event", "schedule"):
        keyboard.append([{"text": "🗑️ Cerrar detalle", "callback_data": "del_msg"}])

    return card_text, {"inline_keyboard": keyboard}


class LibrusTelegramBot:
    def __init__(self):
        db.init_db()
        self.bot_token = db.get_setting("bot_token", os.environ.get("TELEGRAM_BOT_TOKEN", ""))
        self.user_sessions: dict[int, dict[str, Any]] = {}
        self.last_update_id = 0
        self.session: aiohttp.ClientSession | None = None
        self.event_logs: list[dict[str, str]] = []
        self.last_check_time: str = "Nunca"
        self.force_check_event = asyncio.Event()
        self.cached_overview: list[dict[str, Any]] = []
        self.last_overview_time: str = "Nunca"
        self.is_fetching_overview: bool = False

    def log_event(self, message: str) -> None:
        t_str = datetime.now().strftime("%H:%M:%S")
        print(f"[{t_str}] {message}")
        self.event_logs.append({"time": t_str, "message": message})
        if len(self.event_logs) > 60:
            self.event_logs.pop(0)

    def update_interval(self, mins: int) -> None:
        self.log_event(f"Intervalo programado actualizado a {mins} min")
        self.force_check_event.set()

    async def trigger_check_now(self) -> None:
        if not self.session:
            return
        self.log_event("Ejecutando revisión manual inmediata...")
        delivered = await self.run_full_periodic_check(self.session)
        self.last_check_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
        self.log_event(f"Revisión completada. Novedades enviadas: {delivered}")

    async def trigger_summary_now(self) -> None:
        if not self.session:
            return
        active_pupils = db.get_all_active_pupils()
        chats_to_notify = set()
        for p in active_pupils:
            for cid in db.get_chats_for_pupil(p["librus_username"]):
                chats_to_notify.add(cid)
        if not chats_to_notify:
            chats_to_notify.add(db.get_admin_chat_id())
        for cid in chats_to_notify:
            self.log_event(f"Enviando resumen semanal a chat {cid}...")
            await self.send_resumen(self.session, cid)
            await asyncio.sleep(0.5)

    async def trigger_prune_now(self) -> None:
        if not self.session:
            return
        self.log_event("Iniciando purga de mensajes expirados (>45h)...")
        await self.prune_expired_messages(self.session, hours=45.0)
        self.log_event("Purga de mensajes finalizada.")

    async def get_pupil_overview(self, student: dict[str, Any]) -> dict[str, Any]:
        """Obtiene un desglose completo de horarios, exámenes, deberes, notas y mensajes para el dashboard."""
        u = str(student.get("librus_username", "")).strip()
        pwd = str(student.get("password", ""))
        name = student.get("name", u)
        icon = student.get("icon", "👤")

        data: dict[str, Any] = {
            "username": u,
            "name": name,
            "icon": icon,
            "schedules": [],
            "exams": [],
            "homework": [],
            "recent_grades": [],
            "subject_averages": [],
            "overall_average": "-",
            "recent_messages": [],
            "error": None
        }

        if not u or not pwd:
            data["error"] = "Sin credenciales"
            return data

        async with aiohttp.ClientSession() as pupil_session:
            client = LibrusApiClient(pupil_session, u)
            try:
                await client.async_login(pwd)
            except Exception as e:
                data["error"] = f"Error login: {e}"
                return data

            today = date.today()
            today_s = today.isoformat()
            end_date_s = (today + timedelta(days=14)).isoformat()
            cutoff_7d = (today - timedelta(days=7)).isoformat()

            # 1. Asignaturas y categorías
            try:
                subs_resp = await client.async_get_subjects()
                subs = {s["Id"]: s["Name"] for s in subs_resp.get("Subjects", [])}
            except Exception:
                subs = {}

            try:
                hw_cats_resp = await client.async_get_homework_categories()
                hw_cats = {c["Id"]: c["Name"] for c in hw_cats_resp.get("Categories", [])}
            except Exception:
                hw_cats = {}

            try:
                grade_cats_resp = await client.async_get_grade_categories()
                grade_cats = {c["Id"]: c for c in grade_cats_resp.get("Categories", [])}
            except Exception:
                grade_cats = {}

            # 2. Exámenes y Eventos (HomeWorks)
            all_events = []
            try:
                ev_resp = await client.async_get_homeworks()
                all_events = ev_resp.get("HomeWorks", []) or []
                for ev in all_events:
                    d = ev.get("Date") or ""
                    if today_s <= d <= end_date_s:
                        cid = ev.get("Category", {}).get("Id")
                        cat_raw = hw_cats.get(cid, "Examen")
                        cat_icon, cat_es = get_event_icon_and_type(cat_raw)
                        sid = ev.get("Subject", {}).get("Id")
                        sub_raw = subs.get(sid, "General")
                        content = (ev.get("Content") or "").strip()
                        content_es = await self.translate_text(content) if content else ""
                        data["exams"].append({
                            "id": str(ev.get("Id", "")),
                            "date": d,
                            "date_formatted": format_calendar_date(d),
                            "time": f"{ev.get('TimeFrom', '')} - {ev.get('TimeTo', '')}".strip(" -"),
                            "category": cat_es,
                            "category_icon": cat_icon,
                            "subject": translate_subject(sub_raw),
                            "content": content_es or content,
                            "content_raw": content
                        })
                data["exams"].sort(key=lambda x: x["date"])
            except Exception as e:
                print(f"Error eventos dashboard {u}: {e}")

            # 3. Horarios (Hoy, Mañana, y si es fin de semana el Próximo Lunes)
            try:
                tomorrow = today + timedelta(days=1)
                days_to_fetch = [(today, "Hoy"), (tomorrow, "Mañana")]
                if today.weekday() >= 5 and tomorrow.weekday() >= 5:
                    next_mon = today + timedelta(days=(7 - today.weekday()))
                    days_to_fetch.append((next_mon, "Lunes"))

                weeks = {d - timedelta(days=d.weekday()) for d, _ in days_to_fetch}
                combined_tt = {}
                for w in weeks:
                    res = await client.async_get_timetable(w)
                    combined_tt.update(res.get("Timetable", {}))

                for d, label in days_to_fetch:
                    d_str = d.isoformat()
                    dia_nom = DIAS_SEMANA[d.weekday()]
                    day_evs = [ev for ev in all_events if ev.get("Date") == d_str]
                    h_start, h_end, raw_lessons = extract_day_schedule(combined_tt, d_str, day_events=day_evs, hw_cats=hw_cats, subs=subs)
                    lessons = []
                    for l in raw_lessons:
                        is_ev = bool(l.get("IsEvent"))
                        is_canc = bool(l.get("IsCanceled"))
                        if is_ev:
                            s_name = l.get("SubjectName", "Evento")
                            extra = l.get("CategoryName", "Evento")
                        else:
                            s_id = l.get("Subject", {}).get("Id") if isinstance(l.get("Subject"), dict) else None
                            raw_s_name = subs.get(s_id, l.get("Subject", {}).get("Name", "Clase")) if s_id else "Clase"
                            s_name = translate_subject(raw_s_name)
                            classroom = l.get("Classroom", {}).get("Symbol", "") if isinstance(l.get("Classroom"), dict) else ""
                            extra = f"Aula {classroom}" if classroom else ""

                        lessons.append({
                            "hour_from": l.get("HourFrom", ""),
                            "hour_to": l.get("HourTo", ""),
                            "subject": s_name,
                            "classroom": l.get("Classroom", {}).get("Symbol", "") if isinstance(l.get("Classroom"), dict) else "",
                            "teacher": l.get("Teacher", {}).get("Name", "") if isinstance(l.get("Teacher"), dict) else "",
                            "is_event": is_ev,
                            "is_canceled": is_canc,
                            "extra": extra,
                            "details": l.get("Content", "") if is_ev else ""
                        })

                    data["schedules"].append({
                        "date": d.strftime("%d/%m/%Y"),
                        "date_iso": d_str,
                        "day_name": dia_nom,
                        "label": label,
                        "entry": h_start,
                        "exit": h_end,
                        "lessons": lessons
                    })
            except Exception as e:
                print(f"Error horario en dashboard para {u}: {e}")

            # 4. Tareas pendientes / entregas (próximos 14 días)
            try:
                hw_resp = await client.async_get_homework_assignments()
                admin_cid = db.get_admin_chat_id()
                completed_tasks = db.get_completed_tasks(admin_cid, u)
                for hw in (hw_resp.get("HomeWorkAssignments", []) or []):
                    due_d = hw.get("DueDate") or ""
                    if today_s <= due_d <= end_date_s:
                        hid = str(hw.get("Id"))
                        sid = hw.get("Subject", {}).get("Id") if isinstance(hw.get("Subject"), dict) else None
                        sub_raw = subs.get(sid, "General") if sid else "General"
                        topic = (hw.get("Topic") or "").strip()
                        text = (hw.get("Text") or "").strip()
                        content_full = f"{topic}: {text}".strip(": ")
                        content_es = await self.translate_text(content_full) if content_full else topic
                        data["homework"].append({
                            "id": hid,
                            "due_date": due_d,
                            "due_date_formatted": format_calendar_date(due_d),
                            "assign_date": hw.get("AddDate", "")[:10] if hw.get("AddDate") else "",
                            "subject": translate_subject(sub_raw),
                            "topic": topic,
                            "content": content_es,
                            "is_done": hid in completed_tasks
                        })
                data["homework"].sort(key=lambda x: x["due_date"])
            except Exception as e:
                print(f"Error tareas dashboard {u}: {e}")

            # 5. Calificaciones y Promedios
            try:
                grades_resp = await client.async_get_grades()
                raw_grades = grades_resp.get("Grades", [])
                by_subj: dict[int, list[dict[str, Any]]] = {}
                for g in raw_grades:
                    sid = g.get("Subject", {}).get("Id")
                    by_subj.setdefault(sid, []).append(g)

                all_subj_averages = []
                for sid, s_grades in by_subj.items():
                    s_name_raw = subs.get(sid, "General")
                    subj_label = translate_subject(s_name_raw)

                    s_grades_sorted = sorted(s_grades, key=lambda x: x.get("AddDate") or x.get("Date") or "")
                    weighted_sum = 0.0
                    total_weight = 0.0
                    num_grades = []

                    for g in s_grades_sorted:
                        g_val = str(g.get("Grade", "")).strip()
                        add_d = g.get("AddDate") or g.get("Date") or ""
                        is_recent = (add_d >= cutoff_7d)
                        cid = g.get("Category", {}).get("Id")
                        cat = grade_cats.get(cid, {})
                        w = float(cat.get("Weight", 1) or 1)

                        if is_recent:
                            data["recent_grades"].append({
                                "grade": g_val,
                                "subject": subj_label,
                                "date": add_d[:10] if add_d else "",
                                "category": cat.get("Name", "Nota"),
                                "weight": w
                            })

                        if g_val in GRADE_NUMERIC_MAP and cat.get("CountToTheAverage", True) and w > 0:
                            val = GRADE_NUMERIC_MAP[g_val]
                            weighted_sum += val * w
                            total_weight += w
                            num_grades.append(val)

                    if total_weight > 0:
                        subj_avg = weighted_sum / total_weight
                    elif num_grades:
                        subj_avg = sum(num_grades) / len(num_grades)
                    else:
                        subj_avg = None

                    grades_list = [str(g.get("Grade", "")).strip() for g in s_grades_sorted]
                    data["subject_averages"].append({
                        "subject": subj_label,
                        "average": f"{subj_avg:.2f}" if subj_avg else "-",
                        "grades": grades_list[-8:],
                        "grades_count": len(grades_list)
                    })

                    if subj_avg is not None:
                        all_subj_averages.append(subj_avg)

                if all_subj_averages:
                    overall = sum(all_subj_averages) / len(all_subj_averages)
                    data["overall_average"] = f"{overall:.2f}"
                else:
                    data["overall_average"] = "-"

                data["subject_averages"].sort(key=lambda x: x["subject"])
                data["recent_grades"].sort(key=lambda x: x.get("date", ""), reverse=True)
            except Exception as e:
                print(f"Error notas dashboard {u}: {e}")

            # 6. Mensajes de Profesores (últimos 4)
            # NOTA: Usamos exclusivamente el contenido del listado. NUNCA llamamos a async_get_message()
            # para no marcar el mensaje como leído en Librus (preserva readDate null en el servidor).
            try:
                await client.async_bootstrap_messages()
                msgs_resp = await client.async_get_messages(limit=6)
                raw_msgs = msgs_resp.get("data", []) or msgs_resp.get("Messages", []) or []
                for m in raw_msgs[:4]:
                    mid = str(m.get("messageId") or m.get("Id") or "")
                    sender = m.get("senderName") or (m.get("Sender", {}).get("Name") if isinstance(m.get("Sender"), dict) else "Profesor")
                    topic = m.get("topic") or m.get("Topic") or "Sin asunto"
                    send_d = m.get("sendDate") or m.get("SendDate") or ""
                    raw_body = decode_message_content(m.get("content") or "").strip()
                    body_es = await self.translate_text(raw_body) if raw_body else await self.translate_text(topic)

                    data["recent_messages"].append({
                        "id": mid,
                        "sender": sender,
                        "date": send_d[:16] if send_d else "",
                        "topic": topic,
                        "body": body_es
                    })
            except Exception as e:
                print(f"Error mensajes dashboard {u}: {e}")

            return data

    async def refresh_dashboard_overview(self) -> list[dict[str, Any]]:
        """Sincroniza y cachea el estado completo de los 3 alumnos para el panel web."""
        if not self.session or self.is_fetching_overview:
            return self.cached_overview

        self.is_fetching_overview = True
        try:
            self.log_event("Sincronizando estado completo de los alumnos con Librus...")
            pupils = db.get_all_active_pupils()
            tasks = [self.get_pupil_overview(p) for p in pupils]
            results = await asyncio.gather(*tasks, return_exceptions=True)
            new_overview = []
            for r in results:
                if isinstance(r, dict):
                    new_overview.append(r)
                elif isinstance(r, Exception):
                    self.log_event(f"Error en consulta alumno: {r}")
            import re
            new_overview.sort(key=lambda p: int(re.search(r'\d+', str(p.get("username", "0"))).group()) if re.search(r'\d+', str(p.get("username", "0"))) else 99999999)
            self.cached_overview = new_overview
            self.last_overview_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
            self.log_event("Resumen escolar para el panel web actualizado.")
            return self.cached_overview
        except Exception as e:
            self.log_event(f"Error refrescando resumen escolar: {e}")
            return self.cached_overview
        finally:
            self.is_fetching_overview = False


    async def translate_text(self, text: str) -> str:
        """Traduce texto de polaco a español en un hilo separado para no bloquear el bucle async."""
        if not text or not text.strip():
            return ""
        loop = asyncio.get_running_loop()
        return await loop.run_in_executor(None, translate_to_spanish, text)

    async def send_msg(self, session: aiohttp.ClientSession, chat_id: int | str, text: str, reply_markup: dict | None = None) -> int | None:
        url = f"https://api.telegram.org/bot{self.bot_token}/sendMessage"
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup:
            payload["reply_markup"] = reply_markup
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    mid = data.get("result", {}).get("message_id")
                    if mid:
                        try:
                            db.record_chat_message(int(chat_id), mid)
                        except Exception:
                            pass
                    return mid
                else:
                    res_json = await resp.json()
                    print(f"Telegram error {resp.status}: {res_json}")
                    return None
        except Exception as e:
            print(f"Error enviando mensaje a {chat_id}: {e}")
            return None

    async def delete_msg(self, session: aiohttp.ClientSession, chat_id: int | str, message_id: int) -> bool:
        """Borra un mensaje específico del chat de Telegram."""
        url = f"https://api.telegram.org/bot{self.bot_token}/deleteMessage"
        payload = {"chat_id": str(chat_id), "message_id": message_id}
        try:
            async with session.post(url, json=payload, timeout=5) as resp:
                return resp.status == 200
        except Exception:
            return False

    async def delete_messages(self, session: aiohttp.ClientSession, chat_id: int | str, message_ids: list[int]) -> bool:
        """Borra un lote de hasta 100 mensajes simultáneamente (Telegram Bot API 7.0+)."""
        if not message_ids:
            return True
        url = f"https://api.telegram.org/bot{self.bot_token}/deleteMessages"
        payload = {"chat_id": str(chat_id), "message_ids": message_ids}
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    return bool(data.get("ok"))
                return False
        except Exception:
            return False

    async def edit_message_text(self, session: aiohttp.ClientSession, chat_id: int | str, message_id: int, text: str, reply_markup: dict | None = None) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/editMessageText"
        payload: dict[str, Any] = {
            "chat_id": str(chat_id),
            "message_id": message_id,
            "text": text,
            "parse_mode": "HTML",
            "disable_web_page_preview": True,
        }
        if reply_markup is not None:
            payload["reply_markup"] = reply_markup
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Error editando texto del mensaje {message_id}: {e}")
            return False

    async def answer_callback_query(self, session: aiohttp.ClientSession, callback_query_id: str, text: str, show_alert: bool = False) -> bool:
        url = f"https://api.telegram.org/bot{self.bot_token}/answerCallbackQuery"
        payload = {
            "callback_query_id": callback_query_id,
            "text": text,
            "show_alert": show_alert,
        }
        try:
            async with session.post(url, json=payload, timeout=10) as resp:
                return resp.status == 200
        except Exception as e:
            print(f"Error respondiendo callback: {e}")
            return False

    async def check_librus_for_student(self, session: aiohttp.ClientSession, student: dict[str, Any]) -> list[tuple[str, dict | None]]:
        """Comprueba elementos nuevos para avisos push. Estos mensajes NO se borran con el resumen."""
        username = str(student.get("librus_username", "")).strip()
        password = str(student.get("password", ""))
        student_name = student.get("name", username)
        icon = student.get("icon", "👤")

        if not username or not password:
            return []

        messages: list[tuple[str, dict | None]] = []
        client = LibrusApiClient(session, username)
        try:
            await client.async_login(password)
        except Exception as e:
            print(f"[{student_name}] Error en login: {e}")
            return []

        tag = f"<b>{icon} [{student_name.upper()}]</b>"

        # 1. Metadatos
        try:
            subs_resp = await client.async_get_subjects()
            subjects = {s["Id"]: s["Name"] for s in subs_resp.get("Subjects", [])}
            cats_resp = await client.async_get_grade_categories()
            categories = {c["Id"]: c["Name"] for c in cats_resp.get("Categories", [])}
            comms_resp = await client.async_get_grade_comments()
            comments = {c["Id"]: c["Text"] for c in comms_resp.get("Comments", [])}
        except Exception:
            subjects, categories, comments = {}, {}, {}

        # 2. Calificaciones
        try:
            grades_resp = await client.async_get_grades()
            grades = grades_resp.get("Grades", [])
            for g in sorted(grades, key=lambda x: x.get("AddDate", ""), reverse=True):
                gid = str(g.get("Id"))
                if not db.is_item_known(username, "grade", gid):
                    sid = g.get("Subject", {}).get("Id")
                    cid = g.get("Category", {}).get("Id")
                    subj = translate_subject(subjects.get(sid, "General"))
                    cat_raw = categories.get(cid, "General")
                    cat = translate_grade_category(cat_raw)
                    g_comms = [comments.get(c["Id"], "") for c in g.get("Comments", []) if c.get("Id") in comments]
                    translated_comms = []
                    for c_txt in g_comms:
                        if c_txt and c_txt.strip():
                            t_c = await self.translate_text(c_txt.strip())
                            translated_comms.append(t_c if t_c else c_txt.strip())
                    comm_str = f"\n💬 <i>{', '.join(translated_comms)}</i>" if translated_comms else ""
                    msg = (
                        f"{tag} ⭐ <b>Nueva Calificación</b>\n"
                        f"📖 <b>Asignatura:</b> {subj}\n"
                        f"🎯 <b>Nota:</b> <code>{g.get('Grade')}</code>\n"
                        f"🏷️ <b>Categoría:</b> {cat}\n"
                        f"📅 <b>Fecha:</b> {g.get('AddDate')}"
                        f"{comm_str}"
                    )
                    messages.append((msg, None))
                    db.mark_item_known(username, "grade", gid)
        except Exception as e:
            print(f"[{student_name}] Error calificaciones: {e}")

        # 3. Tareas / Deberes
        newly_added_hws: set[str] = set()
        hw_resp: dict[str, Any] = {}
        try:
            hw_resp = await client.async_get_homework_assignments()
            for hw in hw_resp.get("HomeWorkAssignments", []) or []:
                hid = str(hw.get("Id"))
                if not db.is_item_known(username, "homework", hid):
                    hw_topic = hw.get("Topic") or "Sin tema"
                    hw_text = hw.get("Text") or ""
                    hw_topic_es = await self.translate_text(hw_topic)
                    hw_text_es = await self.translate_text(hw_text)
                    d_assign = format_calendar_date(hw.get('Date') or "")
                    d_due = format_calendar_date(hw.get('DueDate') or "")
                    msg = (
                        f"{tag} 📝 <b>Nueva Tarea Asignada</b>\n"
                        f"📌 <b>Tema:</b> {hw_topic_es}\n"
                        f"📅 <b>Fecha Asignada:</b> {d_assign} | ⏰ <b>Entrega:</b> <b>{d_due}</b>\n\n"
                        f"📄 <b>Instrucciones:</b>\n{hw_text_es}"
                    )
                    header_info = {
                        "tag": tag,
                        "topic": hw_topic_es,
                        "assign_d": hw.get("Date") or "-",
                        "due_d": hw.get("DueDate") or "-"
                    }
                    cache_id = db.save_or_update_cache_card(
                        f"push_hw:{username}:{hid}", "hw", username, hid, header_info, hw_text, hw_text_es
                    )
                    markup = {
                        "inline_keyboard": [
                            [
                                {"text": "✅ Hecha", "callback_data": f"done:{username}:{hid}:{cache_id}:es:0"},
                                {"text": "🇵🇱 Ver original", "callback_data": f"card:{cache_id}:pl:0"}
                            ]
                        ]
                    }
                    messages.append((msg, markup))
                    db.mark_item_known(username, "homework", hid)
                    newly_added_hws.add(hid)
        except Exception as e:
            print(f"[{student_name}] Error tareas: {e}")

        # 4. Exámenes y agenda (Nuevos eventos)
        newly_added_events: set[str] = set()
        events_resp: dict[str, Any] = {}
        hw_cats: dict[int, str] = {}
        try:
            events_resp = await client.async_get_homeworks()
            hw_cats = {c["Id"]: c["Name"] for c in (await client.async_get_homework_categories()).get("Categories", [])}
            today_str = date.today().isoformat()
            for ev in sorted(events_resp.get("HomeWorks", []) or [], key=lambda x: x.get("Date", "")):
                ev_date = ev.get("Date", "")
                if ev_date >= today_str:
                    eid = str(ev.get("Id"))
                    if not db.is_item_known(username, "event", eid):
                        cid = ev.get("Category", {}).get("Id")
                        cat_raw = hw_cats.get(cid, "Evento")
                        cat_icon, cat_label = get_event_icon_and_type(cat_raw)
                        ev_content = ev.get("Content") or ""
                        ev_content_es = await self.translate_text(ev_content)
                        ev_date_fmt = format_calendar_date(ev_date)
                        time_part = f" ({ev.get('TimeFrom', '')} - {ev.get('TimeTo', '')})" if ev.get('TimeFrom') else ""
                        msg = (
                            f"{tag} 📅 <b>Próximo Examen / Evento</b>\n"
                            f"🏷️ <b>Tipo:</b> {cat_icon} {cat_label}\n"
                            f"📆 <b>Fecha:</b> {ev_date_fmt}{time_part}\n\n"
                            f"📋 <b>Detalle:</b>\n{ev_content_es}"
                        )
                        messages.append((msg, None))
                        db.mark_item_known(username, "event", eid)
                        newly_added_events.add(eid)
        except Exception as e:
            print(f"[{student_name}] Error exámenes: {e}")

        # 5. Recordatorios periódicos para exámenes y eventos futuros (7d, 3d, 1d, 0d)
        try:
            today = date.today()
            for ev in (events_resp.get("HomeWorks", []) or []):
                ev_date_str = ev.get("Date", "")
                if not ev_date_str:
                    continue
                try:
                    ev_date_obj = datetime.strptime(ev_date_str[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

                days_left = (ev_date_obj - today).days
                if days_left < 0 or days_left > 14:
                    continue

                eid = str(ev.get("Id"))

                milestone = None
                m_icon = "🔔"
                m_desc = ""

                if days_left in (6, 7):
                    milestone = "7d"
                    m_icon = "🔔"
                    m_desc = f"en {days_left} días"
                elif days_left in (2, 3):
                    milestone = "3d"
                    m_icon = "🔔"
                    m_desc = f"en {days_left} días"
                elif days_left == 1:
                    milestone = "1d"
                    m_icon = "⚠️"
                    m_desc = "¡MAÑANA!"
                elif days_left == 0:
                    milestone = "0d"
                    m_icon = "🎯"
                    m_desc = "¡HOY!"

                if milestone:
                    rem_key = f"ev:{eid}:{milestone}"
                    if eid in newly_added_events:
                        # Si acaba de ser notificado como nuevo evento hoy, marcamos el recordatorio para no duplicar
                        db.mark_item_known(username, "reminder", rem_key)
                    elif not db.is_item_known(username, "reminder", rem_key):
                        cid = ev.get("Category", {}).get("Id")
                        cat_raw = hw_cats.get(cid, "Evento")
                        cat_icon, cat_label = get_event_icon_and_type(cat_raw)
                        ev_content = ev.get("Content") or ""
                        ev_content_es = await self.translate_text(ev_content)
                        ev_date_fmt = format_calendar_date(ev_date_str)
                        time_part = f" ({ev.get('TimeFrom', '')} - {ev.get('TimeTo', '')})" if ev.get('TimeFrom') else ""

                        rem_msg = (
                            f"{tag} {m_icon} <b>RECORDATORIO: {cat_label.upper()} {m_desc}</b>\n"
                            f"🏷️ <b>Tipo:</b> {cat_icon} {cat_label}\n"
                            f"📆 <b>Fecha:</b> {ev_date_fmt}{time_part}\n\n"
                            f"📋 <b>Detalle:</b>\n{ev_content_es}"
                        )
                        messages.append((rem_msg, None))
                        db.mark_item_known(username, "reminder", rem_key)
        except Exception as e:
            print(f"[{student_name}] Error recordatorios exámenes: {e}")

        # 6. Recordatorios periódicos para entregas de tareas pendientes (7d, 3d, 1d, 0d)
        try:
            today = date.today()
            for hw in (hw_resp.get("HomeWorkAssignments", []) or []):
                due_date_str = hw.get("DueDate") or ""
                if not due_date_str:
                    continue
                try:
                    due_date_obj = datetime.strptime(due_date_str[:10], "%Y-%m-%d").date()
                except Exception:
                    continue

                days_left = (due_date_obj - today).days
                if days_left < 0 or days_left > 14:
                    continue

                hid = str(hw.get("Id"))

                milestone = None
                m_icon = "🔔"
                m_desc = ""

                if days_left in (6, 7):
                    milestone = "7d"
                    m_icon = "🔔"
                    m_desc = f"en {days_left} días"
                elif days_left in (2, 3):
                    milestone = "3d"
                    m_icon = "🔔"
                    m_desc = f"en {days_left} días"
                elif days_left == 1:
                    milestone = "1d"
                    m_icon = "⚠️"
                    m_desc = "¡MAÑANA!"
                elif days_left == 0:
                    milestone = "0d"
                    m_icon = "🎯"
                    m_desc = "¡HOY!"

                if milestone:
                    rem_key = f"hw:{hid}:{milestone}"
                    if hid in newly_added_hws:
                        db.mark_item_known(username, "reminder", rem_key)
                    elif not db.is_item_known(username, "reminder", rem_key):
                        hw_topic = hw.get("Topic") or "Sin tema"
                        hw_topic_es = await self.translate_text(hw_topic)
                        hw_text = hw.get("Text") or ""
                        hw_text_es = await self.translate_text(hw_text)
                        d_due = format_calendar_date(due_date_str)

                        rem_msg = (
                            f"{tag} {m_icon} <b>RECORDATORIO: ENTREGA DE TAREA {m_desc}</b>\n"
                            f"📌 <b>Tema:</b> {hw_topic_es}\n"
                            f"⏰ <b>Fecha límite:</b> {d_due}\n\n"
                            f"📄 <b>Instrucciones:</b>\n{hw_text_es}"
                        )
                        markup = {
                            "inline_keyboard": [
                                [
                                    {"text": "✅ Marcar como hecha", "callback_data": f"done:{username}:{hid}:0:es:0"}
                                ]
                            ]
                        }
                        messages.append((rem_msg, markup))
                        db.mark_item_known(username, "reminder", rem_key)
        except Exception as e:
            print(f"[{student_name}] Error recordatorios tareas: {e}")

        return messages

    async def run_check_for_chat(self, session: aiohttp.ClientSession, chat_id: int) -> int:
        pupils = db.get_pupils_for_chat(chat_id)
        if not pupils:
            return 0
        total_sent = 0
        for p in pupils:
            msgs = await self.check_librus_for_student(session, p)
            for m, markup in msgs:
                if await self.send_msg(session, chat_id, m, reply_markup=markup):
                    total_sent += 1
                await asyncio.sleep(0.3)
        return total_sent

    async def run_full_periodic_check(self, session: aiohttp.ClientSession) -> int:
        pupils = db.get_all_active_pupils()
        total_delivered = 0
        for p in pupils:
            u = p["librus_username"]
            recipients = db.get_chats_for_pupil(u)
            if not recipients:
                continue

            msgs = await self.check_librus_for_student(session, p)
            for m, markup in msgs:
                for cid in recipients:
                    if await self.send_msg(session, cid, m, reply_markup=markup):
                        total_delivered += 1
                    await asyncio.sleep(0.2)
        return total_delivered

    async def send_resumen(self, session: aiohttp.ClientSession, chat_id: int):
        pupils = db.get_pupils_for_chat(chat_id)
        if not pupils:
            await self.send_msg(session, chat_id, "No tienes ningún alumno configurado en este chat. Escribe /add_pupil para añadir a uno.")
            return

        # 1. BORRAR RESÚMENES ANTERIORES EN ESTE CHAT
        old_summary_msgs = db.get_summary_messages(chat_id)
        if old_summary_msgs:
            print(f"Borrando {len(old_summary_msgs)} mensajes de resúmenes anteriores en chat {chat_id}...")
            for m_id in old_summary_msgs:
                await self.delete_msg(session, chat_id, m_id)
                await asyncio.sleep(0.05)
            db.clear_summary_messages(chat_id)

        # 2. Mensaje de espera
        wait_msg_id = await self.send_msg(session, chat_id, "⏳ Consultando calificaciones, tareas y mensajes de los últimos 7 días en Librus...")
        if wait_msg_id:
            db.add_summary_message(chat_id, wait_msg_id)

        today = date.today()
        today_s = today.isoformat()
        cutoff_date = (today - timedelta(days=7)).isoformat()

        for p in pupils:
            u = p["librus_username"]
            pwd = p["password"]
            p_name = p.get("name", u)
            icon = p.get("icon", "👤")
            tag = f"<b>{icon} [{p_name.upper()}]</b>"

            client = LibrusApiClient(session, u)
            try:
                await client.async_login(pwd)
                await client.async_bootstrap_messages()
            except Exception as e:
                err_id = await self.send_msg(session, chat_id, f"{tag} ❌ Error al conectar con Librus: {e}")
                if err_id:
                    db.add_summary_message(chat_id, err_id)
                continue

            # Metadatos para traducción
            try:
                subs_resp = await client.async_get_subjects()
                subjects = {s["Id"]: s["Name"] for s in subs_resp.get("Subjects", [])}
                cats_resp = await client.async_get_grade_categories()
                categories = {c["Id"]: c["Name"] for c in cats_resp.get("Categories", [])}
                comms_resp = await client.async_get_grade_comments()
                comments = {c["Id"]: c["Text"] for c in comms_resp.get("Comments", [])}
            except Exception:
                subjects, categories, comments = {}, {}, {}

            # 1. Calificaciones de los últimos 7 días
            recent_grades = []
            try:
                grades_resp = await client.async_get_grades()
                for g in (grades_resp.get("Grades") or []):
                    add_d = (g.get("AddDate") or g.get("Date") or "")[:10]
                    if add_d >= cutoff_date:
                        recent_grades.append(g)
                recent_grades.sort(key=lambda x: x.get("AddDate") or x.get("Date") or "", reverse=True)
            except Exception as e:
                print(f"Error notas resumen {u}: {e}")

            # 2. Tareas pendientes VIGENTES (excluyendo caducadas con fecha anterior a hoy)
            completed_ids = db.get_completed_tasks(chat_id, u)
            pending_hw = []
            try:
                hw_resp = await client.async_get_homework_assignments()
                assignments = hw_resp.get("HomeWorkAssignments", []) or []
                for hw in assignments:
                    hid = str(hw.get("Id"))
                    if hid in completed_ids:
                        continue
                    due_date = (hw.get("DueDate") or "")[:10]
                    assign_date = (hw.get("Date") or "")[:10]
                    
                    # Si tiene fecha de entrega y ya ha vencido (es anterior a hoy), está caducada
                    if due_date and due_date < today_s:
                        continue
                    # Si no tiene fecha de entrega, comprobar que al menos la fecha de asignación no sea anterior a hoy
                    if not due_date and assign_date and assign_date < today_s:
                        continue
                    
                    pending_hw.append(hw)
            except Exception as e:
                print(f"Error tareas resumen {u}: {e}")

            # 3. Mensajes de los últimos 7 días
            recent_msgs = []
            try:
                msgs_resp = await client.async_get_messages(limit=25)
                raw_msgs = msgs_resp.get("data", []) or []
                for m in raw_msgs:
                    s_date = (m.get("sendDate") or "")[:10]
                    if s_date >= cutoff_date:
                        recent_msgs.append(m)
            except Exception as e:
                print(f"Error mensajes resumen {u}: {e}")

            # Encabezado del alumno
            header_text = (
                f"{tag} 📊 <b>Resumen de los últimos 7 días</b>\n"
                f"⭐ <b>Calificaciones obtenidas:</b> {len(recent_grades)}\n"
                f"📝 <b>Tareas pendientes (vigentes):</b> {len(pending_hw)}\n"
                f"✉️ <b>Mensajes recibidos:</b> {len(recent_msgs)}"
            )
            h_id = await self.send_msg(session, chat_id, header_text)
            if h_id:
                db.add_summary_message(chat_id, h_id)

            # A. Enviar Calificaciones Recientes en formato tabla ordenada de 3 columnas
            if recent_grades:
                table_rows = []
                comments_list = []
                for g in recent_grades:
                    sid = g.get("Subject", {}).get("Id")
                    cid = g.get("Category", {}).get("Id")
                    subj_full = translate_subject(subjects.get(sid, "General"))
                    # Extraer nombre limpio sin emoji para que la tabla monoespacio alinee perfecto
                    subj_name = subj_full.split(" ", 1)[-1] if " " in subj_full else subj_full
                    val = str(g.get("Grade", "")).strip()
                    add_d = (g.get("AddDate") or g.get("Date") or "")[:10]
                    fecha_str = "Hoy" if add_d == today_s else f"{add_d[8:10]}/{add_d[5:7]}"

                    cat_raw = categories.get(cid, "General")
                    cat = translate_grade_category(cat_raw)

                    table_rows.append({
                        "subj": subj_name[:17],
                        "grade": val[:4],
                        "fecha": fecha_str[:5]
                    })

                    g_comms = [comments.get(c["Id"], "") for c in g.get("Comments", []) if c.get("Id") in comments]
                    comm_list = []
                    for c_txt in g_comms:
                        if c_txt and c_txt.strip():
                            t_c = await self.translate_text(c_txt.strip())
                            comm_list.append(t_c if t_c else c_txt.strip())
                    if comm_list:
                        comments_list.append(f"• <b>{subj_full}</b> (<code>{val}</code> - {cat}): <i>{', '.join(comm_list)}</i>")

                table_content = [
                    f"{tag} ⭐ <b>Calificaciones recientes ({len(recent_grades)}):</b>\n",
                    "<pre>",
                    "ASIGNATURA         NOTA  FECHA",
                    "──────────────────────────────"
                ]
                for r in table_rows:
                    table_content.append(f"{r['subj']:<17}  {r['grade']:^4}  {r['fecha']:>5}")
                table_content.append("</pre>")

                if comments_list:
                    table_content.append("\n💬 <b>Comentarios:</b>\n" + "\n".join(comments_list))

                g_msg = "\n".join(table_content)
                g_id = await self.send_msg(session, chat_id, g_msg)
                if g_id:
                    db.add_summary_message(chat_id, g_id)
                await asyncio.sleep(0.2)
            else:
                m_id = await self.send_msg(session, chat_id, f"{tag} ⭐ <i>No hay nuevas calificaciones en los últimos 7 días.</i>")
                if m_id:
                    db.add_summary_message(chat_id, m_id)

            # B. Enviar tareas vigentes (traducidas al español por defecto)
            if pending_hw:
                for hw in sorted(pending_hw, key=lambda x: x.get("DueDate") or ""):
                    hid = str(hw.get("Id"))
                    topic = hw.get("Topic") or "Sin tema"
                    hw_text = hw.get("Text") or "Sin descripción"
                    assign_d = hw.get("Date") or "-"
                    due_d = hw.get("DueDate") or "-"

                    # Traducir texto de la tarea
                    hw_topic_es = await self.translate_text(topic)
                    hw_text_es = await self.translate_text(hw_text)

                    header_info = {
                        "tag": tag,
                        "topic": hw_topic_es,
                        "assign_d": format_calendar_date(assign_d),
                        "due_d": format_calendar_date(due_d)
                    }
                    cache_id = db.save_or_update_cache_card(
                        f"hw:{u}:{hid}", "hw", u, hid, header_info, hw_text, hw_text_es
                    )

                    cached_row = db.get_cached_card(cache_id)
                    card_text, markup = build_card_content(cached_row, chat_id, lang="es", expanded=False)

                    hw_msg_id = await self.send_msg(session, chat_id, card_text, reply_markup=markup)
                    if hw_msg_id:
                        db.add_summary_message(chat_id, hw_msg_id)
                    await asyncio.sleep(0.2)
            else:
                m_id = await self.send_msg(session, chat_id, f"{tag} ✨ <i>No hay tareas pendientes por entregar.</i>")
                if m_id:
                    db.add_summary_message(chat_id, m_id)

            # Enviar mensajes (traducidos al español por defecto)
            if recent_msgs:
                for m in recent_msgs:
                    mid = str(m.get("messageId"))
                    sender = m.get("senderName") or "Profesor/a"
                    topic = m.get("topic") or "(Sin asunto)"
                    s_date = (m.get("sendDate") or "").replace("T", " ")

                    # NOTA: Usamos exclusivamente el contenido del listado. NUNCA llamamos a async_get_message()
                    # para no marcar el mensaje como leído en Librus (preserva readDate null en el servidor).
                    content_parsed = decode_message_content(m.get("content") or "").strip()

                    # Traducir contenido del mensaje
                    content_es = await self.translate_text(content_parsed)

                    header_info = {
                        "tag": tag,
                        "sender": sender,
                        "topic": topic,
                        "date": s_date
                    }
                    cache_id = db.save_or_update_cache_card(
                        f"msg:{u}:{mid}", "msg", u, mid, header_info, content_parsed, content_es
                    )

                    cached_row = db.get_cached_card(cache_id)
                    card_text, markup = build_card_content(cached_row, chat_id, lang="es", expanded=False)

                    msg_card_id = await self.send_msg(session, chat_id, card_text, reply_markup=markup)
                    if msg_card_id:
                        db.add_summary_message(chat_id, msg_card_id)
                    await asyncio.sleep(0.2)
            else:
                m_id = await self.send_msg(session, chat_id, f"{tag} 📭 <i>No se han recibido mensajes en los últimos 7 días.</i>")
                if m_id:
                    db.add_summary_message(chat_id, m_id)

            await asyncio.sleep(0.3)

    async def send_calendario(self, session: aiohttp.ClientSession, chat_id: int):
        pupils = db.get_pupils_for_chat(chat_id)
        if not pupils:
            await self.send_msg(session, chat_id, "No tienes ningún alumno configurado en este chat. Escribe /add_pupil para añadir a uno.")
            return

        # 1. Borrar mensajes del calendario anterior en este chat
        old_cal_msgs = db.get_calendar_messages(chat_id)
        if old_cal_msgs:
            for m_id in old_cal_msgs:
                await self.delete_msg(session, chat_id, m_id)
                await asyncio.sleep(0.05)
            db.clear_calendar_messages(chat_id)

        # 2. Mensaje de espera
        wait_id = await self.send_msg(session, chat_id, "⏳ Consultando las entregas y exámenes de los próximos 7 días en Librus...")
        if wait_id:
            db.add_calendar_message(chat_id, wait_id)

        today = date.today()
        end_date = today + timedelta(days=7)
        today_s = today.isoformat()
        end_date_s = end_date.isoformat()

        # Encabezado principal
        cal_header = (
            f"📅 <b>CALENDARIO ESCOLAR (Próximos 7 días)</b>\n"
            f"🗓️ <i>Del {today.strftime('%d/%m')} al {end_date.strftime('%d/%m')}</i>\n"
            f"━━━━━━━━━━━━━━━━━━"
        )
        ch_id = await self.send_msg(session, chat_id, cal_header)
        if ch_id:
            db.add_calendar_message(chat_id, ch_id)

        for p in pupils:
            u = p["librus_username"]
            pwd = p["password"]
            p_name = p.get("name", u)
            icon = p.get("icon", "👤")
            tag = f"<b>{icon} [{p_name.upper()}]</b>"

            client = LibrusApiClient(session, u)
            try:
                await client.async_login(pwd)
            except Exception as e:
                err_id = await self.send_msg(session, chat_id, f"{tag} ❌ Error al conectar con Librus: {e}")
                if err_id:
                    db.add_calendar_message(chat_id, err_id)
                continue

            # Obtener asignaturas y categorías
            try:
                cats_resp = await client.async_get_homework_categories()
                cats = {cat["Id"]: cat["Name"] for cat in cats_resp.get("Categories", [])}
            except Exception:
                cats = {}
            try:
                subs_resp = await client.async_get_subjects()
                subs = {sub["Id"]: sub["Name"] for sub in subs_resp.get("Subjects", [])}
            except Exception:
                subs = {}

            # Recoger eventos/exámenes
            events: list[dict[str, Any]] = []
            try:
                ev_resp = await client.async_get_homeworks()
                for ev in (ev_resp.get("HomeWorks", []) or []):
                    d = ev.get("Date") or ""
                    if today_s <= d <= end_date_s:
                        cid = ev.get("Category", {}).get("Id")
                        cat_raw = cats.get(cid, "Evento")
                        sid = ev.get("Subject", {}).get("Id")
                        sub_raw = subs.get(sid, "General")
                        events.append({
                            "type": "event",
                            "date": d,
                            "date_formatted": format_calendar_date(d),
                            "time": f"{ev.get('TimeFrom', '')} - {ev.get('TimeTo', '')}".strip(" -"),
                            "cat_raw": cat_raw,
                            "subj_raw": sub_raw,
                            "content": (ev.get("Content") or "").strip(),
                        })
            except Exception as e:
                print(f"Error eventos {u}: {e}")

            # Recoger entregas de tareas
            try:
                hw_resp = await client.async_get_homework_assignments()
                completed_tasks = db.get_completed_tasks(chat_id, u)
                for hw in (hw_resp.get("HomeWorkAssignments", []) or []):
                    due_d = hw.get("DueDate") or ""
                    if today_s <= due_d <= end_date_s:
                        hid = str(hw.get("Id"))
                        sid = hw.get("Subject", {}).get("Id") if isinstance(hw.get("Subject"), dict) else None
                        sub_raw = subs.get(sid, "General") if sid else "General"
                        is_done = hid in completed_tasks
                        events.append({
                            "type": "hw",
                            "id": hid,
                            "date": due_d,
                            "time": "",
                            "cat_raw": "Zadanie domowe",
                            "subj_raw": sub_raw,
                            "content": f"{hw.get('Topic', '')}: {hw.get('Text', '')}".strip(": "),
                            "is_done": is_done,
                        })
            except Exception as e:
                print(f"Error tareas {u}: {e}")

            # Ordenar por fecha cronológicamente
            events.sort(key=lambda x: x["date"])

            if not events:
                no_ev_id = await self.send_msg(session, chat_id, f"{tag}\n✨ <i>No hay exámenes ni entregas programadas en los próximos 7 días.</i>")
                if no_ev_id:
                    db.add_calendar_message(chat_id, no_ev_id)
                await asyncio.sleep(0.2)
                continue

            # Construir mensaje de calendario para este alumno
            lines = [f"{tag} 📅 <b>Próximas entregas y exámenes:</b>\n"]
            detail_buttons = []
            for ev in events:
                d_formatted = format_calendar_date(ev["date"])
                ev_icon, cat_label = get_event_icon_and_type(ev["cat_raw"])
                subj_label = translate_subject(ev["subj_raw"])
                time_str = f" ({ev['time']})" if ev.get("time") else ""
                done_badge = " ✔ <i>(Completada)</i>" if ev.get("is_done") else ""

                content_raw = ev["content"]
                if content_raw:
                    content_es = await self.translate_text(content_raw)
                    if len(content_es) > 160:
                        content_disp = content_es[:160].rsplit(" ", 1)[0] + "..."
                    else:
                        content_disp = content_es
                    detail_str = f"\n  💬 <i>{content_disp}</i>\n"

                    # Botón para ver el detalle completo e íntegro
                    if len(content_raw.strip()) > 20:
                        ev_key = ev.get("id") or f"{ev['date']}_{ev['cat_raw'][:6]}"
                        header_info = {
                            "tag": tag,
                            "cat": f"{ev_icon} {cat_label}",
                            "subj": subj_label,
                            "date": d_formatted,
                            "time": ev.get("time", ""),
                        }
                        cache_id = db.save_or_update_cache_card(
                            f"cal:{u}:{ev_key}", "cal_ev", u, str(ev_key), header_info, content_raw, content_es
                        )

                        d_part = d_formatted.split(" ")[0][:3] + " " + d_formatted.split(" ")[1].split("/")[0]
                        clean_subj = subj_label.split(" ", 1)[-1] if " " in subj_label else subj_label
                        btn_topic = clean_subj if clean_subj != "General" else cat_label
                        btn_label = f"🔍 {d_part}: {btn_topic}"
                        if len(btn_label) > 28:
                            btn_label = btn_label[:27] + "…"
                        detail_buttons.append({"text": btn_label, "callback_data": f"cal_open:{cache_id}"})
                else:
                    detail_str = "\n"

                lines.append(f"• <b>{d_formatted}</b> | {ev_icon} <b>{cat_label}</b> ({subj_label}){time_str}{done_badge}{detail_str}")

            keyboard = []
            for i in range(0, len(detail_buttons), 2):
                keyboard.append(detail_buttons[i:i + 2])

            reply_markup = {"inline_keyboard": keyboard} if keyboard else None
            card_msg = "\n".join(lines)
            c_msg_id = await self.send_msg(session, chat_id, card_msg, reply_markup=reply_markup)
            if c_msg_id:
                db.add_calendar_message(chat_id, c_msg_id)
            await asyncio.sleep(0.3)

    async def send_notas(self, session: aiohttp.ClientSession, chat_id: int):
        pupils = db.get_pupils_for_chat(chat_id)
        if not pupils:
            await self.send_msg(session, chat_id, "No tienes ningún alumno configurado en este chat. Escribe /add_pupil para añadir a uno.")
            return

        # 1. Borrar boletines de notas anteriores en este chat
        old_msgs = db.get_grades_messages(chat_id)
        if old_msgs:
            for m_id in old_msgs:
                await self.delete_msg(session, chat_id, m_id)
                await asyncio.sleep(0.05)
            db.clear_grades_messages(chat_id)

        # 2. Mensaje de espera
        wait_id = await self.send_msg(session, chat_id, "⏳ Consultando las calificaciones y calculando promedios en Librus...")
        if wait_id:
            db.add_grades_message(chat_id, wait_id)

        cutoff = (date.today() - timedelta(days=7)).isoformat()

        # Encabezado principal
        header_text = (
            "📊 <b>BOLETÍN DE CALIFICACIONES Y PROMEDIOS</b>\n"
            "<i>Semestre actual de Librus</i>\n"
            "━━━━━━━━━━━━━━━━━━"
        )
        h_id = await self.send_msg(session, chat_id, header_text)
        if h_id:
            db.add_grades_message(chat_id, h_id)

        for p in pupils:
            u = p["librus_username"]
            pwd = p["password"]
            p_name = p.get("name", u)
            icon = p.get("icon", "👤")
            tag = f"<b>{icon} [{p_name.upper()}]</b>"

            client = LibrusApiClient(session, u)
            try:
                await client.async_login(pwd)
            except Exception as e:
                err_id = await self.send_msg(session, chat_id, f"{tag} ❌ Error al conectar con Librus: {e}")
                if err_id:
                    db.add_grades_message(chat_id, err_id)
                continue

            try:
                subs_resp = await client.async_get_subjects()
                subs = {sub["Id"]: sub["Name"] for sub in subs_resp.get("Subjects", [])}
                cats_resp = await client.async_get_grade_categories()
                cats = {cat["Id"]: cat for cat in cats_resp.get("Categories", [])}
                grades_resp = await client.async_get_grades()
                grades = grades_resp.get("Grades", [])
            except Exception as e:
                err_id = await self.send_msg(session, chat_id, f"{tag} ❌ Error al obtener calificaciones: {e}")
                if err_id:
                    db.add_grades_message(chat_id, err_id)
                continue

            if not grades:
                empty_id = await self.send_msg(session, chat_id, f"{tag}\n<i>No hay calificaciones registradas todavía este curso.</i>")
                if empty_id:
                    db.add_grades_message(chat_id, empty_id)
                await asyncio.sleep(0.2)
                continue

            # Agrupar por asignatura
            by_subj: dict[int, list[dict[str, Any]]] = {}
            for g in grades:
                sid = g.get("Subject", {}).get("Id")
                by_subj.setdefault(sid, []).append(g)

            subj_rows = []
            all_subj_averages = []

            for sid, s_grades in by_subj.items():
                s_name_raw = subs.get(sid, "General")
                subj_label = translate_subject(s_name_raw)

                # Ordenar cronológicamente
                s_grades_sorted = sorted(s_grades, key=lambda x: x.get("AddDate") or x.get("Date") or "")

                formatted_grades = []
                weighted_sum = 0.0
                total_weight = 0.0
                num_grades = []

                for g in s_grades_sorted:
                    g_val = str(g.get("Grade", "")).strip()
                    add_d = g.get("AddDate") or g.get("Date") or ""
                    is_recent = (add_d >= cutoff)

                    # En negrita si es de los últimos 7 días
                    if is_recent:
                        formatted_grades.append(f"<b>{g_val}</b>")
                    else:
                        formatted_grades.append(f"{g_val}")

                    cid = g.get("Category", {}).get("Id")
                    cat = cats.get(cid, {})
                    w = float(cat.get("Weight", 1) or 1)
                    if g_val in GRADE_NUMERIC_MAP and cat.get("CountToTheAverage", True) and w > 0:
                        val = GRADE_NUMERIC_MAP[g_val]
                        weighted_sum += val * w
                        total_weight += w
                        num_grades.append(val)

                if total_weight > 0:
                    subj_avg = weighted_sum / total_weight
                elif num_grades:
                    subj_avg = sum(num_grades) / len(num_grades)
                else:
                    subj_avg = None

                if subj_avg is not None:
                    all_subj_averages.append(subj_avg)
                    avg_suffix = f" → <b>{subj_avg:.2f}</b>"
                else:
                    avg_suffix = ""

                grades_str = "  ".join(formatted_grades)
                subj_rows.append((subj_label, f"• <b>{subj_label}</b>: {grades_str}{avg_suffix}"))

            # Ordenar asignaturas alfabéticamente
            subj_rows.sort(key=lambda x: x[0])

            lines = [f"{tag} <b>CALIFICACIONES</b>\n"]
            for _, r in subj_rows:
                lines.append(r)

            lines.append("━━━━━━━━━━━━━━━━━━")
            if all_subj_averages:
                final_avg = sum(all_subj_averages) / len(all_subj_averages)
                lines.append(f"🎯 <b>PROMEDIO GENERAL:</b> <b>{final_avg:.2f}</b> / 6.00")
            else:
                lines.append("🎯 <b>PROMEDIO GENERAL:</b> <i>Sin notas numéricas</i>")

            lines.append("ℹ️ <i>Las notas en <b>negrita</b> corresponden a los últimos 7 días.</i>")

            card_msg = "\n".join(lines)
            c_msg_id = await self.send_msg(session, chat_id, card_msg)
            if c_msg_id:
                db.add_grades_message(chat_id, c_msg_id)
            await asyncio.sleep(0.3)

    async def send_horario(self, session: aiohttp.ClientSession, chat_id: int):
        pupils = db.get_pupils_for_chat(chat_id)
        if not pupils:
            await self.send_msg(session, chat_id, "No tienes ningún alumno configurado en este chat. Escribe /add_pupil para añadir a uno.")
            return

        # 1. Borrar horarios anteriores en este chat
        old_msgs = db.get_timetable_messages(chat_id)
        if old_msgs:
            for m_id in old_msgs:
                await self.delete_msg(session, chat_id, m_id)
                await asyncio.sleep(0.05)
            db.clear_timetable_messages(chat_id)

        # 2. Mensaje de espera
        wait_id = await self.send_msg(session, chat_id, "⏳ Consultando los horarios de entrada y salida en Librus...")
        if wait_id:
            db.add_timetable_message(chat_id, wait_id)

        today = date.today()
        tomorrow = today + timedelta(days=1)

        days_to_check = [
            (today, "Hoy"),
            (tomorrow, "Mañana")
        ]

        # Si hoy y mañana caen en fin de semana, calcular también el próximo día lectivo (lunes)
        both_weekend = (today.weekday() >= 5 and tomorrow.weekday() >= 5)
        next_school_day = None
        if both_weekend:
            next_school_day = today + timedelta(days=(7 - today.weekday()))

        # Descargar los horarios de las semanas necesarias por alumno
        pupil_tts: dict[str, dict] = {}
        pupil_events: dict[str, list] = {}
        pupil_hw_cats: dict[str, dict] = {}
        for p in pupils:
            u = p["librus_username"]
            pwd = p["password"]
            client = LibrusApiClient(session, u)
            try:
                await client.async_login(pwd)
                weeks = set()
                for d, _ in days_to_check:
                    weeks.add(d - timedelta(days=d.weekday()))
                if next_school_day:
                    weeks.add(next_school_day - timedelta(days=next_school_day.weekday()))

                combined_tt = {}
                for w in weeks:
                    res = await client.async_get_timetable(w)
                    combined_tt.update(res.get("Timetable", {}))
                pupil_tts[u] = combined_tt

                try:
                    hw_cats_resp = await client.async_get_homework_categories()
                    pupil_hw_cats[u] = {c["Id"]: c["Name"] for c in hw_cats_resp.get("Categories", [])}
                except Exception:
                    pupil_hw_cats[u] = {}

                try:
                    ev_resp = await client.async_get_homeworks()
                    pupil_events[u] = ev_resp.get("HomeWorks", []) or []
                except Exception:
                    pupil_events[u] = []
            except Exception as e:
                print(f"Error horario {u}: {e}")
                pupil_tts[u] = {}
                pupil_events[u] = []
                pupil_hw_cats[u] = {}

        # Construir el mensaje formateado
        lines = [
            "⏰ <b>HORARIOS DE ENTRADA Y SALIDA</b>",
            "━━━━━━━━━━━━━━━━━━",
            ""
        ]

        sections = list(days_to_check)
        if next_school_day:
            sections.append((next_school_day, "Próximo día lectivo"))

        buttons = []
        for d, lbl in sections:
            d_str = d.isoformat()
            dia_nom = DIAS_SEMANA[d.weekday()]
            d_formatted = f"{dia_nom} {d.day:02d}/{d.month:02d}"

            if lbl == "Próximo día lectivo":
                lines.append("━━━━━━━━━━━━━━━━━━")
                lines.append(f"💡 <b>Próximo día lectivo ({d_formatted}):</b>")
            else:
                lines.append(f"📅 <b>{lbl} ({d_formatted}):</b>")

            day_has_classes = False
            for p in pupils:
                u = p["librus_username"]
                p_name = p["name"]
                icon = p.get("icon", "👤")
                tt = pupil_tts.get(u, {})
                day_evs = [e for e in pupil_events.get(u, []) if e.get("Date") == d_str]
                h_start, h_end, lessons = extract_day_schedule(tt, d_str, day_events=day_evs, hw_cats=pupil_hw_cats.get(u, {}))

                if h_start and h_end:
                    day_has_classes = True
                    active_lessons = [l for l in lessons if not l.get("IsCanceled") and not l.get("IsEvent")]
                    event_lessons = [l for l in lessons if l.get("IsEvent")]
                    canc_lessons = [l for l in lessons if l.get("IsCanceled")]
                    parts = []
                    if active_lessons:
                        parts.append(f"{len(active_lessons)} clases")
                    if event_lessons:
                        ev_icons = "".join(l.get("CategoryIcon", "📌") for l in event_lessons)
                        parts.append(f"{ev_icons} {len(event_lessons)} evento" if len(event_lessons) == 1 else f"{ev_icons} {len(event_lessons)} eventos")
                    if canc_lessons and not event_lessons:
                        parts.append(f"{len(canc_lessons)} canc.")
                    cnt_desc = ", ".join(parts) if parts else "0 clases"
                    lines.append(f"• {icon} <b>{p_name}:</b> <code>{h_start}</code> ➔ <b><code>{h_end}</code></b>  <i>({cnt_desc})</i>")
                else:
                    lines.append(f"• {icon} <b>{p_name}:</b> <i>Sin clases</i>")
            lines.append("")

            # Si este día tiene clases, crear un botón para ver el detalle de asignaturas
            if day_has_classes:
                detail_lines = [f"📚 <b>CLASES: {d_formatted} ({lbl})</b>\n"]
                for p in pupils:
                    u = p["librus_username"]
                    p_name = p["name"]
                    icon = p.get("icon", "👤")
                    tt = pupil_tts.get(u, {})
                    day_evs = [e for e in pupil_events.get(u, []) if e.get("Date") == d_str]
                    h_start, h_end, lessons = extract_day_schedule(tt, d_str, day_events=day_evs, hw_cats=pupil_hw_cats.get(u, {}))
                    if lessons:
                        detail_lines.append(f"{icon} <b>{p_name} ({h_start} - {h_end}):</b>")
                        for l in lessons:
                            h_from = l.get("HourFrom", "")
                            h_to = l.get("HourTo", "")
                            if l.get("IsEvent"):
                                s_trans = l.get("SubjectName", "Evento")
                                detail_lines.append(f"  • <code>{h_from}-{h_to}</code>: <b>{s_trans}</b>")
                            elif l.get("IsCanceled"):
                                s_name = l.get("Subject", {}).get("Name", "Clase")
                                s_trans = translate_subject(s_name)
                                detail_lines.append(f"  • <code>{h_from}-{h_to}</code>: <s>{s_trans}</s> <i>(Cancelada)</i>")
                            else:
                                s_name = l.get("Subject", {}).get("Name", "Clase")
                                s_trans = translate_subject(s_name)
                                classroom = l.get("Classroom", {}).get("Symbol", "") if isinstance(l.get("Classroom"), dict) else ""
                                room_str = f" <i>(Aula {classroom})</i>" if classroom else ""
                                detail_lines.append(f"  • <code>{h_from}-{h_to}</code>: {s_trans}{room_str}")
                        detail_lines.append("")
                    else:
                        detail_lines.append(f"{icon} <b>{p_name}:</b> <i>Sin clases</i>\n")

                detail_text = "\n".join(detail_lines)
                header_info = {"tag": "⏰ Horario", "date": d_formatted, "cat": lbl}
                cache_id = db.save_or_update_cache_card(
                    f"sched:{d_str}", "schedule", "all", d_str, header_info, detail_text, detail_text
                )
                btn_lbl = f"📚 Ver clases ({lbl.split()[0]} {d.day:02d}/{d.month:02d})"
                buttons.append([{"text": btn_lbl, "callback_data": f"cal_open:{cache_id}"}])

        reply_markup = {"inline_keyboard": buttons} if buttons else None
        h_msg = "\n".join(lines).strip()
        msg_id = await self.send_msg(session, chat_id, h_msg, reply_markup=reply_markup)
        if msg_id:
            db.add_timetable_message(chat_id, msg_id)

    async def clear_chat(self, session: aiohttp.ClientSession, chat_id: int | str, last_msg_id: int):
        """Borra todos los mensajes recientes posibles del chat (hasta el límite de 48h de Telegram)."""
        self.user_sessions.pop(chat_id, None)
        db.clear_summary_messages(chat_id)
        db.clear_calendar_messages(chat_id)
        db.clear_grades_messages(chat_id)
        db.clear_timetable_messages(chat_id)
        try:
            db.delete_all_chat_messages(int(chat_id))
        except Exception:
            pass

        # Telegram solo permite a los bots borrar mensajes de menos de 48 horas de antigüedad.
        # Recorremos hacia atrás desde el ID del mensaje del comando /clear
        batch_size = 100
        current = last_msg_id
        consecutive_failures = 0
        max_messages_to_check = 1000

        while current > 0 and (last_msg_id - current) < max_messages_to_check:
            batch = list(range(current, max(0, current - batch_size), -1))
            if not batch:
                break

            # Intentar borrado por lote
            ok = await self.delete_messages(session, chat_id, batch)
            if ok:
                current -= batch_size
                await asyncio.sleep(0.05)
                continue

            # Si el lote completo falla (p.ej. abarca mensajes >48h o ya borrados), probar uno a uno
            for mid in batch:
                deleted = await self.delete_msg(session, chat_id, mid)
                if deleted:
                    consecutive_failures = 0
                else:
                    consecutive_failures += 1

                # Si fallan muchos mensajes consecutivos, se alcanzó el límite temporal de 48h
                if consecutive_failures >= 25:
                    break
                await asyncio.sleep(0.02)

            if consecutive_failures >= 25:
                break
            current -= batch_size

        await self.send_msg(
            session,
            chat_id,
            "🧹 <b>Chat limpiado con éxito.</b>\n\n"
            "Se han eliminado los mensajes recientes (dentro del límite de 48h permitido por Telegram).\n"
            "Escribe <b>/resumen</b> para ver las tareas y mensajes de Librus, o <b>/help</b> para ver los comandos."
        )

    async def prune_expired_messages(self, session: aiohttp.ClientSession, hours: float = 45.0):
        """Purga automáticamente mensajes anteriores a 45 horas para no superar el límite de 48h de Telegram."""
        expired = db.get_messages_older_than(hours=hours)
        if not expired:
            return

        by_chat: dict[int, list[int]] = {}
        for r in expired:
            by_chat.setdefault(r["chat_id"], []).append(r["message_id"])

        deleted_records: list[tuple[int, int]] = []
        for cid, mids in by_chat.items():
            for i in range(0, len(mids), 100):
                chunk = mids[i:i + 100]
                ok = await self.delete_messages(session, cid, chunk)
                if not ok:
                    for mid in chunk:
                        await self.delete_msg(session, cid, mid)
                        await asyncio.sleep(0.02)
                deleted_records.extend([(cid, mid) for mid in chunk])
                await asyncio.sleep(0.05)

        if deleted_records:
            db.delete_chat_message_records(deleted_records)
            print(f"[{datetime.now().strftime('%H:%M:%S')}] Purgados {len(deleted_records)} mensajes antiguos (> {hours}h).")

    async def handle_callback_query(self, session: aiohttp.ClientSession, cq: dict[str, Any]):
        cq_id = cq.get("id")
        msg = cq.get("message", {})
        chat_id = msg.get("chat", {}).get("id")
        msg_id = msg.get("message_id")
        data = (cq.get("data") or "").strip()

        if not chat_id or not cq_id or not data:
            return

        # ACCIONES DE TARJETAS (Ver más / Ver menos / Ver original / Ver traducido)
        if data.startswith("card:"):
            parts = data.split(":")
            if len(parts) >= 4:
                cache_id = int(parts[1])
                target_lang = parts[2]
                target_expanded = bool(int(parts[3]))

                cached = db.get_cached_card(cache_id)
                if cached:
                    # Asegurar traducción al español si se pide y aún no existe o si falló anteriormente
                    tr_saved = (cached.get("translated_text") or "").strip()
                    orig_saved = (cached.get("original_text") or "").strip()
                    if target_lang == "es" and (not tr_saved or (tr_saved == orig_saved and len(orig_saved) > 30)):
                        tr = await self.translate_text(orig_saved)
                        db.update_cache_translation(cache_id, tr)
                        cached = db.get_cached_card(cache_id)

                    card_text, markup = build_card_content(cached, chat_id, lang=target_lang, expanded=target_expanded)
                    await self.edit_message_text(session, chat_id, msg_id, card_text, reply_markup=markup)
                    feedback = "Mostrando versión traducida 🇪🇸" if target_lang == "es" else "Mostrando versión original 🇵🇱"
                    await self.answer_callback_query(session, cq_id, feedback)
            return

        # MARCAR TAREA COMO HECHA
        elif data.startswith("done:"):
            parts = data.split(":")
            if len(parts) >= 3:
                pupil_username = parts[1]
                task_id = parts[2]
                cache_id = int(parts[3]) if len(parts) > 3 else None
                current_lang = parts[4] if len(parts) > 4 else "es"
                current_exp = bool(int(parts[5])) if len(parts) > 5 else False

                db.mark_task_completed(chat_id, pupil_username, task_id)
                await self.answer_callback_query(session, cq_id, "✅ ¡Tarea marcada como hecha! No volverá a aparecer en el resumen.")

                if cache_id:
                    cached = db.get_cached_card(cache_id)
                    if cached:
                        card_text, markup = build_card_content(cached, chat_id, lang=current_lang, expanded=current_exp)
                        await self.edit_message_text(session, chat_id, msg_id, card_text, reply_markup=markup)
            return

        # DESMARCAR TAREA
        elif data.startswith("undone:"):
            parts = data.split(":")
            if len(parts) >= 3:
                pupil_username = parts[1]
                task_id = parts[2]
                cache_id = int(parts[3]) if len(parts) > 3 else None
                current_lang = parts[4] if len(parts) > 4 else "es"
                current_exp = bool(int(parts[5])) if len(parts) > 5 else False

                db.unmark_task_completed(chat_id, pupil_username, task_id)
                await self.answer_callback_query(session, cq_id, "↩️ Tarea desmarcada. Volverá a aparecer en tu resumen.")

                if cache_id:
                    cached = db.get_cached_card(cache_id)
                    if cached:
                        card_text, markup = build_card_content(cached, chat_id, lang=current_lang, expanded=current_exp)
                        await self.edit_message_text(session, chat_id, msg_id, card_text, reply_markup=markup)
            return

        # ABRIR DETALLE DE EVENTO / EXAMEN DE CALENDARIO
        elif data.startswith("cal_open:"):
            cache_id = int(data.split(":")[1])
            cached = db.get_cached_card(cache_id)
            if cached:
                tr_saved = (cached.get("translated_text") or "").strip()
                orig_saved = (cached.get("original_text") or "").strip()
                if not tr_saved or (tr_saved == orig_saved and len(orig_saved) > 30):
                    tr_saved = await self.translate_text(orig_saved)
                    db.update_cache_translation(cache_id, tr_saved)
                    cached = db.get_cached_card(cache_id)

                card_text, markup = build_card_content(cached, chat_id, lang="es", expanded=True)
                sent_id = await self.send_msg(session, chat_id, card_text, reply_markup=markup)
                if sent_id:
                    db.add_calendar_message(chat_id, sent_id)
                await self.answer_callback_query(session, cq_id, "Mostrando detalle...")
            return

        # CERRAR MENSAJE DE DETALLE
        elif data == "del_msg":
            await self.delete_msg(session, chat_id, msg_id)
            await self.answer_callback_query(session, cq_id, "Detalle cerrado")
            return

    async def handle_message(self, session: aiohttp.ClientSession, msg: dict[str, Any]):
        chat = msg.get("chat", {})
        chat_id = chat.get("id")
        from_user = msg.get("from", {})
        first_name = from_user.get("first_name", "")
        last_name = from_user.get("last_name", "")
        tg_username = from_user.get("username", "")
        text = (msg.get("text") or "").strip()

        if not chat_id or not text:
            return

        mid = msg.get("message_id")
        if mid:
            try:
                db.record_chat_message(int(chat_id), mid)
            except Exception:
                pass

        chat_row = db.register_or_update_chat(chat_id, first_name, last_name, tg_username)
        is_auth = bool(chat_row.get("is_authorized"))

        user_sess = self.user_sessions.setdefault(chat_id, {})
        step = user_sess.get("step")

        # 1. VERIFICACIÓN DE AUTORIZACIÓN
        current_auth_pass = db.get_auth_password()
        if not is_auth:
            if text.strip() == current_auth_pass or text.strip().lower() == current_auth_pass.lower():
                db.authorize_chat(chat_id)
                user_sess.clear()
                welcome = (
                    f"🎉 <b>¡Acceso autorizado correctamente!</b>\n\n"
                    f"👋 Bienvenido/a <b>{first_name}</b>. Este chat ya tiene permisos activos.\n\n"
                    f"Para dar de alta a tus propios alumnos escolares, escribe el comando:\n"
                    f"➕ <b>/add_pupil</b>\n\n"
                    f"<i>Las notas, deberes y exámenes de los alumnos que agregues solo te llegarán a ti.</i>"
                )
                await self.send_msg(session, chat_id, welcome)
                return
            else:
                user_sess["step"] = "AWAITING_AUTH_PASSWORD"
                prompt = (
                    f"🔐 <b>Acceso protegido - Librus Notifier</b>\n\n"
                    f"Hola {first_name}, para poder utilizar este bot y configurar a tus alumnos, "
                    f"por favor escribe la <b>clave de autorización</b>:"
                )
                await self.send_msg(session, chat_id, prompt)
                return

        # 2. CANCELACIÓN
        if text in ["/cancel", "/cancelar", "cancelar"]:
            self.user_sessions.pop(chat_id, None)
            await self.send_msg(session, chat_id, "❌ Operación cancelada. Escribe /help para ver opciones.")
            return

        # 3. FLUJO INTERACTIVO /add_pupil
        if step == "AWAITING_USERNAME":
            login = text.strip()
            user_sess["temp_user"] = login
            user_sess["step"] = "AWAITING_PASSWORD"
            await self.send_msg(session, chat_id, f"🔑 Usuario recibido: <code>{login}</code>\n\nAhora introduce la <b>contraseña de Librus</b>:")
            return

        elif step == "AWAITING_PASSWORD":
            pwd = text.strip()
            login = user_sess.get("temp_user")
            await self.send_msg(session, chat_id, f"⏳ Conectando con Librus para verificar credenciales de <code>{login}</code>...")

            test_client = LibrusApiClient(session, login)
            try:
                await test_client.async_login(pwd)
                me_resp = await test_client.async_get_me()
                user_info = me_resp.get("Me", {}).get("User", {})
                first_name_librus = user_info.get("FirstName", "").strip()
                last_name_librus = user_info.get("LastName", "").strip()
                student_display_name = f"{first_name_librus} {last_name_librus}".strip() or login

                icon = "👧" if first_name_librus.endswith("a") else "👦"

                db.upsert_pupil(login, pwd, student_display_name, icon, is_active=1)
                db.link_chat_pupil(chat_id, login)
                self.user_sessions.pop(chat_id, None)

                success_msg = (
                    f"🎉 <b>¡Alumno añadido con éxito a tu cuenta!</b>\n\n"
                    f"👤 <b>Nombre:</b> {icon} {student_display_name}\n"
                    f"🆔 <b>Usuario:</b> <code>{login}</code>\n\n"
                    f"Recibirás aquí sus calificaciones, tareas y exámenes automáticamente.\n"
                    f"Puedes consultar el resumen de tareas enviando /resumen"
                )
                await self.send_msg(session, chat_id, success_msg)

            except LibrusInvalidCredentialsError:
                await self.send_msg(session, chat_id, "❌ <b>Error:</b> Usuario o contraseña incorrectos en Librus.\nPor favor, prueba de nuevo con /add_pupil")
                self.user_sessions.pop(chat_id, None)
            except LibrusCaptchaRequiredError:
                await self.send_msg(session, chat_id, "⚠️ <b>Aviso:</b> Librus requiere resolver un Captcha temporal en su web.\nInicia sesión una vez desde el navegador y vuelve a intentarlo.")
                self.user_sessions.pop(chat_id, None)
            except Exception as e:
                await self.send_msg(session, chat_id, f"❌ Error al conectar con Librus: {e}\nInténtalo de nuevo con /add_pupil")
                self.user_sessions.pop(chat_id, None)
            return

        # 4. COMANDOS GENERALES
        cmd = text.split()[0].lower()
        args = text.split()[1:]
        is_admin = (chat_id == db.get_admin_chat_id())

        # COMANDOS DE ADMINISTRADOR
        if cmd in ["/clave", "/password", "/get_password", "/ver_clave"]:
            if not is_admin:
                await self.send_msg(session, chat_id, "⛔ <b>Acceso denegado:</b> Solo el administrador puede consultar la clave de registro.")
                return
            current_pass = db.get_auth_password()
            msg_text = (
                f"🔑 <b>Clave de autorización actual:</b>\n"
                f"<code>{current_pass}</code>\n\n"
                f"Para cambiarla, usa: <code>/set_clave nueva_clave</code>"
            )
            await self.send_msg(session, chat_id, msg_text)
            return

        elif cmd in ["/set_clave", "/set_password", "/cambiar_clave"]:
            if not is_admin:
                await self.send_msg(session, chat_id, "⛔ <b>Acceso denegado:</b> Solo el administrador puede modificar la clave de registro.")
                return
            if not args:
                await self.send_msg(session, chat_id, "⚠️ Debes indicar la nueva clave.\nEjemplo: <code>/set_clave miNuevaClaveSegura</code>")
                return
            new_pass = args[0].strip()
            db.set_auth_password(new_pass)
            await self.send_msg(session, chat_id, f"✅ <b>Clave de registro actualizada con éxito:</b>\n<code>{new_pass}</code>\n\nA partir de ahora los nuevos móviles deberán introducir esta clave para darse de alta.")
            return

        elif cmd in ["/traducir", "/translate"]:
            reply_msg = msg.get("reply_to_message")
            text_to_translate = ""
            if reply_msg and reply_msg.get("text"):
                text_to_translate = reply_msg["text"]
            elif args:
                text_to_translate = " ".join(args)

            if not text_to_translate:
                await self.send_msg(session, chat_id, "ℹ️ <b>Cómo traducir:</b>\n• Responde a cualquier mensaje con <code>/traducir</code>\n• O escribe: <code>/traducir &lt;texto en polaco&gt;</code>")
                return

            translated = await self.translate_text(text_to_translate)
            await self.send_msg(session, chat_id, f"🌐 <b>Traducción al español:</b>\n\n{translated}")
            return

        elif cmd in ["/resumen", "/summary", "resumen"]:
            await self.send_resumen(session, chat_id)
            return

        elif cmd in ["/calendario", "/calendar", "/agenda", "/examenes", "calendario", "agenda", "examenes"]:
            await self.send_calendario(session, chat_id)
            return

        elif cmd in ["/notas", "/calificaciones", "/boletin", "/grades", "notas", "calificaciones", "boletin", "grades"]:
            await self.send_notas(session, chat_id)
            return

        elif cmd in ["/horario", "/horarios", "/schedule", "horario", "horarios", "schedule"]:
            await self.send_horario(session, chat_id)
            return

        elif cmd in ["/clear", "/limpiar", "/borrar", "/borrar_chat", "clear", "limpiar"]:
            await self.clear_chat(session, chat_id, msg.get("message_id", 0))
            return

        elif cmd in ["/start", "/help", "/ayuda"]:
            pupils = db.get_pupils_for_chat(chat_id)
            if pupils:
                pupils_list = "\n".join([f"• {p['icon']} <b>{p['name']}</b> (<code>{p['librus_username']}</code>)" for p in pupils])
            else:
                pupils_list = "<i>No tienes ningún alumno configurado todavía.</i>"

            admin_section = ""
            if is_admin:
                admin_section = (
                    "\n\n👑 <b>Opciones de Administrador:</b>\n"
                    "🔑 /clave - Consultar la contraseña actual\n"
                    "✏️ /set_clave &lt;nueva&gt; - Cambiar la contraseña"
                )

            welcome_text = (
                f"👋 <b>¡Hola {first_name}!</b>\n\n"
                f"📋 <b>Tus alumnos vinculados en este chat:</b>\n{pupils_list}\n\n"
                f"<b>Comandos disponibles:</b>\n"
                f"📊 /resumen - Ver tareas y mensajes de los últimos 7 días\n"
                f"📅 /calendario - Exámenes y entregas de los próximos 7 días\n"
                f"⏰ /horario - Hora de entrada y salida (hoy y mañana)\n"
                f"📈 /notas - Calificaciones, promedios y notas recientes\n"
                f"🧹 /clear - Limpiar mensajes del chat\n"
                f"🌐 /traducir &lt;texto&gt; - Traducir texto al español\n"
                f"➕ /add_pupil - Añadir a tu propio alumno\n"
                f"👥 /pupils - Ver tus alumnos\n"
                f"🔍 /check - Comprobar notas y tareas ahora\n"
                f"❌ /cancel - Cancelar operación en curso"
                f"{admin_section}"
            )
            await self.send_msg(session, chat_id, welcome_text)

        elif cmd in ["/add_pupil", "/add_student", "/anadir_alumno"]:
            user_sess["step"] = "AWAITING_USERNAME"
            prompt = (
                "📚 <b>Añadir nuevo alumno a tu cuenta</b>\n\n"
                "Por favor, escribe el <b>nombre de usuario de Librus</b> (login numérico, ej: <code>12345678</code>):\n\n"
                "<i>(Puedes cancelar en cualquier momento con /cancel)</i>"
            )
            await self.send_msg(session, chat_id, prompt)

        elif cmd in ["/pupils", "/alumnos", "/students"]:
            pupils = db.get_pupils_for_chat(chat_id)
            if not pupils:
                await self.send_msg(session, chat_id, "No tienes ningún alumno configurado en este chat. Escribe /add_pupil para añadir a uno.")
                return
            lines = ["👥 <b>Tus alumnos configurados:</b>\n"]
            for idx, s in enumerate(pupils, 1):
                icon = s.get("icon", "👤")
                name = s.get("name", s.get("librus_username"))
                user = s.get("librus_username")
                lines.append(f"{idx}. {icon} <b>{name}</b> (<code>{user}</code>)")
            lines.append("\nPuedes consultar el resumen con /resumen o añadir más con /add_pupil")
            await self.send_msg(session, chat_id, "\n".join(lines))

        elif cmd in ["/check", "/revisar", "/comprobar"]:
            await self.send_msg(session, chat_id, "🔍 Comprobando novedades en Librus para tus alumnos...")
            sent = await self.run_check_for_chat(session, chat_id)
            if sent == 0:
                await self.send_msg(session, chat_id, "✨ No hay nuevas calificaciones, deberes ni exámenes pendientes para tus alumnos.")

    async def start(self):
        self.log_event("Bot de Librus iniciado.")
        total_p = len(db.get_all_active_pupils())
        self.log_event(f"Total alumnos en BD: {total_p}")

        # Iniciar Servidor Web del Panel de Control en puerto 8088
        panel = web_panel.WebPanel(self)
        web_runner = web.AppRunner(panel.app)
        await web_runner.setup()
        web_port = int(os.environ.get("LIBRUS_WEB_PORT", "8088"))
        web_site = web.TCPSite(web_runner, "0.0.0.0", web_port)
        await web_site.start()
        self.log_event(f"Panel de control web escuchando en http://0.0.0.0:{web_port}")

        async with aiohttp.ClientSession() as session:
            self.session = session

            # Carga inicial del resumen para el dashboard web
            asyncio.create_task(self.refresh_dashboard_overview())

            # Purga inicial de mensajes anteriores a 45h
            try:
                await self.prune_expired_messages(session, hours=45.0)
            except Exception as e:
                self.log_event(f"Error en purga inicial: {e}")

            # Tarea periódica de comprobación con intervalo dinámico
            async def periodic_worker():
                while True:
                    interval_mins = int(db.get_setting("check_interval_minutes", "15"))
                    interval_secs = max(60, interval_mins * 60)
                    try:
                        await asyncio.wait_for(self.force_check_event.wait(), timeout=interval_secs)
                        self.force_check_event.clear()
                    except asyncio.TimeoutError:
                        pass

                    try:
                        self.log_event("Ejecutando revisión periódica automática...")
                        delivered = await self.run_full_periodic_check(session)
                        self.last_check_time = datetime.now().strftime("%d/%m/%Y %H:%M:%S")
                        self.log_event(f"Revisión periódica completada. Novedades enviadas: {delivered}")
                        await self.refresh_dashboard_overview()
                        await self.prune_expired_messages(session, hours=45.0)
                    except Exception as e:
                        self.log_event(f"Error en revisión periódica: {e}")

            asyncio.create_task(periodic_worker())

            # Bucle de polling de Telegram
            while True:
                try:
                    url = f"https://api.telegram.org/bot{self.bot_token}/getUpdates?offset={self.last_update_id + 1}&timeout=20"
                    async with session.get(url, timeout=30) as resp:
                        if resp.status == 200:
                            data = await resp.json()
                            if data.get("ok"):
                                for update in data.get("result", []):
                                    self.last_update_id = update["update_id"]
                                    if "message" in update:
                                        await self.handle_message(session, update["message"])
                                    elif "callback_query" in update:
                                        await self.handle_callback_query(session, update["callback_query"])
                        elif resp.status in [409, 502, 504]:
                            await asyncio.sleep(2)
                        else:
                            await asyncio.sleep(5)
                except asyncio.CancelledError:
                    break
                except Exception as e:
                    await asyncio.sleep(3)


if __name__ == "__main__":
    bot = LibrusTelegramBot()
    try:
        asyncio.run(bot.start())
    except KeyboardInterrupt:
        print("\nBot detenido.")
