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
