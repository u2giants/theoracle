CREATE TABLE "claim_entities" (
	"claim_id" uuid NOT NULL,
	"entity_id" uuid NOT NULL,
	CONSTRAINT "claim_entities_claim_id_entity_id_pk" PRIMARY KEY("claim_id","entity_id")
);
--> statement-breakpoint
CREATE TABLE "claim_metadata" (
	"claim_id" uuid PRIMARY KEY NOT NULL,
	"process_stage" varchar(100),
	"department" varchar(100),
	"geography" varchar(100),
	"document_class" varchar(100),
	"effective_from" timestamp,
	"effective_until" timestamp,
	"superseded_by_claim_id" uuid,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "claim_sub_topics" (
	"claim_id" uuid NOT NULL,
	"sub_topic_id" uuid NOT NULL,
	"assignment_confidence" numeric(4, 3),
	"assignment_reason" varchar(50) NOT NULL,
	"assigned_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "claim_sub_topics_claim_id_sub_topic_id_pk" PRIMARY KEY("claim_id","sub_topic_id")
);
--> statement-breakpoint
CREATE TABLE "claim_top_domains" (
	"claim_id" uuid NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"assignment_confidence" numeric(4, 3),
	"assignment_reason" varchar(50) NOT NULL,
	"assigned_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "claim_top_domains_claim_id_top_domain_id_pk" PRIMARY KEY("claim_id","top_domain_id")
);
--> statement-breakpoint
CREATE TABLE "document_chunk_entities" (
	"document_chunk_id" uuid NOT NULL,
	"entity_id" uuid NOT NULL,
	CONSTRAINT "document_chunk_entities_document_chunk_id_entity_id_pk" PRIMARY KEY("document_chunk_id","entity_id")
);
--> statement-breakpoint
CREATE TABLE "document_chunk_top_domains" (
	"document_chunk_id" uuid NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"assignment_confidence" numeric(4, 3),
	"assignment_reason" varchar(50) NOT NULL,
	"assigned_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "document_chunk_top_domains_document_chunk_id_top_domain_id_pk" PRIMARY KEY("document_chunk_id","top_domain_id")
);
--> statement-breakpoint
CREATE TABLE "document_top_domains" (
	"document_id" uuid NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"assignment_confidence" numeric(4, 3),
	"assignment_reason" varchar(50) NOT NULL,
	"assigned_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "document_top_domains_document_id_top_domain_id_pk" PRIMARY KEY("document_id","top_domain_id")
);
--> statement-breakpoint
CREATE TABLE "entities" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"entity_type" varchar(50) NOT NULL,
	"canonical_value" varchar(255) NOT NULL,
	"display_label" varchar(255),
	"aliases" jsonb,
	"domain_hints" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "entity_proposals" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"proposed_entity_type" varchar(50) NOT NULL,
	"proposed_canonical_value" varchar(255) NOT NULL,
	"raw_strings_observed" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"proposed_aliases" jsonb,
	"proposed_domain_hints" jsonb,
	"observed_in_source_type" varchar(50) NOT NULL,
	"observed_in_source_id" uuid,
	"status" varchar(50) NOT NULL,
	"merged_into_entity_id" uuid,
	"proposed_by_model_run_id" uuid,
	"reviewed_by_employee_id" uuid,
	"reviewed_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "knowledge_sub_topics" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"name" varchar(255) NOT NULL,
	"description" text,
	"centroid" vector(1536),
	"member_count" integer DEFAULT 0 NOT NULL,
	"review_status" varchar(50) NOT NULL,
	"approved_by_employee_id" uuid,
	"approved_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "knowledge_top_domains" (
	"id" varchar(100) PRIMARY KEY NOT NULL,
	"name" varchar(255) NOT NULL,
	"description" text NOT NULL,
	"belongs_here" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"does_not_belong_here" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"common_entity_hints" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"default_excluded_document_classes" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"neighboring_domain_ids" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"display_order" integer NOT NULL,
	"is_active" boolean DEFAULT true NOT NULL,
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "message_entities" (
	"message_id" uuid NOT NULL,
	"entity_id" uuid NOT NULL,
	CONSTRAINT "message_entities_message_id_entity_id_pk" PRIMARY KEY("message_id","entity_id")
);
--> statement-breakpoint
CREATE TABLE "message_top_domains" (
	"message_id" uuid NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"assignment_confidence" numeric(4, 3),
	"assignment_reason" varchar(50) NOT NULL,
	"assigned_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "message_top_domains_message_id_top_domain_id_pk" PRIMARY KEY("message_id","top_domain_id")
);
--> statement-breakpoint
CREATE TABLE "taxonomy_change_log" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"change_type" varchar(100) NOT NULL,
	"before_state" jsonb,
	"after_state" jsonb,
	"reason" text,
	"approved_by_employee_id" uuid,
	"proposal_id" uuid,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "taxonomy_proposals" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"proposal_type" varchar(50) NOT NULL,
	"payload" jsonb NOT NULL,
	"proposed_by_model_run_id" uuid,
	"status" varchar(50) NOT NULL,
	"reviewed_by_employee_id" uuid,
	"reviewed_at" timestamp,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "claim_entities" ADD CONSTRAINT "claim_entities_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_entities" ADD CONSTRAINT "claim_entities_entity_id_entities_id_fk" FOREIGN KEY ("entity_id") REFERENCES "public"."entities"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_metadata" ADD CONSTRAINT "claim_metadata_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_metadata" ADD CONSTRAINT "claim_metadata_superseded_by_claim_id_claims_id_fk" FOREIGN KEY ("superseded_by_claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_sub_topics" ADD CONSTRAINT "claim_sub_topics_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_sub_topics" ADD CONSTRAINT "claim_sub_topics_sub_topic_id_knowledge_sub_topics_id_fk" FOREIGN KEY ("sub_topic_id") REFERENCES "public"."knowledge_sub_topics"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_top_domains" ADD CONSTRAINT "claim_top_domains_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_top_domains" ADD CONSTRAINT "claim_top_domains_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_chunk_entities" ADD CONSTRAINT "document_chunk_entities_document_chunk_id_document_chunks_id_fk" FOREIGN KEY ("document_chunk_id") REFERENCES "public"."document_chunks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_chunk_entities" ADD CONSTRAINT "document_chunk_entities_entity_id_entities_id_fk" FOREIGN KEY ("entity_id") REFERENCES "public"."entities"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_chunk_top_domains" ADD CONSTRAINT "document_chunk_top_domains_document_chunk_id_document_chunks_id_fk" FOREIGN KEY ("document_chunk_id") REFERENCES "public"."document_chunks"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_chunk_top_domains" ADD CONSTRAINT "document_chunk_top_domains_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_top_domains" ADD CONSTRAINT "document_top_domains_document_id_documents_id_fk" FOREIGN KEY ("document_id") REFERENCES "public"."documents"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "document_top_domains" ADD CONSTRAINT "document_top_domains_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "entity_proposals" ADD CONSTRAINT "entity_proposals_merged_into_entity_id_entities_id_fk" FOREIGN KEY ("merged_into_entity_id") REFERENCES "public"."entities"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "entity_proposals" ADD CONSTRAINT "entity_proposals_proposed_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("proposed_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "entity_proposals" ADD CONSTRAINT "entity_proposals_reviewed_by_employee_id_employees_id_fk" FOREIGN KEY ("reviewed_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "knowledge_sub_topics" ADD CONSTRAINT "knowledge_sub_topics_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "knowledge_sub_topics" ADD CONSTRAINT "knowledge_sub_topics_approved_by_employee_id_employees_id_fk" FOREIGN KEY ("approved_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_entities" ADD CONSTRAINT "message_entities_message_id_messages_id_fk" FOREIGN KEY ("message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_entities" ADD CONSTRAINT "message_entities_entity_id_entities_id_fk" FOREIGN KEY ("entity_id") REFERENCES "public"."entities"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_top_domains" ADD CONSTRAINT "message_top_domains_message_id_messages_id_fk" FOREIGN KEY ("message_id") REFERENCES "public"."messages"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "message_top_domains" ADD CONSTRAINT "message_top_domains_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "taxonomy_change_log" ADD CONSTRAINT "taxonomy_change_log_approved_by_employee_id_employees_id_fk" FOREIGN KEY ("approved_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "taxonomy_change_log" ADD CONSTRAINT "taxonomy_change_log_proposal_id_taxonomy_proposals_id_fk" FOREIGN KEY ("proposal_id") REFERENCES "public"."taxonomy_proposals"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "taxonomy_proposals" ADD CONSTRAINT "taxonomy_proposals_proposed_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("proposed_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "taxonomy_proposals" ADD CONSTRAINT "taxonomy_proposals_reviewed_by_employee_id_employees_id_fk" FOREIGN KEY ("reviewed_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "claim_entities_entity_idx" ON "claim_entities" USING btree ("entity_id");--> statement-breakpoint
CREATE INDEX "claim_sub_topics_sub_topic_idx" ON "claim_sub_topics" USING btree ("sub_topic_id");--> statement-breakpoint
CREATE INDEX "claim_top_domains_top_domain_idx" ON "claim_top_domains" USING btree ("top_domain_id");--> statement-breakpoint
CREATE INDEX "document_chunk_entities_entity_idx" ON "document_chunk_entities" USING btree ("entity_id");--> statement-breakpoint
CREATE INDEX "document_chunk_top_domains_top_domain_idx" ON "document_chunk_top_domains" USING btree ("top_domain_id");--> statement-breakpoint
CREATE INDEX "document_top_domains_top_domain_idx" ON "document_top_domains" USING btree ("top_domain_id");--> statement-breakpoint
CREATE UNIQUE INDEX "entities_type_value_unique" ON "entities" USING btree ("entity_type","canonical_value");--> statement-breakpoint
CREATE INDEX "entities_type_idx" ON "entities" USING btree ("entity_type");--> statement-breakpoint
CREATE INDEX "entity_proposals_status_idx" ON "entity_proposals" USING btree ("status");--> statement-breakpoint
CREATE INDEX "entity_proposals_type_value_idx" ON "entity_proposals" USING btree ("proposed_entity_type","proposed_canonical_value");--> statement-breakpoint
CREATE UNIQUE INDEX "knowledge_sub_topics_top_domain_name_unique" ON "knowledge_sub_topics" USING btree ("top_domain_id","name");--> statement-breakpoint
CREATE INDEX "knowledge_sub_topics_top_domain_idx" ON "knowledge_sub_topics" USING btree ("top_domain_id");--> statement-breakpoint
CREATE INDEX "knowledge_sub_topics_review_status_idx" ON "knowledge_sub_topics" USING btree ("review_status");--> statement-breakpoint
CREATE INDEX "message_entities_entity_idx" ON "message_entities" USING btree ("entity_id");--> statement-breakpoint
CREATE INDEX "message_top_domains_top_domain_idx" ON "message_top_domains" USING btree ("top_domain_id");--> statement-breakpoint
CREATE INDEX "taxonomy_change_log_change_type_idx" ON "taxonomy_change_log" USING btree ("change_type");--> statement-breakpoint
CREATE INDEX "taxonomy_change_log_proposal_idx" ON "taxonomy_change_log" USING btree ("proposal_id");--> statement-breakpoint
CREATE INDEX "taxonomy_proposals_status_idx" ON "taxonomy_proposals" USING btree ("status");--> statement-breakpoint
CREATE INDEX "taxonomy_proposals_type_status_idx" ON "taxonomy_proposals" USING btree ("proposal_type","status");