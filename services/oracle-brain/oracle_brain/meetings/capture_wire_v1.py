"""Strict retained response observations; not TLS identity, authority or source proof.

The existing participation raw-frame owner validates exact complete HTTP bytes.
Only the fixed S07 provider operation owner supplies its own authenticated wire.
"""
import hashlib,json
from datetime import datetime,timezone
from uuid import UUID
from oracle_brain.hosting.gateway import unique_object
from oracle_brain.meetings.participation_wire_v1 import observed_participation_wire_v1

def observe_capture_wire_v1(raw,*,effect,expected_bot,error=None,now=None):
    facts=observed_participation_wire_v1(raw,error=error)
    result=dict(kind='UNKNOWN',bot_id=None,latest_status=None,complete=facts['complete'])
    if effect not in ('capture-create','capture-leave','capture-retrieve'):raise ValueError('fixed capture effect required')
    if not facts['complete']:return result
    try:
        split=raw.index(b'\r\n\r\n');body=raw[split+4:]
        headers={name.lower():value.strip().lower() for name,value in (line.split(b':',1) for line in raw[:split].split(b'\r\n')[1:])}
        if headers.get(b'connection')!=b'close':return result
        if effect=='capture-leave':
            if type(expected_bot) is UUID and facts['http_status']==200 and not body:result.update(kind='leave-observed',bot_id=str(expected_bot))
            return result
        if facts['http_status']!=(201 if effect=='capture-create' else 200) or headers.get(b'content-type') not in (b'application/json',b'application/json; charset=utf-8'):return result
        value=json.loads(body.decode('utf-8'),object_pairs_hook=unique_object,parse_constant=lambda _:(_ for _ in ()).throw(ValueError()))
        if type(value) is not dict or type(value.get('id')) is not str or str(UUID(value['id']))!=value['id']:return result
        if effect=='capture-create':
            if expected_bot is None:result.update(kind='create-observed',bot_id=value['id'])
            return result
        if type(expected_bot) is not UUID or value['id']!=str(expected_bot) or type(value.get('status_changes')) is not list or len(value['status_changes'])>2048:return result
        latest=None;at=None;now=now or datetime.now(timezone.utc)
        for item in value['status_changes']:
            if type(item) is not dict or type(item.get('code')) is not str or not 0<len(item['code'])<=128 or item['code']!=item['code'].strip() or any(ord(c)<32 or ord(c)==127 for c in item['code']):return result
            stamp=item.get('created_at')
            if type(stamp) is not str or len(stamp)>40:return result
            time=datetime.fromisoformat(stamp.replace('Z','+00:00'))
            if time.tzinfo is None or time>now:return result
            if at is None or time>at:latest=dict(code=item['code'],created_at=stamp);at=time
            elif time==at and latest!=dict(code=item['code'],created_at=stamp):return result
        result.update(kind='metadata-observed',bot_id=str(expected_bot),latest_status=latest,metadata_sha256=hashlib.sha256(body).hexdigest());return result
    except (ValueError,TypeError,KeyError,UnicodeError):return result
