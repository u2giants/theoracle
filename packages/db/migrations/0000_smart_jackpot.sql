CREATE TYPE "public"."auth_provider" AS ENUM('microsoft', 'google', 'authentik', 'magic_link_dev');--> statement-breakpoint
CREATE TYPE "public"."brain_section_review_status" AS ENUM('draft', 'approved', 'needs_review', 'rejected');--> statement-breakpoint
CREATE TYPE "public"."channel_status" AS ENUM('active', 'archived', 'locked');--> statement-breakpoint
CREATE TYPE "public"."claim_status" AS ENUM('pending_review', 'approved', 'rejected', 'superseded');--> statement-breakpoint
CREATE TYPE "public"."contradiction_status" AS ENUM('possible', 'open', 'resolved', 'dismissed');--> statement-breakpoint
CREATE TYPE "public"."document_status" AS ENUM('pending_processing', 'processing', 'complete', 'failed');--> statement-breakpoint
CREATE TYPE "public"."evidence_source_type" AS ENUM('message', 'document_chunk', 'external_system', 'manual_admin');--> statement-breakpoint
CREATE TYPE "public"."extraction_status" AS ENUM('pending', 'processing', 'complete', 'failed', 'skipped');--> statement-breakpoint
CREATE TYPE "public"."gap_priority" AS ENUM('low', 'medium', 'high', 'urgent');--> statement-breakpoint
CREATE TYPE "public"."gap_status" AS ENUM('open', 'queued', 'asked', 'resolved', 'stale', 'rejected');--> statement-breakpoint
CREATE TYPE "public"."intervention_decision" AS ENUM('no_intervention', 'queued_gap', 'live_interjection', 'admin_review');--> statement-breakpoint
CREATE TYPE "public"."knowledge_domain" AS ENUM('design', 'licensing', 'production', 'sourcing', 'logistics', 'sales', 'coldlion', 'customers', 'retail_compliance', 'sampling', 'costing', 'artwork_files', 'factory_communication', 'quality_control', 'approvals', 'shipping_documents', 'general');--> statement-breakpoint
CREATE TYPE "public"."message_role" AS ENUM('user', 'assistant', 'system');--> statement-breakpoint
CREATE TYPE "public"."oracle_intervention_trigger_type" AS ENUM('direct_mention', 'possible_contradiction', 'lull_gap', 'manual_admin', 'system_test');--> statement-breakpoint
CREATE TABLE "brain_section_versions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"section_id" varchar(255) NOT NULL,
	"version_number" integer NOT NULL,
	"markdown" text NOT NULL,
	"structured_content" jsonb,
	"change_summary" text NOT NULL,
	"created_by_model_run_id" uuid,
	"review_status" "brain_section_review_status" DEFAULT 'draft' NOT NULL,
	"reviewed_by_employee_id" uuid,
	"reviewed_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "brain_sections" (
	"id" varchar(255) PRIMARY KEY NOT NULL,
	"knowledge_domain" "knowledge_domain" NOT NULL,
	"related_domains" jsonb,
	"title" varchar(255) NOT NULL,
	"category" varchar(100) NOT NULL,
	"current_version_id" uuid,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "channel_participants" (
	"channel_id" uuid NOT NULL,
	"employee_id" uuid NOT NULL,
	"joined_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "channel_participants_channel_id_employee_id_pk" PRIMARY KEY("channel_id","employee_id")
);
--> statement-breakpoint
CREATE TABLE "channels" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"name" varchar(255),
	"is_group_chat" boolean DEFAULT false NOT NULL,
	"status" "channel_status" DEFAULT 'active' NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "claim_domains" (
	"claim_id" uuid NOT NULL,
	"domain" "knowledge_domain" NOT NULL,
	CONSTRAINT "claim_domains_claim_id_domain_pk" PRIMARY KEY("claim_id","domain")
);
--> statement-breakpoint
CREATE TABLE "claim_evidence" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"claim_id" uuid NOT NULL,
	"source_type" "evidence_source_type" NOT NULL,
	"source_message_id" uuid,
	"source_document_chunk_id" uuid,
	"source_external_record_id" varchar(255),
	"asserted_by_employee_id" uuid,
	"uploaded_by_employee_id" uuid,
	"created_by_employee_id" uuid,
	"exact_quote" text NOT NULL,
	"char_start" integer,
	"char_end" integer,
	"page_number" integer,
	"confidence" integer,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "claims" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"claim_type" varchar(100) NOT NULL,
	"summary" text NOT NULL,
	"impact_score" integer NOT NULL,
	"confidence_score" integer NOT NULL,
	"status" "claim_status" NOT NULL,
	"embedding" vector(1536),
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "contradictions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"claim_a_id" uuid NOT NULL,
	"claim_b_id" uuid NOT NULL,
	"description" text NOT NULL,
	"severity" varchar(50) NOT NULL,
	"status" "contradiction_status" DEFAULT 'possible' NOT NULL,
	"detection_confidence" integer,
	"retrieved_claim_ids" jsonb,
	"new_message_id" uuid,
	"interjection_decision" "intervention_decision",
	"suggested_question" text,
	"assigned_gap_id" uuid,
	"resolved_by_claim_id" uuid,
	"created_by_model_run_id" uuid,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"resolved_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "document_chunks" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"document_id" uuid NOT NULL,
	"chunk_index" integer NOT NULL,
	"page_number" integer,
	"sheet_name" varchar(255),
	"row_start" integer,
	"row_end" integer,
	"raw_text" text NOT NULL,
	"token_count" integer,
	"content_hash" varchar(255),
	"embedding" vector(1536),
	"metadata_json" jsonb
);
--> statement-breakpoint
CREATE TABLE "documents" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"uploader_id" uuid NOT NULL,
	"file_name" varchar(255) NOT NULL,
	"storage_bucket" varchar(100) NOT NULL,
	"storage_path" varchar(500) NOT NULL,
	"file_type" varchar(50) NOT NULL,
	"status" "document_status" DEFAULT 'pending_processing' NOT NULL,
	"processing_error" text,
	"processed_at" timestamp,
	"parser_version" varchar(50),
	"ocr_confidence" integer,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "employee_invites" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"employee_id" uuid NOT NULL,
	"token_hash" varchar(255) NOT NULL,
	"token_last_four" varchar(4) NOT NULL,
	"expires_at" timestamp NOT NULL,
	"used_at" timestamp,
	"revoked_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "employee_invites_token_hash_unique" UNIQUE("token_hash")
);
--> statement-breakpoint
CREATE TABLE "employees" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"auth_user_id" uuid,
	"email" varchar(320) NOT NULL,
	"auth_provider" "auth_provider",
	"auth_provider_subject" varchar(255),
	"name" varchar(255) NOT NULL,
	"role" varchar(255) NOT NULL,
	"department" varchar(255) NOT NULL,
	"is_admin" boolean DEFAULT false NOT NULL,
	"disabled_at" timestamp,
	"last_login_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "employees_auth_user_id_unique" UNIQUE("auth_user_id"),
	CONSTRAINT "employees_email_unique" UNIQUE("email")
);
--> statement-breakpoint
CREATE TABLE "gaps" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"gap_type" varchar(50) NOT NULL,
	"section_id" varchar(255),
	"related_claim_ids" jsonb,
	"related_contradiction_id" uuid,
	"question_to_ask" text NOT NULL,
	"why_it_matters" text NOT NULL,
	"target_employee_id" uuid,
	"target_department" varchar(255),
	"priority" "gap_priority" NOT NULL,
	"status" "gap_status" DEFAULT 'open' NOT NULL,
	"asked_in_message_id" uuid,
	"resolved_by_claim_id" uuid,
	"created_by_model_run_id" uuid,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	"resolved_at" timestamp
);
--> statement-breakpoint
CREATE TABLE "job_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"trigger_run_id" varchar(255) NOT NULL,
	"job_type" varchar(100) NOT NULL,
	"status" varchar(50) NOT NULL,
	"started_at" timestamp NOT NULL,
	"finished_at" timestamp,
	"input_json" jsonb,
	"output_json" jsonb,
	"error" text,
	"retry_count" integer DEFAULT 0 NOT NULL
);
--> statement-breakpoint
CREATE TABLE "message_attachments" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"message_id" uuid NOT NULL,
	"document_id" uuid NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "messages" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"channel_id" uuid NOT NULL,
	"employee_id" uuid,
	"role" "message_role" NOT NULL,
	"content" text NOT NULL,
	"client_message_id" varchar(255),
	"reply_to_message_id" uuid,
	"metadata_json" jsonb,
	"extraction_status" "extraction_status" DEFAULT 'pending' NOT NULL,
	"extracted_at" timestamp,
	"extraction_error" text,
	"edited_at" timestamp,
	"deleted_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "model_runs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"task_type" varchar(100) NOT NULL,
	"model" varchar(100) NOT NULL,
	"provider" varchar(100) NOT NULL,
	"prompt_version" varchar(50),
	"input_hash" varchar(255),
	"input_tokens" integer,
	"output_tokens" integer,
	"cost_usd" numeric(12, 6),
	"latency_ms" integer,
	"success" boolean NOT NULL,
	"error" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "oracle_interventions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"channel_id" uuid NOT NULL,
	"trigger_type" "oracle_intervention_trigger_type" NOT NULL,
	"related_gap_id" uuid,
	"related_contradiction_id" uuid,
	"related_message_id" uuid,
	"interjection_message_id" uuid,
	"confidence" integer,
	"impact_score" integer,
	"was_live_interjection" boolean NOT NULL,
	"reason" text,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "section_claims" (
	"section_id" varchar(255) NOT NULL,
	"claim_id" uuid NOT NULL,
	CONSTRAINT "section_claims_section_id_claim_id_pk" PRIMARY KEY("section_id","claim_id")
);
--> statement-breakpoint
CREATE TABLE "settings" (
	"key" varchar(100) PRIMARY KEY NOT NULL,
	"value" jsonb NOT NULL,
	"description" text,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "brain_section_versions" ADD CONSTRAINT "brain_section_versions_section_id_brain_sections_id_fk" FOREIGN KEY ("section_id") REFERENCES "public"."brain_sections"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "brain_section_versions" ADD CONSTRAINT "brain_section_versions_created_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("created_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "brain_section_versions" ADD CONSTRAINT "brain_section_versions_reviewed_by_employee_id_employees_id_fk" FOREIGN KEY ("reviewed_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "channel_participants" ADD CONSTRAINT "channel_participants_channel_id_channels_id_fk" FOREIGN KEY ("channel_id") REFERENCES "public"."channels"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "channel_participants" ADD CONSTRAINT "channel_participants_employee_id_employees_id_fk" FOREIGN KEY ("employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_domains" ADD CONSTRAINT "claim_domains_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_source_message_id_messages_id_fk" FOREIGN KEY ("source_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_source_document_chunk_id_document_chunks_id_fk" FOREIGN KEY ("source_document_chunk_id") REFERENCES "public"."document_chunks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_asserted_by_employee_id_employees_id_fk" FOREIGN KEY ("asserted_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_uploaded_by_employee_id_employees_id_fk" FOREIGN KEY ("uploaded_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_evidence" ADD CONSTRAINT "claim_evidence_created_by_employee_id_employees_id_fk" FOREIGN KEY ("created_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "contradictions" ADD CONSTRAINT "contradictions_claim_a_id_claims_id_fk" FOREIGN KEY ("claim_a_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "contradictions" ADD CONSTRAINT "contradictions_claim_b_id_claims_id_fk" FOREIGN KEY ("claim_b_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "contradictions" ADD CONSTRAINT "contradictions_new_message_id_messages_id_fk" FOREIGN KEY ("new_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "contradictions" ADD CONSTRAINT "contradictions_resolved_by_claim_id_claims_id_fk" FOREIGN KEY ("resolved_by_claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "contradictions" ADD CONSTRAINT "contradictions_created_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("created_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_chunks" ADD CONSTRAINT "document_chunks_document_id_documents_id_fk" FOREIGN KEY ("document_id") REFERENCES "public"."documents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "documents" ADD CONSTRAINT "documents_uploader_id_employees_id_fk" FOREIGN KEY ("uploader_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "employee_invites" ADD CONSTRAINT "employee_invites_employee_id_employees_id_fk" FOREIGN KEY ("employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_section_id_brain_sections_id_fk" FOREIGN KEY ("section_id") REFERENCES "public"."brain_sections"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_related_contradiction_id_contradictions_id_fk" FOREIGN KEY ("related_contradiction_id") REFERENCES "public"."contradictions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_target_employee_id_employees_id_fk" FOREIGN KEY ("target_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_asked_in_message_id_messages_id_fk" FOREIGN KEY ("asked_in_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_resolved_by_claim_id_claims_id_fk" FOREIGN KEY ("resolved_by_claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "gaps" ADD CONSTRAINT "gaps_created_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("created_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_attachments" ADD CONSTRAINT "message_attachments_message_id_messages_id_fk" FOREIGN KEY ("message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_attachments" ADD CONSTRAINT "message_attachments_document_id_documents_id_fk" FOREIGN KEY ("document_id") REFERENCES "public"."documents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "messages" ADD CONSTRAINT "messages_channel_id_channels_id_fk" FOREIGN KEY ("channel_id") REFERENCES "public"."channels"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "messages" ADD CONSTRAINT "messages_employee_id_employees_id_fk" FOREIGN KEY ("employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_interventions" ADD CONSTRAINT "oracle_interventions_channel_id_channels_id_fk" FOREIGN KEY ("channel_id") REFERENCES "public"."channels"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_interventions" ADD CONSTRAINT "oracle_interventions_related_gap_id_gaps_id_fk" FOREIGN KEY ("related_gap_id") REFERENCES "public"."gaps"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_interventions" ADD CONSTRAINT "oracle_interventions_related_contradiction_id_contradictions_id_fk" FOREIGN KEY ("related_contradiction_id") REFERENCES "public"."contradictions"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_interventions" ADD CONSTRAINT "oracle_interventions_related_message_id_messages_id_fk" FOREIGN KEY ("related_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_interventions" ADD CONSTRAINT "oracle_interventions_interjection_message_id_messages_id_fk" FOREIGN KEY ("interjection_message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "section_claims" ADD CONSTRAINT "section_claims_section_id_brain_sections_id_fk" FOREIGN KEY ("section_id") REFERENCES "public"."brain_sections"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "section_claims" ADD CONSTRAINT "section_claims_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE UNIQUE INDEX "brain_section_versions_section_version_unique" ON "brain_section_versions" USING btree ("section_id","version_number");--> statement-breakpoint
CREATE INDEX "brain_section_versions_section_version_idx" ON "brain_section_versions" USING btree ("section_id","version_number");--> statement-breakpoint
CREATE INDEX "channel_participants_employee_idx" ON "channel_participants" USING btree ("employee_id");--> statement-breakpoint
CREATE INDEX "claim_domains_domain_idx" ON "claim_domains" USING btree ("domain");--> statement-breakpoint
CREATE INDEX "claim_evidence_claim_idx" ON "claim_evidence" USING btree ("claim_id");--> statement-breakpoint
CREATE INDEX "claim_evidence_message_idx" ON "claim_evidence" USING btree ("source_message_id");--> statement-breakpoint
CREATE INDEX "claim_evidence_document_chunk_idx" ON "claim_evidence" USING btree ("source_document_chunk_id");--> statement-breakpoint
CREATE INDEX "claims_status_created_idx" ON "claims" USING btree ("status","created_at");--> statement-breakpoint
CREATE INDEX "claims_impact_idx" ON "claims" USING btree ("impact_score");--> statement-breakpoint
CREATE INDEX "claims_confidence_idx" ON "claims" USING btree ("confidence_score");--> statement-breakpoint
CREATE INDEX "contradictions_status_severity_idx" ON "contradictions" USING btree ("status","severity");--> statement-breakpoint
CREATE UNIQUE INDEX "document_chunks_document_chunk_unique" ON "document_chunks" USING btree ("document_id","chunk_index");--> statement-breakpoint
CREATE INDEX "document_chunks_document_idx" ON "document_chunks" USING btree ("document_id");--> statement-breakpoint
CREATE UNIQUE INDEX "documents_storage_unique" ON "documents" USING btree ("storage_bucket","storage_path");--> statement-breakpoint
CREATE INDEX "documents_uploader_idx" ON "documents" USING btree ("uploader_id");--> statement-breakpoint
CREATE INDEX "gaps_status_priority_idx" ON "gaps" USING btree ("status","priority");--> statement-breakpoint
CREATE INDEX "gaps_target_status_idx" ON "gaps" USING btree ("target_employee_id","status");--> statement-breakpoint
CREATE INDEX "job_runs_type_status_started_idx" ON "job_runs" USING btree ("job_type","status","started_at");--> statement-breakpoint
CREATE INDEX "messages_channel_created_idx" ON "messages" USING btree ("channel_id","created_at");--> statement-breakpoint
CREATE INDEX "messages_extraction_idx" ON "messages" USING btree ("extraction_status","role","created_at");--> statement-breakpoint
CREATE UNIQUE INDEX "messages_channel_client_message_unique" ON "messages" USING btree ("channel_id","client_message_id");--> statement-breakpoint
CREATE INDEX "model_runs_task_created_idx" ON "model_runs" USING btree ("task_type","created_at");--> statement-breakpoint
CREATE INDEX "section_claims_claim_idx" ON "section_claims" USING btree ("claim_id");