import 'dotenv/config';
import type { Config } from 'drizzle-kit';

// DIRECT_URL is the unpooled connection for migrations (spec 3.4).
const url = process.env.DIRECT_URL ?? process.env.DATABASE_URL ?? '';

export default {
  schema: './src/schema.ts',
  out: './migrations',
  dialect: 'postgresql',
  dbCredentials: {
    url,
  },
  strict: true,
  verbose: true,
} satisfies Config;
