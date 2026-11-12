# Production Deployment & Operations Guide
## Indian Stock Market Research & Intelligence Platform

### 1. System Architecture Overview
The platform is designed around a decoupled, fault-tolerant architecture adhering to **Architecture Revision 2.1**:
- **Application Server:** Django 5.1 running under Gunicorn (4 workers, 2 threads per worker).
- **Relational Database:** PostgreSQL 16 (Strict ACID compliance for immutable transaction ledger and audited models).
- **Cache & Message Broker:** Redis 7 (Sub-millisecond quote caching, session caching, and Celery task broker).
- **Background Task Workers:** Celery 5.4 worker pool for asynchronous indicator recalculation, Bhavcopy ingestion, and alert evaluation.
- **Task Scheduler:** Celery Beat for periodic data freshness health checks and automated Bhavcopy downloads.
- **Reverse Proxy / SSL:** Nginx with Let's Encrypt SSL/TLS termination and WhiteNoise static asset compression.

---

### 2. Environment Variables Checklist
Create a production `.env` file with the following variables:

```bash
# Security & Cryptography
DJANGO_SECRET_KEY="<generate-high-entropy-random-50-character-secret>"
FIELD_ENCRYPTION_KEY="<generate-fernet-key-via-Fernet.generate_key()>"
DJANGO_SETTINGS_MODULE="config.settings.production"
DJANGO_ALLOWED_HOSTS="yourdomain.com,api.yourdomain.com"

# Database Configuration (PostgreSQL Required)
DATABASE_URL="postgresql://stockuser:securepassword@db:5432/stockmarket_intel"

# Redis Cache & Broker
REDIS_URL="redis://redis:6379/0"
CELERY_BROKER_URL="redis://redis:6379/1"

# External Data & AI Providers (Optional)
GEMINI_API_KEY="<your-google-gemini-api-key>"
KITE_API_KEY=""
KITE_API_SECRET=""
```

---

### 3. Containerized Deployment (Docker Compose)
Deploying via Docker Compose ensures non-root isolation and reproducible container orchestration:

```bash
# 1. Clone repository on production host
git clone <repository-url> /opt/stockmarket_intel
cd /opt/stockmarket_intel

# 2. Configure environment file
cp .env.example .env
nano .env

# 3. Build containers and start background daemon services
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build

# 4. Run database migrations
docker compose exec web python manage.py migrate

# 5. Collect static assets with WhiteNoise compression
docker compose exec web python manage.py collectstatic --noinput

# 6. Seed NIFTY 250 universe listings and historical daily candles
docker compose exec web python manage.py seed_nifty250
```

---

### 4. Automated Daily Bhavcopy Cron Schedule
The official National Stock Exchange of India (NSE) Bhavcopy is settled and published around **18:30 IST (13:00 UTC)** on trading days.

Add the following cron entry on the host to ingest settled post-market data automatically:

```crontab
# Ingest official daily Bhavcopy at 18:45 IST on weekdays (Monday - Friday)
45 13 * * 1-5 docker compose -f /opt/stockmarket_intel/docker-compose.yml exec -T web python manage.py import_market_data --source=bhavcopy >> /var/log/bhavcopy.log 2>&1
```

---

### 5. Database Backup and Recovery
Run the automated backup script to create atomic PostgreSQL snapshots:

```bash
# Execute automated backup
./scripts/backup_db.sh

# Restore from snapshot
./scripts/restore_db.sh ./backups/stock_intel_YYYYMMDD_HHMMSS.dump
```

