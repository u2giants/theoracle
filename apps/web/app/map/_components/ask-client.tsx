'use client';

import Link from 'next/link';
import { Fragment, useState, type FormEvent, type ReactNode } from 'react';
import ReactMarkdown from 'react-markdown';
import { Button } from '@/components/ui/button';
import { brainPost, sourceHref } from './brain';

type Citation = {
  source_id: string;
  title: string;
  chunk_id: string | null;
  quote: string;
  locator: Record<string, unknown> | null;
};

type Answer = {
  answer_md: string;
  citations: Citation[];
  mode_used: string;
  entities: { id: string; name?: string; canonical_name?: string; type?: string }[];
  communities: { id: string; level: number; title: string }[];
  unknowns?: string[];
};

type Turn = { question: string; answer: Answer | null; error: string | null };

// Turn every [n] marker in rendered text into a link to the cited passage.
function withCitationLinks(children: ReactNode, citations: Citation[]): ReactNode {
  if (typeof children === 'string') {
    const parts = children.split(/(\[\d+\])/g);
    return parts.map((part, index) => {
      const match = /^\[(\d+)\]$/.exec(part);
      const cite = match ? citations[Number(match[1]) - 1] : undefined;
      if (!match || !cite) return <Fragment key={index}>{part}</Fragment>;
      return (
        <Link
          key={index}
          href={sourceHref(cite.source_id, cite.chunk_id)}
          data-testid="citation-marker"
          title={`${cite.title}: “${cite.quote}”`}
          className="text-blue-700 underline"
        >
          {part}
        </Link>
      );
    });
  }
  if (Array.isArray(children)) {
    return children.map((child, index) => (
      <Fragment key={index}>{withCitationLinks(child, citations)}</Fragment>
    ));
  }
  return children;
}

function AnswerView({ answer }: { answer: Answer }) {
  const link = (children: ReactNode) => withCitationLinks(children, answer.citations);
  return (
    <div className="space-y-3" data-testid="answer">
      <div className="space-y-2 text-sm [&_ol]:list-decimal [&_ol]:pl-5 [&_ul]:list-disc [&_ul]:pl-5">
        <ReactMarkdown
          components={{
            p: ({ children }) => <p>{link(children)}</p>,
            li: ({ children }) => <li>{link(children)}</li>,
          }}
        >
          {answer.answer_md}
        </ReactMarkdown>
      </div>
      {answer.citations.length > 0 && (
        <ol className="list-decimal space-y-1 pl-5 text-xs">
          {answer.citations.map((cite, index) => (
            <li key={`${cite.source_id}-${index}`}>
              <Link href={sourceHref(cite.source_id, cite.chunk_id)} className="underline">
                {cite.title}
              </Link>
              : “{cite.quote}”
            </li>
          ))}
        </ol>
      )}
      <div className="text-xs text-muted-foreground" data-testid="answer-meta">
        <p>Mode used: {answer.mode_used}</p>
        {answer.entities.length > 0 && (
          <p>
            Consulted:{' '}
            {answer.entities.map((entity, index) => (
              <Fragment key={entity.id}>
                {index > 0 && ', '}
                <Link href={`/map/entity/${entity.id}`} className="underline">
                  {entity.name ?? entity.canonical_name ?? entity.id}
                </Link>
              </Fragment>
            ))}
          </p>
        )}
        {answer.communities.length > 0 && (
          <p>
            Areas consulted:{' '}
            {answer.communities.map((community, index) => (
              <Fragment key={community.id}>
                {index > 0 && ', '}
                <Link href={`/map/community/${community.id}`} className="underline">
                  {community.title}
                </Link>
              </Fragment>
            ))}
          </p>
        )}
      </div>
    </div>
  );
}

export function AskClient() {
  const [question, setQuestion] = useState('');
  const [turns, setTurns] = useState<Turn[]>([]);
  const [busy, setBusy] = useState(false);

  async function ask(event: FormEvent) {
    event.preventDefault();
    const text = question.trim();
    if (!text || busy) return;
    setBusy(true);
    setQuestion('');
    const history = turns
      .filter((turn) => turn.answer)
      .flatMap((turn) => [
        { role: 'user', content: turn.question },
        { role: 'assistant', content: turn.answer?.answer_md ?? '' },
      ])
      .slice(-6);
    setTurns((prev) => [...prev, { question: text, answer: null, error: null }]);
    try {
      const answer = await brainPost<Answer>('answer', { question: text, mode: 'auto', history });
      setTurns((prev) =>
        prev.map((turn, index) => (index === prev.length - 1 ? { ...turn, answer } : turn)),
      );
    } catch (err) {
      const message = err instanceof Error ? err.message : 'answer failed';
      setTurns((prev) =>
        prev.map((turn, index) => (index === prev.length - 1 ? { ...turn, error: message } : turn)),
      );
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="mx-auto max-w-3xl space-y-4 p-6">
      <Link href="/map" className="text-sm underline">
        ← Company Map
      </Link>
      <h1 className="text-2xl font-semibold">Ask the Company Map</h1>
      <div className="space-y-6">
        {turns.map((turn, index) => (
          <div key={index} className="space-y-2">
            <p className="rounded bg-muted px-3 py-2 text-sm font-medium">{turn.question}</p>
            {turn.answer && <AnswerView answer={turn.answer} />}
            {turn.error && <p className="text-sm text-red-700">Could not answer: {turn.error}</p>}
            {!turn.answer && !turn.error && (
              <p className="text-sm text-muted-foreground">Thinking…</p>
            )}
          </div>
        ))}
      </div>
      <form onSubmit={ask} className="space-y-2">
        <textarea
          value={question}
          onChange={(event) => setQuestion(event.target.value)}
          rows={3}
          placeholder="For example: Where does licensing approval stall and why?"
          className="w-full rounded border p-2 text-sm"
          aria-label="Question"
        />
        <Button type="submit" disabled={busy || !question.trim()}>
          {busy ? 'Answering…' : 'Ask'}
        </Button>
      </form>
    </main>
  );
}
