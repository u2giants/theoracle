"""Owned invented separate observer process; uses the actual protected owner."""
import json,os,signal,threading
from pathlib import Path
from oracle_brain.hosting.original_intake_v1 import load_original_intake_settings_v1,_pinned
from oracle_brain.hosting.meeting_capture_v1 import load_meeting_capture_settings_v1
from oracle_brain.hosting.meeting_supervisor_observer_v1 import load_meeting_supervisor_observer_settings_v2,protected_meeting_supervisor_server_v2
from uuid import UUID
p=json.loads(_pinned(os.environ['ORACLE2_INVENTED_OBSERVER_CONFIG_FILE'],os.environ['ORACLE2_INVENTED_OBSERVER_CONFIG_SHA256']))
assert set(p)=={'host','appointment','issuer','reviewer','capture','observer','peer','port_file'}
h=load_original_intake_settings_v1(p['host']['path'],p['host']['sha256'],p['appointment']['path'],p['appointment']['sha256'],UUID(p['issuer']),UUID(p['reviewer']))
c=load_meeting_capture_settings_v1(h,p['capture']['path'],p['capture']['sha256'])
s=load_meeting_supervisor_observer_settings_v2(c,p['observer']['path'],p['observer']['sha256'])
server=protected_meeting_supervisor_server_v2(s,p['peer']['path'],p['peer']['sha256']);stop=threading.Event()
for sig in (signal.SIGTERM,signal.SIGINT):signal.signal(sig,lambda *_:stop.set())
t=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.01});t.start()
port=Path(p['port_file']);port.write_text(str(server.server_port));port.chmod(0o600)
try:stop.wait()
finally:server.shutdown();server.server_close();t.join(3);assert not t.is_alive() and not server._active
