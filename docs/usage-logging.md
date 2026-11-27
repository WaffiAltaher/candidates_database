# Usage logging

The container logs every request and counts usage per day, to see how the system is used.

## What is logged

One logfmt line per request, written by `container/main.py` through the `access` logger (`candidates/access_log.py`):

```
event=request method=POST path=/search status=200 duration_ms=1840 user=alice network=203.0.113.0/24 country=NL request_id=3f2a9c
```

| Field | Meaning |
|---|---|
| `event` | Always `request` |
| `method`, `path`, `status` | HTTP method, path (no query string), response status |
| `duration_ms` | Time to handle the request |
| `user` | Authenticated username; on `/login` the raw typed username; `-` if none |
| `network` | Client network: IPv4 truncated to /24, IPv6 to /48; `-` if unknown |
| `country` | ISO country code; `-` if unknown |
| `request_id` | The `X-Request-ID` header, `-` if absent |

The full IP is never stored: it is truncated in the app (`candidates/client_network.py`) and only the network is logged. The client address comes from the `X-Real-IP` header (falling back to the TCP peer; `X-Forwarded-For` is ignored). The country comes from DB-IP Country Lite, downloaded at each image build into `/app/geoip/dbip-country-lite.mmdb` (override with `GEOIP_DB_PATH`).

## Where and how long

- **Cockpit "Scaleway Logs"** keeps every line for **7 days**.
- **`usage_daily`** (PostgreSQL) keeps **daily totals for 12 months**. One row per `(day, username, network, country)` with the counters:
  - `requests`: authenticated requests.
  - `logins`: successful logins.
  - `failed_logins`: wrong password. For an unknown username the row is `(unknown)` with network and country `*`.
  - `blocked_logins`: logins refused by the rate limit (429). The row has network and country `*`; unknown usernames go to `(unknown)`.
  - Days are Europe/Amsterdam calendar days.
  - Rows older than one year are deleted automatically, at the first write each day.

## Privacy

- **Purpose:** usage statistics.
- **Lawful basis:** legitimate interest (GDPR Art. 6(1)(f)).
- **Minimisation:** only the truncated network and country are kept, never the full IP (see `docs/adr/0002-log-truncated-client-networks.md`).
- **Transparency:** the login page shows a notice with a link to this section.
- **Known caveat:** AI search can technically read `usage_daily`. The prompt tells the model not to; that is not a hard barrier. Accepted.
- **Known caveat:** the raw typed username on `/login` is logged, so a password typed into the username field would appear in Cockpit for 7 days. Accepted.

## Data-subject requests

Rows in `usage_daily` for one user:

```sql
SELECT * FROM usage_daily WHERE username = 'alice';
DELETE FROM usage_daily WHERE username = 'alice';
```

Cockpit lines: find them with the Loki query by `user` (see below). Cockpit lines expire after 7 days and cannot be deleted individually.

## Viewing usage

The **Usage** page in the app shows the daily totals.

For the detailed lines, open Cockpit: Scaleway console → Cockpit → Open dashboards (Grafana) → Explore → data source **Scaleway Logs**.

Scaleway wraps each output line in JSON (`{"stream":..., "message":"<our line>"}`), so queries unwrap it before `logfmt`. Do not filter on `stream`; filter on `event="request"`. The selector below is for the current container; the `resource_name` prefix comes from the Terraform namespace and changes only if the namespace is recreated. If it stops matching, copy the current value from Explore → label browser.

Selector: `{resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"}`

All request lines:

```
{resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request"
```

One user's lines:

```
{resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" | user="alice"
```

Requests per day:

```
sum(count_over_time({resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" [1d]))
```

Requests per country over 7 days:

```
sum by (country) (count_over_time({resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" [7d]))
```

Top networks:

```
topk(10, sum by (network) (count_over_time({resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" [7d])))
```

Failed logins:

```
{resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" | path="/login" | status="401"
```

One request by `request_id`:

```
{resource_type="serverless_container", resource_name="candidatesdb25d8ab32-candidates-api"} | json | line_format "{{.message}}" | logfmt | event="request" | request_id="3f2a9c"
```

## Credits

IP geolocation by [DB-IP](https://db-ip.com), licensed CC-BY 4.0.
