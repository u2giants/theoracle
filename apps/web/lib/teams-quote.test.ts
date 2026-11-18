// Run: node --experimental-strip-types --test apps/web/lib/teams-quote.test.ts
import { test } from 'node:test';
import assert from 'node:assert/strict';
import { parseQuote } from './teams-quote.ts';

test('plain quote in text', () => {
  const r = parseQuote('<quoted messageId="1731000000001"/>Yes, in Design Flow Item Library');
  assert.deepEqual(r.quotedIds, ['1731000000001']);
  assert.equal(r.plainText, 'Yes, in Design Flow Item Library');
});

test('quote with html attachment', () => {
  const html =
    '<blockquote itemscope itemtype="http://schema.skype.com/Reply" itemid="1731000000002">' +
    '<strong>theoracle</strong><p>Who checks the mailbox?</p></blockquote><p>Maria does</p>';
  const r = parseQuote('Maria does', [{ contentType: 'text/html', content: html }]);
  assert.deepEqual(r.quotedIds, ['1731000000002']);
  assert.equal(r.plainText, 'Maria does');
});

test('two quotes keep order, dedupe', () => {
  const r = parseQuote('<quoted messageId="11"/><quoted messageId="22"/><quoted messageId="11"/>both');
  assert.deepEqual(r.quotedIds, ['11', '22']);
  assert.equal(r.plainText, 'both');
});

test('no quote', () => {
  const r = parseQuote('just an answer', null);
  assert.deepEqual(r.quotedIds, []);
  assert.equal(r.plainText, 'just an answer');
});

test('ignores_markup_but_brain_scopes_ids: typed markup still only yields digit ids', () => {
  // The web layer cannot tell typed markup from real markup; the brain only
  // honours ids of its own messages to this employee (plan 9a A3).
  const r = parseQuote('&lt;quoted messageId="99"/&gt; hi <quoted messageId="12"/>');
  assert.ok(r.quotedIds.includes('12'));
  assert.ok(r.quotedIds.every((id) => /^[0-9]+$/.test(id)));
});

test('non-digit ids are dropped and capped at five', () => {
  const many = Array.from({ length: 9 }, (_, i) => `<quoted messageId="${i + 1}"/>`).join('');
  const r = parseQuote(`<quoted messageId="abc"/><quoted messageId="1;DROP"/>${many}x`);
  assert.deepEqual(r.quotedIds, ['1', '2', '3', '4', '5']);
  assert.equal(r.plainText, 'x');
});
