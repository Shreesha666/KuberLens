# Security & Regulatory Compliance Policy
## Indian Stock Market Research & Intelligence Platform

### 1. Security Architecture Principles
The platform adheres strictly to the security standards documented in **Architecture Revision 2.1** and the **Master Specification**:
1. **Confidentiality:** All sensitive tokens, broker API secrets, and encryption keys are encrypted at rest and never exposed to the frontend, browser logs, or application logs.
2. **Integrity:** The portfolio transaction ledger is strictly immutable. Historical buy/sell transactions cannot be modified or deleted in-place; all corrections occur via explicit reversal entries (`BUY_REVERSAL`, `SELL_REVERSAL`).
3. **Availability:** Multi-tier fallback data providers (Jugaad-Data -> Yahoo Finance -> Cached EOD) ensure system uptime during provider outages without halting user research.

---

### 2. Strict Research-Only & Zero Order-Placement Policy
In accordance with **Master Specification Section 22**:
- The platform is strictly an analytical, research, and tracking platform.
- **No automated or manual order execution endpoints exist.**
- The broker integration module (`apps/brokers/`, `integrations/broker_providers/zerodha/client.py`) includes hardcoded permission guards that explicitly raise `PermissionError` if order execution (`place_order`, `modify_order`, `cancel_order`) is invoked.
- Broker connections operate solely in read-only mode to synchronize existing portfolio holdings and retrieve verified market quotes.

---

### 3. Symmetric Field-Level Encryption (Fernet)
All sensitive broker secrets (e.g., Zerodha Kite API Secret, OAuth access tokens) are stored in the database as authenticated ciphertext:
- **Algorithm:** AES-128 in CBC mode with HMAC-SHA256 authenticated encryption using `cryptography.fernet.Fernet`.
- **Key Storage:** The encryption key (`FIELD_ENCRYPTION_KEY`) is stored exclusively in environment variables and never checked into source control.
- **Ciphertext Isolation:** Raw database columns (`api_secret_encrypted`, `access_token_encrypted`) hold only base64-encoded encrypted bytes. Decryption is performed in-memory only when communicating with broker APIs.

---

### 4. Transport & Session Security
- **Strict Transport Security (HSTS):** Enabled in production (`SECURE_HSTS_SECONDS = 31536000`, `includeSubDomains`, `preload`).
- **Cookie Flags:** `SESSION_COOKIE_SECURE = True`, `CSRF_COOKIE_SECURE = True`, `SESSION_COOKIE_HTTPONLY = True`, `SameSite = "Lax"`.
- **Cross-Origin Framing:** `X_FRAME_OPTIONS = "DENY"` prevents all clickjacking attacks.
- **Content Type Sniffing:** `SECURE_CONTENT_TYPE_NOSNIFF = True` blocks MIME-confusion attacks.

---

### 5. Multi-Tenant User Data Isolation
Every data query for portfolios, holdings, watchlists, trade journals, alert rules, and backtest simulations explicitly scopes to the authenticated user:
```python
# Standard Query Pattern
portfolio = get_object_or_404(Portfolio, user=request.user)
user_trades = TradeJournal.objects.filter(user=request.user)
```
Direct object reference attacks (IDOR) are prevented through strict object-level authorization checks.

