# Indian Stock Market Research & Intelligence Platform

A personal stock market research, technical analysis, portfolio intelligence, and decision-support platform designed specifically for the Indian equity markets (NSE and BSE).

---

## 1. Project Overview & Architecture

The platform is engineered as a **Django Modular Monolith** adhering to clean architecture principles:
- **Presentation Layer:** Unified persistent HTML shell with Bootstrap 5 and HTMX (`django-htmx`). Dynamic `#main-content` swapping with browser URL push and history restoration.
- **Backend & Domain Services:** Python 3.12+ and Django 5.1 with pure service layers separating business calculations from views and ORM queries.
- **Data Integrity:** Decoupled canonical asset identity (`Instrument`) from exchange listings (`ExchangeListing`), raw market data separated from derived versioned indicators, and an immutable transaction ledger for portfolio accounting.
- **Security:** Authenticated symmetric encryption (Fernet / AES-128-CBC + HMAC-SHA256) for stored broker credentials with out-of-band master key management.

Authoritative specification reference: [`MASTER_SPECIFICATION_DJANGO.md`](MASTER_SPECIFICATION_DJANGO.md)  
System architecture reference: [`ARCHITECTURE.md`](ARCHITECTURE.md)

---

## 2. Phase 1 Implementation Status

Phase 1 (Django Foundation, Operations & Dynamic UI Shell) is **🟢 COMPLETED** and validated:
- [x] Django modular monolith project structure with split settings (`base.py`, `development.py`, `production.py`).
- [x] Custom user model (`accounts.CustomUser` with UUID primary key) initialized before first database migration.
- [x] User preferences model (`accounts.UserPreference`) with theme and alerting controls.
- [x] Persistent HTML shell (`templates/base/shell.html`) with header ticker, breadcrumbs, and responsive sidebar.
- [x] Dual-mode dynamic navigation powered by `django-htmx`:
  - Full-page shell rendering on direct URL load and refresh.
  - Efficient partial-template swapping on HTMX navigation.
  - Client-side history restoration (`htmx:historyRestore`) updating DOM and active sidebar class.
- [x] Platform security: Symmetric Fernet encryption utilities for credential protection.
- [x] Operational runbook scripts: Automated PostgreSQL backup (`scripts/backup_db.sh`) and restoration (`scripts/restore_db.sh`).
- [x] Service health check endpoint (`/core/health/`) and custom 404/500 error pages.
- [x] Automated test suite: 16 passing unit and integration tests covering navigation, authentication, encryption, and template tags.

---

## 3. Local Development Quickstart

### Prerequisites
- Python 3.12+ or 3.13
- Git

### 1. Clone & Set Up Virtual Environment
```bash
# Clone the repository
git clone <repo_url>
cd stockmarket_analytics_django

# Create and activate virtual environment
python3 -m venv .venv
source .venv/bin/activate
```

### 2. Install Dependencies
```bash
pip install -r requirements/local.txt
```

### 3. Configure Environment Variables
Copy `.env.example` to `.env`:
```bash
cp .env.example .env
```
*(Default settings in `.env` are pre-configured for local development.)*

### 4. Apply Database Migrations
```bash
python manage.py migrate
```

### 5. Create Default Development Superuser
Run the included helper command to create a default administrator:
```bash
python manage.py create_dev_user
```
**Default Credentials:**
- **Username:** `admin`
- **Password:** `Admin@12345`

### 6. Seed Instruments & Exchange Listings
```bash
python manage.py seed_instruments
```

### 7. (Optional) Sync Quotes or Historical Candles via CLI
```bash
# Sync live/delayed quote for RELIANCE
python manage.py import_market_data --symbol RELIANCE --exchange NSE

# Backfill 30 days of daily historical candles
python manage.py import_market_data --symbol RELIANCE --exchange NSE --history --days 30
```

### 8. Start Development Server
```bash
python manage.py runserver 8000
```
Open [http://localhost:8000](http://localhost:8000) in your web browser.  
Visit [http://localhost:8000/settings/data-sources/](http://localhost:8000/settings/data-sources/) to monitor provider health and metrics.

---

## 4. Running Tests and Quality Checks

### Run Automated Tests
```bash
pytest
```

### Run Tests with Full Coverage Analysis
```bash
pytest --cov=apps --cov=services --cov=integrations --cov-report=term-missing
```

### Run Linter Checks
```bash
ruff check .
```

### Verify Deployment Configuration
```bash
python manage.py check --deploy --settings=config.settings.production
```

---

## 5. Upcoming Phases

- **Phase 3:** Stock Research Engine, Autocomplete Search, Technical & Fundamental Snapshots (Raw vs Derived)
- **Phase 4:** Portfolio Accounting (FIFO Lot Matching & Capital Charges)
- **Phase 5:** Stock Screener & Custom Watchlists

