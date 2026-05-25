ALTER TABLE "claims" ADD COLUMN "candidate_hash" varchar(64);--> statement-breakpoint
CREATE INDEX "claims_candidate_hash_idx" ON "claims" USING btree ("candidate_hash");