# OpsPulse

OpsPulse is an open-source, self-hostable incident-response and on-call application. The codebase uses a React/TypeScript UI, a FastAPI gateway, focused Python services, PostgreSQL, RabbitMQ, Redis, and Mailpit for local email testing.

## Local run

Requirements: Docker Engine and the Docker Compose plugin.

```bash
docker compose up --build -d
```

Open `http://127.0.0.1:8080`. Mailpit's email inbox is at `http://127.0.0.1:8026`; RabbitMQ management is at `http://127.0.0.1:15672` (local default credentials: `opspulse` / `opspulse-local-rabbit-password`).

On first run, choose **Create first account**. The first account becomes the administrator. In the default local-development profile, later registrations become members. Administrative changes to teams, routing keys, and on-call schedules require an administrator account.

Useful commands:

```bash
docker compose ps
docker compose logs -f
docker compose down
# Destructive: also removes local database and Redis data
docker compose down --volumes
```

The Compose defaults are for loopback-only local development. Do not expose these defaults to the public internet. Copy `.env.example` to `.env` only if you want to override the local defaults.

## REST Endpoint integration

OpsPulse supports two ingestion forms:

- `POST /api/alerts/v1/alerts/{ROUTING_KEY}` — routing key in the URL, compatible with the common REST Endpoint pattern.
- `POST /api/events` — routing key in the `x-alert-harbor-routing-key` header.

Example:

```bash
curl -i -X POST 'http://127.0.0.1:8080/api/alerts/v1/alerts/YOUR_ROUTING_KEY' \
  -H 'Content-Type: application/json' \
  -d '{"message_type":"CRITICAL","entity_id":"checkout-500","entity_display_name":"Checkout API","state_message":"HTTP 500 rate exceeded","vo_annotate.u.Runbook":"https://example.com/runbook","vo_annotate.s.Context":"Error rate exceeded the service threshold"}'
```

The routing key must be created in **Teams → REST routing keys**. Treat it as a secret; anyone who obtains it can submit events to that integration. The UI only exposes key management to administrators. OpsPulse stores a SHA-256 digest of each routing key and shows the full secret only when it is created; save it securely at that time.

Supported `message_type` values:

| Type | Behavior |
|---|---|
| `CRITICAL` | Creates an incident or updates the active incident with the same team and `entity_id`. |
| `WARNING` | Creates or updates an incident only when warnings are enabled for that routing key. |
| `ACKNOWLEDGEMENT` | Acknowledges the active incident matching the team and `entity_id`. |
| `INFO` | Appends a timeline event and does not open an incident. |
| `RECOVERY` | Resolves the active incident matching the team and `entity_id`. |

`entity_id` is generated when omitted, but producers must send a stable ID to correlate lifecycle messages. `entity_display_name` is the human-readable label; `state_message` carries the details. Annotation prefixes are `vo_annotate.u.<title>` for URLs, `vo_annotate.s.<title>` for text notes (maximum 1,124 characters), and `vo_annotate.i.<title>` for image URLs. Annotation URLs must be valid HTTP(S) URLs.

Success responses include `result: success` and `entity_id`. Failures return `result: failure` and a message. Alert bodies are limited by `MAX_ALERT_BODY_BYTES` (1 MiB by default). The incident service writes lifecycle, timeline, audit, and outbox records in one database transaction. A background worker publishes outbox events to RabbitMQ, sends email for triggered incidents when the team has a valid on-call email configured, and schedules delayed escalation recipients. Acknowledging or resolving an incident cancels pending escalation steps.

## API access

The gateway requires a bearer token for application APIs. Login and initial registration are public; inbound alert routes are authenticated by their routing key. The first registered user becomes an administrator and creates the workspace; later members join that workspace. Each deployment represents one workspace, and incident retention is enforced independently by workspace ID. Administrative mutation routes are restricted to that workspace administrator.

## Database migrations

For local development, SQLAlchemy creates the tables automatically. For a production deployment, set `APP_ENV=production`, provide unique secrets, set `ALLOW_SELF_REGISTRATION=false` and `AUTO_CREATE_SCHEMA=false`, then apply `migrations/001_init.sql` to an empty PostgreSQL database before starting services. Schema evolution should use new ordered migrations; do not edit an already-applied migration in a deployed environment.

Production configuration fails closed when development credentials are detected. Configure a strong unique `JWT_SECRET`, `INTERNAL_API_TOKEN`, PostgreSQL password, and RabbitMQ password through a secret manager. Use HTTPS at the ingress/load balancer, restrict service-to-service network access, configure SMTP credentials/TLS and a real sender address, back up PostgreSQL, and set log/metric retention before public deployment. If using a database password with reserved URL characters, provide a correctly percent-encoded `DATABASE_URL`; a URL-safe random password is simpler for the local Compose configuration.

## Source layout

- `frontend/` — React UI and API client.
- `gateway/` — API routing and JWT authorization.
- `services/identity/` — account registration, login, password hashing, tokens.
- `services/organization/` — team and routing-key management.
- `services/incident/` — incident lifecycle, timeline, audit, and durable outbox writes.
- `services/alert-routing/` — REST Endpoint payload validation and routing-key validation.
- `services/escalation/` — on-call schedules and escalation-policy storage.
- `services/notification/` — SMTP provider and notification endpoint.
- `services/audit/` — audit event reads.
- `services/worker/` — outbox publishing and asynchronous notification delivery.
- `shared/` — database, data models, event contracts, security, and messaging.
- `migrations/` — PostgreSQL schema migration SQL.
- `tests/` — unit and integration-level logic tests.
- `deploy/prometheus/` and `deploy/grafana/` — local observability configuration.

## Tests

Install the development dependencies from the project root, then run:

```bash
pip install -r requirements-dev.txt
pytest -q
python -m compileall -q gateway services shared tests
```

The test suite exercises payload validation, lifecycle transitions, team-scoped aggregation, outbox creation, password/token security, and idempotent notification delivery. Docker image builds and full Compose startup must also be verified in an environment with Docker before treating a release as production-ready.

## License and upstream attribution

This project is distributed under the GNU Affero General Public License v3.0. See `LICENSE`, `TRADEMARKS.md`, and `ORIGINAL-SOFTWARE.md` for the applicable license and attribution context. OpsPulse is not the official upstream product and is not endorsed by the original authors.
