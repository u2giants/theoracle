CREATE TABLE "employee_identities" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"employee_id" uuid NOT NULL,
	"auth_provider" "auth_provider" NOT NULL,
	"auth_user_id" uuid NOT NULL,
	"auth_provider_subject" varchar(255),
	"email" varchar(320) NOT NULL,
	"linked_at" timestamp DEFAULT now() NOT NULL,
	"last_login_at" timestamp,
	CONSTRAINT "employee_identities_auth_user_id_unique" UNIQUE("auth_user_id")
);
--> statement-breakpoint
CREATE TABLE "model_run_usage_details" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"model_run_id" uuid NOT NULL,
	"context_pack_id" uuid,
	"route_id" varchar(100) NOT NULL,
	"input_tokens" integer,
	"cached_input_tokens" integer,
	"cache_write_tokens" integer,
	"output_tokens" integer,
	"reasoning_tokens" integer,
	"provider_request_id" varchar(255),
	"raw_usage_json" jsonb,
	"fell_back_from_route_id" varchar(100),
	"fallback_reason" varchar(100),
	"created_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "model_run_usage_details_model_run_id_unique" UNIQUE("model_run_id")
);
--> statement-breakpoint
CREATE TABLE "oracle_context_packs" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"model_run_id" uuid,
	"task_type" varchar(100) NOT NULL,
	"route_id" varchar(100) NOT NULL,
	"prompt_version" varchar(50),
	"schema_version" varchar(50),
	"stable_prefix_hash" varchar(64) NOT NULL,
	"semi_stable_context_hash" varchar(64),
	"retrieved_context_hash" varchar(64),
	"dynamic_input_hash" varchar(64) NOT NULL,
	"tool_schema_hash" varchar(64),
	"output_schema_hash" varchar(64),
	"blocks_json" jsonb,
	"retrieval_plan_id" varchar(100),
	"selected_domains" jsonb,
	"selected_source_types" jsonb,
	"selected_process_stages" jsonb,
	"selected_entity_ids" jsonb,
	"included_message_ids" jsonb,
	"included_document_chunk_ids" jsonb,
	"included_claim_ids" jsonb,
	"included_gap_ids" jsonb,
	"included_contradiction_ids" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "provider_cached_content" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"provider" varchar(50) NOT NULL,
	"cache_kind" varchar(50) NOT NULL,
	"provider_resource_name" varchar(500),
	"source_hash" varchar(64) NOT NULL,
	"source_token_estimate" integer,
	"source_description" text,
	"expected_reuse_count" integer NOT NULL,
	"actual_reuse_count" integer DEFAULT 0 NOT NULL,
	"latest_planned_reuse_step" varchar(100),
	"hard_expiration_at" timestamp NOT NULL,
	"cleanup_owner" varchar(100),
	"status" varchar(50) DEFAULT 'active' NOT NULL,
	"deleted_at" timestamp,
	"status_reason" text,
	"created_by_job_run_id" uuid,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "employee_identities" ADD CONSTRAINT "employee_identities_employee_id_employees_id_fk" FOREIGN KEY ("employee_id") REFERENCES "public"."employees"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_run_usage_details" ADD CONSTRAINT "model_run_usage_details_model_run_id_model_runs_id_fk" FOREIGN KEY ("model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "model_run_usage_details" ADD CONSTRAINT "model_run_usage_details_context_pack_id_oracle_context_packs_id_fk" FOREIGN KEY ("context_pack_id") REFERENCES "public"."oracle_context_packs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "oracle_context_packs" ADD CONSTRAINT "oracle_context_packs_model_run_id_model_runs_id_fk" FOREIGN KEY ("model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "provider_cached_content" ADD CONSTRAINT "provider_cached_content_created_by_job_run_id_job_runs_id_fk" FOREIGN KEY ("created_by_job_run_id") REFERENCES "public"."job_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "employee_identities_provider_employee_idx" ON "employee_identities" USING btree ("auth_provider","employee_id");--> statement-breakpoint
CREATE INDEX "employee_identities_employee_idx" ON "employee_identities" USING btree ("employee_id");--> statement-breakpoint
CREATE INDEX "employee_identities_email_idx" ON "employee_identities" USING btree ("email");--> statement-breakpoint
CREATE UNIQUE INDEX "employee_identities_provider_employee_unique" ON "employee_identities" USING btree ("auth_provider","employee_id");--> statement-breakpoint
CREATE INDEX "model_run_usage_details_route_idx" ON "model_run_usage_details" USING btree ("route_id");--> statement-breakpoint
CREATE INDEX "model_run_usage_details_context_pack_idx" ON "model_run_usage_details" USING btree ("context_pack_id");--> statement-breakpoint
CREATE INDEX "model_run_usage_details_fellback_idx" ON "model_run_usage_details" USING btree ("fell_back_from_route_id");--> statement-breakpoint
CREATE INDEX "oracle_context_packs_task_created_idx" ON "oracle_context_packs" USING btree ("task_type","created_at");--> statement-breakpoint
CREATE INDEX "oracle_context_packs_route_idx" ON "oracle_context_packs" USING btree ("route_id");--> statement-breakpoint
CREATE INDEX "oracle_context_packs_model_run_idx" ON "oracle_context_packs" USING btree ("model_run_id");--> statement-breakpoint
CREATE INDEX "oracle_context_packs_stable_prefix_hash_idx" ON "oracle_context_packs" USING btree ("stable_prefix_hash");--> statement-breakpoint
CREATE INDEX "provider_cached_content_status_idx" ON "provider_cached_content" USING btree ("status");--> statement-breakpoint
CREATE INDEX "provider_cached_content_provider_status_idx" ON "provider_cached_content" USING btree ("provider","status");--> statement-breakpoint
CREATE INDEX "provider_cached_content_source_hash_idx" ON "provider_cached_content" USING btree ("source_hash");--> statement-breakpoint
CREATE INDEX "provider_cached_content_expiration_idx" ON "provider_cached_content" USING btree ("hard_expiration_at");--> statement-breakpoint
CREATE INDEX "provider_cached_content_cleanup_owner_idx" ON "provider_cached_content" USING btree ("cleanup_owner");