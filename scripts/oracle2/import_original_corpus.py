#!/usr/bin/env python3
"""Import only qualified original readings into a NEW isolated loopback workspace.

This operator path does not appoint reviewers, confirm process drafts, query a
model, or enable questions. Those remain separate reviewed readiness controls.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import sys
from urllib.parse import urlsplit
from uuid import UUID, uuid4
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'services/oracle-brain'))
from oracle_brain.ingest.originals import ReadingProvenance, ReadingResponse, ReviewResponse


def qualified_sources(manifest, readings, inventory):
    summary = json.loads((readings / 'summary.json').read_text())
    if not summary.get('complete') or summary.get('failures'):
        raise ValueError('whole original inventory has not passed reading review')
    names = {str(UUID(r['source_id'])): r['filename'] for r in inventory}
    ids = [str(UUID(r['source_id'])) for r in manifest]
    if not ids or len(ids) != len(set(ids)) or set(names) != set(ids):
        raise ValueError('original upload inventory incomplete or duplicated')
    if summary['original_uploads'] != len(ids):
        raise ValueError('reading upload inventory does not match manifest')
    output = []
    for row in manifest:
        digest = row['sha256']
        path = readings / (digest + '.json')
        if path.is_symlink() or path.resolve().parent != readings.resolve():
            raise PermissionError('reading escapes private output directory')
        value = json.loads(path.read_text())
        meta = ReadingProvenance.model_validate(value['provenance'])
        reading = ReadingResponse.model_validate(value['reading'])
        review = ReviewResponse.model_validate(value['review'])
        if (meta.original_hash != digest or meta.content_type != row['file_type'] or
            meta.content_hash != hashlib.sha256(value['text'].encode()).hexdigest() or
            not reading.complete or [p.page_number for p in reading.pages] != list(range(1,meta.page_count+1)) or
            any(not p.text.strip() or p.uncertainties for p in reading.pages) or
            not review.complete_supported or review.unsupported or
            review.omissions or review.uncertainties or
            review.checked_pages != list(range(1, meta.page_count + 1)) or
            meta.review_receipt != hashlib.sha256(review.model_dump_json().encode()).hexdigest()
            and meta.evidence_kind != 'native_text'):
            raise ValueError('original reading proof does not match manifest')
        if meta.evidence_kind == 'native_text' and (
            meta.original_hash != meta.content_hash or value['text'] != reading.pages[0].text or
            meta.review_receipt != hashlib.sha256((meta.original_hash + ':strict-utf8-byte-roundtrip').encode()).hexdigest()):
            raise ValueError('native reading is not a lossless original-byte decoding')
        source_id = str(UUID(row['source_id']))
        if source_id not in summary['aliases'].get(digest, []):
            raise ValueError('upload alias missing from reviewed inventory')
        output.append((UUID(source_id), names[source_id], row['file_type'], value['text'], meta))
    return output


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--manifest', required=True, type=Path)
    parser.add_argument('--readings', required=True, type=Path)
    parser.add_argument('--inventory', required=True, type=Path)
    parser.add_argument('--workspace-id', required=True, type=UUID)
    parser.add_argument('--actor-id', required=True, type=UUID)
    args = parser.parse_args()
    database = os.environ['ORACLE2_ORIGINAL_IMPORT_DATABASE_URL']
    parsed = urlsplit(database)
    if (parsed.hostname not in {'127.0.0.1', 'localhost', '::1'} or parsed.path != '/oracle2' or
        parsed.username != 'oracle2_admin' or parsed.password != 'oracle2_local_admin_only'):
        raise PermissionError('original import requires the isolated loopback Oracle2 database')
    sources = qualified_sources(json.loads(args.manifest.read_text()), args.readings,
                                json.loads(args.inventory.read_text()))
    import psycopg
    with psycopg.connect(database) as connection:
        with connection.transaction():
            connection.execute('SELECT pg_advisory_xact_lock(hashtextextended(%s,0))', (str(args.workspace_id),))
            if connection.execute('SELECT count(*) FROM oracle2.sources WHERE workspace_id=%s',
                                  (args.workspace_id,)).fetchone()[0]:
                raise PermissionError('original import requires a new empty workspace')
            for sid, filename, content_type, text, metadata in sources:
                connection.execute('INSERT INTO oracle2.sources(source_id,workspace_id,uploaded_by,filename,content_type,status) VALUES (%s,%s,%s,%s,%s,%s)',
                    (sid,args.workspace_id,args.actor_id,filename,content_type,'draft'))
                for index, kind, body in [(0,'paragraph',text), (2147483647,'original',text), (2147483646,'original-metadata',metadata.model_dump_json())]:
                    connection.execute('INSERT INTO oracle2.source_blocks(block_id,source_id,workspace_id,block_index,kind,text,span_start,span_end) VALUES (%s,%s,%s,%s,%s,%s,0,%s)',
                        (uuid4(),sid,args.workspace_id,index,kind,body,len(body)))
                connection.execute('INSERT INTO oracle2.drafts(draft_id,source_id,workspace_id,created_by,process_name,status) VALUES (%s,%s,%s,%s,%s,%s)',
                    (uuid4(),sid,args.workspace_id,args.actor_id,filename,'draft'))
    print(json.dumps({'imported_original_uploads':len(sources),'distinct_originals':len({s[4].original_hash for s in sources}),'questions_enabled':False}))

if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'success':False,'error_class':type(error).__name__}))
        raise SystemExit(1)
