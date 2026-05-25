CREATE TABLE "extraction_batches" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"job_run_id" uuid,
	"model_run_id" uuid,
	"context_pack_id" uuid,
	"batch_type" varchar(50) NOT NULL,
	"status" varchar(50) DEFAULT 'pending_model' NOT NULL,
	"source_message_ids" jsonb,
	"source_document_chunk_ids" jsonb,
	"source_hash" varchar(64) NOT NULL,
	"raw_model_output" jsonb,
	"validation_summary" jsonb,
	"validation_attempt_count" integer DEFAULT 0 NOT NULL,
	"consecutive_quote_failure_count" integer DEFAULT 0 NOT NULL,
	"model_run_ids_attempted" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"route_ids_attempted" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"error" text,
	"started_at" timestamp DEFAULT now() NOT NULL,
	"finished_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "extraction_candidate_evidence" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"candidate_id" uuid NOT NULL,
	"source_type" "evidence_source_type" NOT NULL,
	"source_message_id" uuid,
	"source_document_chunk_id" uuid,
	"source_external_record_id" varchar(255),
	"asserted_by_employee_id" uuid,
	"uploaded_by_employee_id" uuid,
	"created_by_employee_id" uuid,
	"exact_quote_provided" text NOT NULL,
	"normalized_quote" text,
	"char_start_provided" integer,
	"char_end_provided" integer,
	"validated_exact_quote" text,
	"validated_char_start" integer,
	"validated_char_end" integer,
	"page_number" integer,
	"validation_status" varchar(50) DEFAULT 'pending' NOT NULL,
	"validation_method" varchar(100),
	"validation_error" text,
	"confidence" integer,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"validated_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "extraction_candidates" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"extraction_batch_id" uuid NOT NULL,
	"status" varchar(50) DEFAULT 'pending_validation' NOT NULL,
	"claim_type" varchar(100) NOT NULL,
	"summary" text NOT NULL,
	"impact_score" integer NOT NULL,
	"confidence_score" integer,
	"domains" jsonb NOT NULL,
	"proposed_entities" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"proposed_metadata" jsonb,
	"stance" varchar(50),
	"contains_sensitive_personal_data" boolean DEFAULT false NOT NULL,
	"contains_sensitive_hr_data" boolean DEFAULT false NOT NULL,
	"is_personal_conflict" boolean DEFAULT false NOT NULL,
	"sensitivity_reason" text,
	"risk_flags" jsonb,
	"requires_review" boolean DEFAULT true NOT NULL,
	"review_reason" text,
	"duplicate_of_candidate_id" uuid,
	"duplicate_of_claim_id" uuid,
	"promoted_to_claim_id" uuid,
	"raw_candidate_json" jsonb NOT NULL,
	"validation_error" text,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"validated_at" timestamp,
	"promoted_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "extraction_validation_results" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"candidate_id" uuid,
	"candidate_evidence_id" uuid,
	"check_name" varchar(100) NOT NULL,
	"status" varchar(50) NOT NULL,
	"detail" text,
	"metadata_json" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "extraction_batches" ADD CONSTRAINT "extraction_batches_job_run_id_job_runs_id_fk" FOREIGN KEY ("job_run_id") REFERENCES "public"."job_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_batches" ADD CONSTRAINT "extraction_batches_model_run_id_model_runs_id_fk" FOREIGN KEY ("model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_batches" ADD CONSTRAINT "extraction_batches_context_pack_id_oracle_context_packs_id_fk" FOREIGN KEY ("context_pack_id") REFERENCES "public"."oracle_context_packs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_candidate_id_extraction_candidates_id_fk" FOREIGN KEY ("candidate_id") REFERENCES "public"."extraction_candidates"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_source_message_id_messages_id_fk" FOREIGN KEY ("source_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_source_document_chunk_id_document_chunks_id_fk" FOREIGN KEY ("source_document_chunk_id") REFERENCES "public"."document_chunks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_asserted_by_employee_id_employees_id_fk" FOREIGN KEY ("asserted_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_uploaded_by_employee_id_employees_id_fk" FOREIGN KEY ("uploaded_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidate_evidence" ADD CONSTRAINT "extraction_candidate_evidence_created_by_employee_id_employees_id_fk" FOREIGN KEY ("created_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidates" ADD CONSTRAINT "extraction_candidates_extraction_batch_id_extraction_batches_id_fk" FOREIGN KEY ("extraction_batch_id") REFERENCES "public"."extraction_batches"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidates" ADD CONSTRAINT "extraction_candidates_duplicate_of_claim_id_claims_id_fk" FOREIGN KEY ("duplicate_of_claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_candidates" ADD CONSTRAINT "extraction_candidates_promoted_to_claim_id_claims_id_fk" FOREIGN KEY ("promoted_to_claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_validation_results" ADD CONSTRAINT "extraction_validation_results_candidate_id_extraction_candidates_id_fk" FOREIGN KEY ("candidate_id") REFERENCES "public"."extraction_candidates"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "extraction_validation_results" ADD CONSTRAINT "extraction_validation_results_candidate_evidence_id_extraction_candidate_evidence_id_fk" FOREIGN KEY ("candidate_evidence_id") REFERENCES "public"."extraction_candidate_evidence"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "extraction_batches_status_idx" ON "extraction_batches" USING btree ("status");--> statement-breakpoint
CREATE INDEX "extraction_batches_status_created_idx" ON "extraction_batches" USING btree ("status","created_at");--> statement-breakpoint
CREATE INDEX "extraction_batches_source_hash_idx" ON "extraction_batches" USING btree ("source_hash");--> statement-breakpoint
CREATE INDEX "extraction_batches_batch_type_idx" ON "extraction_batches" USING btree ("batch_type");--> statement-breakpoint
CREATE INDEX "extraction_batches_model_run_idx" ON "extraction_batches" USING btree ("model_run_id");--> statement-breakpoint
CREATE INDEX "extraction_batches_context_pack_idx" ON "extraction_batches" USING btree ("context_pack_id");--> statement-breakpoint
CREATE INDEX "extraction_candidate_evidence_candidate_idx" ON "extraction_candidate_evidence" USING btree ("candidate_id");--> statement-breakpoint
CREATE INDEX "extraction_candidate_evidence_source_message_idx" ON "extraction_candidate_evidence" USING btree ("source_message_id");--> statement-breakpoint
CREATE INDEX "extraction_candidate_evidence_source_chunk_idx" ON "extraction_candidate_evidence" USING btree ("source_document_chunk_id");--> statement-breakpoint
CREATE INDEX "extraction_candidate_evidence_validation_status_idx" ON "extraction_candidate_evidence" USING btree ("validation_status");--> statement-breakpoint
CREATE INDEX "extraction_candidates_status_idx" ON "extraction_candidates" USING btree ("status");--> statement-breakpoint
CREATE INDEX "extraction_candidates_batch_idx" ON "extraction_candidates" USING btree ("extraction_batch_id");--> statement-breakpoint
CREATE INDEX "extraction_candidates_promoted_claim_idx" ON "extraction_candidates" USING btree ("promoted_to_claim_id");--> statement-breakpoint
CREATE INDEX "extraction_candidates_duplicate_claim_idx" ON "extraction_candidates" USING btree ("duplicate_of_claim_id");--> statement-breakpoint
CREATE INDEX "extraction_candidates_sensitivity_idx" ON "extraction_candidates" USING btree ("contains_sensitive_hr_data","is_personal_conflict");--> statement-breakpoint
CREATE INDEX "extraction_candidates_created_at_idx" ON "extraction_candidates" USING btree ("created_at");--> statement-breakpoint
CREATE INDEX "extraction_validation_results_candidate_idx" ON "extraction_validation_results" USING btree ("candidate_id");--> statement-breakpoint
CREATE INDEX "extraction_validation_results_candidate_evidence_idx" ON "extraction_validation_results" USING btree ("candidate_evidence_id");--> statement-breakpoint
CREATE INDEX "extraction_validation_results_check_name_status_idx" ON "extraction_validation_results" USING btree ("check_name","status");--> statement-breakpoint
CREATE INDEX "extraction_validation_results_created_at_idx" ON "extraction_validation_results" USING btree ("created_at");