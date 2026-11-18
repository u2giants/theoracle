-- Issue #604, plan Step 10: questions left 'asked' by the old one-shot bot
-- have no stored Teams message id, so no reply can be matched to them.
-- Return them to 'open'; the next tick opens a clean conversation.
-- Idempotent: questions held by a live conversation are never touched.
UPDATE cmap.open_question q
   SET state = 'open', asked_at = NULL, target_employee_id = NULL
 WHERE q.state = 'asked'
   AND NOT EXISTS (
     SELECT 1
       FROM cmap.interview_turn t
       JOIN cmap.interview_conversation c ON c.id = t.conversation_id
      WHERE t.question_id = q.id AND c.state <> 'closed'
   );
