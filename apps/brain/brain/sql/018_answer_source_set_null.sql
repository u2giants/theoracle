-- Repair plan A7: deleting a source that is an interview answer must not
-- raise; the question keeps its answer text and loses only the link.
-- Idempotent.
ALTER TABLE cmap.open_question
  DROP CONSTRAINT IF EXISTS open_question_answer_source_id_fkey;
ALTER TABLE cmap.open_question
  ADD CONSTRAINT open_question_answer_source_id_fkey
  FOREIGN KEY (answer_source_id) REFERENCES cmap.source(id) ON DELETE SET NULL;
