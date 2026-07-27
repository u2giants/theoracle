CREATE TABLE "claim_translation_events" (
	"id" uuid PRIMARY KEY DEFAULT gen_random_uuid() NOT NULL,
	"claim_id" uuid NOT NULL,
	"lang" varchar(12) NOT NULL,
	"action" varchar(30) NOT NULL,
	"acted_by_employee_id" uuid,
	"before_state" jsonb,
	"after_state" jsonb,
	"created_at" timestamp DEFAULT now() NOT NULL
);
--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "translation_model_provider" varchar(100);--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "translation_model_id" varchar(255);--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "translation_prompt_version" varchar(100);--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "review_status" varchar(30) DEFAULT 'pending_review' NOT NULL;--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "reviewed_by_employee_id" uuid;--> statement-breakpoint
ALTER TABLE "claim_translations" ADD COLUMN "reviewed_at" timestamp;--> statement-breakpoint
ALTER TABLE "claim_translation_events" ADD CONSTRAINT "claim_translation_events_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_translation_events" ADD CONSTRAINT "claim_translation_events_acted_by_employee_id_employees_id_fk" FOREIGN KEY ("acted_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE set null ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "claim_translation_events_claim_lang_idx" ON "claim_translation_events" USING btree ("claim_id","lang","created_at");--> statement-breakpoint
ALTER TABLE "claim_translations" ADD CONSTRAINT "claim_translations_reviewed_by_employee_id_employees_id_fk" FOREIGN KEY ("reviewed_by_employee_id") REFERENCES "public"."employees"("id") ON DELETE set null ON UPDATE no action;