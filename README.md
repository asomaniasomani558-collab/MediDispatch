# MediDispatch GH

Emergency Medical Dispatch for Ghana: four applications on one modular Flask backend.

| App | URL | Who | Login |
|---|---|---|---|
| Civilian PWA | `/civilian/` | Bystanders | None (bearer token per report) |
| Paramedic | `/paramedic/` | Ambulance crews (mobile) | `paramedic` |
| Hospital command centre | `/hospital/` | ER desks (desktop) | `hospital_admin` |
| Super Admin / Dev portal | `/admin/` | System administrators | `super_admin` |

> **Why this matters for Ghana:** see [docs/IMPACT_AND_RATIONALE.md](docs/IMPACT_AND_RATIONALE.md) for the national statistics behind the project and the case for a local open-weight AI model (30 cited sources).

> **Status: engineering prototype.** It implements the full specification and passes 166 automated tests on SQLite and PostgreSQL 16, but it is **not cleared for clinical use**. See [Before go-live](#before-go-live) for what must happen first.

---

## Quick start (local development)

```bash
python3 -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python scripts/seed_data.py --demo     # hospitals, super admin, demo staff, sample reports
python run.py                           # http://127.0.0.1:5000
```

The seed script prints generated passwords once. To choose them yourself:

```bash
SEED_ADMIN_PASSWORD='...' SEED_DEMO_PASSWORD='...' python scripts/seed_data.py --demo
```

Demo accounts: `superadmin`, `medic.kumasi`, `medic.accra`, `kath.er` (Komfo Anokye), `kbth.er` (Korle Bu).

Development uses SQLite and needs no Redis or Ollama. Without Ollama, triage runs on MEWS rules alone, which is the designed fallback.

## Production (Docker)

```bash
cp .env.example .env
# Fill in SECRET_KEY, FIELD_ENCRYPTION_KEYS (flask --app run.py generate-key) and POSTGRES_PASSWORD.
docker compose up -d --build
docker compose exec web python scripts/seed_data.py
```

Stack: **Nginx** (static files, WebSocket upgrade, rate limit) → **Gunicorn + Eventlet** (1 worker per container) → **PostgreSQL 16**, **Redis 7** (Socket.IO message queue), **Ollama** (Llama 3.2 3B, pulled by the `ollama-pull` job).

The app refuses to start in production with a placeholder `SECRET_KEY`, a missing encryption key, or a non-PostgreSQL database. Ollama is deliberately not a hard dependency: the system starts and triages without it.

HTTPS is required in production (`SESSION_COOKIE_SECURE=true`). Enable the TLS block in `deploy/nginx/nginx.conf` and mount your certificates.

---

## Clinical safety: the AI harness

`app/services/triage.py` and `app/services/ai/llm_harness.py`

1. **MEWS baseline** (Subbe et al., 2001) from respiratory rate, heart rate, systolic BP, temperature and AVPU:

   | Points | 3 | 2 | 1 | 0 | 1 | 2 | 3 |
   |---|---|---|---|---|---|---|---|
   | Systolic BP | ≤70 | 71–80 | 81–100 | 101–199 | | ≥200 | |
   | Heart rate | | ≤40 | 41–50 | 51–100 | 101–110 | 111–129 | ≥130 |
   | Resp. rate | | <9 | | 9–14 | 15–20 | 21–29 | ≥30 |
   | Temp (°C) | | <35 | | 35–38.4 | | ≥38.5 | |
   | AVPU | | | | Alert | Voice | Pain | Unresponsive |

   Severity: 0–1 LOW, 2–3 MODERATE, 4 HIGH, ≥5 CRITICAL.

2. **Raise-only red flags** on top of MEWS: any single parameter scoring 3 → at least HIGH; SpO2 <90% → HIGH, <85% → CRITICAL; GCS ≤12 → HIGH, ≤8 → CRITICAL; glucose <3.0 mmol/L → HIGH; HR or RR of 0 → CRITICAL with CPR first. Missing MEWS inputs are flagged, never silently scored as normal.
3. **AI recommendation**: vitals and symptoms go to local Llama 3.2 3B via Ollama's structured-output mode (JSON schema, temperature 0). The reply is strictly validated; anything off-schema is rejected. Symptom text is length-limited and fenced as data against prompt injection.
4. **Safety override**: `final = max(baseline, ai)`. The AI can raise severity, never lower it. Rule-based actions are always shown; AI actions are added separately, labelled advisory.
5. **Fallback**: offline, timeout (2 s connect / 12 s read), HTTP error, malformed JSON, or any exception → MEWS result, no crash. A circuit breaker skips the AI for 60 s after 3 consecutive failures, so an outage adds no latency.

`tests/test_triage.py` covers every MEWS band boundary, all fallback paths, and a 400-case randomised property test asserting the final severity always equals `max(baseline, ai)`.

## Security and compliance (Ghana Data Protection Act, 2012 – Act 843)

| Requirement | Implementation |
|---|---|
| Encryption at rest | Names, phone numbers, GPS, vitals, symptoms, triage and photos are Fernet-encrypted (AES + HMAC) column types. Key rotation via `MultiFernet`. |
| Audit logging | Every view of a patient record or photo writes an `audit_logs` row **before** data is returned; if the write fails, the data is withheld (fail closed). |
| Append-only | Blocked at three layers: ORM events, bulk-statement guard, and a PostgreSQL trigger. Rows are SHA-256 hash-chained; *Audit log → Verify integrity* detects tampering. |
| Strict RBAC | Role-checked blueprints plus record-level checks: paramedics see only cases they claimed, hospitals only patients sent to them. Super admins cannot open patient records by default (`ADMIN_CAN_VIEW_PATIENT_DATA=false`). A civilian token authenticates nothing outside its own report. |
| CSRF | Flask-WTF `CSRFProtect` on every state-changing request (forms and JSON). |
| Media retention | Photos expire 30 days after upload and are purged hourly (background job, or `flask purge-media`). Uploads are re-encoded, which strips EXIF/GPS metadata. |
| Sessions | scrypt hashes, lockout after 5 failures, sessions invalidated on password change or account disable, open-redirect protection. |
| Headers | Strict CSP (no inline scripts), `X-Frame-Options: DENY`, `nosniff`, `no-referrer`, `Cache-Control: no-store` on all dynamic pages. |
| Real-time privacy | WebSocket broadcasts carry non-identifying summaries only; clients fetch details over audited HTTP. Anonymous sockets are refused. |

## Civilian camera: privacy by construction

The camera never starts without a consent checkbox **and** a tap on "Turn on camera". While on, the live `<video>` preview and a "Camera on" badge are visible. Only single still frames are uploaded, each after the user presses "Send photo". The camera stops on Stop, on Capture, when the page is hidden, and when the report closes. There is no streaming code path.

## Offline resilience

- **Civilian:** a service worker caches the app shell, first-aid steps and fonts; reports queue in `localStorage` and retry automatically; "Call 112" is a plain `tel:` link that always works; state survives reloads.
- **Staff:** if WebSockets drop, screens fall back to polling, with a slow safety-net poll even while live.
- **Server:** global error handlers roll back and return a calm message that points to 112; the AI and Redis are optional.

## Tests

```bash
python -m pytest -q                                   # SQLite (fast)
TEST_DATABASE_URL=postgresql+psycopg2://user:pw@host/db python -m pytest -q   # PostgreSQL
```

| File | Covers |
|---|---|
| `test_triage.py` | MEWS bands, red flags, raise-only override, all AI failure modes, circuit breaker |
| `test_matching.py` | Distance, capability scoring, full/inactive hospitals, unknown location |
| `test_security.py` | Encryption at rest, RBAC matrix, CSRF, append-only audit, tamper detection, sessions |
| `test_civilian.py` | Reporting, GPS pings, consented photos, EXIF stripping, 30-day purge, rate limits |
| `test_workflow.py` | End-to-end flow across all four apps, admin CRUD, WebSocket routing |

## Project layout

```text
app/
  __init__.py          app factory, security headers, error handlers, CLI
  config.py            Development / Testing / Production
  extensions.py        db, socketio, login_manager, csrf
  models/              User, Hospital, Emergency, CivilianSession, Media, AuditLog
  services/            triage, matching, encryption, media, audit, access, realtime, security, first_aid
    ai/llm_harness.py  Ollama wrapper (validation, timeouts, circuit breaker)
  blueprints/          auth, civilian, paramedic, hospital, admin, api
  templates/           Jinja2
  static/              vanilla CSS / JS (camera.js, gps.js, socket.js, sw.js), fonts, icons
scripts/seed_data.py   Ghana hospitals + super admin (+ --demo)
tests/                 pytest suite
deploy/nginx/          reverse proxy config
docs/                  original specification and logo sheet
run.py / wsgi.py       dev server / production entry point
```

## Before go-live

These items need people and decisions that code can't supply:

- **Clinical sign-off.** First-aid text, rule-based actions, red-flag thresholds and the AI system prompt must be reviewed and approved by the MoH / National Ambulance Service clinical lead, ideally with a documented clinical safety case.
- **Live model validation.** The harness was tested against simulated Ollama replies and real connection failures, not a running Llama 3.2 model. Evaluate its suggestions on representative cases before relying on them, and monitor the "AI raised severity" rate.
- **Hospital data.** Seeded coordinates are approximate and bed/specialist figures are sample data. Verify every facility.
- **Key management.** Losing `FIELD_ENCRYPTION_KEYS` means losing all patient data. Store keys in a secrets manager, back them up separately from the database, and rehearse rotation.
- **Independent security review and penetration test**, plus a data protection impact assessment and registration with Ghana's Data Protection Commission.
- **Database migrations.** Add Flask-Migrate/Alembic before the first schema change; `flask init-db` only creates tables.
- **Eventlet is deprecated upstream** and Gunicorn 26 removed its worker, so Gunicorn is pinned to 25.3.0. Plan a move to gevent (`--worker-class gevent`, `SOCKETIO_ASYNC_MODE=gevent`), which Flask-SocketIO supports.
- **Scaling.** One worker per container; add replicas behind Nginx with `ip_hash` and the Redis queue. The admin "live connections" count is per worker.
- **Reach.** Many bystanders may lack data or smartphones; an SMS/USSD reporting channel would extend coverage.

## AI model licence

Built with Llama. The AI harness uses Meta's Llama 3.2 3B, served locally by Ollama and licensed under the [Llama 3.2 Community License](https://huggingface.co/meta-llama/Llama-3.2-3B-Instruct) (open-weight, not OSI open source). Use is subject to Meta's Acceptable Use Policy; confirm with legal counsel that decision support for licensed clinicians is within scope. Any other model can be used by setting `OLLAMA_MODEL`.
