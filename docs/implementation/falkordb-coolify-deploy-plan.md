# FalkorDB on Coolify — executable deployment plan (DRAFT, not executed)

**STATUS 2026-10-15:** attempt 9 STOPPED at §6 step 7 (Coolify scheduled-task command limited to 255 chars). Networks internal, DNS record created,
both services STOPPED; §9 not run.

Prepared 2026-10-14 (EDT); revised the same day after DeepSeek plan reviews 1, 2 and 4-14
(all REJECT; review 3 was not a plan-content review and has no findings to carry; review files are local-only under the gitignored `.ai/reviews/`, so the
findings are restated by ID in §12 with where each is resolved).
Read-only discovery only; no Coolify, Tailscale or 1Password mutation made. Every
mutating step needs the assigned AI reviewer's exact-input APPROVE and
`ai-task-gates check --before infrastructure` first.

## Governing owner decisions (verbatim, recorded on u2giants/theoracle#27, 2026-10-14)
- "i confirm this setup." — website on Vercel; long jobs on Trigger.dev; FalkorDB
  ALONE on Coolify, reachable only over a private, encrypted, authenticated
  connection. The native Coolify gateway/executor/projector pieces move back to Trigger.dev.
- "i created 'Coolify API token - Oracle read/write' as read/write and make it permanent
  because there will always be ongoing maintenance and improvements that has to be done by ai."
- "i don't want it to be solely dependent on tailscale", then "confirmed" to: PRIMARY route =
  public TLS port on hetz (178.156.180.212) requiring a verified client certificate (mTLS) plus
  password; Tailscale is only a SECONDARY/backup route.

**Supersession.** By these decisions this plan supersedes, in
`dev/oracle2/hosting/README.md`, ONLY: "No graph/ledger port is published", "published
store ports" in its not-permitted list, and the executor's no-Tailscale rule (the README
carries a matching banner). The stores ARE published on the public internet, protected by
mutual TLS + password (§3); the tailnet bind is a backup route. The native
gateway/executor/projector topology is superseded by the first decision;
`plan_oracle_consultant_overhaul.md`'s old "Current topology" sentence is marked HISTORICAL,
and both plans' STATUS carry a dated "CURRENT STATUS / DRIFT — October 14, 2026, 4:47 PM EDT" paragraph. Still binding from
the README: pinned digests, non-root hardening (§5), no secrets in argv, candidate/confirmed
separation, no store INTERNET egress (§5 networks; the host and host-published services stay reachable — disclosed residual), verified TLS (§3).
**Host firewall (read-only finding, `u2giants/ansible` main `ca373d0`):** no Ansible change is
needed to OPEN the ports. Its `firewall` role manages only host `filter INPUT` SSH rules
(INPUT default policy ACCEPT; `roles/firewall/README.md`, `AGENTS.md` "Firewall default policy
is ACCEPT"), and Docker-published ports traverse `FORWARD`/`DOCKER` chains, which the role
leaves to Docker; `DOCKER-USER` is empty in `roles/firewall/files/hetz.rules.v4`. Publishing
the port in compose therefore opens it. A provider-level (Hetzner Cloud) firewall is not
modelled in that repository and no Hetzner Cloud API token exists in `vibe_coding` (read-only
lookup 2026-10-14: only "1Password Service Account Token - hetzner_vps"), so `GET /v1/firewalls`
could not be run. **Blocked — no Hetzner Cloud API token in vault;** if §9 check 4 finds the
ports filtered, the root Oracle coordinator asks the owner for a read/write Hetzner Cloud API
token (stored in `vibe_coding`), then reads `GET /v1/firewalls` and, under the same reviewer gate,
adds the inbound TCP 16390-16391 rule by API and re-runs check 4. The only optional
host change — a per-source connection rate limit in `DOCKER-USER` (§3 brute force) — would be a
`roles/firewall` change, and that repository's `.ai-devops/task-gates.json` forbids
`infrastructure`/`production` actions while `plan_oracle_workflow_integrity.md` STATUS records
"Ansible main … still refuses host/infrastructure mutation". It STOPS at that gate and is
not part of this action.

**Existing native apps and data (M4).** The project currently holds 12 applications
(`oracle-public-invented-native*`, live read 2026-10-14). They are NOT touched here.
Stopping/retiring them is a later, separately reviewed step tracked as checklist item
`- [ ] retire native Coolify gateway/executor/projector apps` on u2giants/theoracle#27.
The new stores start EMPTY; there is no migration — the native candidate/confirmed
stores hold synthetic data only.

## 1. Fixed inputs (verified read-only 2026-10-14, Eastern time)
- **Coolify API endpoint (M5/L4): `http://100.66.37.58:8000/api/v1` over the tailnet.**
  `GET /version` returned `4.4.6`. Why not `https://coolify.designflow.app`: its response
  headers show `server: cloudflare` / `cf-ray`, i.e. TLS terminates at Cloudflare's edge,
  not the Coolify origin, so the bearer token would be decrypted by a third party. The
  tailnet path is encrypted end-to-end by WireGuard between this machine and host `hetz`,
  matching the prior record (`docs/operations/oracle-inert-native-application.md`).
  **Gate before every mutation:** `GET /version` must equal `4.4.6`; otherwise STOP.
- **Credential**, by 1Password TITLE only (vault `vibe_coding`, field `credential`):
  "Coolify API token - Oracle read/write" (owner's permanent token) for mutations;
  "Coolify API token - Oracle read-only observer" for reads. The older whole-server item
  "Coolify API Token - Hetz production VPS" is not used. The title contains "/", which an
  `op://` path cannot carry: resolve title→reference privately at execution time and pass
  it only in `op_run` env values; never write an item ID into a repository file.
- **Project** "Oracle native acceptance"; live environments: `production` (id 16) and
  `synthetic-acceptance` (id 17, holds the native acceptance apps). **Target (M3): a NEW
  environment `oracle-graph-production`**, created in §6 step 1, so the graph stores share
  no environment with native or synthetic apps. Server/project/environment UUIDs are
  re-read with the observer token at execution time and recorded only in the issue receipt.
- **Collision check:** list `/applications` (12, none `oracle-falkordb*`), `/services`
  (2, none) and `/databases` (0); abort if any `oracle-falkordb*` or `oracle-graph-production` exists.
- **Image:** `falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d`
  (same digest as theoracle CI, `dev/oracle2/compose.yaml`, `dev/oracle2/hosting/topology.yaml`).
- **Local Docker used for feasibility:** Engine 29.1.3 originally; every network/forwarder/auth/restore
  behaviour re-proven on Engine 29.6.0 (dind, Compose 5.1.4, 2026-10-14; §12), the version hetz runs.

## 2. Two services, one shape
| | confirmed | candidate |
|---|---|---|
| Coolify service | `oracle-falkordb-confirmed` | `oracle-falkordb-candidate` |
| Public bind (PRIMARY) | `178.156.180.212:16390` | `178.156.180.212:16391` |
| Tailnet bind (backup) | `100.66.37.58:6390` | `100.66.37.58:6391` |
| DNS name (server SAN) | `oracle-graph.designflow.app` | `oracle-graph.designflow.app` |
| Volumes | `oracle-falkordb-confirmed-data`, `-backups` | `oracle-falkordb-candidate-data`, `-backups` |
| Password item | `Oracle FalkorDB confirmed — graph password` | `Oracle FalkorDB candidate — graph password` |
| Server TLS item | `Oracle FalkorDB confirmed — server TLS` | `Oracle FalkorDB candidate — server TLS` |
| Worker TLS item | `Oracle FalkorDB confirmed — worker client TLS` | `Oracle FalkorDB candidate — worker client TLS` |
| CA (shared) | `Oracle FalkorDB — private CA` (CA cert + CA key) | same |
| Tailscale ACL port | `tcp:6390` | `tcp:6391` |
Every step runs once per column (`<ROLE>`, `<PUBPORT>` 16390/16391, `<PORT>` 6390/6391).
**Public port choice:** 16390/16391 — unprivileged, not 6379/6380 (constant internet
Redis scanning), outside Coolify/Traefik's 80/443/8000/6001/6002, and paired with the tailnet
ports for readability. Before create, a read-only `nc -zv 178.156.180.212 16390 16391` from
outside must show both closed (nothing else bound); if open, STOP. Shared across roles: image digest, CA, DNS name `oracle-graph.designflow.app`, and
both bind IPs (`178.156.180.212`, `100.66.37.58`); everything else is per role.
**Name collision note:** `oracle-graph.designflow.app` (this FalkorDB endpoint) is unrelated to the
pre-existing Entra/1Password secret `oracle-graph-backend` (`docs/configuration.md`, Microsoft Graph
API access) — different system, different credential; never interchange them.

## 3. Transport, TLS and identities
**PRIMARY:** public TLS on `178.156.180.212:<PUBPORT>`, reached by the worker as
`oracle-graph.designflow.app:<PUBPORT>`. Server: `port 0` (plaintext listener disabled, so
plaintext is rejected), `tls-port 6379`, `tls-protocols "TLSv1.3"`, `tls-auth-clients yes`
(a client certificate signed by the private CA is required before any command), ACL users (no
`requirepass`: it would re-enable the `default` user),
`protected-mode yes`. Trigger static outbound IPs are NOT required; an IP allowlist from a paid
Trigger static-IP plan is an optional later hardening, not a dependency.
**BACKUP:** the same listener reached on tailnet `100.66.37.58:<PORT>` through the separate `tailnet-fwd`
sidecar (§5: raw TCP pass-through, TLS still ends at falkordb; its own container, so a missing tailnet
IP cannot stop the store or the public port; re-resolves `falkordb` every 10 s); reached
via userspace Tailscale (§7) with the same mTLS + password.
**DNS (read-only check 2026-10-14):** `designflow.app` is on Cloudflare (NS
`aida`/`graham.ns.cloudflare.com`); `oracle-graph.designflow.app` does not exist yet;
`coolify.designflow.app` resolves to Cloudflare proxy addresses. The new record must be
**DNS-only (grey cloud)** `A oracle-graph → 178.156.180.212`: the Cloudflare proxy carries only
HTTP(S) on fixed ports (raw TCP needs paid Spectrum) and would terminate TLS, breaking mTLS.
Creating it is a mutation (Cloudflare API, vault item "cloudflare token"), same reviewer gate.

Certificates prove WHO may open a TLS connection; Redis maps no certificate to a user, so any
CA-signed cert (including `hc.crt` inside the server container) can connect. Command authority is
therefore enforced separately by Redis ACL users (§5): `default` disabled; `worker` (password =
vault item, graph commands only, `-@dangerous`, so no CONFIG/DEBUG/MODULE/FLUSHALL); `healthcheck`
(PING only) and `backup` (PING/BGSAVE/LASTSAVE only), both with random passwords generated inside
the container at each start onto tmpfs (never in vault, env or argv). Verified on a throwaway
container of the pinned digest 2026-10-14: worker GRAPH.QUERY CREATE and GRAPH.RO_QUERY succeed;
worker CONFIG GET, MODULE LIST, FLUSHALL → `NOPERM`, DEBUG → refused; healthcheck PING → PONG,
GRAPH.QUERY and GET → `NOPERM`; unauthenticated PING → `NOAUTH`.
Three certificate identities per role, each going ONLY where it is used:
| Identity | Files | Goes to |
|---|---|---|
| Server | `server.crt`, `server.key` (SANs `DNS:oracle-graph.designflow.app`, `IP:178.156.180.212`, `IP:100.66.37.58`, `IP:127.0.0.1`) | server container only (item "server TLS") |
| Healthcheck client | `hc.crt`, `hc.key` (CN `oracle-falkordb-<ROLE>-healthcheck`) | server container only (item "server TLS") |
| Trigger worker client | `worker.crt`, `worker.key` (CN `oracle-trigger-worker-<ROLE>`) | worker item only; never in the server container |
`ca.crt` (public) goes to both. Storage in `vibe_coding`: CA cert + CA key → "Oracle FalkorDB —
private CA"; server + healthcheck cert/key → "Oracle FalkorDB <ROLE> — server TLS"; worker client
cert/key + CA cert → "Oracle FalkorDB <ROLE> — worker client TLS". **CA key handling:** the CA item holds the CA key at rest. For issuance only, it is piped from 1Password into
an ephemeral tmpfs directory (`mktemp -d` under `/dev/shm`, mode 0700), used by `openssl`
to sign the six certificates (two roles × three identities), then the whole directory is
removed (`rm -rf`; on tmpfs `shred` gives no overwrite guarantee, so the protection is that the
files only ever lived in RAM-backed `/dev/shm` and are deleted immediately after signing). It is never written to persistent disk,
a repository, chat or logs. Each item is written via pipe (`op item create … <stdin`).

**Hostname verification.** Primary route: the worker connects to
`oracle-graph.designflow.app:<PUBPORT>` with `ssl_cert_reqs="required"`, `ssl_ca_certs=<CA>`,
`ssl_check_hostname=True`, so the server cert's DNS SAN is verified (no loopback compromise on the
primary path). Installed versions checked: `falkordb` 1.7.1, `redis` 8.1.0, `graphrag_sdk` 1.4.0.
`graphrag_sdk.core.connection.ConnectionConfig` has `ssl`, `ssl_cert_reqs` (default `required`),
`ssl_ca_certs`, `ssl_certfile`, `ssl_keyfile`, `ssl_check_hostname` (default True), passed into the
redis pool; `from_url(url, **kwargs)` lets explicit kwargs win. `falkordb.FalkorDB.__init__` accepts
the same four plus `ssl_check_hostname` (default **False** — must be set True). Backup route only:
connect address is the loopback forwarder, verified against the `IP:127.0.0.1` SAN (neither client
exposes an SNI override); acceptable because the forwarder is in-process and the CA is private.

**Revocation and rotation (owner: root Oracle coordinator).** Certificates are 90-day; rotation every
60 days or on suspicion. On issuance, add to u2giants/theoracle#27 a dated checklist item
`- [ ] rotate FalkorDB certificates by <issue date + 60 days> (owner: root Oracle coordinator)`, and
§9 records each certificate's notAfter.
Revoke a worker identity: issue a new worker cert, update the worker item and Trigger env, then
re-issue the server's trust by rotating the CA if the old cert must die before expiry (Redis has
no CRL support, so revocation = rotate the CA: generate new CA, re-issue all six certs, update the
server env `FALKORDB_SERVER_TLS_B64` and restart, update worker items, archive the old CA item).
Password rotation: new password item value → Coolify env → restart → worker env. Each rotation is
a mutation behind the same reviewer gate; record dates on #27.

**Brute force / rate limit.** Without a valid client certificate the TLS handshake fails before
any AUTH attempt, so the password cannot be guessed by unauthenticated hosts; Redis has no
built-in AUTH rate limit. Residual: handshake-flood DoS on the public port. Mitigation options
(not in this action): the gated Ansible `DOCKER-USER` hashlimit rule (header), or the optional
Trigger static-IP allowlist.

**Worker code change (later action, scoped now):** `services/oracle-brain/oracle_brain/graph/falkor.py`
`FalkorGraphStore.__init__` gains `ca_certs`, `certfile`, `keyfile` inputs and passes
`ssl_ca_certs/ssl_certfile/ssl_keyfile/ssl_cert_reqs="required"/ssl_check_hostname=True` to
`FalkorDB(...)`; `graph/graphrag.py` and `operating_model/sdk_projection.py` pass the same
fields as kwargs to `ConnectionConfig.from_url`. Inputs come from Trigger env file paths,
never URL query parameters.

## 4. Secrets (generated in vault, never echoed)
Load `secrets-to-1password`; serialize 1Password access. Per role:
`op item create --vault vibe_coding --category password --title 'Oracle FalkorDB <ROLE> — graph password' --tags oracle,falkordb,coolify --generate-password='letters,digits,40' >/dev/null`.
TLS items per §3. No item ID is written to any repository file.

## 5. Compose (per role)
Validated by `dev/oracle2/hosting/validate_falkordb_plan.py` (§11), which extracts this
block, substitutes each role, normalizes it with `docker compose config --format json` and requires
exact equality with the committed golden `dev/oracle2/hosting/golden/falkordb-<role>.json`.
**Networks (M6), proven locally on Docker 29.1.3 and re-proven on 29.6.0 (§12):** a container whose only network is
`internal: true` gets NO working published port (TCP connect to the published port refused),
so the README's internal+isolated store network cannot carry the published ingress (public or tailnet). Instead the
service sits on a single bridge with `enable_ip_masquerade=false`: published port answered
`+PONG` (tested on a loopback bind; the public-IP bind is proven live by §9 check 4), and outbound TCP to 1.1.1.1:443 from the container failed (egress blocked). The
data-files job uses `network_mode: none`. After deploy, `docker inspect` (read-only, on the
host by the root Oracle coordinator's host path (HOST-PATH, see §6 step 0b): `docker inspect <ctr> --format '{{json .NetworkSettings.Networks}}'`)
must show the service attached ONLY to
`oracle-graph-<ROLE>` plus Coolify's per-service network `<SVC>` (attempt 7 proved Coolify 4.4.6 always
adds it, `external: true`, created by `docker network create --attachable <SVC>` only when absent; no supported
setting removes it). That network MUST be `internal=true` (no egress); any other egress-capable network → STOP.
The procedure that enforces this is §6 step 4a.
```yaml
name: oracle-falkordb-<ROLE>
services:
  data-files:
    image: falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d
    entrypoint: ["/bin/sh","-c","chown 999:999 /var/lib/falkordb/data /backups && chmod 0700 /var/lib/falkordb/data /backups"]
    user: "0:0"
    cap_drop: [ALL]
    cap_add: [CHOWN, FOWNER]
    security_opt: [no-new-privileges:true]
    read_only: true
    network_mode: none
    restart: "no"
    volumes:
      - oracle-falkordb-<ROLE>-data:/var/lib/falkordb/data
      - oracle-falkordb-<ROLE>-backups:/backups
  falkordb:
    image: falkordb/falkordb:v4.20.7@sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d
    restart: unless-stopped
    user: "999:999"
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    read_only: true
    pids_limit: 256
    mem_limit: 2g
    cpus: 1.0
    networks: [oracle-graph-<ROLE>]
    depends_on: {data-files: {condition: service_completed_successfully}}
    environment:
      FALKORDB_PASSWORD: ${FALKORDB_PASSWORD}
      FALKORDB_SERVER_TLS_B64: ${FALKORDB_SERVER_TLS_B64}  # tar: ca.crt server.crt server.key hc.crt hc.key
    entrypoint: ["/bin/sh","-c"]
    command:
      - |
        set -e; umask 077
        : "$${FALKORDB_PASSWORD:?missing}" "$${FALKORDB_SERVER_TLS_B64:?missing}"
        printf '%s' "$$FALKORDB_SERVER_TLS_B64" | base64 -d | tar -x -C /run/auth
        rnd() { head -c 24 /dev/urandom | base64 | tr -d '/+=\n'; }
        rnd > /run/auth/hc.password; rnd > /run/auth/backup.password
        G='+GRAPH.QUERY +GRAPH.RO_QUERY +GRAPH.DELETE +GRAPH.LIST +GRAPH.EXPLAIN +GRAPH.PROFILE +GRAPH.CONSTRAINT'
        {
          echo 'user default off'
          echo "user worker on >$$FALKORDB_PASSWORD ~* &* -@all +@connection $$G -@dangerous"
          echo "user healthcheck on >$$(cat /run/auth/hc.password) -@all +ping"
          echo "user backup on >$$(cat /run/auth/backup.password) -@all +ping +bgsave +lastsave"
        } > /run/auth/users.acl
        : > /run/auth/server.conf
        unset FALKORDB_PASSWORD FALKORDB_SERVER_TLS_B64 G
        cat >> /run/auth/server.conf <<'EOF'
        port 0
        tls-port 6379
        tls-cert-file /run/auth/server.crt
        tls-key-file /run/auth/server.key
        tls-ca-cert-file /run/auth/ca.crt
        tls-auth-clients yes
        tls-protocols "TLSv1.3"
        bind 0.0.0.0
        protected-mode yes
        dir /var/lib/falkordb/data
        appendonly yes
        appendfsync everysec
        save 900 1
        save 300 100
        aclfile /run/auth/users.acl
        rename-command DEBUG ""
        EOF
        cat > /run/auth/backup.sh <<'BK'
        set -eu; export REDISCLI_AUTH="$$(cat /run/auth/backup.password)"
        C="redis-cli --user backup --tls --cacert /run/auth/ca.crt --cert /run/auth/hc.crt --key /run/auth/hc.key -h 127.0.0.1 -p 6379"
        before=$$($$C LASTSAVE); $$C BGSAVE >/dev/null
        i=0; while [ "$$($$C LASTSAVE)" = "$$before" ]; do i=$$((i+1)); [ $$i -le 600 ] || exit 1; sleep 1; done
        d=/backups/$$(date -u +%Y%m%dT%H%M%SZ); mkdir -m 0700 "$$d"
        cp /var/lib/falkordb/data/dump.rdb "$$d/"
        [ ! -d /var/lib/falkordb/data/appendonlydir ] || cp -r /var/lib/falkordb/data/appendonlydir "$$d/"
        (cd "$$d" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)
        ls -1d /backups/2*/ | sort | head -n -14 | xargs -r rm -rf
        BK
        exec redis-server /run/auth/server.conf --loadmodule /var/lib/falkordb/bin/falkordb.so
    tmpfs:
      - /run/auth:rw,noexec,nosuid,size=1m,uid=999,gid=999,mode=0700
      - /tmp:rw,noexec,nosuid,size=16m,uid=999,gid=999,mode=0700
    volumes:
      - oracle-falkordb-<ROLE>-data:/var/lib/falkordb/data
      - oracle-falkordb-<ROLE>-backups:/backups
    ports:
      - "178.156.180.212:<PUBPORT>:6379"   # PRIMARY: public, mTLS + password
    healthcheck:
      test: ["CMD-SHELL","REDISCLI_AUTH=\"$$(cat /run/auth/hc.password)\" redis-cli --user healthcheck --tls --cacert /run/auth/ca.crt --cert /run/auth/hc.crt --key /run/auth/hc.key -h 127.0.0.1 -p 6379 ping | grep -q PONG"]
      interval: 15s
      timeout: 5s
      retries: 5
  tailnet-fwd:   # backup route only; raw TCP pass-through (TLS ends at falkordb), so a missing
                 # tailnet IP fails THIS container, never the store or its public port
    image: nginx@sha256:72aeb3308ef6cb3118242fb16389518923916dfa206e32d1a8377acc328b9870
    restart: unless-stopped
    user: "101:101"
    cap_drop: [ALL]
    security_opt: [no-new-privileges:true]
    read_only: true
    pids_limit: 32
    mem_limit: 32m
    networks: [oracle-graph-<ROLE>]
    tmpfs:
      - /tmp:rw,noexec,nosuid,size=1m,uid=101,gid=101,mode=0700
    entrypoint: ["/bin/sh","-c"]
    command:
      - |
        printf 'pid /tmp/n.pid; error_log stderr; events {} stream { resolver 127.0.0.11 valid=10s ipv6=off; server { listen 6379; set $$u falkordb:6379; proxy_pass $$u; } }' > /tmp/n.conf
        exec nginx -c /tmp/n.conf -e stderr -g 'daemon off;'
    ports:
      - "100.66.37.58:<PORT>:6379"        # backup: tailnet
networks:
  oracle-graph-<ROLE>:
    name: oracle-graph-<ROLE>
    driver: bridge
    driver_opts:
      com.docker.network.bridge.enable_ip_masquerade: "false"
volumes:
  oracle-falkordb-<ROLE>-data: {name: oracle-falkordb-<ROLE>-data}
  oracle-falkordb-<ROLE>-backups: {name: oracle-falkordb-<ROLE>-backups}
```
**Pinned names:** the network and both volumes carry explicit `name:`, so Docker uses exactly
`oracle-graph-<ROLE>`, `oracle-falkordb-<ROLE>-data`, `oracle-falkordb-<ROLE>-backups` whatever
project name Coolify passes (`-p <uuid>`); every command in this plan uses these names. Verified
`docker compose -p svc-uuid123 config` emits them unprefixed (the top-level `name:` is overridden by
`-p`, so it is documentary only; the resource `name:` pins are what matter). Preflight (read): before §6 step 2
`docker volume ls -q` / `docker network ls` on hetz must show none of these names (STOP if any
exists — a pinned name would otherwise attach to someone else's resource). Container names stay
Coolify-generated; commands resolve them with `docker ps -q --filter label=com.docker.compose.service=falkordb --filter network=oracle-graph-<ROLE>`.
**Host-access residual (L4, measured locally on Docker 29.1.3, 2026-10-14; not re-measured on 29.6.0, §9 check 5 records it on hetz):** on a
`enable_ip_masquerade=false` bridge the container reached its gateway `:22` and `172.17.0.1:22`
(OPEN) while `1.1.1.1:443` timed out; `gateway_mode_ipv4=routed` gave the same, and
`gateway_mode_ipv4=isolated` is refused by Docker for non-internal networks ("can only be used for
an internal network"). No compose network setting blocks host access while publishing a port; only
a host firewall rule could, which is the gated Ansible path. The same route reaches EVERY host-published service: Coolify's own PostgreSQL and Redis,
Traefik 80/443, the Coolify API/UI 8000/6001/6002, other apps' published ports, and host SSH :22
(SSH is additionally restricted by the host INPUT rules to Tailscale/localhost/`10.0.1.0/24`, which
include the Docker bridge range only if it falls in those sources — not assumed). The FalkorDB
container holds the worker graph password in its environment, so a container compromise would have
that network reach PLUS valid store credentials. Recorded as a residual (also in the README
banner); only a gated host firewall `DOCKER-USER`/INPUT rule could close it.
Notes: password reaches redis-cli via `REDISCLI_AUTH` env (not argv). The image entrypoint
and `REDIS_ARGS` route are replaced because config must be materialised from Coolify env
onto tmpfs under a read-only root (recorded deviation from `coolify-synthetic.yaml`). The worker
ACL user cannot run CONFIG/DEBUG/MODULE (`-@dangerous`); `DEBUG` is also renamed away. No domain/FQDN: no Traefik route.

**Token rule (all HTTP calls, Coolify and Cloudflare):** tokens never enter argv. Every call is
`printf 'header = "Authorization: Bearer %s"\n' "$T" | curl --config - …` (curl reads the header
from stdin; `printf` is a shell builtin, so no process argv carries the token). Bodies come from
`--data @<file on tmpfs>` when stdin is used for the config.

## 6. Coolify calls (tailnet endpoint; `op_run`, bodies from stdin, token in env `T`)
Before each step: `GET /version` == `4.4.6`. Lesson from
`docs/operations/oracle-inert-native-application-corrected.md`: 4.4.6 returned 500 on an empty
`docker_compose_domains` array — omit every domain field; if create still returns 500, STOP
and record the body.
0a. Read, preflight (memory overcommit): `cat /proc/sys/vm/overcommit_memory` on hetz. Not readable
   from here 2026-10-14 (Coolify 4.4.6 API has no server-command GET; edge-dev3 SSH to hetz denied for
   ahazan/ai/root) — status Blocked; the executor reads it over its approved host path and records it.
   The image logs `Memory overcommit must be enabled!` at start. If the value is 0: documented risk —
   `BGSAVE`/AOF rewrite fork may fail under memory pressure (backup step then fails loudly, §9 check 7);
   the fix `sysctl vm.overcommit_memory=1` is host config, so it is a SEPARATELY gated Ansible item on
   #27 (`- [ ] vm.overcommit_memory=1 on hetz`), never done in this action.
0d. Note (forwarder re-resolution, proven locally 2026-10-14): with Docker DNS `127.0.0.11`,
   `valid=10s` and a variable upstream, recreating the store on a new IP (192.168.240.2 → .4) kept
   the forwarded route answering after ≤10 s without restarting the forwarder.
0c. Read, preflight (bind IPs): via HOST-PATH, `ip -br addr` on hetz must list BOTH 178.156.180.212
   and 100.66.37.58; either missing → STOP. Decoupling (re-proven on docker:29.6.0-dind, Compose
   5.1.4, 2026-10-14): the public route never depends on Tailscale. With 100.66.37.58 never assigned,
   `compose up` exits 1, `tailnet-fwd` stays `Created`, while the store is healthy and public
   `16391` answers PONG. In a preceding run where the address had been present and was then
   removed, `compose up` exited 0 and Docker listened on the absent address, so container state is
   NOT evidence either way. When the address appears later, the never-started forwarder is NOT started
   automatically (tailnet still refused, measured); it needs a redeploy. A Coolify deploy that reports
   failure must be read per container (`docker ps -a`), not assumed down. **The tailnet route is
   proven only by §9 check 4 (a real mTLS PING over 100.66.37.58), never by container state.**
0b. Read, preflight (host executor): every host-side command in this plan (§5 inspect, step 7 `docker ps`,
   §6 0a, §8 restore, §9 checks 5/7/8, §10) is run ONLY by the root Oracle coordinator over its own
   approved host path (HOST-PATH) — not from edge-dev3, whose SSH to hetz is denied (measured
   2026-10-14). Preflight: HOST-PATH runs `docker version --format '{{.Server.Version}}'` on hetz and
   requires `29.6.0` (read 2026-10-14; any other version → STOP), and reads and records
   `docker compose version --short` (record only, never a STOP; the goldens' generator Compose version is in
   `dev/oracle2/hosting/golden/meta.json` and the validator prints a note on mismatch);
   if HOST-PATH is unavailable → STOP before step 2 (nothing created). HOST-PATH = this executing
   session over one ControlMaster `ai@100.66.37.58` (owner/coordinator-approved substitution).
0. Read, preflight (tailnet bind): `tailscale status` on the executor lists `100.66.37.58 hetz`
   active (read 2026-10-14: yes) and `GET /api/v1/servers` over that address returns 200 — the
   Coolify API itself is served on it, proving the address exists on hetz. If not, STOP before create.
1. Mutation, once: create environment `oracle-graph-production` in the project
   (`POST /projects/<PROJECT_UUID>/environments {"name":"oracle-graph-production"}`); if 4.4.6 answers 404/405 for this route, STOP and report — do not fall back to an existing environment.
Env ordering (L2): Coolify can only attach envs to an existing service, so the compose does NOT use
`${VAR:?}` (which fails `docker compose config` while unset — reproduced); create with
`instant_deploy:false`, add envs, then start. The container's own shell refuses to start if
either value is empty (runtime `:?` check), so a missing env fails closed.
2. Mutation, per role (Coolify 4.4.6 OpenAPI `POST /services`, request fields `type`, `name`,
   `description`, `project_uuid`, `environment_name`, `server_uuid`, `destination_uuid`,
   `instant_deploy`, `docker_compose_raw`; responses 201/400/401/409/422): any 4xx → STOP, record
   the body, create nothing else (the repo's `POST /applications/public` route in
   `prepare_coolify_payload.py` builds an Application from a git repo and is not used here): send `server_uuid`, `project_uuid`,
   `environment_name:"oracle-graph-production"`, `name:"oracle-falkordb-<ROLE>"`, `description`,
   `docker_compose_raw` (base64), `instant_deploy:false`. Record UUID in the issue receipt only.
2a. Resume rule (service already exists from an earlier attempt, compose since changed): with the service
   stopped, `PATCH /services/<SVC>` with only `docker_compose_raw` (base64 of the current rendered role block);
   any 4xx/5xx → STOP. Then read back `GET /services/<SVC>` and require its decoded `docker_compose_raw` to
   normalize (validator `normalize`) byte-equal to the committed golden for that role, else STOP. Re-check that
   both env keys are still present and non-empty (step 3 rule); if Coolify cleared them, re-run step 3.
3. Mutation: `PATCH /services/<SVC>/envs` (body `{"key","value"}`) for `FALKORDB_PASSWORD` and `FALKORDB_SERVER_TLS_B64` — Coolify 4.4.6 auto-creates these keys empty from the compose `${...}` references (attempt 5 got 409 on POST); use `POST` only if a key is absent in `GET /services/<SVC>/envs`. Afterwards re-read the envs and STOP unless both keys are present and non-empty (value never printed). Resume rule: on rerun, reuse the existing environment, confirmed service and 1Password items created by attempt 5 (verify by name/uuid in receipts), never create duplicates;
   body built from env by python, written to a tmpfs file and sent with the token rule (`curl --config - --data @$BODY`); print only the HTTP code.
4. Read: `GET /services/<SVC>` — no FQDN/domain; both env key names present.
4a. Mutation (network, per role, via HOST-PATH, before every start): if `<SVC>` exists: require
   `docker network inspect <SVC>` to list only this role's containers plus `coolify-proxy` (attempt 8: Coolify attaches its Traefik proxy to every service network; any other container → STOP); stop the service (§10 stop) and
   confirm exited; for each listed container `docker network disconnect -f <SVC> <ctr>`; `docker network rm <SVC>`.
   Then `docker network create --internal --attachable <SVC>`, and for each of this role's containers (NOT `coolify-proxy`) recorded above
   `docker network connect <SVC> <ctr>` (works on exited containers; re-binds the endpoint to the new network ID —
   without it a restart fails with "network <old-id> not found"). If step 5 still fails with that error, STOP.
   After step 5: require `docker network inspect <SVC> --format '{{.Internal}}'` = `true` and outbound TCP to
   1.1.1.1:443 from the container to fail; otherwise stop the service and STOP. If Coolify re-attaches
   `coolify-proxy` on start, accept and record it: the service has no FQDN so Traefik routes nothing to it, the
   network stays internal (no egress), and Traefik reachability is already the disclosed host-access residual (§5 L4).
   Any STOP after a service has started: first stop the started services (§10 stop), then report. Ingress uses `oracle-graph-<ROLE>`.
5. Mutation: `POST /services/<SVC>/start` (attempt 6: GET returned 405 "This endpoint has changed to a POST request"). Lifecycle verb rule for start/stop/restart only: if Coolify answers 405 with a message naming the other verb, retry that same endpoint once with the named verb and record it; any other error STOPs.
6. Mutation, once, before §9 (DNS; Cloudflare token from vault item "cloudflare token" in env `CF`).
   Zone id `921eb133a3f7d5802780445b283f84ce` = `designflow.app` (read-only GET
   `/client/v4/zones?name=designflow.app`, 2026-10-14; re-read at execution and STOP if different).
   First `GET /client/v4/zones/<ZONE>/dns_records?name=oracle-graph.designflow.app` must return 0
   records, then:
   `printf '%s' '{"type":"A","name":"oracle-graph.designflow.app","content":"178.156.180.212","ttl":300,"proxied":false,"comment":"Oracle FalkorDB public mTLS endpoint (u2giants/theoracle#27)"}' > "$BODY"` then
   `printf 'header = "Authorization: Bearer %s"\n' "$CF" | curl -sS --config - -X POST https://api.cloudflare.com/client/v4/zones/921eb133a3f7d5802780445b283f84ce/dns_records -H 'Content-Type: application/json' --data @"$BODY"`
   — record the returned record id on #27 with the checklist item
   `- [ ] remove oracle-graph DNS record on rollback`. Pass: `dig +short oracle-graph.designflow.app`
   returns only `178.156.180.212`.
7. Mutation, per role (backup task; Coolify 4.4.6 OpenAPI `POST /services/{uuid}/scheduled-tasks`,
   fields name/command/frequency/container/timeout/enabled): body file on tmpfs
   `{"name":"falkordb-backup","command":"sh /run/auth/backup.sh","frequency":"17 3 * * *","container":"<CTR>","timeout":900,"enabled":true}`
   `<CTR>` is resolved, never hardcoded: first `GET /services/<SVC>` (read) and take the
   `applications[].name` whose compose service is `falkordb` (expected `falkordb`, confirmed live);
   cross-check via HOST-PATH with `docker ps --filter label=com.docker.compose.service=falkordb --filter network=oracle-graph-<ROLE> --format '{{.Names}}'`.
   If no single match → STOP, do not create the task.
   (the body file is built by `python3 -c` with `json.dumps`; the 22-char `command` fits Coolify 4.4.6's
   255-char limit and runs the entrypoint-written §8 script; before creating the task, require
   `docker exec <CTR> sh -n /run/auth/backup.sh` via HOST-PATH to succeed, else STOP), sent with
   the token rule: `… | curl -sS --config - -X POST http://100.66.37.58:8000/api/v1/services/<SVC>/scheduled-tasks -H 'Content-Type: application/json' --data @"$BODY"`;
   record the returned task uuid. For §9 check 7 run it once: `POST /services/<SVC>/scheduled-tasks/<TASK>/execute`,
   then poll `GET /services/<SVC>/scheduled-tasks/<TASK>/executions` until status `success`.
8. Mutation (§9 check 6 restart): `POST /services/<SVC>/restart`, then poll `GET /services/<SVC>` until healthy.

## 7. Tailscale backup route (later action; covers both ports)
Grant `{"src":["tag:oracle-trigger-worker"],"dst":["tag:hetz-coolify"],"ip":["tcp:6390","tcp:6391"]}`,
nothing else to those ports; ephemeral pre-authorized key tagged `tag:oracle-trigger-worker`
(item `Oracle Trigger worker — Tailscale ephemeral auth key`). Worker bootstrap: userspace
`tailscaled`, forwarders 127.0.0.1:16390→100.66.37.58:6390 and 127.0.0.1:16391→:6391, TLS per §3.

## 8. Backup, retention, restore (M8) — owner: root Oracle coordinator
Coolify 4.4.6 scheduled task on each service (container `<CTR>` resolved in §6 step 7), cron `17 3 * * *`,
server timezone America/New_York (verify the service's timezone field reads it; else use
`17 7 * * *` UTC and note DST). Task command (Coolify 4.4.6 limits it to 255 chars; attempt 9 got 500 on the 704-char inline script): `sh /run/auth/backup.sh` — the entrypoint writes this script (byte-identical except the trailing retention comment, which the compose copy omits; retention: keep 14 newest) to tmpfs at every start, so it is pinned by the compose golden:
```sh
set -eu; export REDISCLI_AUTH="$(cat /run/auth/backup.password)"
C="redis-cli --user backup --tls --cacert /run/auth/ca.crt --cert /run/auth/hc.crt --key /run/auth/hc.key -h 127.0.0.1 -p 6379"
before=$($C LASTSAVE); $C BGSAVE >/dev/null
i=0; while [ "$($C LASTSAVE)" = "$before" ]; do i=$((i+1)); [ $i -le 600 ] || exit 1; sleep 1; done
d=/backups/$(date -u +%Y%m%dT%H%M%SZ); mkdir -m 0700 "$d"
cp /var/lib/falkordb/data/dump.rdb "$d/"
[ ! -d /var/lib/falkordb/data/appendonlydir ] || cp -r /var/lib/falkordb/data/appendonlydir "$d/"
(cd "$d" && find . -type f ! -name SHA256SUMS -exec sha256sum {} + > SHA256SUMS)
ls -1d /backups/2*/ | sort | head -n -14 | xargs -r rm -rf   # retention: keep 14 newest
```
Off-server copy: not in this action; checklist item `- [ ] off-server FalkorDB backup copy`
on u2giants/theoracle#27, owner root coordinator.
**Restore test** (before admission, then monthly; owner root coordinator), per role, on the
host as a throwaway, in this ORDER (starting first and copying after loads an empty store — proven):
1. `docker volume create falkordb-restore-<ROLE>`; `docker run --rm --network none -v falkordb-restore-<ROLE>:/d --entrypoint chown <digest> 999:999 /d`
2. Copy + verify via a helper (host paths under `/var/lib/docker/volumes` are not writable directly):
   `docker run --rm --network none --user 999:999 -v oracle-falkordb-<ROLE>-backups:/b:ro -v falkordb-restore-<ROLE>:/d --entrypoint sh <digest> -c 's=$(ls -1d /b/2*/ | sort | tail -1); cp -a "$s"/. /d/ && cd /d && sha256sum -c SHA256SUMS && rm SHA256SUMS'` — any `FAILED` → STOP.
3. Run (`<AOF>` = `yes` if step 2 copied `appendonlydir`, else `no` — with AOF on and no AOF files
   Redis ignores `dump.rdb` and starts empty): `docker run -d --name falkordb-restore-<ROLE> --network none --user 999:999 --read-only --cap-drop ALL --security-opt no-new-privileges:true --tmpfs /tmp -v falkordb-restore-<ROLE>:/var/lib/falkordb/data --entrypoint redis-server <digest> --dir /var/lib/falkordb/data --appendonly <AOF> --loadmodule /var/lib/falkordb/bin/falkordb.so`
   (NO published port; reached by `docker exec` only).
Pass: canary present, `GRAPH.LIST` and node counts equal source. Verified locally 2026-10-14 on the
pinned digest (all files `OK`, canary returned). Then `docker rm -f` and `docker volume rm`.

## 9. Success checks (per role; receipts in the issue)
1. `GET /version` == 4.4.6 before and after.
2. DNS (§6 step 6): `oracle-graph.designflow.app` resolves to `178.156.180.212` only (grey cloud).
   ACL: worker CONFIG GET → `NOPERM`; healthcheck user GRAPH.QUERY → `NOPERM`; `default` → `NOAUTH`.
3. Plaintext refused; TLS without client cert refused; no password `NOAUTH`; wrong `WRONGPASS`.
4. Public route, from edge-dev3 to the PUBLIC IP. First `ip route get 178.156.180.212` must show
   the public uplink `dev eno1 via 192.168.1.2` (edge-dev3's home ISP NIC — read 2026-10-14:
   `178.156.180.212 via 192.168.1.2 dev eno1 src 192.168.3.42`); any other device (`tailscale0`, a
   bridge, a Hetzner private network) → STOP. This path leaves edge-dev3 over the public internet,
   outside Hetzner. Then connect to
   `178.156.180.212:<PUBPORT>` with SNI/verify name `oracle-graph.designflow.app`
   (`openssl s_client -connect 178.156.180.212:<PUBPORT> -servername oracle-graph.designflow.app -verify_hostname oracle-graph.designflow.app -CAfile ca.crt -cert worker.crt -key worker.key -verify_return_error`; the three files are materialized by `op read`
   into a `mktemp -d /dev/shm/fk.XXXX` (mode 0700) and removed at the end), and the locked client
   `uv run --project services/oracle-brain python -c 'import redis; …ssl_certfile/keyfile/ca_certs…'`
   in place of `redis-cli --tls -h oracle-graph.designflow.app -p <PUBPORT> --user worker` (REDISCLI_AUTH): The
   off-tailnet Trigger.dev probe belongs to the later worker action (§13). Checks: `oracle-graph.designflow.app:<PUBPORT>` with CA + worker
   cert + password → PONG with hostname verified (`openssl s_client -verify_hostname`); without client
   cert → handshake refused; plaintext → refused; `178.156.180.212` ports 6390/6391/6379 closed.
   Backup route: same from a tagged tailnet node after §7.
5. Network: service attached only to `oracle-graph-<ROLE>` and Coolify's `<SVC>` network, the latter `Internal=true`; outbound internet TCP from the container
   fails. Host/bridge probe (L4): TCP from the container to its network gateway and to `172.17.0.1`
   is RECORDED, not claimed blocked — see residual below.
6. Canary from edge-dev3 (worker user, public route): `GRAPH.QUERY oracle2_synthetic_probe "CREATE (:Canary {id:'fk-<ROLE>'})"`;
   §6 step 8 restart; `GRAPH.RO_QUERY oracle2_synthetic_probe "MATCH (c:Canary) RETURN c.id"` returns it.
7. §6 step 7 execute → status `success`; restore test of §8 returns the canary.
8. Argv scan for the password VALUE (not the variable name), pattern read from a file so the scanner's
   own argv never holds it, own shell PID skipped: `docker exec <ctr> sh -c 'umask 077; P=/run/auth/scan.pat; sed -n "s/^user worker on >\([^ ]*\) .*/\1/p" /run/auth/users.acl > $P; [ -s $P ] || { echo SCAN-EMPTY-PATTERN; exit 1; }; for f in /proc/[0-9]*/cmdline; do [ "${f#/proc/}" = "$$/cmdline" ] && continue; grep -qaFf $P "$f" 2>/dev/null && echo "LEAK $f"; done; rm -f $P; echo SCAN-RAN'`
   prints exactly `SCAN-RAN` (anything else, including no output, is a FAIL). Verified 2026-10-14 on a throwaway of the pinned digest: clean → no output; a planted
   process carrying the value in argv → `LEAK /proc/<pid>/cmdline`.
9. `GRAPH.DELETE oracle2_synthetic_probe` (worker user) → `OK`; `GRAPH.LIST` no longer lists it.

## 10. Rollback (only what this plan created)
Per role: `POST /services/<SVC>/stop` (same lifecycle verb rule as §6 step 5), then `DELETE /services/<SVC>?delete_volumes=false&delete_connected_networks=true&delete_configurations=true&docker_cleanup=true`
(volumes are KEPT by default; switch to `delete_volumes=true` only after a fresh §8 backup and
only if the store held synthetic data alone); delete the empty
`oracle-graph-production` environment; ONLY when both roles are being removed (the record is shared)
delete the DNS-only `A oracle-graph.designflow.app` record
(Cloudflare API, vault item "cloudflare token"; mutation, same gate) and tick/close the #27
checklist item `- [ ] remove oracle-graph DNS record on rollback` added when the record is created;
archive (not delete) vault items. Nothing else is touched.

## 11. Evidence
**Scope of the automated gate:** the W10 validator/test cover ONLY the compose block. The backup
script, restore commands, argv scan and API payloads are covered by the dated manual local runs
recorded in §8/§9 (not by CI) and are re-proven live by §9 checks 7/8 during execution.
**Validator (test gap):** `services/oracle-brain/tests/test_falkordb_coolify_plan.py` calls the
validator's golden-equality `check` for both roles plus mutation cases (FAILS, never skips, if Docker
Compose v2 is absent; the W10 runner needs it); goldens are in the W10 input hash; no PyYAML needed (the validator normalizes with `docker compose config`, not a YAML library). Required: listed as
`falkordb_coolify_plan` in `scripts/oracle2/verify_workflow_integrity.py` DOCUMENTARY, which
`.github/workflows/oracle2-contracts.yml` runs (`--stage W10`); that runner fails on any skip. `python3 dev/oracle2/hosting/validate_falkordb_plan.py` — run
2026-10-14: PASS for both roles. Gate is EXACT EQUALITY: each role's rendered block, normalized by
`docker compose config --format json` (fixed dummy env), must equal the committed golden fixture
`dev/oracle2/hosting/golden/falkordb-<role>.json` field-for-field and byte-for-byte (entrypoint and
command scripts included, so an appended `>> server.conf`, removed env, `driver: host`, changed
entrypoint, `volumes_from`/`userns_mode` all fail with a unified diff). Goldens change only via
`--write-golden` plus a reviewed fixture diff; the security content of the golden is what §3/§5 state.
**Pre-create feasibility receipt — 2026-10-14**, local throwaway containers of digest
`sha256:13996aa523f0dd283f6bd6df6620b094dcea525452417c4d6ef9bef15dc9998d`, full §5 hardening,
self-signed test CA in a tmpfs dir: (1) container reached `healthy` with TLS-only config;
(2) `redis-cli --tls --cacert --cert --key` + `REDISCLI_AUTH` PING / `GRAPH.QUERY` CREATE and
MATCH succeeded; (3) no-password → `NOAUTH`; (4) plaintext connection refused; (5) no password
in any `/proc/*/cmdline`, healthcheck included; (6) data survived restart; (7) `BGSAVE` copy
restored into a fresh `--network none` container. Plus the two network probes in §5. Not
covered: redis-cli does not verify hostnames (SDK hostname check is a live step). Residual,
accepted: the password is visible in the container environment to Docker/Coolify host
administrators — same trust boundary as Coolify's own env storage. All throwaway resources removed.

## 12. Review findings → resolution
Review 1: H1 supersession (header); H2 credential/endpoint (§1); H3 two services (§2);
M1/M2 doc map + STATUS; M3 hardening (§5); M4 backup volume (§5, §8); M5 healthcheck (§5);
M6 create lesson + collision (§1, §6); M7 ACL both ports + TLS (§3, §7); L1 mutation labels
(§6); L2 pointers (§1, §3); L3 entrypoint deviation (§5).
Re-proof on Engine 29.6.0 (dind, 2026-10-14): health, both routes, mTLS/ACL matrix (worker graph ok;
CONFIG/MODULE/FLUSHALL/GET NOPERM; DEBUG unknown; default NOAUTH; no-cert/rogue/plaintext refused;
healthcheck PING only), no egress (masquerade false; control bridge reached), nginx re-resolve
(.3→.4, immediate, fwd not restarted), §8 backup rc 0, restore sha256 OK + canary; decoupling as §6 0c.
Residual: hetz `vm.overcommit_memory=0` (read 2026-10-14) — BGSAVE/AOF fork may fail under pressure;
fix is the separately gated Ansible item on #27.
Review 16 (APPROVED): M1 hetz Compose recorded not gated, golden meta.json + validator note; M2 29.1.3
lines reconciled; L1 error labels; L2 --write-golden controlled FAIL + parents; L3 mutations both roles;
L4 root plans qualified (provider firewall contingency).
Review 15 (APPROVED; non-blocking): goldens in W10 input hash; §5/§11 gate wording; check 4
`-verify_return_error`; real mutation cases; rollback `delete_volumes=false` by default.
Review 14: validator replaced by exact golden-fixture equality (docker compose config, per role,
byte-compared scripts) + mutation tests for every listed bypass.
Review 13: M §3 describes the sidecar; M forwarder re-resolves (resolver + variable upstream),
proven, validated; L baton state; L cpus/tmpfs asserted.
Review 12: M every server directive exactly once (no additive overrides) + tests; M tailnet port
moved to a separate hardened TCP-forward sidecar, bind-IP preflight 0c, decoupling proven; L
validator controlled FAIL per role; L header/baton.
Review 11: H host checks → root coordinator HOST-PATH + 0b STOP; M OpenAPI-cited create + 4xx
STOP; M restore `--appendonly` follows AOF presence; M "internet egress"; M §11 scope narrowed; L
locked redis client, explicit `sh -eu -c`, /dev/shm certs, HANDOFF.d baton.
Review 10: M banners future tense; M scheduled-task container resolved by GET; L scan guard +
marker; L validator mutation tests; L DNS delete only with both roles; L AOF-optional backup; L header.
Review 9: H pinned network/volume names + top-level name, validator+tests, `compose -p` verified;
M route must be `dev eno1` + closing residual; L healthcheck flag regex; L literal port test; L
docs/deployment.md superseded.
Review 8: 1 exact per-user ACL privilege lists + mutation tests; 2 value-based argv scan from a
pattern file, self-PID skipped, verified; 3 restore order copy→verify→run via 999:999 helper, verified;
4 validator devices/restart/data-files entrypoint/backups mount/volume driver/loadmodule; 5
overcommit preflight (§6 0a).
Review 7: H §6 steps 7-8 (scheduled task + restart, OpenAPI v4.4.6); H §9.4 edge-dev3 public IP +
`ip route get`, Trigger probe deferred; M validator depends_on/tmpfs/parsed config + specific-error
tests; M Hetzner Blocked wording; M residual blast radius; L bind wording; L §9.5/6/9 commands.
Review 6: 1 token rule (stdin curl config, §6); 2 requirepass removed (§3); 3 Hetzner firewall
unverified + owner contingency (header); 4 validator backup/appendonly/DEBUG/bind + removal tests; 5
compose test hard-fails; 6 tailnet preflight (§6 step 0); 7 plan+validator in W10 input hash; 8 tmpfs
wording (§3); 9 named probe sources (§9).
Review 5: H test wired into `scripts/oracle2/verify_workflow_integrity.py` DOCUMENTARY list (§11);
M uv.lock regenerated (`uv lock --check` 0); M DNS as §6 step 6; M ACL users (§3, §5); L validator
long-syntax binds + TLS paths + single substitution path; L shared-items text (§2); L header; L name
collision (§2).
Review 4: M1 validator strengthened (§11); M2 network model in README banner; M3 DNS rollback
(§10); L1 rotation owner (§3); L2 env ordering (§6); L3 pytest declared; PyYAML not needed (§11); L4 host
residual (§5, §9).
Owner route decision (public mTLS primary, Tailscale backup): header, §2, §3, §5, §9.
Review 2: H1 three identities (§3); H2 CA key wording (§3); M1 overhaul line marked
HISTORICAL; M2 README banner + doc-map hosting row; M3 new environment (§1, §6); M4 native
apps/no migration (header); M5 tailnet endpoint + version gate (§1); M6 networks (§5); M7
client scope + versions (§3); M8 backup script/owner/restore (§8); L1 review files
local-only (top); L2 section refs fixed; L3 receipt (§11); L4 version gate (§1, §6); test gap (§11).

## 13. Scope and open items
THIS action: create the DNS-only record, the environment and two services, prove §9. Later,
separately reviewed: Tailscale backup grant/key (§7), Trigger.dev off-tailnet route probe, DOCKER-USER rate limit (Ansible gate),
optional Trigger static-IP allowlist, worker code change (§3), native-app retirement and off-server backup
(both #27 checklist items). Open: Tailscale admin credential not yet identified.

**Closing residual (carried into the #27 receipt):** THIS action proves the public route only from
one external vantage (edge-dev3, home ISP). Reachability from the real consumer network (Trigger.dev
cloud) and the state of any Hetzner Cloud firewall remain unproven until the later worker action's
Trigger.dev probe; #27 item `- [ ] public route proven from Trigger.dev (closes FalkorDB route residual)`.
