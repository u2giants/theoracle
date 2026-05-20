-- Spec 7.2 — Row Level Security policies.
--
-- Conventions:
-- * service_role bypasses RLS automatically in Supabase, but we add explicit
--   USING (true) policies for clarity where needed.
-- * `authenticated` is the role Supabase clients run as after sign-in.
-- * Chat/document/intelligence tables are gated through current_employee_id().
-- * Intelligence tables (claims/gaps/etc) are admin-only via
--   current_employee_is_admin(); employees only see them via privileged
--   server routes that use the service role.

-- ===========================================================================
-- Employees
-- ===========================================================================
ALTER TABLE employees ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS employees_self_select   ON employees;
DROP POLICY IF EXISTS employees_admin_all     ON employees;

CREATE POLICY employees_self_select ON employees
  FOR SELECT
  TO authenticated
  USING (auth_user_id = auth.uid() OR public.current_employee_is_admin());

CREATE POLICY employees_admin_all ON employees
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Employee invites — admin only
-- ===========================================================================
ALTER TABLE employee_invites ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS employee_invites_admin_all ON employee_invites;

CREATE POLICY employee_invites_admin_all ON employee_invites
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Channels
-- ===========================================================================
ALTER TABLE channels ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS channels_participant_select ON channels;
DROP POLICY IF EXISTS channels_admin_all          ON channels;

CREATE POLICY channels_participant_select ON channels
  FOR SELECT
  TO authenticated
  USING (
    public.current_employee_is_admin()
    OR EXISTS (
      SELECT 1 FROM channel_participants cp
      WHERE cp.channel_id = channels.id
        AND cp.employee_id = public.current_employee_id()
    )
  );

CREATE POLICY channels_admin_all ON channels
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Channel participants
-- ===========================================================================
ALTER TABLE channel_participants ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS channel_participants_member_select ON channel_participants;
DROP POLICY IF EXISTS channel_participants_admin_all     ON channel_participants;

CREATE POLICY channel_participants_member_select ON channel_participants
  FOR SELECT
  TO authenticated
  USING (
    public.current_employee_is_admin()
    OR EXISTS (
      SELECT 1 FROM channel_participants me
      WHERE me.channel_id  = channel_participants.channel_id
        AND me.employee_id = public.current_employee_id()
    )
  );

CREATE POLICY channel_participants_admin_all ON channel_participants
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Messages
-- ===========================================================================
ALTER TABLE messages ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS messages_participant_select ON messages;
DROP POLICY IF EXISTS messages_self_insert        ON messages;
DROP POLICY IF EXISTS messages_self_update        ON messages;
DROP POLICY IF EXISTS messages_admin_all          ON messages;

CREATE POLICY messages_participant_select ON messages
  FOR SELECT
  TO authenticated
  USING (
    public.current_employee_is_admin()
    OR EXISTS (
      SELECT 1 FROM channel_participants cp
      WHERE cp.channel_id  = messages.channel_id
        AND cp.employee_id = public.current_employee_id()
    )
  );

-- Employee can only insert their own user-role messages into channels they belong to.
-- Assistant/system messages must come through service_role (Oracle route handlers).
CREATE POLICY messages_self_insert ON messages
  FOR INSERT
  TO authenticated
  WITH CHECK (
    role = 'user'
    AND employee_id = public.current_employee_id()
    AND EXISTS (
      SELECT 1 FROM channel_participants cp
      WHERE cp.channel_id  = messages.channel_id
        AND cp.employee_id = public.current_employee_id()
    )
  );

-- Employees may edit only their own messages (for edited_at flow); admins can do anything.
CREATE POLICY messages_self_update ON messages
  FOR UPDATE
  TO authenticated
  USING (employee_id = public.current_employee_id())
  WITH CHECK (employee_id = public.current_employee_id() AND role = 'user');

CREATE POLICY messages_admin_all ON messages
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Documents
-- ===========================================================================
ALTER TABLE documents ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS documents_uploader_select  ON documents;
DROP POLICY IF EXISTS documents_attached_select  ON documents;
DROP POLICY IF EXISTS documents_self_insert      ON documents;
DROP POLICY IF EXISTS documents_admin_all        ON documents;

CREATE POLICY documents_uploader_select ON documents
  FOR SELECT
  TO authenticated
  USING (uploader_id = public.current_employee_id());

CREATE POLICY documents_attached_select ON documents
  FOR SELECT
  TO authenticated
  USING (
    EXISTS (
      SELECT 1
      FROM message_attachments ma
      JOIN messages m              ON m.id = ma.message_id
      JOIN channel_participants cp ON cp.channel_id = m.channel_id
      WHERE ma.document_id = documents.id
        AND cp.employee_id = public.current_employee_id()
    )
  );

CREATE POLICY documents_self_insert ON documents
  FOR INSERT
  TO authenticated
  WITH CHECK (uploader_id = public.current_employee_id());

CREATE POLICY documents_admin_all ON documents
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Document chunks — derived from documents; same visibility
-- ===========================================================================
ALTER TABLE document_chunks ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS document_chunks_inherit_select ON document_chunks;
DROP POLICY IF EXISTS document_chunks_admin_all      ON document_chunks;

CREATE POLICY document_chunks_inherit_select ON document_chunks
  FOR SELECT
  TO authenticated
  USING (
    public.current_employee_is_admin()
    OR EXISTS (
      SELECT 1 FROM documents d
      WHERE d.id = document_chunks.document_id
        AND (
          d.uploader_id = public.current_employee_id()
          OR EXISTS (
            SELECT 1
            FROM message_attachments ma
            JOIN messages m              ON m.id = ma.message_id
            JOIN channel_participants cp ON cp.channel_id = m.channel_id
            WHERE ma.document_id = d.id
              AND cp.employee_id = public.current_employee_id()
          )
        )
    )
  );

CREATE POLICY document_chunks_admin_all ON document_chunks
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Message attachments — visible if the underlying message is visible
-- ===========================================================================
ALTER TABLE message_attachments ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS message_attachments_inherit_select ON message_attachments;
DROP POLICY IF EXISTS message_attachments_admin_all      ON message_attachments;

CREATE POLICY message_attachments_inherit_select ON message_attachments
  FOR SELECT
  TO authenticated
  USING (
    public.current_employee_is_admin()
    OR EXISTS (
      SELECT 1
      FROM messages m
      JOIN channel_participants cp ON cp.channel_id = m.channel_id
      WHERE m.id = message_attachments.message_id
        AND cp.employee_id = public.current_employee_id()
    )
  );

CREATE POLICY message_attachments_admin_all ON message_attachments
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());

-- ===========================================================================
-- Intelligence tables — admin-only (spec 7.2 "Intelligence Tables")
-- ===========================================================================
DO $$
DECLARE t text;
BEGIN
  FOR t IN SELECT unnest(ARRAY[
    'claims',
    'claim_domains',
    'claim_evidence',
    'brain_sections',
    'brain_section_versions',
    'section_claims',
    'gaps',
    'contradictions',
    'model_runs',
    'job_runs',
    'oracle_interventions'
  ])
  LOOP
    EXECUTE format('ALTER TABLE %I ENABLE ROW LEVEL SECURITY', t);
    EXECUTE format('DROP POLICY IF EXISTS %I_admin_all ON %I', t, t);
    EXECUTE format(
      'CREATE POLICY %I_admin_all ON %I FOR ALL TO authenticated ' ||
      'USING (public.current_employee_is_admin()) ' ||
      'WITH CHECK (public.current_employee_is_admin())',
      t, t
    );
  END LOOP;
END $$;

-- ===========================================================================
-- Settings — admins read/write, all authenticated employees may read so the
-- chat client can render the cool-down / model name. Sensitive settings should
-- not live here.
-- ===========================================================================
ALTER TABLE settings ENABLE ROW LEVEL SECURITY;

DROP POLICY IF EXISTS settings_authenticated_select ON settings;
DROP POLICY IF EXISTS settings_admin_all            ON settings;

CREATE POLICY settings_authenticated_select ON settings
  FOR SELECT
  TO authenticated
  USING (true);

CREATE POLICY settings_admin_all ON settings
  FOR ALL
  TO authenticated
  USING (public.current_employee_is_admin())
  WITH CHECK (public.current_employee_is_admin());
