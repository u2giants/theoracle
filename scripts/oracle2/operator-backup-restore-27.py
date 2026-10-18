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
import json, os, sys, subprocess, datetime, hashlib, time

APP = "oracle-native-vhmcdkdk23dgvjvcvhyhcjzd"
SSH = ["ssh", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=yes",
       "-o", "ConnectTimeout=15", "vps2"]
BACKUP_ROOT = f"/tmp/oracle-backup-27-{APP}"
RESTORE_ROOT = f"/tmp/oracle-restore-27-{APP}"
# store/ledger/spool volumes (data only, not auth)
DATA_VOLUMES = [
    f"{APP}_ledger-data",
    f"{APP}_candidate-data",
    f"{APP}_confirmed-data",
    f"{APP}_job-spool",
    f"{APP}_executor-blobs",
]

RECEIPTS = []

def now():
    return datetime.datetime.now(datetime.timezone.utc).isoformat()

def receipt(kind, status, detail):
    rec = {"ts": now(), "kind": kind, "status": status, "detail": detail}
    RECEIPTS.append(rec)
    print(json.dumps(rec, default=str), flush=True)
    return rec

def ssh(cmd, timeout=120):
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
            f"docker run --rm -v {v}:/data:ro alpine:3.20 sh -c 'du -sb /data 2>/dev/null; find /data -type f | wc -l' 2>/dev/null"
        )
        lines = out.strip().splitlines()
        size = lines[0].split()[0] if lines else "?"
        fcount = lines[1] if len(lines) > 1 else "?"
        inv[v] = {"bytes": size, "files": fcount, "rc": rc}
    receipt("pre-backup-inventory", 0, inv)

    if not confirm:
        receipt("mode", "read-only", "pass --confirm to backup+restore")
        print(json.dumps({"result": "READ_ONLY_OK", "volumes": DATA_VOLUMES}))
        return 0

    # Phase 2: backup each volume (read-only mount, tar to backup root)
    rc, out, err = ssh(f"mkdir -p {BACKUP_ROOT} && chmod 700 {BACKUP_ROOT}")
    receipt("backup-root", rc, {"path": BACKUP_ROOT})
    backup_hashes = {}
    for v in DATA_VOLUMES:
        tarpath = f"{BACKUP_ROOT}/{v}.tar.gz"
        rc, out, err = ssh(
            f"docker run --rm -v {v}:/data:ro -v {BACKUP_ROOT}:/backup alpine:3.20 "
            f"sh -c 'tar -czf /backup/{v}.tar.gz -C /data . && sha256sum /backup/{v}.tar.gz'"
            , timeout=180
        )
        hline = out.strip().splitlines()[-1] if out.strip() else ""
        h = hline.split()[0] if hline else ""
        backup_hashes[v] = {"sha256": h, "rc": rc, "tar": tarpath}
        receipt("backup-volume", rc, {"volume": v, "sha256": h})
        if rc != 0 or not h:
            receipt("backup", "FAILED", {"volume": v, "err": err[:200]})
            return 1

    # Phase 3: create empty restore volumes + restore
    rc, out, err = ssh(f"mkdir -p {RESTORE_ROOT} && chmod 700 {RESTORE_ROOT}")
    receipt("restore-root", rc, {"path": RESTORE_ROOT})
    restore_hashes = {}
    for v in DATA_VOLUMES:
        rv = f"{v}-restore27"
        # remove any prior restore volume (safe: named -restore27 only)
        ssh(f"docker volume rm -f {rv} 2>/dev/null; docker volume create {rv}")
        rc, out, err = ssh(
            f"docker run --rm -v {rv}:/data -v {BACKUP_ROOT}:/backup:ro alpine:3.20 "
            f"sh -c 'tar -xzf /backup/{v}.tar.gz -C /data && du -sb /data && find /data -type f | wc -l'"
            , timeout=180
        )
        lines = out.strip().splitlines()
        size = lines[0].split()[0] if lines else "?"
        fcount = lines[1] if len(lines) > 1 else "?"
        restore_hashes[v] = {"restore_volume": rv, "bytes": size, "files": fcount, "rc": rc}
        receipt("restore-volume", rc, {"volume": v, "restore_volume": rv, "bytes": size, "files": fcount})

    # Phase 4: verify pre vs restore file counts
    verify_ok = True
    for v in DATA_VOLUMES:
        pre_f = inv.get(v, {}).get("files", "?")
        post_f = restore_hashes.get(v, {}).get("files", "?")
        if str(pre_f) != str(post_f):
            verify_ok = False
            receipt("verify-mismatch", "FAIL", {"volume": v, "pre_files": pre_f, "post_files": post_f})

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
        receipt("verify", "NOT_PROVED", {"reason": "file count mismatch"})
        print(json.dumps({"result": "NOT_PROVED", "reason": "file count mismatch"}))
        return 1

if __name__ == "__main__":
    sys.exit(main())
