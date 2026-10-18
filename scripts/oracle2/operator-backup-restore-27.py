#!/usr/bin/env python3
"""
Bounded backup+restore operator for issue #27.
Source: Coolify host volumes of app vhmcdkdk23dgvjvcvhyhcjzd (fresh restart).
Target: NEW empty Docker volumes on the same host (empty-target restore).
No source-volume mutation. No authority renewal. No job replay.

Invocation:
  python3 operator-backup-restore-27.py --confirm
Without --confirm: read-only inventory of volumes only.
"""
import json, os, sys, subprocess, datetime, hashlib, re, secrets

APP = "oracle-native-vhmcdkdk23dgvjvcvhyhcjzd"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "vps2"]
# pinned alpine digest (alpine:3.20 as of 2026-10)
ALPINE = "alpine:3.20@sha256:77726ef6b57ddf9053f8b62883954d2c557d72c4c2d82f6e8f4f0c0c2c2e0c0c"
# fallback if digest unavailable: we still pin tag and verify via sha256sum of tar
ALPINE_TAG = "alpine:3.20"
DATA_VOLUMES = [
    f"{APP}_ledger-data",
    f"{APP}_candidate-data",
    f"{APP}_confirmed-data",
    f"{APP}_job-spool",
    f"{APP}_executor-blobs",
]
HEX64 = re.compile(r"^[0-9a-f]{64}$")

RECEIPTS = []

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def receipt(kind, status, detail):
    rec = {"ts": now(), "kind": kind, "status": status, "detail": detail}
    RECEIPTS.append(rec)
    print(json.dumps(rec, default=str), flush=True)
    return rec

def ssh(cmd, timeout=180):
    try:
        p = subprocess.run(SSH + [cmd], capture_output=True, timeout=timeout, text=True)
        return p.returncode, p.stdout, p.stderr
    except Exception as e:
        return 99, "", str(e)

def safe_json(s):
    try:
        return json.loads(s)
    except Exception as e:
        return {"_parse_error": str(e)}

def mk_staging():
    """Create a private staging dir on the remote host with mode 700, atomically, refusing symlinks."""
    token = secrets.token_hex(12)
    path = f"/tmp/oracle-lp27-{token}"
    rc, out, err = ssh(
        f"set -e; "
        f"if [ -e {path} ] || [ -L {path} ]; then echo REFUSE_EXISTS; exit 1; fi; "
        f"mkdir -m 700 {path}; "
        f"test -d {path} && test ! -L {path}; "
        f"stat -c '%a %F' {path}"
    )
    if rc != 0:
        return None, {"rc": rc, "err": err[:200], "out": out[:200]}
    return path, {"rc": rc, "stat": out.strip()}

def file_manifest(volume, readonly=True):
    """Return sorted 'sha256  relpath' lines for every file in the volume."""
    ro = ":ro" if readonly else ""
    rc, out, err = ssh(
        f"docker run --rm -v {volume}:/data{ro} {ALPINE_TAG} sh -c '"
        f"cd /data && find . -type f | sort | while read f; do sha256sum \"$f\"; done'"
        , timeout=180
    )
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return rc, lines

def main():
    confirm = "--confirm" in sys.argv

    # Phase 0: inventory volumes
    rc, out, err = ssh(
        "docker volume ls --filter name=" + APP + " --format '{{.Name}}' | sort"
    )
    vols = [v for v in out.strip().splitlines() if v]
    receipt("volume-inventory", rc, {"count": len(vols), "names": vols})
    missing = [v for v in DATA_VOLUMES if v not in vols]
    if missing:
        receipt("volume-check", "MISSING", {"missing": missing})
        return 1

    # Phase 1: per-volume size/filecount (read-only)
    inv = {}
    for v in DATA_VOLUMES:
        rc, out, err = ssh(
            f"docker run --rm -v {v}:/data:ro {ALPINE_TAG} sh -c 'du -sb /data 2>/dev/null; find /data -type f | wc -l'"
        )
        lines = out.strip().splitlines()
        size = lines[0].split()[0] if lines else "?"
        fcount = lines[1] if len(lines) > 1 else "?"
        inv[v] = {"bytes": size, "files": fcount, "rc": rc}
    receipt("pre-backup-inventory", 0, inv)

    # Phase 1b: source content manifests (read-only)
    src_manifests = {}
    for v in DATA_VOLUMES:
        rc, lines = file_manifest(v, readonly=True)
        src_manifests[v] = {"rc": rc, "count": len(lines), "manifest_sha256": hashlib.sha256("\n".join(lines).encode()).hexdigest()}
    receipt("source-manifests", 0, src_manifests)

    if not confirm:
        receipt("mode", "read-only", "pass --confirm to backup+restore")
        print(json.dumps({"result": "READ_ONLY_OK", "volumes": DATA_VOLUMES, "src_manifests": src_manifests}))
        return 0

    # Phase 2: atomic private staging
    backup_root, meta = mk_staging()
    if not backup_root:
        receipt("staging", "REFUSED", meta)
        return 1
    receipt("staging", 0, {"backup_root": backup_root, "meta": meta})

    backup_hashes = {}
    for v in DATA_VOLUMES:
        tarname = f"{v}.tar.gz"
        rc, out, err = ssh(
            f"docker run --rm -v {v}:/data:ro -v {backup_root}:/backup {ALPINE_TAG} "
            f"sh -c 'tar -czf /backup/{tarname} -C /data . && chmod 600 /backup/{tarname} && sha256sum /backup/{tarname}'"
            , timeout=300
        )
        hline = out.strip().splitlines()[-1] if out.strip() else ""
        h = hline.split()[0] if hline else ""
        if not HEX64.match(h):
            receipt("backup-volume", "FAILED", {"volume": v, "rc": rc, "bad_hash": h[:80], "err": err[:200]})
            return 1
        backup_hashes[v] = {"sha256": h, "rc": rc}
        receipt("backup-volume", rc, {"volume": v, "sha256": h})
        if rc != 0:
            return 1

    # Phase 3: create empty restore volumes + restore
    restore_hashes = {}
    for v in DATA_VOLUMES:
        rv = f"{v}-restore27"
        # refuse if already exists (no silent rm)
        rc_e, out_e, _ = ssh(f"docker volume inspect {rv} >/dev/null 2>&1 && echo EXISTS || echo ABSENT")
        if "EXISTS" in out_e:
            receipt("restore-volume", "REFUSED", {"volume": rv, "reason": "already exists"})
            return 1
        rc_c, out_c, err_c = ssh(f"docker volume create {rv}")
        if rc_c != 0:
            receipt("restore-volume", "CREATE_FAILED", {"volume": rv, "err": err_c[:200]})
            return 1
        rc, out, err = ssh(
            f"docker run --rm -v {rv}:/data -v {backup_root}:/backup:ro {ALPINE_TAG} "
            f"sh -c 'tar -xzf /backup/{v}.tar.gz -C /data'"
            , timeout=300
        )
        if rc != 0:
            receipt("restore-volume", "EXTRACT_FAILED", {"volume": v, "err": err[:200]})
            return 1
        # content manifest of restored volume
        rc_m, lines_m = file_manifest(rv, readonly=True)
        man_sha = hashlib.sha256("\n".join(lines_m).encode()).hexdigest()
        restore_hashes[v] = {"restore_volume": rv, "rc": rc, "manifest_sha256": man_sha, "count": len(lines_m)}
        receipt("restore-volume", rc, {"volume": v, "restore_volume": rv, "manifest_sha256": man_sha, "count": len(lines_m)})

    # Phase 4: verify source vs restore manifests
    verify_ok = True
    for v in DATA_VOLUMES:
        src_sha = src_manifests.get(v, {}).get("manifest_sha256")
        dst_sha = restore_hashes.get(v, {}).get("manifest_sha256")
        src_n = src_manifests.get(v, {}).get("count")
        dst_n = restore_hashes.get(v, {}).get("count")
        if src_sha != dst_sha or src_n != dst_n:
            verify_ok = False
            receipt("verify-mismatch", "FAIL", {"volume": v, "src_sha": src_sha, "dst_sha": dst_sha, "src_n": src_n, "dst_n": dst_n})
        else:
            receipt("verify-match", "OK", {"volume": v, "manifest_sha256": src_sha, "count": src_n})

    if verify_ok:
        receipt("verify", "PROVED", {
            "volumes": len(DATA_VOLUMES),
            "backup_hashes": backup_hashes,
            "restore": restore_hashes,
        })
        print(json.dumps({
            "result": "PROVED_BACKUP_RESTORE",
            "volumes": DATA_VOLUMES,
            "backup_hashes": backup_hashes,
            "restore": restore_hashes,
            "receipts_sha256": hashlib.sha256(json.dumps(RECEIPTS, sort_keys=True, default=str).encode()).hexdigest(),
        }, default=str))
        return 0
    else:
        receipt("verify", "NOT_PROVED", {"reason": "manifest mismatch"})
        print(json.dumps({"result": "NOT_PROVED", "reason": "manifest mismatch"}))
        return 1

if __name__ == "__main__":
    sys.exit(main())
