"""Original monotonic fence cannot renew with UTC rollback or nested calls."""
import time,threading
import pytest
from oracle_brain.hosting import _protected_control_listener_v1 as m

def test_no_context_is_denied_and_old_owner_optional_seam_stays_unchanged():
 assert m.request_remaining_v1(required=False) is None
 with pytest.raises(PermissionError,match='fence required'):m.request_remaining_v1()

def test_nested_context_never_extends_and_resets_on_error(monkeypatch):
 tick=[10.];monkeypatch.setattr(m.time,'monotonic',lambda:tick[0])
 with m._request_fence_v1(12.):
  with m._request_fence_v1(100.):
   assert m.request_remaining_v1()==2
   tick[0]=12.
   with pytest.raises(PermissionError,match='elapsed'):m.request_remaining_v1()
  with pytest.raises(PermissionError):m.request_remaining_v1()
 assert m.request_remaining_v1(required=False) is None

def test_new_threads_do_not_borrow_request_fence():
 results=[]
 with m._request_fence_v1(float(time.monotonic()+1)):
  def worker():
   try:m.request_remaining_v1()
   except PermissionError:results.append('denied')
  t=threading.Thread(target=worker);t.start();t.join()
 assert results==['denied']

@pytest.mark.parametrize('value',[None,True,30,float('nan'),float('inf')])
def test_no_coerced_or_nonfinite_fence(value):
 with pytest.raises(PermissionError):
  with m._request_fence_v1(value):pass


def test_hosting_forwarders_share_the_single_core_fence_without_importing_transport():
 from oracle_brain.operating_model import request_deadline_v1 as core
 assert m.request_remaining_v1 is core.request_remaining_v1
 assert m._request_fence_v1 is core._request_fence_v1
 with m._request_fence_v1(float(time.monotonic()+1)):
  assert core.request_remaining_v1()>0


@pytest.mark.parametrize('operation',['catalog','setter','commit'])
def test_later_SQL_send_refuses_when_prearmed_timeout_no_longer_fits(monkeypatch,operation):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 tick=[10.];monkeypatch.setattr(core.time,'monotonic',lambda:tick[0])
 class Connection:
  def __init__(self):self.sent=[]
  def execute(self,*args):self.sent.append(args);return self
 c=Connection();deadline=datetime.now(timezone.utc)+timedelta(seconds=30)
 with core._request_fence_v1(15.),core._sql_window_v1(c,deadline,armed_timeout_ms=2000):
  core.sql_execute_v1(c,deadline,'SELECT current_user')
  tick[0]=13.1
  with pytest.raises(PermissionError,match='already armed'):
   if operation=='setter':core.sql_rearm_v1(c,deadline,timeout_ms=100)
   elif operation=='commit':core._sql_send_window_v1(c,deadline)
   else:core.sql_execute_v1(c,deadline,'SELECT catalog')
 assert len(c.sent)==1


def test_SQL_setter_remains_under_old_bound_until_actual_success(monkeypatch):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 tick=[10.];monkeypatch.setattr(core.time,'monotonic',lambda:tick[0])
 class Connection:
  def __init__(self):self.sent=[];self.fail=False
  def execute(self,*args):
   self.sent.append(args)
   if self.fail:raise OSError('observed setter outcome unknown')
   return self
 c=Connection();deadline=datetime.now(timezone.utc)+timedelta(seconds=30)
 with core._request_fence_v1(15.),core._sql_window_v1(c,deadline,armed_timeout_ms=2000):
  c.fail=True
  with pytest.raises(OSError):core.sql_rearm_v1(c,deadline,timeout_ms=100)
  tick[0]=13.2
  with pytest.raises(PermissionError,match='already armed'):core.sql_execute_v1(c,deadline,'SELECT later')
 assert len(c.sent)==1


def test_successful_SQL_rearm_records_actual_new_bound_without_renewing_original(monkeypatch):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 tick=[10.];monkeypatch.setattr(core.time,'monotonic',lambda:tick[0])
 class Connection:
  def __init__(self):self.sent=[]
  def execute(self,*args):self.sent.append(args);return self
 c=Connection();deadline=datetime.now(timezone.utc)+timedelta(seconds=30)
 with core._request_fence_v1(15.),core._sql_window_v1(c,deadline,armed_timeout_ms=2000):
  core.sql_rearm_v1(c,deadline,timeout_ms=100)
  tick[0]=14.8
  core.sql_execute_v1(c,deadline,'SELECT permitted')
  tick[0]=14.95
  with pytest.raises(PermissionError):core.sql_execute_v1(c,deadline,'SELECT too_late')
 assert len(c.sent)==2
 with pytest.raises(PermissionError,match='captured|prearmed'):core.sql_execute_v1(c,deadline,'SELECT outside_owner')


def test_SQL_UTC_rollback_cannot_extend_captured_monotonic_window(monkeypatch):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 tick=[10.];monkeypatch.setattr(core.time,'monotonic',lambda:tick[0])
 wall=[datetime.now(timezone.utc)]
 class Clock(datetime):
  @classmethod
  def now(cls,tz=None):return wall[0]
 monkeypatch.setattr(core,'datetime',Clock)
 class Connection:
  def execute(self,*args):pytest.fail('rollback allowed late SQL effect')
 c=Connection();deadline=Clock.fromisoformat((wall[0]+timedelta(seconds=30)).isoformat())
 with core._request_fence_v1(12.),core._sql_window_v1(c,deadline,armed_timeout_ms=1000):
  tick[0]=11.1
  wall[0]-=timedelta(days=1)
  # Actual UTC rollback and a later supplied deadline cannot override the
  # listener's same captured monotonic fence or allow another send.
  with pytest.raises(PermissionError):core.sql_execute_v1(c,deadline+timedelta(days=1),'SELECT late')
  with pytest.raises(PermissionError):core.sql_execute_v1(c,deadline,'SELECT late')


def test_catalog_legacy_API_preserved_only_without_actual_captured_SQL_window():
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 class Connection:
  def __init__(self):self.sent=[]
  def execute(self,*args):self.sent.append(args);return self
 c=Connection();foreign=Connection();deadline=datetime.now(timezone.utc)+timedelta(seconds=10)
 assert core.sql_execute_current_v1(c,'SELECT legacy') is c
 with core._sql_window_v1(c,deadline,armed_timeout_ms=100):
  core.sql_execute_current_v1(c,'SELECT guarded')
  with pytest.raises(PermissionError,match='differs'):core.sql_execute_current_v1(foreign,'SELECT never')
  with pytest.raises(PermissionError,match='prearmed'):core.sql_execute_v1(foreign,deadline,'SELECT never')
 assert len(c.sent)==2 and foreign.sent==[]
 assert core.sql_execute_current_v1(foreign,'SELECT restored_legacy') is foreign


@pytest.mark.parametrize('timeout',[True,0,-1,30001,1.5,float('nan'),float('inf')])
def test_SQL_timeout_metadata_is_strict_and_cannot_send_before_validation(timeout):
 from datetime import datetime,timedelta,timezone
 from oracle_brain.operating_model import request_deadline_v1 as core
 class Connection:
  def execute(self,*args):pytest.fail('invalid timeout sent SQL')
 c=Connection();deadline=datetime.now(timezone.utc)+timedelta(seconds=10)
 with pytest.raises(PermissionError):
  with core._sql_window_v1(c,deadline,armed_timeout_ms=timeout):pass
 with core._sql_window_v1(c,deadline,armed_timeout_ms=100):
  with pytest.raises(PermissionError):core.sql_rearm_v1(c,deadline,timeout_ms=timeout)
