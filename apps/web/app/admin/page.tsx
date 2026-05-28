// /admin redirects to /admin/employees.
//
// Historical note: /admin used to BE the Employees page. When the admin
// area grew more sub-pages, every other one got a real sub-route while
// Employees stayed at the bare root — which was confusing in the nav
// (clicking "Employees" landed you on /admin, not /admin/employees).
// Moved to /admin/employees on 2026-05-28; this redirect keeps any
// bookmarks and pre-move deep links working.

import { redirect } from 'next/navigation';

export default function AdminIndexPage(): never {
  redirect('/admin/employees');
}
