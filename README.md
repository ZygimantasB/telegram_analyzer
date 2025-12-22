# Telegram Analyzer

A powerful Django web application for syncing, storing, analyzing, and managing your Telegram messages. Connect multiple Telegram accounts, track deleted messages, analyze chat activity, and much more.

![Python](https://img.shields.io/badge/Python-3.12+-blue.svg)
![Django](https://img.shields.io/badge/Django-6.0-green.svg)
![PostgreSQL](https://img.shields.io/badge/PostgreSQL-16-blue.svg)
![License](https://img.shields.io/badge/License-MIT-yellow.svg)

## Features

### Core Features

| Feature | Description |
|---------|-------------|
| **Multi-Account Support** | Connect and manage multiple Telegram accounts |
| **Message Sync** | Sync all messages from all your chats with background processing |
| **Deleted Message Tracking** | Detect and preserve messages that were deleted |
| **Media Download** | Automatically download media files (photos, videos, documents) |
| **Real-time Progress** | Live sync progress tracking with auto-refresh |

### Analytics & Insights

| Feature | Description |
|---------|-------------|
| **Dashboard** | Overview of all your chats and statistics |
| **Word Cloud** | Visualize most used words in conversations |
| **Top Senders** | See who sends the most messages |
| **Activity Heatmap** | Visualize message activity by day/hour |
| **Member Analytics** | Analyze group members, roles, and activity |

### Organization Tools

| Feature | Description |
|---------|-------------|
| **Bookmarks** | Save important messages for quick access |
| **Tags** | Organize messages with custom color-coded tags |
| **Folders** | Group chats into custom folders |
| **Notes** | Add personal notes to any message |
| **Advanced Search** | Search messages with filters (date, chat, sender, media type) |

### Media Management

| Feature | Description |
|---------|-------------|
| **Media Gallery** | Browse all media in a visual gallery |
| **Slideshow Mode** | View media in fullscreen slideshow |
| **Duplicate Detection** | Find duplicate media files using perceptual hashing |
| **Bulk Download** | Download multiple media files at once |

### Members & Participants

| Feature | Description |
|---------|-------------|
| **Member List** | View all users from your groups/channels |
| **User Profiles** | Detailed user info with activity stats |
| **Role Tracking** | Track admins, creators, and member roles |
| **Auto-Sync Members** | Members synced automatically during Sync All |

### Alerts & Automation

| Feature | Description |
|---------|-------------|
| **Keyword Alerts** | Get notified when specific keywords appear |
| **Deletion Alerts** | Track when messages are deleted |
| **Scheduled Backups** | Automatic periodic backups of your data |

### Export & Backup

| Feature | Description |
|---------|-------------|
| **JSON Export** | Export messages in JSON format |
| **CSV Export** | Export to spreadsheet-compatible CSV |
| **HTML Export** | Beautiful HTML export for viewing |
| **Member Export** | Export group member lists to CSV |

### Security & Privacy

| Feature | Description |
|---------|-------------|
| **Encrypted Sessions** | Telegram sessions encrypted with Fernet |
| **Audit Log** | Track all actions performed in the app |
| **User Authentication** | Secure login with email-based auth |

## Tech Stack

- **Backend:** Django 6.0, Python 3.12+
- **Database:** PostgreSQL
- **Telegram API:** Telethon 1.42.0
- **Frontend:** Bootstrap 5, Chart.js
- **Encryption:** Cryptography (Fernet)

## Installation

### Prerequisites

- Python 3.12 or higher
- PostgreSQL 14+
- Telegram API credentials ([Get them here](https://my.telegram.org/apps))

### 1. Clone the repository

```bash
git clone https://github.com/yourusername/telegram-analyzer.git
cd telegram-analyzer
```

### 2. Create virtual environment

```bash
# Using uv (recommended)
uv venv
source .venv/bin/activate  # Linux/Mac
.venv\Scripts\activate     # Windows

# Or using standard venv
python -m venv .venv
source .venv/bin/activate
```

### 3. Install dependencies

```bash
# Using uv
uv pip install -e .

# Or using pip
pip install -e .
```

### 4. Configure environment variables

Create a `.env` file in the project root:

```env
# Django
DJANGO_SECRET_KEY=your-secret-key-here
DEBUG=True

# Telegram API
TELEGRAM_APP_API_ID=your-api-id
TELEGRAM_API_HASH=your-api-hash

# PostgreSQL Database
DB_POSTGRESQL_NAME=telegram_analyzer
DB_POSTGRESQL_USERNAME=postgres
DB_POSTGRESQL_PASSWORD=your-password
DB_POSTGRESQL_HOST=localhost
DB_POSTGRESQL_PORT=5432
```

### 5. Create database

```bash
# Connect to PostgreSQL and create database
psql -U postgres
CREATE DATABASE telegram_analyzer;
\q
```

### 6. Run migrations

```bash
python manage.py migrate
```

### 7. Create superuser (optional)

```bash
python manage.py createsuperuser
```

### 8. Run the development server

```bash
python manage.py runserver
```

Visit `http://localhost:8000` in your browser.

## Usage

### Connecting Your Telegram Account

1. Go to the dashboard and click "Connect Telegram"
2. Enter your phone number (with country code)
3. Enter the verification code sent to your Telegram
4. If you have 2FA enabled, enter your password
5. Done! Your account is now connected

### Syncing Messages

1. Click "Sync All" on the dashboard
2. Watch the real-time progress as messages are synced
3. Media files under 1MB are downloaded automatically
4. Larger files can be downloaded manually from the gallery
5. Group members are synced automatically

### Tracking Deleted Messages

1. Messages are automatically checked for deletion during sync
2. Go to "Deleted Messages" to see all deleted messages
3. Set up deletion alerts to get notified immediately

### Using Analytics

1. Go to Analytics from the dashboard
2. Select a chat or view all chats combined
3. Explore word clouds, activity patterns, and top senders

### Viewing Group Members

1. Go to "Members" from the dashboard
2. View all discovered users across your groups
3. Click on a user to see their profile and activity
4. View member analytics for role distribution

## Project Structure

```
telegram_analyzer/
├── telegram_analyzer_app/     # Main Django project settings
├── telegram_functionality/    # Core Telegram features
│   ├── models.py             # Database models
│   ├── views.py              # Main views
│   ├── views_advanced.py     # Advanced feature views
│   ├── services.py           # Telegram API integration
│   ├── templates/            # HTML templates
│   └── static/               # CSS, JS, images
├── users/                     # User authentication app
├── media/                     # Uploaded/downloaded media
├── static/                    # Static files
└── manage.py
```

## Key Models

| Model | Description |
|-------|-------------|
| `TelegramSession` | Encrypted Telegram session storage |
| `TelegramChat` | Chat metadata (type, title, sync status) |
| `TelegramMessage` | Message storage with deletion tracking |
| `TelegramUser` | Telegram user profiles |
| `ChatMembership` | User membership in chats with roles |
| `SyncTask` | Background sync progress tracking |
| `Bookmark` | Saved message bookmarks |
| `Tag` | Custom tags for organizing messages |
| `Folder` | Custom chat folders |
| `Note` | Notes attached to messages |
| `KeywordAlert` | Keyword notification rules |
| `ScheduledBackup` | Backup schedule configuration |
| `AuditLog` | Action audit trail |

## API Endpoints

### Authentication
- `POST /telegram/connect/` - Start Telegram connection
- `POST /telegram/verify-code/` - Verify phone code
- `POST /telegram/verify-2fa/` - Verify 2FA password

### Sync
- `GET /telegram/start-sync/` - Start background sync
- `GET /telegram/sync-status/<id>/` - Get sync progress page
- `GET /telegram/sync-progress/<id>/` - API for sync progress

### Chats & Messages
- `GET /telegram/chats/` - List all chats
- `GET /telegram/chats/<chat_id>/` - View chat messages
- `GET /telegram/search/` - Search messages
- `GET /telegram/deleted/` - View deleted messages

### Members
- `GET /telegram/members/` - List all users
- `GET /telegram/members/chat/<chat_id>/` - Chat members
- `GET /telegram/members/chat/<chat_id>/sync/` - Sync chat members
- `GET /telegram/members/user/<user_id>/` - User profile
- `GET /telegram/members/analytics/` - Member analytics
- `GET /telegram/members/export/` - Export members CSV

### Analytics
- `GET /telegram/analytics/` - Analytics dashboard
- `GET /telegram/analytics/word-cloud/` - Word cloud data
- `GET /telegram/analytics/top-senders/` - Top senders
- `GET /telegram/analytics/heatmap/` - Activity heatmap

### Export
- `GET /telegram/export/` - Export page
- `GET /telegram/export/json/` - Export as JSON
- `GET /telegram/export/csv/` - Export as CSV
- `GET /telegram/export/html/` - Export as HTML

### Organization
- `GET /telegram/bookmarks/` - View bookmarks
- `GET /telegram/tags/` - Manage tags
- `GET /telegram/folders/` - Manage folders
- `GET /telegram/notes/` - View notes

### Alerts & Backups
- `GET /telegram/alerts/` - Keyword alerts
- `GET /telegram/backups/` - Scheduled backups
- `GET /telegram/audit-log/` - Audit log

### Media
- `GET /telegram/gallery/` - Media gallery
- `GET /telegram/gallery/duplicates/` - Find duplicates

## Development

### Running Tests

```bash
python manage.py test
```

### Creating Migrations

```bash
python manage.py makemigrations
python manage.py migrate
```

### Collecting Static Files

```bash
python manage.py collectstatic
```

## Contributing

1. Fork the repository
2. Create a feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

## License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## Disclaimer

This tool is for personal use only. Please respect Telegram's Terms of Service and others' privacy when using this application. Do not use this tool for:
- Spying on others without consent
- Mass data collection
- Any illegal activities

## Acknowledgments

- [Telethon](https://github.com/LonamiWebs/Telethon) - Telegram MTProto API library
- [Django](https://www.djangoproject.com/) - Web framework
- [Bootstrap](https://getbootstrap.com/) - Frontend framework
- [Chart.js](https://www.chartjs.org/) - Charts library

---

Made with Python and Django
