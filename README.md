# Librus Synergia Bot & Web Dashboard 🎓🤖

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Python: 3.10+](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Framework: aiohttp](https://img.shields.io/badge/AsyncIO-aiohttp-informational.svg)](https://docs.aiohttp.org/)
[![Database: SQLite](https://img.shields.io/badge/Database-SQLite-lightgrey.svg)](https://www.sqlite.org/)

An advanced, asynchronous Telegram bot and responsive Web Dashboard for tracking student progress in the **Librus Synergia** school register. Affectionately nicknamed *"Srta. Rottenmeier"*, it helps parents stay on top of daily school life across multiple children with zero friction.

---

## ✨ Key Features

- 👨‍👩‍👧‍👦 **Multi-Student Dashboard:** Unified tracking for multiple children sorted consistently by seniority/ID.
- 🔕 **Non-Intrusive Read Status:** Message checks **do not mark messages as read** in the official Librus portal, preserving unread badges for spouses and other family members.
- ⏰ **Smart Timetable & Excursions:**
  - Displays daily entry and exit times.
  - Automatically incorporates school trips, workshops, and extracurricular events into the daily schedule.
  - Distinguishes cancelled classes with strikethrough badges to prevent unexplained gaps in the timetable.
- 🔔 **Recurring Reminders:** Proactive reminder alerts for upcoming exams and assignment deadlines at 7 days, 3 days, 1 day, and morning-of.
- 📊 **Organized Grade Tables:** Clean, monospace-aligned summaries showing subject, grade, evaluation category, and teacher comments.
- 🌐 **Instant Polish Translation:** Automatic translation with inline buttons to toggle between translated and original Polish text, plus expandable "View More/Less" controls.
- 🖥️ **Modern Web Dashboard:**
  - Dark mode interface accessible from any browser on your local network.
  - Accordion timetables, pending tasks with completion checkboxes, upcoming exams, and grade overview.
  - Live daemon status and one-click manual synchronization.
- 🔒 **Multi-User Access Control:** Password-protected authorization so specific chats only receive updates for their assigned students.

---

## 🛠️ Architecture

```
librus-synergia-bot/
├── librus_bot.py              # Main Telegram polling bot and background scheduler
├── web_panel.py               # Aiohttp HTTP server & embedded interactive dashboard
├── db.py                      # SQLite persistence layer (chats, pupils, cache, settings)
├── avatar.jpg                 # Default bot & dashboard avatar
├── librus_config.example.json # Configuration template
├── librus.service             # Systemd service unit for 24/7 background operation
├── requirements.txt           # Python package dependencies
├── LICENSE                    # MIT License
└── README.md                  # Project documentation
```

---

## 🚀 Quick Start

### 1. Prerequisites
- Python 3.10 or higher
- A Telegram account and a Bot Token from [@BotFather](https://t.me/botfather)
- Librus Synergia parent or student credentials

### 2. Clone and Install Dependencies
```bash
git clone https://github.com/jmvilaplana/librus-synergia-bot.git
cd librus-synergia-bot

# Create and activate virtual environment
python3 -m venv venv
source venv/bin/activate    # On Windows: venv\Scripts\activate

# Install requirements
pip install -r requirements.txt
```

### 3. Configure Credentials
Copy the example configuration file:
```bash
cp librus_config.example.json librus_config.json
```
Edit `librus_config.json` with your parameters:
```json
{
  "telegram": {
    "bot_token": "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz",
    "chat_id": "123456789"
  },
  "students": [
    {
      "name": "Alicja",
      "username": "1234567u",
      "password": "your_secure_password",
      "icon": "👧",
      "enabled": true
    },
    {
      "name": "Bartek",
      "username": "7654321u",
      "password": "your_secure_password",
      "icon": "👦",
      "enabled": true
    }
  ]
}
```

> **Note:** `librus_config.json` is automatically ignored by `.gitignore` to prevent committing sensitive passwords to public repositories.

Alternatively, you can pass settings via environment variables:
```bash
export TELEGRAM_BOT_TOKEN="your_bot_token"
export LIBRUS_AUTH_PASSWORD="your_custom_auth_pin"
export LIBRUS_ADMIN_CHAT_ID="your_telegram_chat_id"
export LIBRUS_WEB_PORT=8088
```

### 4. Run the Bot
```bash
python librus_bot.py
```
- Open `http://<your-server-ip>:8088` in your browser to access the Web Dashboard.
- Open Telegram and type `/start` to begin chatting with the bot.

---

## 🤖 Telegram Bot Commands

| Command | Description |
| :--- | :--- |
| `/start` | Welcome greeting, authentication prompt, and keyboard menu. |
| `/resumen` | Generates a clean consolidated overview of upcoming exams, homework, and recent grades (automatically purges old summary messages to keep chats tidy). |
| `/horario` | Shows today's and tomorrow's school entry & exit times, with interactive buttons to view lesson breakdowns and excursion details. |
| `/notas` | Displays recent grades and calculated grade point averages per subject. |
| `/examenes` | Lists scheduled tests and exams across the next 14 days. |
| `/deberes` | Lists pending homework tasks with due dates. |
| `/check` | Forces an immediate manual synchronization check with Librus. |
| `/add_pupil` | Interactive wizard to configure a student account directly from Telegram. |
| `/mis_alumnos`| Lists all students currently linked to your chat. |
| `/set_clave <clave>` | Changes the authorization password required for new devices. |
| `/limpiar` | Cleans up bot messages in the current chat. |

---

## ⚙️ Running as a System Service (Systemd)

To run the bot 24/7 on a Linux server or Raspberry Pi:

1. Edit `librus.service` to reflect your Linux username and deployment path:
   ```ini
   [Service]
   User=jose
   WorkingDirectory=/home/jose/librus
   ExecStart=/home/jose/librus/venv/bin/python -u librus_bot.py
   ```

2. Copy the unit file and enable the service:
   ```bash
   sudo cp librus.service /etc/systemd/system/librus.service
   sudo systemctl daemon-reload
   sudo systemctl enable librus.service
   sudo systemctl start librus.service
   ```

3. Check service logs:
   ```bash
   journalctl -u librus.service -f
   ```

---

## 🔒 Privacy & Security

- All student credentials, cached tokens, and school records are stored strictly on your local SQLite database (`librus.db`) or local configuration file (`librus_config.json`).
- No telemetry, analytics, or third-party cloud proxies are used.
- All requests communicate directly between your machine, the official Librus Synergia API (`api.librus.pl`), and the Telegram Bot API (`api.telegram.org`).

---

## 📄 License

This project is licensed under the terms of the [MIT License](LICENSE).
Feel free to use, modify, and distribute it.
