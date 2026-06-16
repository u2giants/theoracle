CREATE TABLE "claim_translations" (
	"claim_id" uuid NOT NULL,
	"lang" varchar(12) NOT NULL,
	"summary" text NOT NULL,
	"embedding" vector(1536),
	"translated_by_model_run_id" uuid,
	"source_hash" varchar(64),
	"created_at" timestamp DEFAULT now() NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "claim_translations_claim_id_lang_pk" PRIMARY KEY("claim_id","lang")
);
--> statement-breakpoint
ALTER TABLE "claims" ADD COLUMN "source_lang" varchar(12) DEFAULT 'en' NOT NULL;--> statement-breakpoint
ALTER TABLE "employees" ADD COLUMN "locale" varchar(12) DEFAULT 'en' NOT NULL;--> statement-breakpoint
ALTER TABLE "claim_translations" ADD CONSTRAINT "claim_translations_claim_id_claims_id_fk" FOREIGN KEY ("claim_id") REFERENCES "public"."claims"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "claim_translations" ADD CONSTRAINT "claim_translations_translated_by_model_run_id_model_runs_id_fk" FOREIGN KEY ("translated_by_model_run_id") REFERENCES "public"."model_runs"("id") ON DELETE no action ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "claim_translations_lang_idx" ON "claim_translations" USING btree ("lang");