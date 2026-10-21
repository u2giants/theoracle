<!-- Privacy rendering: infrastructure references are non-executable publication placeholders. Original Git blob f233ef5091b7ecad8120ba66805506c3f417d0a7 at ab73ef791ad48f187fa5d2998428aec99ce6bd82; exact originals are retained in the #27 private custody archive. No obligations, authority, timing or acceptance are changed. -->
# Exact read-only native hosting preflight

Status: REVIEW_REQUIRED. No execution has occurred.

Owner: Codex chat 01a132aa-596e-7d72-9957-cbabf6a79cf6 on #27/#58.
Prepared October 12, 2026, 8:56 PM EDT. This requests independent review of precisely one read-only inventory, not installation or credential issuance.

Merged application source: d97b0023c75c2f83c3c6404dbbdaecf2098e26a0. Existing target is the known hetz peer, exact SSH target ai@hetz with strict existing known-host verification. Existing ai login password is injected through the protected vault process into ORACLE_HETZ_READ_PASSWORD; reviewers never access the vault. No new credential, provider call, source processing, server edit, container start/stop/removal or network mutation is authorized.

The verbatim retained public operator below is retained with the sole reviewed change that its SSH known-host input is a mode0600 owned snapshot, then copied byte-for-byte to this session's protected private receipt directory, mode0700, and executed once. Operator SHA256: 36a1a171c80635f5343731d705ba292ccb0c21fe457d6fe447998ad944c62050. It validates supplied Docker IDs and runs only two bounded remote commands: `docker network ls --no-trunc --format '{{.ID}}'` and `docker network inspect` followed by validated exact network IDs. It drops secret environment before children, uses no shell locally, disables SSH agent/forwardings/control reuse, keeps the existing password only in a0600 temporary file read through an0700 askpass helper, and deletes only that newly owned temporary credential folder when done. Remote raw output is held in memory and never printed; persisted projection contains only CIDR collision receipts and hashes. No secret values enter arguments, reports or repositories. Failures refuse; no retry or host-key replacement.

Purpose: fresh collision receipt for the eight proposed IPv4/IPv6 ranges 172.30.41–44.0/24 and fd42:6f72:6163:41–44::/64. Receipt is preparation only. Docker isolated-mode qualification, exact merged image publication/managed pull, inert Application creation, synthetic issuer/bundle review, platform env installation, deployment and remote acceptance require separate exact-input action review and task gates before mutations.

Reviewer must state whether this precise read-only inventory is APPROVE, REJECT or BLOCKED; an APPROVE does not authorize any later mutation.

## Verbatim operator

```python
"""Exact existing-credential host READ ONLY bridge. Requires root action review."""
import hashlib
import ipaddress
import json
import os
from pathlib import Path
import re
import selectors
import subprocess
import tempfile
import time

LIMIT=1_048_576
TARGET='ai@hetz'
PROSPECTIVE=tuple([f'172.30.{i}.0/24' for i in range(41,45)]+[f'fd42:6f72:6163:{i}::/64' for i in range(41,45)])

class Denied(Exception):pass

def bounded_read(argv):
    # No shell, forwarding, retry, credential environment, or remote write.
    process=subprocess.Popen(argv,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        env={k:v for k,v in os.environ.items() if k in ('PATH','HOME','LANG','LC_ALL','SSH_ASKPASS','SSH_ASKPASS_REQUIRE','DISPLAY','ORACLE_PASSWORD_FILE')},stdin=subprocess.DEVNULL)
    selector=selectors.DefaultSelector();buffers={'stdout':bytearray(),'stderr':bytearray()}
    selector.register(process.stdout,selectors.EVENT_READ,'stdout')
    selector.register(process.stderr,selectors.EVENT_READ,'stderr')
    deadline=time.monotonic()+20
    try:
        while selector.get_map():
            remaining=deadline-time.monotonic()
            if remaining<=0:raise Denied('ssh_timeout')
            for key,_ in selector.select(min(remaining,0.2)):
                chunk=os.read(key.fileobj.fileno(),65536)
                if not chunk:selector.unregister(key.fileobj);continue
                buffers[key.data].extend(chunk)
                if len(buffers[key.data])>(LIMIT if key.data=='stdout' else 4096):
                    raise Denied('response_limit')
        code=process.wait(timeout=max(0.001,deadline-time.monotonic()))
        if code!=0:raise Denied('ssh_exit_nonzero')
        return bytes(buffers['stdout'])
    except subprocess.TimeoutExpired:raise Denied('ssh_timeout')
    finally:
        selector.close()
        if process.poll() is None:process.kill();process.wait(timeout=2)
        process.stdout.close();process.stderr.close()
        buffers['stderr'].clear()

def ids_from(raw):
    try:ids=raw.decode('ascii').splitlines()
    except UnicodeDecodeError:raise Denied('invalid_network_ids')
    if not 1<=len(ids)<=100 or len(set(ids))!=len(ids) or any(not re.fullmatch('[0-9a-f]{64}',x) for x in ids):
        raise Denied('invalid_network_ids')
    return ids

def unique_object(pairs):
    result={}
    for key,value in pairs:
        if key in result:raise Denied('duplicate_json_field')
        result[key]=value
    return result

def projection(raw,expected_ids):
    try:rows=json.loads(raw,object_pairs_hook=unique_object)
    except (ValueError,UnicodeDecodeError):raise Denied('invalid_network_json')
    if not isinstance(rows,list) or len(rows)!=len(expected_ids):raise Denied('invalid_network_population')
    returned=[row.get('Id') if isinstance(row,dict) else None for row in rows]
    if len(set(returned))!=len(returned) or set(returned)!=set(expected_ids):raise Denied('invalid_network_identity')
    ipam=[]
    for row in rows:
        if not isinstance(row,dict) or not isinstance(row.get('IPAM'),dict):raise Denied('invalid_ipam')
        configs=row['IPAM'].get('Config') or []
        if not isinstance(configs,list) or len(configs)>100:raise Denied('invalid_ipam')
        for config in configs:
            if not isinstance(config,dict) or not isinstance(config.get('Subnet'),str):raise Denied('invalid_subnet')
            try:
                subnet=ipaddress.ip_network(config['Subnet'],strict=True)
                gateway=ipaddress.ip_address(config['Gateway']) if config.get('Gateway') else None
            except ValueError:raise Denied('invalid_subnet')
            if gateway is not None and (gateway.version!=subnet.version or gateway not in subnet):raise Denied('invalid_gateway')
            ipam.append({'subnet':str(subnet),'gateway':str(gateway) if gateway else None})
    overlaps={}
    for candidate in PROSPECTIVE:
        wanted=ipaddress.ip_network(candidate)
        overlaps[candidate]=any(wanted.version==ipaddress.ip_network(x['subnet']).version and wanted.overlaps(ipaddress.ip_network(x['subnet'])) for x in ipam)
    return {'network_count':len(rows),'ipam':ipam,'inspect_sha256':hashlib.sha256(raw).hexdigest(),'overlap':overlaps}

def main():
    # Pop before writing a key or launching any child. No child inherits it.
    password=os.environ.pop('ORACLE_HETZ_READ_PASSWORD','')
    if not password or len(password.encode())>65536 or '\x00' in password or '\n' in password or '\r' in password:
        raise Denied('password_field_rejected')
    known=Path(__file__).resolve().parent/'known-hosts.snapshot'
    if not known.is_file():raise Denied('existing_known_hosts_required')
    root=Path(__file__).resolve().parent
    if root.stat().st_mode&0o777!=0o700:raise Denied('protected_receipt_directory_required')
    with tempfile.TemporaryDirectory(prefix='oracle-hetz-read-') as directory:
        os.chmod(directory,0o700);path=Path(directory)/'existing-password'
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,'w') as file:file.write(password);file.flush();os.fsync(file.fileno())
        password=''
        wrapper=Path(directory)/'askpass'
        wrapper_source="#!/usr/bin/python3\nimport os,stat,sys\np=os.environ['ORACLE_PASSWORD_FILE']\nf=os.open(p,os.O_RDONLY|os.O_NOFOLLOW)\ns=os.fstat(f)\nif not stat.S_ISREG(s.st_mode) or stat.S_IMODE(s.st_mode)!=0o600 or s.st_uid!=os.getuid():sys.exit(1)\nv=os.read(f,65537)\nos.close(f)\nif not v or len(v)>65536 or any(c in v for c in (b'\\x00',b'\\n',b'\\r')):sys.exit(1)\nsys.stdout.buffer.write(v+b'\\n')\n"
        fd=os.open(wrapper,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o700)
        with os.fdopen(fd,'w') as file:file.write(wrapper_source);file.flush();os.fsync(file.fileno())
        os.environ.update(SSH_ASKPASS=str(wrapper),SSH_ASKPASS_REQUIRE='force',DISPLAY='oracle-readonly:0',ORACLE_PASSWORD_FILE=str(path))
        ssh=['/usr/bin/ssh','-n','-F','/dev/null','-o','PubkeyAuthentication=no','-o','IdentityAgent=none','-o','BatchMode=no','-o','NumberOfPasswordPrompts=1','-o','PreferredAuthentications=password','-o','ConnectTimeout=10','-o','StrictHostKeyChecking=yes','-o','UserKnownHostsFile='+str(known),'-o','GlobalKnownHostsFile=/dev/null','-o','PasswordAuthentication=yes','-o','KbdInteractiveAuthentication=no','-o','ForwardAgent=no','-o','ClearAllForwardings=yes','-o','RequestTTY=no','-o','ControlMaster=no','-o','ControlPath=none',TARGET]
        listed=bounded_read(ssh+["docker network ls --no-trunc --format '{{.ID}}'"])
        ids=ids_from(listed)
        inspected=bounded_read(ssh+['docker network inspect '+' '.join(ids)])
        result=projection(inspected,ids);del inspected,listed,ids
        for variable in ('SSH_ASKPASS','SSH_ASKPASS_REQUIRE','DISPLAY','ORACLE_PASSWORD_FILE'):os.environ.pop(variable,None)
    result.update(schema='oracle-readonly-ipam/v1',operator_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),production_mutations=0,credential_issuance=0)
    destination=root/('ipam-'+str(time.time_ns())+'.json')
    fd=os.open(destination,os.O_WRONLY|os.O_CREAT|os.O_EXCL|os.O_NOFOLLOW,0o600)
    with os.fdopen(fd,'w') as file:json.dump(result,file,sort_keys=True,indent=2);file.flush();os.fsync(file.fileno())
    # Never output addresses, identifiers, key paths, stderr, or credential bytes.
    print(json.dumps({'read_only':True,'network_count':result['network_count'],'inspect_sha256':result['inspect_sha256'],'any_overlap':any(result['overlap'].values()),'operator_sha256':result['operator_sha256']}))

if __name__=='__main__':
    try:main()
    except Exception as error:
        reason=str(error) if isinstance(error,Denied) else 'readonly_inventory_denied'
        print(json.dumps({'read_only':True,'completed':False,'reason':reason}))
        raise SystemExit(1)
```

## Execution guard and current evidence

The prior Muse verdict approves documentation only and explicitly leaves operational findings gating inventory. This revision resolves them; fresh independent exact-head approval is required for this guarded inventory before execution. The coordinator is the root decision owner (root does not mean Unix UID0). No production mutation action is requested or authorized. The repository deploy action will separately gate Coolify installation; the generic production action is forbidden and will not be used to bypass that managed release route.

The fresh local peer read resolves hetz toPRIVATE_HOST_SHA256_69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae, the exact verified encrypted tailnet peer. The retained ED25519 host-key fingerprint is SHA256:FeonQSuZip/nt3Zd7qXd0QqDqK+Q7B9tq1lubIiCEfg. The guard pins the whole existing known-host file and refuses a DNS/known-host/operator mismatch before opening SSH; no host key is replaced. It compiles the exact hash-checked retained operator bytes, avoiding Markdown transcription, and consumes one exclusive attempt marker before the first remote action. Failure spends the attempt; re-execution needs a new reviewed plan. Reviewers execute no credentialed calls.

The coordinator retains the receipt privately, checks all eight overlap booleans, records its hash/NY activity time on #27/#58, and refuses network creation if any overlap or ambiguity exists. No arbitrary receipt is accepted; exact operator/current inventory provenance is required. Source claims refer to PR96 and completed runs38328410148/38328410081/38328410102/38328410073, merge d97b0023c75c2f83c3c6404dbbdaecf2098e26a0 and completed main runs38329175387/38329175369/38329175392/38329175860. Main artifact sha256:73a2ca47c6525dc35ed41cc6592660d5ba59136d878efce436fe9a66bfd29813 was downloaded and locally pulled; image revision label matches exact merged source. Managed-server pull remains unproved. No tests or source claims imply private/company acceptance.

Fresh reviewer request: APPROVE, REJECT or BLOCKED this exact guard plus retained operator for the single read-only inventory, with any operational blockers stated explicitly. Approval of documentation alone is insufficient.

```python
import hashlib,os,stat,socket
from pathlib import Path
root=Path(__file__).resolve().parent
operator=root/'hetz_password_readonly.py'
expected='36a1a171c80635f5343731d705ba292ccb0c21fe457d6fe447998ad944c62050'
def protected(path,mode):
 s=path.lstat()
 if path.is_symlink() or s.st_uid!=os.getuid() or stat.S_IMODE(s.st_mode)!=mode:raise PermissionError('protected exact input required')
protected(root,0o700);protected(operator,0o600)
raw=operator.read_bytes()
if hashlib.sha256(raw).hexdigest()!=expected:raise PermissionError('operator drift')
known=root/'known-hosts.snapshot'
protected(known,0o600)
if known.is_symlink() or hashlib.sha256(known.read_bytes()).hexdigest()!='9657aee7f8edd5aeebc454953ab4562edfb3101838a4aa2807014166eeb3870a':raise PermissionError('known-host drift')
if set(x[4][0] for x in socket.getaddrinfo('hetz',22))!={'PRIVATE_HOST_SHA256_69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae'}:raise PermissionError('peer DNS drift')
fd=os.open(root/'attempt.claim',os.O_CREAT|os.O_EXCL|os.O_WRONLY|os.O_NOFOLLOW,0o600)
os.write(fd,expected.encode());os.fsync(fd);os.close(fd)
exec(compile(raw,str(operator),'exec'),{'__name__':'__main__','__file__':str(operator)})
```

The known-host snapshot is copied locally from the current protected existing known-host file, verified against its pinned SHA before execution, and never replaced or edited by this plan. Owner/mode checks now cover it. It sits inside the owned0700 session directory and is passed to SSH as its sole host-key file. This closes the unrelated-known-host update race; competing hostile processes with the same OS uid are outside this local boundary.

Coordinator fresh observations, October12,2026,9:00PM EDT: local DNS returned exactlyPRIVATE_HOST_SHA256_69e08d69438f83a96aefc4a9f82450e9244100f6db11b1e2cae8f3b956f054ae; the encrypted tailnet census identifies that peer as hetz; existing Coolify GET/version4.4.6 and GET/server inventory authenticate that target and serverUUID onwp0kd7w1w74w9yeotnoihp. The existing SSH ED25519 fingerprint was independently read using ssh-keygen from retained known-hosts and equals the recorded value. Snapshot/operator hashes were computed from exact bytes before review. These are coordinator-verified observations, not reviewer-run credentials. The reviewer should assess whether these exact current observations suffice for this read-only action and issue the action verdict explicitly; unverifiable live behavior must remain unknown. No hosted mutation is implied.
