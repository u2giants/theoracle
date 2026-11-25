'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useState } from 'react';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { brainGet, brainPost, brainPut, type FunctionRow } from '../../_components/brain';
import { LoadState } from '../../_components/bits';

type AccessResponse = {
  can_correct: boolean;
  is_admin: boolean;
};

type CorrectionNote = {
  id: string;
  employee_id: string;
  employee_name: string;
  function_id: string | null;
  function_name: string | null;
  page_ref: string | null;
  what_is_wrong: string;
  correction_text: string;
  status: 'open' | 'applied' | 'dismissed';
  source_id: string | null;
  reviewed_by: string | null;
  reviewed_at: string | null;
  review_note: string | null;
  created_at: string | null;
};

type PermissionEmployee = {
  employee_id: string;
  name: string;
  email: string;
  role: string;
  is_admin: boolean;
  can_correct: boolean;
};

type StatusFilter = 'all' | 'open' | 'applied' | 'dismissed';

function statusBadgeClass(status: CorrectionNote['status']): string {
  if (status === 'applied') return 'bg-green-50 text-green-700 border-green-200';
  if (status === 'dismissed') return 'bg-muted text-muted-foreground border-border';
  return 'bg-amber-50 text-amber-800 border-amber-200';
}

function statusLabel(status: CorrectionNote['status']): string {
  if (status === 'applied') return 'Applied to map';
  if (status === 'dismissed') return 'Dismissed';
  return 'Open';
}

function NoteRow({
  note,
  isAdmin,
  busyId,
  onApply,
  onDismiss,
}: {
  note: CorrectionNote;
  isAdmin: boolean;
  busyId: string | null;
  onApply: (noteId: string, reviewNote: string) => void;
  onDismiss: (noteId: string, reviewNote: string) => void;
}) {
  const [reviewNote, setReviewNote] = useState(note.review_note ?? '');
  const busy = busyId === note.id;

  return (
    <div
      data-testid="correction-note-row"
      data-status={note.status}
      className="space-y-2 rounded border p-3"
    >
      <div className="flex flex-wrap items-center justify-between gap-2">
        <div className="flex flex-wrap items-center gap-2 text-sm font-medium">
          <span>{note.what_is_wrong}</span>
          <span
            className={`rounded border px-1.5 py-0.5 text-xs font-normal ${statusBadgeClass(note.status)}`}
          >
            {statusLabel(note.status)}
          </span>
        </div>
        <span className="text-xs text-muted-foreground">
          {note.function_name ?? 'Company-wide'} ·{' '}
          {note.created_at ? note.created_at.slice(0, 10) : '—'}
        </span>
      </div>

      <p className="whitespace-pre-wrap text-sm text-foreground">{note.correction_text}</p>

      <div className="flex flex-wrap items-center gap-3 text-xs text-muted-foreground">
        {isAdmin && note.employee_name && <span>Submitted by {note.employee_name}</span>}
        {note.page_ref && <span>From: {note.page_ref}</span>}
        {note.source_id && (
          <Link href={`/map/source/${encodeURIComponent(note.source_id)}`} className="underline">
            View applied source
          </Link>
        )}
      </div>

      {note.review_note && note.status !== 'open' && (
        <p className="text-xs text-muted-foreground">Review note: {note.review_note}</p>
      )}

      {isAdmin && note.status === 'open' && (
        <div className="flex flex-wrap items-center gap-2 pt-1">
          <Input
            data-testid={`review-note-${note.id}`}
            className="h-8 max-w-xs text-xs"
            placeholder="Optional note for reviewer"
            value={reviewNote}
            onChange={(event) => setReviewNote(event.target.value)}
            disabled={busy}
          />
          <Button
            data-testid={`apply-note-${note.id}`}
            size="sm"
            disabled={busy}
            onClick={() => onApply(note.id, reviewNote)}
          >
            {busy ? 'Working…' : 'Apply to map'}
          </Button>
          <Button
            data-testid={`dismiss-note-${note.id}`}
            size="sm"
            variant="outline"
            disabled={busy}
            onClick={() => onDismiss(note.id, reviewNote)}
          >
            Dismiss
          </Button>
        </div>
      )}
    </div>
  );
}

export function CorrectionsClient({
  isAdmin,
  initialFunctionRef,
  initialPageRef,
}: {
  isAdmin: boolean;
  initialFunctionRef: string;
  initialPageRef: string;
}) {
  const [access, setAccess] = useState<AccessResponse | null>(null);
  const [functions, setFunctions] = useState<FunctionRow[]>([]);
  const [notes, setNotes] = useState<CorrectionNote[]>([]);
  const [employees, setEmployees] = useState<PermissionEmployee[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [functionId, setFunctionId] = useState('');
  const [whatIsWrong, setWhatIsWrong] = useState('');
  const [correctionText, setCorrectionText] = useState('');
  const [submitting, setSubmitting] = useState(false);
  const [submitSuccess, setSubmitSuccess] = useState<string | null>(null);
  const [submitError, setSubmitError] = useState<string | null>(null);

  const [statusFilter, setStatusFilter] = useState<StatusFilter>('all');
  const [busyNoteId, setBusyNoteId] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);

  const [permissionsOpen, setPermissionsOpen] = useState(false);
  const [employeeQuery, setEmployeeQuery] = useState('');
  const [busyEmployeeId, setBusyEmployeeId] = useState<string | null>(null);
  const [permError, setPermError] = useState<string | null>(null);

  const loadAll = useCallback(async () => {
    try {
      const accessBody = await brainGet<AccessResponse>('corrections/access');
      setAccess(accessBody);
      const allowed = accessBody.can_correct || accessBody.is_admin || isAdmin;
      if (!allowed) {
        setError(null);
        return;
      }

      const [fnBody, notesBody, permsBody] = await Promise.all([
        brainGet<{ functions: FunctionRow[] }>('functions').catch(() => ({
          functions: [] as FunctionRow[],
        })),
        brainGet<{ notes: CorrectionNote[] }>('corrections/notes'),
        accessBody.is_admin || isAdmin
          ? brainGet<{ employees: PermissionEmployee[] }>('corrections/permissions').catch(() => ({
              employees: [] as PermissionEmployee[],
            }))
          : Promise.resolve({ employees: [] as PermissionEmployee[] }),
      ]);

      const activeFunctions = fnBody.functions.filter((fn) => fn.active);
      setFunctions(activeFunctions);
      setNotes(notesBody.notes);
      setEmployees(permsBody.employees);
      setFunctionId((current) => {
        if (current || !initialFunctionRef) return current;
        const matched = activeFunctions.find(
          (fn) => fn.key === initialFunctionRef || fn.id === initialFunctionRef,
        );
        return matched ? matched.id : current;
      });
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'failed to load corrections');
    } finally {
      setLoading(false);
    }
  }, [initialFunctionRef, isAdmin]);

  useEffect(() => {
    async function load() {
      await loadAll();
    }
    void load();
  }, [loadAll]);

  async function handleSubmit(event: React.FormEvent) {
    event.preventDefault();
    setSubmitError(null);
    setSubmitSuccess(null);
    const wrong = whatIsWrong.trim();
    const text = correctionText.trim();
    if (!wrong) {
      setSubmitError('Please describe what appears wrong on the map.');
      return;
    }
    if (!text) {
      setSubmitError('Please enter the correct details.');
      return;
    }

    setSubmitting(true);
    try {
      await brainPost<{ note: CorrectionNote }>('corrections/notes', {
        what_is_wrong: wrong,
        correction_text: text,
        function_id: functionId || null,
        page_ref: initialPageRef.trim() || null,
      });
      setWhatIsWrong('');
      setCorrectionText('');
      setSubmitSuccess('Correction submitted. An administrator will review and apply it to the map.');
      await loadAll();
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : 'submit failed');
    } finally {
      setSubmitting(false);
    }
  }

  async function handleApply(noteId: string, reviewNote: string) {
    setBusyNoteId(noteId);
    setActionError(null);
    try {
      await brainPost(`corrections/notes/${encodeURIComponent(noteId)}/apply`, {
        review_note: reviewNote.trim() || null,
      });
      await loadAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'apply failed');
    } finally {
      setBusyNoteId(null);
    }
  }

  async function handleDismiss(noteId: string, reviewNote: string) {
    setBusyNoteId(noteId);
    setActionError(null);
    try {
      await brainPost(`corrections/notes/${encodeURIComponent(noteId)}/dismiss`, {
        review_note: reviewNote.trim() || null,
      });
      await loadAll();
    } catch (err) {
      setActionError(err instanceof Error ? err.message : 'dismiss failed');
    } finally {
      setBusyNoteId(null);
    }
  }

  async function toggleEmployeeAccess(employee: PermissionEmployee) {
    setBusyEmployeeId(employee.employee_id);
    setPermError(null);
    const nextValue = !employee.can_correct;
    try {
      await brainPut(`corrections/permissions/${encodeURIComponent(employee.employee_id)}`, {
        can_correct: nextValue,
      });
      setEmployees((prev) =>
        prev.map((row) =>
          row.employee_id === employee.employee_id ? { ...row, can_correct: nextValue } : row,
        ),
      );
    } catch (err) {
      setPermError(err instanceof Error ? err.message : 'permission update failed');
    } finally {
      setBusyEmployeeId(null);
    }
  }

  const visibleNotes = useMemo(() => {
    if (statusFilter === 'all') return notes;
    return notes.filter((n) => n.status === statusFilter);
  }, [notes, statusFilter]);

  const filteredEmployees = useMemo(() => {
    const q = employeeQuery.trim().toLowerCase();
    if (!q) return employees;
    return employees.filter(
      (e) =>
        e.name.toLowerCase().includes(q) ||
        e.email.toLowerCase().includes(q) ||
        e.role.toLowerCase().includes(q),
    );
  }, [employees, employeeQuery]);

  const enabledReviewerCount = useMemo(
    () => employees.filter((e) => e.can_correct).length,
    [employees],
  );

  if (loading || error) {
    return <LoadState error={error} loading={loading} />;
  }

  const canCorrect = Boolean(access?.can_correct || access?.is_admin || isAdmin);
  const viewerIsAdmin = Boolean(access?.is_admin || isAdmin);

  if (!canCorrect) {
    return (
      <Card data-testid="corrections-unauthorized">
        <CardHeader>
          <CardTitle className="text-base">Restricted access</CardTitle>
          <CardDescription>
            Correction submissions are currently open to designated reviewers only.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <Link href="/map" className="text-sm underline">
            Return to the Company Map
          </Link>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-6">
      <Card>
        <CardHeader>
          <CardTitle className="text-base">Submit a correction</CardTitle>
          <CardDescription>
            Describe what is inaccurate or missing on the Company Map and explain how it actually
            works.
          </CardDescription>
        </CardHeader>
        <CardContent>
          <form onSubmit={(event) => void handleSubmit(event)} className="space-y-4">
            <div className="space-y-1">
              <label className="block text-sm font-medium" htmlFor="correction-function">
                Department / area
              </label>
              <select
                id="correction-function"
                data-testid="correction-function"
                className="h-9 w-full max-w-md rounded-md border bg-background px-3 text-sm"
                value={functionId}
                onChange={(event) => setFunctionId(event.target.value)}
                disabled={submitting}
              >
                <option value="">General / Company-wide</option>
                {functions.map((fn) => (
                  <option key={fn.id} value={fn.id}>
                    {fn.name}
                  </option>
                ))}
              </select>
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium" htmlFor="correction-what-wrong">
                What is wrong?
              </label>
              <Input
                id="correction-what-wrong"
                data-testid="correction-what-wrong"
                placeholder="e.g. Licensing does not approve factory audits — Compliance handles FAMA"
                value={whatIsWrong}
                onChange={(event) => setWhatIsWrong(event.target.value)}
                disabled={submitting}
                maxLength={500}
              />
            </div>

            <div className="space-y-1">
              <label className="block text-sm font-medium" htmlFor="correction-text">
                What is actually true?
              </label>
              <textarea
                id="correction-text"
                data-testid="correction-text"
                rows={5}
                className="w-full rounded-md border bg-background px-3 py-2 text-sm shadow-xs focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                placeholder="Type the accurate workflow, rule, role owner, or step-by-step process here..."
                value={correctionText}
                onChange={(event) => setCorrectionText(event.target.value)}
                disabled={submitting}
                maxLength={10000}
              />
            </div>

            {initialPageRef && (
              <p className="text-xs text-muted-foreground">Referenced page: {initialPageRef}</p>
            )}

            <div className="flex flex-wrap items-center gap-3">
              <Button data-testid="correction-submit" type="submit" disabled={submitting}>
                {submitting ? 'Submitting…' : 'Submit correction'}
              </Button>
              {submitSuccess && (
                <span data-testid="correction-success" className="text-sm text-green-700">
                  {submitSuccess}
                </span>
              )}
              {submitError && (
                <span data-testid="correction-error" className="text-sm text-red-700">
                  {submitError}
                </span>
              )}
            </div>
          </form>
        </CardContent>
      </Card>

      <Card>
        <CardHeader className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <CardTitle className="text-base">
              {viewerIsAdmin ? 'All submitted corrections' : 'Your submitted corrections'}
            </CardTitle>
            <CardDescription>
              {viewerIsAdmin
                ? 'Apply verified corrections to feed them straight into the Company Map.'
                : 'Track whether your corrections are open or applied to the map.'}
            </CardDescription>
          </div>
          {viewerIsAdmin && (
            <div className="flex gap-1 text-xs">
              {(['all', 'open', 'applied', 'dismissed'] as const).map((tab) => (
                <Button
                  key={tab}
                  size="sm"
                  variant={statusFilter === tab ? 'default' : 'outline'}
                  onClick={() => setStatusFilter(tab)}
                >
                  {tab === 'all' ? 'All' : tab.charAt(0).toUpperCase() + tab.slice(1)}
                </Button>
              ))}
            </div>
          )}
        </CardHeader>
        <CardContent className="space-y-3">
          {actionError && <p className="text-sm text-red-700">{actionError}</p>}
          {visibleNotes.length === 0 ? (
            <p className="text-sm text-muted-foreground">No corrections submitted yet.</p>
          ) : (
            visibleNotes.map((note) => (
              <NoteRow
                key={note.id}
                note={note}
                isAdmin={viewerIsAdmin}
                busyId={busyNoteId}
                onApply={(id, rn) => void handleApply(id, rn)}
                onDismiss={(id, rn) => void handleDismiss(id, rn)}
              />
            ))
          )}
        </CardContent>
      </Card>

      {viewerIsAdmin && (
        <Card data-testid="corrections-permissions-card">
          <CardHeader className="flex flex-row items-center justify-between gap-2">
            <div>
              <CardTitle className="text-base">Who can submit corrections</CardTitle>
              <CardDescription>
                {enabledReviewerCount} employee{enabledReviewerCount === 1 ? '' : 's'} enabled
                (plus admins).
              </CardDescription>
            </div>
            <Button
              size="sm"
              variant="outline"
              data-testid="toggle-permissions-panel"
              onClick={() => setPermissionsOpen((v) => !v)}
            >
              {permissionsOpen ? 'Hide list' : 'Manage reviewers'}
            </Button>
          </CardHeader>
          {permissionsOpen && (
            <CardContent className="space-y-3">
              <Input
                data-testid="permissions-search"
                className="max-w-sm"
                placeholder="Search employees by name or email..."
                value={employeeQuery}
                onChange={(event) => setEmployeeQuery(event.target.value)}
              />
              {permError && <p className="text-sm text-red-700">{permError}</p>}
              <div className="divide-y rounded border">
                {filteredEmployees.map((emp) => {
                  const busy = busyEmployeeId === emp.employee_id;
                  return (
                    <div
                      key={emp.employee_id}
                      className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-sm"
                    >
                      <div>
                        <span className="font-medium">{emp.name || emp.email}</span>
                        <span className="ml-2 text-xs text-muted-foreground">
                          {emp.email}
                          {emp.role ? ` · ${emp.role}` : ''}
                        </span>
                      </div>
                      {emp.is_admin ? (
                        <span className="rounded bg-muted px-2 py-1 text-xs text-muted-foreground">
                          Admin (always enabled)
                        </span>
                      ) : (
                        <Button
                          size="sm"
                          variant={emp.can_correct ? 'default' : 'outline'}
                          disabled={busy}
                          data-testid={`perm-toggle-${emp.employee_id}`}
                          onClick={() => void toggleEmployeeAccess(emp)}
                        >
                          {busy ? 'Saving…' : emp.can_correct ? 'Enabled' : 'Off'}
                        </Button>
                      )}
                    </div>
                  );
                })}
              </div>
            </CardContent>
          )}
        </Card>
      )}
    </div>
  );
}
