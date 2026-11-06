// Drizzle schema for the public tables the live system still uses:
// employees, employee_identities, employee_directory_roles, departments,
// employee_departments.
// The Company Map lives in the `cmap` schema and is owned by apps/brain.
// IMPORTANT: do not change column names without coordinating raw SQL migrations.

import {
  boolean,
  index,
  pgEnum,
  pgTable,
  primaryKey,
  text,
  timestamp,
  uniqueIndex,
  uuid,
  varchar,
} from 'drizzle-orm/pg-core';
import { DEPARTMENTS } from '@oracle/shared';

// Org-unit departments. Source list lives in shared/src/domains.ts. The
// `departments` metadata table (defined below) carries per-row display label,
// description, and optional head_employee_id.
export const departmentEnum = pgEnum('department', DEPARTMENTS);

// auth_provider includes the dev-only `magic_link_dev` stub (see DECISIONS.md).
// Production providers per spec 4.1 are microsoft / google / authentik.
export const authProviderEnum = pgEnum('auth_provider', [
  'microsoft',
  'google',
  'authentik',
  'magic_link_dev',
]);

// ---------------------------------------------------------------------------
// 6.3 Employees and Invites
// ---------------------------------------------------------------------------

export const employees = pgTable('employees', {
  id: uuid('id').primaryKey().defaultRandom(),

  // Primary contact email. NOT the auth identity — see employee_identities for
  // the (provider, auth_user_id) mappings. Kept here for display, admin contact,
  // and first-login bootstrap (matching a freshly-arrived provider email to an
  // employee row that has not yet been linked to any identity).
  email: varchar('email', { length: 320 }).notNull().unique(),

  name: varchar('name', { length: 255 }).notNull(),
  role: varchar('role', { length: 255 }).notNull(),
  // DEPRECATED: single-value legacy field. Kept for backward compat during
  // migration. Authoritative source is now `departments` (text[]).
  department: varchar('department', { length: 255 }),
  // Multi-department support. Each value is a free-text department name.
  // The Oracle retrieval layer uses these as soft RRF score hints (not filters).
  departments: text('departments').array().notNull().default([]),
  isAdmin: boolean('is_admin').default(false).notNull(),

  // Preferred content/chat language for this employee. Set manually by an admin
  // to route an employee into the "China group" ('zh-CN'). Drives retrieval
  // rendering, Brain snippet language, answer language, and the source_lang
  // stamped on claims this employee authors. Defaults to English. See china_imp.md.
  locale: varchar('locale', { length: 12 }).notNull().default('en'),

  disabledAt: timestamp('disabled_at'),
  // "Most recent login from any identity" — denormalized convenience column.
  // Per-identity last_login_at lives on employee_identities.
  lastLoginAt: timestamp('last_login_at'),
  createdAt: timestamp('created_at').defaultNow().notNull(),
});

// One employee can have many identities — a Google account, a Microsoft 365
// account, future Authentik, etc. The linker looks up by
// (auth_provider, auth_user_id) here; if no identity matches, it falls back to
// matching the verified provider email against employees.email and creates a
// new identity row attached to that employee.
export const employeeIdentities = pgTable(
  'employee_identities',
  {
    id: uuid('id').primaryKey().defaultRandom(),
    employeeId: uuid('employee_id')
      .references(() => employees.id, { onDelete: 'cascade' })
      .notNull(),
    authProvider: authProviderEnum('auth_provider').notNull(),
    // Supabase auth.users.id — globally unique across providers in Supabase.
    authUserId: uuid('auth_user_id').notNull().unique(),
    // Stable provider-side user id (Google `sub`, Microsoft `oid`). May be null
    // for the magic-link stub where there is no provider subject.
    authProviderSubject: varchar('auth_provider_subject', { length: 255 }),
    // Verified email captured AT LINK TIME. We denormalize because provider
    // emails can drift; this is the email value we accepted at first link.
    email: varchar('email', { length: 320 }).notNull(),
    linkedAt: timestamp('linked_at').defaultNow().notNull(),
    lastLoginAt: timestamp('last_login_at'),
  },
  (t) => ({
    providerEmployeeIdx: index('employee_identities_provider_employee_idx').on(
      t.authProvider,
      t.employeeId,
    ),
    employeeIdx: index('employee_identities_employee_idx').on(t.employeeId),
    emailIdx: index('employee_identities_email_idx').on(t.email),
    // One employee can have at most one identity per provider — prevents
    // accidentally double-linking the same Google account twice, for example.
    providerEmployeeUnique: uniqueIndex('employee_identities_provider_employee_unique').on(
      t.authProvider,
      t.employeeId,
    ),
  }),
);

// ---------------------------------------------------------------------------
// Departments — org units. Enum values in `department_enum`; per-row metadata
// here. `employee_departments` is the many-to-many join (one employee can
// belong to multiple departments).
// ---------------------------------------------------------------------------

export const departments = pgTable('departments', {
  id: departmentEnum('id').primaryKey(),
  // Human-facing label. Editable in /admin/departments without a migration.
  displayLabel: varchar('display_label', { length: 120 }).notNull(),
  description: text('description'),
  // Optional designated head. Used as the prioritized recipient when a
  // clarification request routes to this department; falls back to all
  // members if NULL.
  headEmployeeId: uuid('head_employee_id').references(() => employees.id, {
    onDelete: 'set null',
  }),
  createdAt: timestamp('created_at').defaultNow().notNull(),
  updatedAt: timestamp('updated_at').defaultNow().notNull(),
});

export const employeeDepartments = pgTable(
  'employee_departments',
  {
    employeeId: uuid('employee_id')
      .notNull()
      .references(() => employees.id, { onDelete: 'cascade' }),
    departmentId: departmentEnum('department_id')
      .notNull()
      .references(() => departments.id, { onDelete: 'cascade' }),
    addedAt: timestamp('added_at').defaultNow().notNull(),
  },
  (t) => [primaryKey({ columns: [t.employeeId, t.departmentId] })],
);

// DesignFlow role names per employee, mirrored read-only from the shared
// company directory by the brain `directory_sync` job (migration
// sql/15_employee_directory_roles.sql owns the DDL). Replace-only from that
// job — never hand-maintained. Oracle-only fields stay on `employees`.
export const employeeDirectoryRoles = pgTable(
  'employee_directory_roles',
  {
    employeeId: uuid('employee_id')
      .notNull()
      .references(() => employees.id, { onDelete: 'cascade' }),
    roleName: text('role_name').notNull(),
  },
  (t) => [primaryKey({ columns: [t.employeeId, t.roleName] })],
);

// Admin-managed reviewer groups for sending a claim-review question to several
// people at once. These are intentionally separate from org departments:
// departments drive permissions and routing, while groups are lightweight
// assignment lists such as "Licensor reviewers" or "Walmart SOP owners".

export type Employee = typeof employees.$inferSelect;
export type NewEmployee = typeof employees.$inferInsert;
export type EmployeeIdentity = typeof employeeIdentities.$inferSelect;
export type Department = typeof departments.$inferSelect;
export type EmployeeDepartment = typeof employeeDepartments.$inferSelect;
export type EmployeeDirectoryRole = typeof employeeDirectoryRoles.$inferSelect;
