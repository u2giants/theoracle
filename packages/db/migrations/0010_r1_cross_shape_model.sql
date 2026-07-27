CREATE TABLE "business_conversation_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"decision_status" varchar(50),
	"contested" boolean DEFAULT false NOT NULL,
	"speaker" text,
	"due_date" date,
	"action_status" varchar(50),
	"meeting_reference" text
);
--> statement-breakpoint
CREATE TABLE "business_element_claims" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"version_id" uuid NOT NULL,
	"element_id" uuid,
	"relation_id" uuid,
	"claim_id" uuid NOT NULL,
	"support_role" varchar(50) DEFAULT 'primary' NOT NULL,
	"claim_status_at_link" varchar(50) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_element_systems" (
	"element_id" uuid NOT NULL,
	"entity_id" uuid NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "business_element_systems_element_id_entity_id_pk" PRIMARY KEY("element_id","entity_id")
);
--> statement-breakpoint
CREATE TABLE "business_elements" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"version_id" uuid NOT NULL,
	"element_key" varchar(120) NOT NULL,
	"shape" varchar(50) NOT NULL,
	"element_kind" varchar(50) NOT NULL,
	"label" text NOT NULL,
	"owner_department_id" "department",
	"owner_entity_id" uuid,
	"owner_raw" text,
	"provisional" boolean DEFAULT true NOT NULL,
	"confidence_score" integer,
	"sort_order" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_narrative_macro_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"macro_kind" varchar(50) NOT NULL,
	"goal" text,
	"constraint" text,
	"risk" text,
	"rationale" text
);
--> statement-breakpoint
CREATE TABLE "business_object_top_domains" (
	"object_id" uuid NOT NULL,
	"top_domain_id" varchar(100) NOT NULL,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	CONSTRAINT "business_object_top_domains_object_id_top_domain_id_pk" PRIMARY KEY("object_id","top_domain_id")
);
--> statement-breakpoint
CREATE TABLE "business_object_versions" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"object_id" uuid NOT NULL,
	"version_number" integer NOT NULL,
	"status" varchar(50) DEFAULT 'pending_review' NOT NULL,
	"summary" text,
	"created_from_change_id" uuid,
	"model_run_id" uuid,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL,
	"approved_at" timestamp with time zone
);
--> statement-breakpoint
CREATE TABLE "business_objects" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"object_kind" varchar(50) NOT NULL,
	"name" text NOT NULL,
	"slug" varchar(160) NOT NULL,
	"status" varchar(50) DEFAULT 'draft' NOT NULL,
	"current_version_id" uuid,
	"summary" text,
	"embedding" vector(1536),
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_paths" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"version_id" uuid NOT NULL,
	"path_key" varchar(120) NOT NULL,
	"name" text NOT NULL,
	"path_type" varchar(50) NOT NULL,
	"element_keys_ordered" jsonb DEFAULT '[]'::jsonb NOT NULL,
	"terminal_outcome" text,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_process_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"node_type" varchar(50) NOT NULL,
	"lane_label" text,
	"presentation_label" text
);
--> statement-breakpoint
CREATE TABLE "business_reference_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"entity_type" varchar(120) NOT NULL,
	"attribute_key" varchar(160) NOT NULL,
	"attribute_value" text NOT NULL,
	"reference_kind" varchar(50) NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_relations" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"version_id" uuid NOT NULL,
	"relation_key" varchar(120) NOT NULL,
	"shape" varchar(50) NOT NULL,
	"relation_kind" varchar(50) NOT NULL,
	"from_element_key" varchar(120) NOT NULL,
	"to_element_key" varchar(120) NOT NULL,
	"condition" text,
	"provisional" boolean DEFAULT true NOT NULL,
	"confidence_score" integer,
	"sort_order" integer,
	"created_at" timestamp with time zone DEFAULT now() NOT NULL,
	"updated_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "business_responsibility_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"role" text NOT NULL,
	"action" text NOT NULL,
	"object" text NOT NULL,
	"trigger" text,
	"required_system" text
);
--> statement-breakpoint
CREATE TABLE "business_rule_details" (
	"element_id" uuid PRIMARY KEY NOT NULL,
	"scope" text NOT NULL,
	"condition" text,
	"effect" text NOT NULL,
	"exception" text
);
--> statement-breakpoint
ALTER TABLE "recommendations" ALTER COLUMN "process_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "recommendations" ALTER COLUMN "version_id" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD COLUMN "object_id" uuid;--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD COLUMN "object_kind" varchar(50);--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD COLUMN "proposed_slug" varchar(160);--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD COLUMN "base_object_version_id" uuid;--> statement-breakpoint
ALTER TABLE "recommendations" ADD COLUMN "object_id" uuid;--> statement-breakpoint
ALTER TABLE "recommendations" ADD COLUMN "object_version_id" uuid;--> statement-breakpoint
ALTER TABLE "recommendations" ADD COLUMN "object_kind" varchar(50);--> statement-breakpoint
ALTER TABLE "business_conversation_details" ADD CONSTRAINT "business_conversation_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_claims" ADD CONSTRAINT "business_element_claims_version_id_business_object_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_claims" ADD CONSTRAINT "business_element_claims_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_claims" ADD CONSTRAINT "business_element_claims_relation_id_business_relations_id_fk" FOREIGN KEY ("relation_id") REFERENCES "public"."business_relations"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_claims" ADD CONSTRAINT "business_element_claims_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE restrict ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_systems" ADD CONSTRAINT "business_element_systems_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_element_systems" ADD CONSTRAINT "business_element_systems_entity_id_entities_id_fk" FOREIGN KEY ("entity_id") REFERENCES "public"."entities"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_elements" ADD CONSTRAINT "business_elements_version_id_business_object_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_elements" ADD CONSTRAINT "business_elements_owner_department_id_departments_id_fk" FOREIGN KEY ("owner_department_id") REFERENCES "public"."departments"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_elements" ADD CONSTRAINT "business_elements_owner_entity_id_entities_id_fk" FOREIGN KEY ("owner_entity_id") REFERENCES "public"."entities"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_narrative_macro_details" ADD CONSTRAINT "business_narrative_macro_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_object_top_domains" ADD CONSTRAINT "business_object_top_domains_object_id_business_objects_id_fk" FOREIGN KEY ("object_id") REFERENCES "public"."business_objects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_object_top_domains" ADD CONSTRAINT "business_object_top_domains_top_domain_id_knowledge_top_domains_id_fk" FOREIGN KEY ("top_domain_id") REFERENCES "public"."knowledge_top_domains"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_object_versions" ADD CONSTRAINT "business_object_versions_object_id_business_objects_id_fk" FOREIGN KEY ("object_id") REFERENCES "public"."business_objects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_object_versions" ADD CONSTRAINT "business_object_versions_model_run_id_model_runs_id_fk" FOREIGN KEY ("model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_paths" ADD CONSTRAINT "business_paths_version_id_business_object_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_process_details" ADD CONSTRAINT "business_process_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_reference_details" ADD CONSTRAINT "business_reference_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_relations" ADD CONSTRAINT "business_relations_version_id_business_object_versions_id_fk" FOREIGN KEY ("version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_responsibility_details" ADD CONSTRAINT "business_responsibility_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_rule_details" ADD CONSTRAINT "business_rule_details_element_id_business_elements_id_fk" FOREIGN KEY ("element_id") REFERENCES "public"."business_elements"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "business_element_claims_claim_idx" ON "business_element_claims" USING btree ("claim_id");--> statement-breakpoint
CREATE INDEX "business_element_claims_element_idx" ON "business_element_claims" USING btree ("element_id");--> statement-breakpoint
CREATE INDEX "business_element_claims_relation_idx" ON "business_element_claims" USING btree ("relation_id");--> statement-breakpoint
CREATE UNIQUE INDEX "business_elements_version_element_unique" ON "business_elements" USING btree ("version_id","element_key");--> statement-breakpoint
CREATE INDEX "business_elements_version_shape_idx" ON "business_elements" USING btree ("version_id","shape");--> statement-breakpoint
CREATE INDEX "business_object_top_domains_domain_idx" ON "business_object_top_domains" USING btree ("top_domain_id");--> statement-breakpoint
CREATE INDEX "business_object_versions_object_status_idx" ON "business_object_versions" USING btree ("object_id","status");--> statement-breakpoint
CREATE UNIQUE INDEX "business_object_versions_object_version_unique" ON "business_object_versions" USING btree ("object_id","version_number");--> statement-breakpoint
CREATE UNIQUE INDEX "business_objects_kind_slug_unique" ON "business_objects" USING btree ("object_kind","slug");--> statement-breakpoint
CREATE INDEX "business_objects_kind_status_idx" ON "business_objects" USING btree ("object_kind","status");--> statement-breakpoint
CREATE INDEX "business_objects_current_version_idx" ON "business_objects" USING btree ("current_version_id");--> statement-breakpoint
CREATE UNIQUE INDEX "business_paths_version_path_unique" ON "business_paths" USING btree ("version_id","path_key");--> statement-breakpoint
CREATE UNIQUE INDEX "business_relations_version_relation_unique" ON "business_relations" USING btree ("version_id","relation_key");--> statement-breakpoint
CREATE INDEX "business_relations_version_shape_idx" ON "business_relations" USING btree ("version_id","shape");--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD CONSTRAINT "business_model_changes_object_id_business_objects_id_fk" FOREIGN KEY ("object_id") REFERENCES "public"."business_objects"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "business_model_changes" ADD CONSTRAINT "business_model_changes_base_object_version_id_business_object_versions_id_fk" FOREIGN KEY ("base_object_version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_object_id_business_objects_id_fk" FOREIGN KEY ("object_id") REFERENCES "public"."business_objects"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "recommendations" ADD CONSTRAINT "recommendations_object_version_id_business_object_versions_id_fk" FOREIGN KEY ("object_version_id") REFERENCES "public"."business_object_versions"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "business_model_changes_object_status_idx" ON "business_model_changes" USING btree ("object_id","status");--> statement-breakpoint
CREATE INDEX "business_model_changes_proposed_namespace_idx" ON "business_model_changes" USING btree ("object_kind","proposed_slug","status");--> statement-breakpoint
CREATE INDEX "recommendations_object_status_idx" ON "recommendations" USING btree ("object_id","status");