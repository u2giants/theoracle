-- Bootstrap a pilot authority chain on an isolated oracle2 store.
-- Usage (psql): set the owner/actor UUIDs, run once after 001_foundation.sql.
-- The owner must be appointed with a signed message (see authz.appoint_owner);
-- this script only creates the non-root pilot delegation when a root exists.

-- Example (after appoint_owner for :owner_id):
--   SELECT gen_random_uuid() AS appointment_id \gset
--   INSERT INTO oracle2.appointments
--     (appointment_id,workspace_id,actor_id,scope,granted_by)
--   VALUES (:'appointment_id', :'workspace_id'::uuid, :'actor_id'::uuid, 'review', :'owner_id'::uuid);
--   -- repeat for 'confirm'

-- Guard: refuse if the grantor has no live root lineage (has_authority check
-- is enforced in application code before any draft mutation).
SELECT 'run appoint_owner + delegate via oracle_brain.authz / scripts/oracle2' AS note;
