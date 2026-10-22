"""Fixed-purpose uninstalled research process; protected inputs appoint nothing."""
from datetime import datetime,timezone
import os,re,signal,sys,threading
from pathlib import Path
from ..research.durable_authority_v1 import load_research_settings_v1
from ..operating_model.protected_inputs_v1 import _parse,_pinned
from .research_service_v1 import ResearchPeerV1,protected_research_server_v1


def _installed_pair(prefix):
    path=os.environ.get(prefix+'_FILE','');seal=os.environ.get(prefix+'_SHA256','')
    if (not Path(path).is_absolute() or str(Path(path))!=path
            or not re.fullmatch(r'[a-f0-9]{64}',seal)):
        raise PermissionError('independent protected research installation required')
    return path,seal


def main():
    if len(sys.argv)!=1 or threading.current_thread() is not threading.main_thread():
        raise PermissionError('fixed research entry requires main process and no selectors')
    config,seal=_installed_pair('ORACLE2_RESEARCH_CONFIG')
    peer_path,peer_seal=_installed_pair('ORACLE2_RESEARCH_PEER')
    settings=load_research_settings_v1(config,seal)
    profile=_parse(ResearchPeerV1,_pinned(peer_path,peer_seal))
    server=protected_research_server_v1(settings,peer_path,peer_seal)
    stopped=threading.Event();previous={};started=False
    def stop(signum,frame):stopped.set()
    thread=threading.Thread(target=server.serve_forever,kwargs={'poll_interval':.05},daemon=False)
    try:
        for signum in (signal.SIGTERM,signal.SIGINT):
            previous[signum]=signal.signal(signum,stop)
        thread.start();started=True
        horizon=min(settings.config.expires_at,settings.config.original_horizon,profile.expires_at,profile.original_horizon)
        while not stopped.wait(.1):
            if not thread.is_alive():raise PermissionError('research listener stopped unexpectedly')
            if datetime.now(timezone.utc)>=horizon:break
    finally:
        if thread.is_alive():server.shutdown()
        server.server_close()
        if started:thread.join(2)
        for signum,handler in previous.items():signal.signal(signum,handler)
        if thread.is_alive() or server._active:raise PermissionError('research listener cleanup incomplete')


if __name__=='__main__':
    try:main()
    except Exception:raise SystemExit('Research service unavailable') from None
