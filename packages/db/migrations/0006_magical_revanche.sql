CREATE TABLE "model_capabilities" (
	"id" text PRIMARY KEY NOT NULL,
	"provider" text NOT NULL,
	"display_name" text NOT NULL,
	"context_length" integer,
	"max_output_tokens" integer,
	"prompt_per_1m_usd" numeric,
	"completion_per_1m_usd" numeric,
	"vision" boolean DEFAULT false NOT NULL,
	"pdf" boolean DEFAULT false NOT NULL,
	"thinking" boolean DEFAULT false NOT NULL,
	"structured_outputs" boolean DEFAULT false NOT NULL,
	"tool_calling" boolean DEFAULT false NOT NULL,
	"prompt_caching" boolean DEFAULT false NOT NULL,
	"output_cap" boolean DEFAULT false NOT NULL,
	"knowledge_cutoff" date,
	"source" text NOT NULL,
	"refreshed_at" timestamp with time zone DEFAULT now() NOT NULL
);
--> statement-breakpoint
CREATE TABLE "typing_indicators" (
	"channel_id" uuid NOT NULL,
	"employee_id" uuid NOT NULL,
	"expires_at" timestamp with time zone NOT NULL,
	"updated_at" timestamp DEFAULT now() NOT NULL,
	CONSTRAINT "typing_indicators_channel_id_employee_id_pk" PRIMARY KEY("channel_id","employee_id")
);
--> statement-breakpoint
ALTER TABLE "employees" ALTER COLUMN "department" DROP NOT NULL;--> statement-breakpoint
ALTER TABLE "employees" ADD COLUMN "departments" text[] DEFAULT '{}' NOT NULL;--> statement-breakpoint
ALTER TABLE "entity_proposals" ADD COLUMN "proposal_count" integer DEFAULT 1 NOT NULL;--> statement-breakpoint
ALTER TABLE "typing_indicators" ADD CONSTRAINT "typing_indicators_channel_id_channels_id_fk" FOREIGN KEY ("channel_id") REFERENCES "public"."channels"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
ALTER TABLE "typing_indicators" ADD CONSTRAINT "typing_indicators_employee_id_employees_id_fk" FOREIGN KEY ("employee_id") REFERENCES "public"."employees"("id") ON DELETE cascade ON UPDATE no action;--> statement-breakpoint
CREATE INDEX "model_capabilities_provider_idx" ON "model_capabilities" USING btree ("provider");--> statement-breakpoint
CREATE INDEX "model_capabilities_refreshed_idx" ON "model_capabilities" USING btree ("refreshed_at");--> statement-breakpoint
CREATE INDEX "typing_indicators_expires_at_idx" ON "typing_indicators" USING btree ("expires_at");