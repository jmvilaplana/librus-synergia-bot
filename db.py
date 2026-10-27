"""
Módulo de base de datos SQLite para Librus Synergia Notifier con multi-familia.
Gestiona chats autorizados por contraseña por clave configurable y alumnos por usuario.
"""

from __future__ import annotations

import sqlite3
import os
import json
from datetime import datetime, timedelta
from typing import Any

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_FILE = os.path.join(BASE_DIR, "librus.db")
CONFIG_FILE = os.path.join(BASE_DIR, "librus_config.json")
AUTH_PASSWORD_DEFAULT = os.environ.get("LIBRUS_AUTH_PASSWORD", "changeme")
ADMIN_CHAT_ID_DEFAULT = int(os.environ.get("LIBRUS_ADMIN_CHAT_ID", "0"))


def get_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    conn = get_connection()
    cur = conn.cursor()

    # 1. Settings
    cur.execute("""
    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT
    )
    """)

    # 2. Chats / Dispositivos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chats (
        chat_id INTEGER PRIMARY KEY,
        first_name TEXT,
        last_name TEXT,
        username TEXT,
        is_authorized INTEGER DEFAULT 0,
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    # 3. Alumnos
    cur.execute("""
    CREATE TABLE IF NOT EXISTS pupils (
        librus_username TEXT PRIMARY KEY,
        password TEXT NOT NULL,
        name TEXT NOT NULL,
        icon TEXT DEFAULT '👤',
        is_active INTEGER DEFAULT 1,
        created_at TEXT
    )
    """)

    # 4. Relación chat <-> alumno (qué chats reciben los avisos de qué alumnos)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_pupils (
        chat_id INTEGER NOT NULL,
        pupil_username TEXT NOT NULL,
        created_at TEXT,
        PRIMARY KEY (chat_id, pupil_username)
    )
    """)

    # 5. Historial de notificaciones ya enviadas
    cur.execute("""
    CREATE TABLE IF NOT EXISTS notifications (
        pupil_username TEXT,
        item_type TEXT,
        item_id TEXT,
        created_at TEXT,
        PRIMARY KEY (pupil_username, item_type, item_id)
    )
    """)

    # 6. Tareas marcadas como completadas / hechas por el usuario
    cur.execute("""
    CREATE TABLE IF NOT EXISTS completed_tasks (
        chat_id INTEGER NOT NULL,
        pupil_username TEXT NOT NULL,
        task_id TEXT NOT NULL,
        completed_at TEXT,
        PRIMARY KEY (chat_id, pupil_username, task_id)
    )
    """)

    # 7. Caché de mensajes y traducciones
    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages_cache (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        msg_key TEXT UNIQUE,
        card_type TEXT DEFAULT 'msg',
        header_info TEXT,
        pupil_username TEXT,
        item_id TEXT,
        original_text TEXT NOT NULL,
        translated_text TEXT,
        created_at TEXT
    )
    """)

    # 8. Mensajes temporales de resúmenes (para borrarlos al pedir uno nuevo)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS summary_messages (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        created_at TEXT,
        PRIMARY KEY (chat_id, message_id)
    )
    """)

    # 9. Registro de mensajes en chats para purga automática tras 45 horas
    cur.execute("""
    CREATE TABLE IF NOT EXISTS chat_messages (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        created_at TEXT NOT NULL,
        PRIMARY KEY (chat_id, message_id)
    )
    """)

    # 10. Mensajes temporales de calendario (para borrarlos al pedir uno nuevo)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS calendar_messages (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        created_at TEXT,
        PRIMARY KEY (chat_id, message_id)
    )
    """)

    # 11. Mensajes temporales de notas (para borrarlos al pedir uno nuevo)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS grades_messages (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        created_at TEXT,
        PRIMARY KEY (chat_id, message_id)
    )
    """)

    # 12. Mensajes temporales de horario (para borrarlos al pedir uno nuevo)
    cur.execute("""
    CREATE TABLE IF NOT EXISTS timetable_messages (
        chat_id INTEGER NOT NULL,
        message_id INTEGER NOT NULL,
        created_at TEXT,
        PRIMARY KEY (chat_id, message_id)
    )
    """)

    conn.commit()

    # Comprobar columnas en messages_cache
    cur.execute("PRAGMA table_info(messages_cache)")
    cache_cols = [col["name"] for col in cur.fetchall()]
    if "card_type" not in cache_cols:
        cur.execute("ALTER TABLE messages_cache ADD COLUMN card_type TEXT DEFAULT 'msg'")
    if "header_info" not in cache_cols:
        cur.execute("ALTER TABLE messages_cache ADD COLUMN header_info TEXT")
    if "pupil_username" not in cache_cols:
        cur.execute("ALTER TABLE messages_cache ADD COLUMN pupil_username TEXT")
    if "item_id" not in cache_cols:
        cur.execute("ALTER TABLE messages_cache ADD COLUMN item_id TEXT")
    conn.commit()

    # Inicializar contraseña de registro y admin si no existen
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('auth_password', ?)", (AUTH_PASSWORD_DEFAULT,))
    cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES ('admin_chat_id', ?)", (str(ADMIN_CHAT_ID_DEFAULT),))
    conn.commit()

    # Comprobar columnas en chats
    cur.execute("PRAGMA table_info(chats)")
    cols = [col["name"] for col in cur.fetchall()]
    if "is_authorized" not in cols:
        cur.execute("ALTER TABLE chats ADD COLUMN is_authorized INTEGER DEFAULT 0")
        conn.commit()
    if "auto_translate" not in cols:
        cur.execute("ALTER TABLE chats ADD COLUMN auto_translate INTEGER DEFAULT 0")
        conn.commit()

    # Auto-importar configuración inicial desde librus_config.json si existe
    import_config_if_exists(conn)

    conn.commit()
    conn.close()


def get_setting(key: str, default: str = "") -> str:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key = ?", (key,))
    row = cur.fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, value))
    conn.commit()
    conn.close()


def get_auth_password() -> str:
    return get_setting("auth_password", AUTH_PASSWORD_DEFAULT)


def set_auth_password(new_pass: str) -> None:
    set_setting("auth_password", new_pass.strip())


def get_admin_chat_id() -> int:
    try:
        return int(get_setting("admin_chat_id", str(ADMIN_CHAT_ID_DEFAULT)))
    except Exception:
        return ADMIN_CHAT_ID_DEFAULT


def get_chat(chat_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def register_or_update_chat(chat_id: int, first_name: str = "", last_name: str = "", username: str = "") -> dict[str, Any]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
    existing = cur.fetchone()
    now_str = datetime.now().isoformat()

    if existing:
        cur.execute("""
        UPDATE chats SET first_name = ?, last_name = ?, username = ?
        WHERE chat_id = ?
        """, (first_name, last_name, username, chat_id))
        conn.commit()
        cur.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row)
    else:
        # Nuevo chat: no autorizado por defecto a menos que coincida con admin_chat_id
        admin_id_str = get_setting("admin_chat_id", "0")
        admin_id = int(admin_id_str) if admin_id_str.isdigit() else 0
        auth = 1 if (admin_id and chat_id == admin_id) else 0
        cur.execute("""
        INSERT INTO chats (chat_id, first_name, last_name, username, is_authorized, is_active, created_at)
        VALUES (?, ?, ?, ?, ?, 1, ?)
        """, (chat_id, first_name, last_name, username, auth, now_str))
        conn.commit()
        cur.execute("SELECT * FROM chats WHERE chat_id = ?", (chat_id,))
        row = cur.fetchone()
        conn.close()
        return dict(row)


def authorize_chat(chat_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE chats SET is_authorized = 1 WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def is_chat_authorized(chat_id: int) -> bool:
    chat = get_chat(chat_id)
    return bool(chat and chat.get("is_authorized"))


def link_chat_pupil(chat_id: int, pupil_username: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO chat_pupils (chat_id, pupil_username, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, pupil_username, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def unlink_chat_pupil(chat_id: int, pupil_username: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_pupils WHERE chat_id = ? AND pupil_username = ?", (chat_id, pupil_username))
    conn.commit()
    conn.close()


def get_pupils_for_chat(chat_id: int) -> list[dict[str, Any]]:
    """Devuelve solo los alumnos vinculados a este chat, ordenados por ID (antiguo a nuevo)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT p.librus_username, p.password, p.name, p.icon, p.is_active
    FROM pupils p
    INNER JOIN chat_pupils cp ON cp.pupil_username = p.librus_username
    WHERE cp.chat_id = ? AND p.is_active = 1
    ORDER BY CAST(p.librus_username AS INTEGER) ASC
    """, (chat_id,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def get_chats_for_pupil(pupil_username: str) -> list[int]:
    """Devuelve la lista de chat_ids autorizados que deben recibir notificaciones de este alumno."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT cp.chat_id
    FROM chat_pupils cp
    INNER JOIN chats c ON c.chat_id = cp.chat_id
    WHERE cp.pupil_username = ? AND c.is_authorized = 1 AND c.is_active = 1
    """, (pupil_username,))
    rows = [r["chat_id"] for r in cur.fetchall()]
    conn.close()
    return rows


def get_all_active_pupils() -> list[dict[str, Any]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT DISTINCT p.librus_username, p.password, p.name, p.icon, p.is_active 
    FROM pupils p 
    WHERE p.is_active = 1
    ORDER BY CAST(p.librus_username AS INTEGER) ASC
    """)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def upsert_pupil(username: str, password: str, name: str, icon: str = "👤", is_active: int = 1) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO pupils (librus_username, password, name, icon, is_active, created_at)
    VALUES (?, ?, ?, ?, ?, ?)
    ON CONFLICT(librus_username) DO UPDATE SET
        password = excluded.password,
        name = excluded.name,
        icon = excluded.icon,
        is_active = excluded.is_active
    """, (username, password, name, icon, is_active, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def is_item_known(pupil_username: str, item_type: str, item_id: str | int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT 1 FROM notifications 
    WHERE pupil_username = ? AND item_type = ? AND item_id = ?
    """, (str(pupil_username), item_type, str(item_id)))
    res = cur.fetchone() is not None
    conn.close()
    return res


def mark_item_known(pupil_username: str, item_type: str, item_id: str | int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR IGNORE INTO notifications (pupil_username, item_type, item_id, created_at)
    VALUES (?, ?, ?, ?)
    """, (str(pupil_username), item_type, str(item_id), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def mark_task_completed(chat_id: int, pupil_username: str, task_id: str | int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO completed_tasks (chat_id, pupil_username, task_id, completed_at)
    VALUES (?, ?, ?, ?)
    """, (chat_id, str(pupil_username), str(task_id), datetime.now().isoformat()))
    conn.commit()
    conn.close()


def unmark_task_completed(chat_id: int, pupil_username: str, task_id: str | int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    DELETE FROM completed_tasks
    WHERE chat_id = ? AND pupil_username = ? AND task_id = ?
    """, (chat_id, str(pupil_username), str(task_id)))
    conn.commit()
    conn.close()


def is_task_completed(chat_id: int, pupil_username: str, task_id: str | int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT 1 FROM completed_tasks
    WHERE chat_id = ? AND pupil_username = ? AND task_id = ?
    """, (chat_id, str(pupil_username), str(task_id)))
    res = cur.fetchone() is not None
    conn.close()
    return res


def get_completed_tasks(chat_id: int, pupil_username: str) -> set[str]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT task_id FROM completed_tasks
    WHERE chat_id = ? AND pupil_username = ?
    """, (chat_id, str(pupil_username)))
    rows = {str(r["task_id"]) for r in cur.fetchall()}
    conn.close()
    return rows


def save_or_get_cache_message(msg_key: str, original_text: str) -> tuple[int, str | None]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, translated_text FROM messages_cache WHERE msg_key = ?", (msg_key,))
    row = cur.fetchone()
    if row:
        conn.close()
        return row["id"], row["translated_text"]
    cur.execute("""
    INSERT INTO messages_cache (msg_key, original_text, created_at)
    VALUES (?, ?, ?)
    """, (msg_key, original_text, datetime.now().isoformat()))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id, None


def get_cached_message_by_id(cache_id: int) -> dict[str, Any] | None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM messages_cache WHERE id = ?", (cache_id,))
    row = cur.fetchone()
    conn.close()
    return dict(row) if row else None


def update_cache_translation(cache_id: int, translation: str) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE messages_cache SET translated_text = ? WHERE id = ?", (translation, cache_id))
    conn.commit()
    conn.close()


def get_auto_translate(chat_id: int) -> bool:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT auto_translate FROM chats WHERE chat_id = ?", (chat_id,))
    row = cur.fetchone()
    conn.close()
    return bool(row and row["auto_translate"])


def set_auto_translate(chat_id: int, enabled: bool) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("UPDATE chats SET auto_translate = ? WHERE chat_id = ?", (1 if enabled else 0, chat_id))
    conn.commit()
    conn.close()


def add_summary_message(chat_id: int, message_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO summary_messages (chat_id, message_id, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_summary_messages(chat_id: int) -> list[int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM summary_messages WHERE chat_id = ? ORDER BY message_id ASC", (chat_id,))
    rows = [r["message_id"] for r in cur.fetchall()]
    conn.close()
    return rows


def clear_summary_messages(chat_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM summary_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def add_calendar_message(chat_id: int, message_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO calendar_messages (chat_id, message_id, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_calendar_messages(chat_id: int) -> list[int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM calendar_messages WHERE chat_id = ? ORDER BY message_id ASC", (chat_id,))
    rows = [r["message_id"] for r in cur.fetchall()]
    conn.close()
    return rows


def clear_calendar_messages(chat_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM calendar_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def add_grades_message(chat_id: int, message_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO grades_messages (chat_id, message_id, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_grades_messages(chat_id: int) -> list[int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM grades_messages WHERE chat_id = ? ORDER BY message_id ASC", (chat_id,))
    rows = [r["message_id"] for r in cur.fetchall()]
    conn.close()
    return rows


def clear_grades_messages(chat_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM grades_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def add_timetable_message(chat_id: int, message_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    INSERT OR REPLACE INTO timetable_messages (chat_id, message_id, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, message_id, datetime.now().isoformat()))
    conn.commit()
    conn.close()


def get_timetable_messages(chat_id: int) -> list[int]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT message_id FROM timetable_messages WHERE chat_id = ? ORDER BY message_id ASC", (chat_id,))
    rows = [r["message_id"] for r in cur.fetchall()]
    conn.close()
    return rows


def clear_timetable_messages(chat_id: int) -> None:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM timetable_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def save_or_update_cache_card(
    msg_key: str,
    card_type: str,
    pupil_username: str,
    item_id: str,
    header_info: dict[str, Any],
    original_text: str,
    translated_text: str | None = None
) -> int:
    conn = get_connection()
    cur = conn.cursor()
    header_json = json.dumps(header_info, ensure_ascii=False)
    now_str = datetime.now().isoformat()
    
    cur.execute("SELECT id, translated_text FROM messages_cache WHERE msg_key = ?", (msg_key,))
    row = cur.fetchone()
    if row:
        cache_id = row["id"]
        # Actualizar header_info y original_text por si cambió
        if translated_text:
            cur.execute("""
            UPDATE messages_cache SET card_type = ?, pupil_username = ?, item_id = ?, header_info = ?, original_text = ?, translated_text = ?
            WHERE id = ?
            """, (card_type, pupil_username, item_id, header_json, original_text, translated_text, cache_id))
        else:
            cur.execute("""
            UPDATE messages_cache SET card_type = ?, pupil_username = ?, item_id = ?, header_info = ?, original_text = ?
            WHERE id = ?
            """, (card_type, pupil_username, item_id, header_json, original_text, cache_id))
        conn.commit()
        conn.close()
        return cache_id

    cur.execute("""
    INSERT INTO messages_cache (msg_key, card_type, pupil_username, item_id, header_info, original_text, translated_text, created_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """, (msg_key, card_type, pupil_username, item_id, header_json, original_text, translated_text, now_str))
    new_id = cur.lastrowid
    conn.commit()
    conn.close()
    return new_id


get_cached_card = get_cached_message_by_id


def record_chat_message(chat_id: int, message_id: int, created_at: str | None = None) -> None:
    """Registra un mensaje enviado o recibido en un chat con su marca temporal."""
    conn = get_connection()
    cur = conn.cursor()
    now_str = created_at or datetime.now().isoformat()
    cur.execute("""
    INSERT OR REPLACE INTO chat_messages (chat_id, message_id, created_at)
    VALUES (?, ?, ?)
    """, (chat_id, message_id, now_str))
    conn.commit()
    conn.close()


def get_messages_older_than(hours: float = 45.0) -> list[dict[str, Any]]:
    """Devuelve los mensajes registrados hace más de N horas (por defecto 45h)."""
    cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
    SELECT chat_id, message_id, created_at FROM chat_messages
    WHERE created_at < ?
    ORDER BY message_id ASC
    """, (cutoff,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows


def delete_chat_message_records(records: list[tuple[int, int]]) -> None:
    """Elimina registros de la tabla de chat_messages una vez borrados de Telegram."""
    if not records:
        return
    conn = get_connection()
    cur = conn.cursor()
    cur.executemany("DELETE FROM chat_messages WHERE chat_id = ? AND message_id = ?", records)
    conn.commit()
    conn.close()


def delete_all_chat_messages(chat_id: int) -> None:
    """Elimina todos los registros de chat_messages para un chat dado (ej. tras /clear)."""
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM chat_messages WHERE chat_id = ?", (chat_id,))
    conn.commit()
    conn.close()


def get_system_stats() -> dict[str, int]:
    """Obtiene métricas y conteos de la base de datos."""
    conn = get_connection()
    cur = conn.cursor()
    stats = {}
    for table in ["pupils", "chats", "completed_tasks", "messages_cache", "chat_messages", "notifications"]:
        try:
            cur.execute(f"SELECT COUNT(*) FROM {table}")
            stats[table] = cur.fetchone()[0]
        except Exception:
            stats[table] = 0
    conn.close()
    return stats



if __name__ == "__main__":
    init_db()
    print("BD inicializada.")
    admin_id_val = int(get_setting("admin_chat_id", "0") or "0")
    print("Alumnos para admin chat:", [p["name"] for p in get_pupils_for_chat(admin_id_val)])


def import_config_if_exists(conn: sqlite3.Connection | None = None) -> None:
    """Importa configuración inicial desde librus_config.json si existe."""
    if not os.path.exists(CONFIG_FILE):
        return
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            cfg = json.load(f)

        should_close = False
        if conn is None:
            conn = get_connection()
            should_close = True

        cur = conn.cursor()
        tg = cfg.get("telegram", {})
        token = tg.get("bot_token", "")
        admin_chat = tg.get("chat_id", "")

        if token:
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('bot_token', ?)", (token,))
        if admin_chat:
            cur.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('admin_chat_id', ?)", (str(admin_chat),))
            cur.execute("""
            INSERT OR IGNORE INTO chats (chat_id, first_name, is_authorized, is_active, created_at)
            VALUES (?, 'Admin', 1, 1, ?)
            """, (int(admin_chat), datetime.now().isoformat()))
            cur.execute("UPDATE chats SET is_authorized = 1 WHERE chat_id = ?", (int(admin_chat),))

        admin_id_int = int(admin_chat) if str(admin_chat).isdigit() else None

        for st in cfg.get("students", []):
            u = str(st.get("username", "")).strip()
            p = str(st.get("password", "")).strip()
            name = st.get("name", "").strip() or u
            icon = st.get("icon", "👤")
            if u and p:
                cur.execute("""
                INSERT OR REPLACE INTO pupils (librus_username, password, name, icon, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
                """, (u, p, name, icon, datetime.now().isoformat()))
                if admin_id_int:
                    cur.execute("""
                    INSERT OR IGNORE INTO chat_pupils (chat_id, pupil_username, created_at)
                    VALUES (?, ?, ?)
                    """, (admin_id_int, u, datetime.now().isoformat()))

        conn.commit()
        if should_close:
            conn.close()
    except Exception as e:
        print(f"[WARN] Error importando librus_config.json: {e}")
