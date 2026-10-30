"""Step 12 end-to-end proof on a throwaway database (not CI).

Phase A (replayed): build the fixture map. Phase B (real HTTP): an employee
messages the bot, the hourly tick routes an open question over HTTP to a
local stand-in for /api/teams/bot/proactive, the employee answers through the
brain's /interview/teams/inbound, and the answer becomes a source. Phase C
(live ScaleDown + OpenRouter): the answer source is read, extracted, resolved,
projected and the community reports rebuilt; print whether a report now cites it.
"""
import json, os, sys, threading, time
from http.server import BaseHTTPRequestHandler, HTTPServer
sys.path.insert(0, os.path.join(os.getcwd(), "tests"))
import httpx, psycopg, pytest, uvicorn
from brain.config import get_settings
from brain import storage as storage_mod
from conftest import FakeStorage
from map_seed import E2E_EMPLOYEE_SQL, _reset, seed_map
from brain.migrate import migrate

TOKEN = "step12-proof-token"
os.environ["BRAIN_SHARED_TOKEN"] = TOKEN
os.environ["BRAIN_INTERVIEW_ENABLED"] = "true"
os.environ["BRAIN_WEB_BASE_URL"] = "http://127.0.0.1:8851"
get_settings.cache_clear()
migrate()
db = psycopg.connect(get_settings().database_url, autocommit=False)
db.execute(E2E_EMPLOYEE_SQL); db.commit(); _reset(db)
db.execute("TRUNCATE cmap.open_question, cmap.teams_conversation, cmap.employee_flags"); db.commit()
fake = FakeStorage()
storage_mod.get_storage = lambda settings=None: fake
live_env = {k: os.environ.get(k) for k in ("BRAIN_SCALEDOWN_ENABLED", "SCALEDOWN_API_KEY", "BRAIN_FRONTIER_MODEL")}
with pytest.MonkeyPatch.context() as mp:
    ids = seed_map(db, mp)
for k, v in live_env.items():
    if v is None: os.environ.pop(k, None)
    else: os.environ[k] = v
get_settings.cache_clear()
jess_id, jess_name = ids["jessica_id"], ids["jessica_name"]
print("A map built: jessica entity =", jess_name)

# The employee who will be asked: name matches the Person entity.
db.execute("INSERT INTO public.employees (id, email, name, role) VALUES "
           "('00000000-0000-4000-8000-00000000f001','jessica@test.invalid',%s,'Licensing') ON CONFLICT DO NOTHING", (jess_name,))
lic = db.execute("SELECT entity_ids FROM cmap.community WHERE id=%s", (ids["licensing_community_id"],)).fetchone()[0]
others = [str(e) for (e,) in db.execute("SELECT id FROM cmap.entity WHERE id = ANY(%s) AND entity_type <> 'Person'", (lic,)).fetchall()]
print("A licensing community non-person entities:", len(others))
db.execute("INSERT INTO cmap.open_question (question, why, entity_ids) VALUES (%s,'Licensing approval',%s)",
           ("When Jessica is out, who signs licensor approval forms, and how long does that add?", others))
db.commit()

sent = []
class Stub(BaseHTTPRequestHandler):
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["content-length"])))
        sent.append({"path": self.path, "token_ok": self.headers.get("x-brain-token") == TOKEN, **body})
        self.send_response(200); self.send_header("content-type", "application/json"); self.end_headers()
        self.wfile.write(b'{"sent":true}')
    def log_message(self, *a): pass
threading.Thread(target=HTTPServer(("127.0.0.1", 8851), Stub).serve_forever, daemon=True).start()
from brain.main import app
server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=8852, log_level="warning"))
threading.Thread(target=server.run, daemon=True).start()
while not server.started: time.sleep(0.1)
B = "http://127.0.0.1:8852"; H = {"x-brain-token": TOKEN}
ref = {"conversation": {"id": "a:proof"}, "serviceUrl": "https://smba.example.invalid/", "user": {"id": "29:proof"}}

from brain.interview.tick import maybe_queue_interview_tick, run_interview_tick
print("B before first message, tick =", run_interview_tick(), "sent =", len(sent))
r = httpx.post(f"{B}/interview/teams/inbound", headers=H, json={"email": "jessica@test.invalid", "conversation_ref": ref, "text": "hi"}).json()
print("B first message ->", r)
print("B hourly tick queued =", maybe_queue_interview_tick())
print("B tick =", run_interview_tick())
print("B proactive call ->", json.dumps(sent[-1]))
ANSWER = "Marco in Legal signs them when Jessica is out, but he only checks his queue on Fridays, so it adds about a week."
r = httpx.post(f"{B}/interview/teams/inbound", headers=H, json={"email": "jessica@test.invalid", "conversation_ref": ref, "text": ANSWER}).json()
print("B answer ->", r)
src = r["source_id"]
print("B source:", db.execute("SELECT kind, title FROM cmap.source WHERE id=%s", (src,)).fetchone())
print("B question:", db.execute("SELECT state, answer_source_id::text = %s FROM cmap.open_question", (src,)).fetchone())
db.commit()

if "--live" not in sys.argv:
    sys.exit(0)
from brain.read.pipeline import handle_read_source
from brain.extract.flat import handle_classify_extract
from brain.extract.relations import handle_relations
from brain.resolve.resolve import run_resolve
from brain.graph.project import run_project
from brain.graph.communities import run_communities
before = db.execute("SELECT count(*) FROM cmap.community c, jsonb_array_elements(COALESCE(c.findings,'[]')) f WHERE f->'source_ids' ? %s", (src,)).fetchone()[0]
db.commit()
handle_read_source({"id": None, "payload": {"source_id": src}})
print("C chunks:", db.execute("SELECT count(*) FROM cmap.chunk WHERE source_id=%s", (src,)).fetchone()[0]); db.commit()
handle_classify_extract({"payload": {"source_id": src}})
handle_relations({"payload": {"source_id": src}})
print("C mentions:", db.execute("SELECT string_agg(surface_name, ', ') FROM cmap.mention m JOIN cmap.chunk c ON c.id=m.chunk_id WHERE c.source_id=%s", (src,)).fetchone()[0]); db.commit()
print("C resolve:", run_resolve())
print("C project:", run_project())
print("C communities:", run_communities())
rows = db.execute("SELECT c.level, c.title, f->>'text' FROM cmap.community c, jsonb_array_elements(COALESCE(c.findings,'[]')) f WHERE f->'source_ids' ? %s", (src,)).fetchall()
print("C findings citing the interview answer: before =", before, "after =", len(rows))
for row in rows: print("   ", row)
