'use client';

import * as React from 'react';
import { useEffect, useMemo, useRef, useState } from 'react';
import { useRouter } from 'next/navigation';
import { Send, Users, Paperclip } from 'lucide-react';
import { createSupabaseBrowserClient } from '@oracle/auth/client';
import type { RealtimeChannel } from '@supabase/supabase-js';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { cn } from '@/lib/utils';
import { DocumentUpload } from './document-upload';

type ChatMessage = {
  id: string;
  channelId: string;
  employeeId: string | null;
  role: 'user' | 'assistant' | 'system';
  content: string;
  createdAt: Date | string;
  authorName: string | null;
};

type Participant = {
  id: string;
  name: string;
  role: string;
};

type Channel = {
  id: string;
  name: string | null;
  isGroupChat: boolean;
  status: 'active' | 'archived' | 'locked';
};

type Me = { id: string; name: string };

type PresenceState = Record<string, Array<{ name: string; typing?: boolean }>>;

export function ChannelChat({
  channel,
  me,
  initialMessages,
  participants,
}: {
  channel: Channel;
  me: Me;
  initialMessages: ChatMessage[];
  participants: Participant[];
}) {
  const router = useRouter();
  const [messages, setMessages] = useState<ChatMessage[]>(initialMessages);
  const [draft, setDraft] = useState('');
  const [sending, setSending] = useState(false);
  const [oracleThinking, setOracleThinking] = useState(false);
  const [presence, setPresence] = useState<PresenceState>({});
  const [showUpload, setShowUpload] = useState(false);
  const [droppedFile, setDroppedFile] = useState<File | null>(null);
  const [isDragging, setIsDragging] = useState(false);
  const presenceChannel = useRef<RealtimeChannel | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);

  // Merge server-side message updates (triggered by router.refresh()) into
  // local state. useState(initialMessages) only fires on mount; subsequent
  // prop changes from router.refresh() are ignored by React unless we sync
  // them here. We merge by ID so optimistic updates and realtime messages
  // are never clobbered, and we re-sort chronologically.
  useEffect(() => {
    setMessages((cur) => {
      const knownIds = new Set(cur.map((m) => m.id));
      const incoming = initialMessages.filter((m) => !knownIds.has(m.id));
      if (incoming.length === 0) return cur; // nothing new — skip re-render
      const merged = [...cur, ...incoming];
      merged.sort(
        (a, b) =>
          new Date(a.createdAt).getTime() - new Date(b.createdAt).getTime(),
      );
      return merged;
    });
  }, [initialMessages]);

  // Auto-scroll on new messages.
  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight });
  }, [messages]);

  // Realtime: subscribe to inserts on messages filtered by channel_id, and
  // presence (who's online + typing) on a sibling channel.
  useEffect(() => {
    const inserts = supabase
      .channel(`messages:channel=${channel.id}`)
      .on(
        'postgres_changes',
        {
          event: 'INSERT',
          schema: 'public',
          table: 'messages',
          filter: `channel_id=eq.${channel.id}`,
        },
        async (payload) => {
          const row = payload.new as {
            id: string;
            channel_id: string;
            employee_id: string | null;
            role: 'user' | 'assistant' | 'system';
            content: string;
            created_at: string;
          };
          // Resolve author name client-side (small targeted query, RLS-gated).
          let authorName: string | null = null;
          if (row.employee_id) {
            const { data } = await supabase
              .from('employees')
              .select('name')
              .eq('id', row.employee_id)
              .maybeSingle();
            authorName = (data?.name as string | undefined) ?? null;
          }
          setMessages((cur) => {
            if (cur.some((m) => m.id === row.id)) return cur; // de-dup our own insert
            return [
              ...cur,
              {
                id: row.id,
                channelId: row.channel_id,
                employeeId: row.employee_id,
                role: row.role,
                content: row.content,
                createdAt: row.created_at,
                authorName,
              },
            ];
          });
        },
      )
      .subscribe();

    const presenceCh = supabase.channel(`presence:channel=${channel.id}`, {
      config: { presence: { key: me.id } },
    });
    presenceChannel.current = presenceCh;
    presenceCh
      .on('presence', { event: 'sync' }, () => {
        setPresence(presenceCh.presenceState() as unknown as PresenceState);
      })
      .subscribe(async (status) => {
        if (status === 'SUBSCRIBED') {
          await presenceCh.track({ name: me.name, typing: false });
        }
      });

    return () => {
      void supabase.removeChannel(inserts);
      void supabase.removeChannel(presenceCh);
    };
  }, [channel.id, me.id, me.name, supabase]);

  // Typing indicator with debounce.
  const typingTimer = useRef<ReturnType<typeof setTimeout> | null>(null);
  function broadcastTyping(typing: boolean) {
    if (!presenceChannel.current) return;
    void presenceChannel.current.track({ name: me.name, typing });
  }

  async function sendMessage(e: React.FormEvent) {
    e.preventDefault();
    if (!draft.trim() || sending) return;
    setSending(true);
    const snapshot = draft;
    setDraft(''); // optimistic clear
    try {
      // Route through the server API so the insert uses the service-role
      // connection (DIRECT_URL) and server-side session validation — this
      // sidesteps any browser-client Supabase auth issues.
      const res = await fetch('/api/messages', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channelId: channel.id, content: snapshot }),
      });

      if (!res.ok) {
        const errBody = await res.text();
        console.error('[send] api/messages failed', res.status, errBody);
        throw new Error(`${res.status}: ${errBody}`);
      }

      const data = (await res.json()) as {
        id: string;
        channelId: string;
        employeeId: string;
        role: 'user' | 'assistant' | 'system';
        content: string;
        createdAt: string;
      };

      // Optimistic add — the realtime feed will de-dup by id.
      setMessages((cur) => {
        if (cur.some((m) => m.id === data.id)) return cur;
        return [
          ...cur,
          {
            id: data.id,
            channelId: channel.id,
            employeeId: me.id,
            role: 'user',
            content: snapshot,
            createdAt: data.createdAt,
            authorName: me.name,
          },
        ];
      });
      broadcastTyping(false);

      // Phase 3: trigger Oracle reply.
      // DMs — Oracle is the only other participant, so reply to every message.
      // Group chats — only reply when the message directly addresses @oracle.
      const oracleMentioned = /^\s*(@oracle\b|oracle,)/i.test(snapshot);
      if (!channel.isGroupChat || oracleMentioned) {
        setOracleThinking(true);
        void fetchOracleReply(channel.id);
      }
    } catch (err) {
      console.error('[send] failed', err);
      setDraft(snapshot); // restore on error
      alert('Send failed — check the browser console for details.');
    } finally {
      setSending(false);
    }
  }

  async function fetchOracleReply(channelId: string) {
    try {
      const res = await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channelId }),
      });
      if (!res.ok) {
        const body = await res.text();
        console.error('[oracle] /api/chat failed', res.status, body);
        return;
      }
      const data = await res.json();
      console.log('[oracle] reply inserted', data);
      // Refresh so the server re-fetches messages; the useEffect sync will
      // merge the new assistant message into local state.
      router.refresh();
    } catch (err) {
      console.error('[oracle] fetch threw', err);
    } finally {
      setOracleThinking(false);
    }
  }

  const onlineNames = useMemo(() => {
    const names = new Set<string>();
    Object.values(presence).forEach((arr) =>
      arr.forEach((p) => names.add(p.name)),
    );
    return names;
  }, [presence]);

  const typingNames = useMemo(() => {
    const names: string[] = [];
    Object.entries(presence).forEach(([employeeId, arr]) => {
      if (employeeId === me.id) return;
      arr.forEach((p) => {
        if (p.typing) names.push(p.name);
      });
    });
    return names;
  }, [presence, me.id]);

  function handleDragOver(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (e.dataTransfer.types.includes('Files')) setIsDragging(true);
  }
  function handleDragLeave(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    // Only clear when leaving the root container, not a child.
    if (!e.currentTarget.contains(e.relatedTarget as Node)) setIsDragging(false);
  }
  function handleDrop(e: React.DragEvent) {
    e.preventDefault();
    e.stopPropagation();
    setIsDragging(false);
    const file = e.dataTransfer.files[0];
    if (file) {
      setDroppedFile(file);
      setShowUpload(true);
    }
  }

  return (
    <div
      className="relative flex h-full flex-col"
      onDragOver={handleDragOver}
      onDragLeave={handleDragLeave}
      onDrop={handleDrop}
    >
      {isDragging && (
        <div className="pointer-events-none absolute inset-0 z-20 flex items-center justify-center bg-primary/10">
          <div className="rounded-xl border-2 border-dashed border-primary bg-background/90 px-10 py-8 text-center shadow-lg">
            <Paperclip className="mx-auto mb-3 size-8 text-primary" />
            <p className="text-sm font-semibold text-primary">Drop to attach</p>
          </div>
        </div>
      )}
      <header className="border-b px-6 py-4">
        <div className="flex items-center justify-between">
          <div>
            <h1 className="text-lg font-semibold">
              {channel.name ?? (channel.isGroupChat ? 'Group chat' : 'Direct message')}
            </h1>
            <p className="text-xs text-muted-foreground">
              {channel.isGroupChat ? 'group' : 'direct'} ·{' '}
              {participants.map((p) => p.name).join(', ')}
            </p>
          </div>
          <div className="flex items-center gap-3 text-xs text-muted-foreground">
            <Users className="size-4" />
            <span>
              {onlineNames.size}/{participants.length} online
            </span>
          </div>
        </div>
      </header>

      <div ref={scrollRef} className="flex-1 overflow-y-auto px-6 py-4">
        <div className="mx-auto max-w-3xl space-y-3">
          {messages.length === 0 ? (
            <p className="text-sm text-muted-foreground">
              No messages yet. Say hi.
            </p>
          ) : null}
          {messages.map((m) => (
            <MessageRow key={m.id} message={m} isMine={m.employeeId === me.id} />
          ))}
          {oracleThinking && <OracleThinkingBubble />}
        </div>
      </div>

      {showUpload ? (
        <div className="border-t bg-muted/30 px-6 py-4">
          <DocumentUpload
            channelId={channel.id}
            employeeId={me.id}
            initialFile={droppedFile}
            onDone={(msg) => {
              setDroppedFile(null);
              // Add the attachment message to state immediately — don't wait
              // for realtime or router.refresh() to pick it up.
              if (msg) {
                setMessages((cur) => {
                  if (cur.some((m) => m.id === msg.id)) return cur;
                  return [
                    ...cur,
                    {
                      id: msg.id,
                      channelId: msg.channelId,
                      employeeId: msg.employeeId,
                      role: msg.role as 'user' | 'assistant' | 'system',
                      content: msg.content,
                      createdAt: msg.createdAt,
                      authorName: msg.authorName,
                    },
                  ];
                });
              }
              setShowUpload(false);
              router.refresh();
              // Trigger Oracle reply after an upload — same rules as regular messages:
              // DMs always trigger; group chats only when caption addresses @oracle.
              const captionText = msg?.content ?? '';
              const oracleMentioned = /^\s*(@oracle\b|oracle,)/i.test(captionText);
              if (!channel.isGroupChat || oracleMentioned) {
                setOracleThinking(true);
                void fetchOracleReply(channel.id);
              }
            }}
          />
        </div>
      ) : null}

      <footer className="border-t px-6 py-4">
        <div className="mx-auto max-w-3xl">
          {typingNames.length > 0 ? (
            <p className="mb-2 text-xs text-muted-foreground">
              {typingNames.join(', ')} {typingNames.length === 1 ? 'is' : 'are'} typing…
            </p>
          ) : null}
          <form onSubmit={sendMessage} className="flex items-center gap-2">
            <Button
              type="button"
              variant="ghost"
              size="icon"
              onClick={() => setShowUpload((s) => !s)}
              aria-label="Attach document"
            >
              <Paperclip className="size-4" />
            </Button>
            <Input
              value={draft}
              onChange={(e) => {
                setDraft(e.target.value);
                broadcastTyping(true);
                if (typingTimer.current) clearTimeout(typingTimer.current);
                typingTimer.current = setTimeout(() => broadcastTyping(false), 2000);
              }}
              placeholder={
                channel.isGroupChat
                  ? 'Type a message. Use @oracle to ask the Oracle.'
                  : 'Type a message…'
              }
              disabled={sending}
            />
            <Button type="submit" disabled={!draft.trim() || sending}>
              <Send className="size-4" />
              <span className="sr-only">Send</span>
            </Button>
          </form>
        </div>
      </footer>
    </div>
  );
}

function OracleThinkingBubble() {
  return (
    <div className="flex flex-col gap-1 items-start">
      <div className="text-xs text-muted-foreground">Oracle</div>
      <div className="rounded-lg bg-blue-50 px-4 py-3">
        <span className="inline-flex items-center gap-1">
          {[0, 1, 2].map((i) => (
            <span
              key={i}
              className="inline-block h-2 w-2 rounded-full bg-blue-400 animate-bounce"
              style={{ animationDelay: `${i * 150}ms` }}
            />
          ))}
        </span>
      </div>
    </div>
  );
}

function MessageRow({ message, isMine }: { message: ChatMessage; isMine: boolean }) {
  const isOracle = message.role === 'assistant';
  return (
    <div
      className={cn(
        'flex flex-col gap-1',
        isMine ? 'items-end' : 'items-start',
      )}
    >
      <div className="text-xs text-muted-foreground">
        {isOracle ? 'Oracle' : message.authorName ?? 'Unknown'} ·{' '}
        {new Date(message.createdAt).toLocaleTimeString()}
      </div>
      <div
        className={cn(
          'max-w-[80%] rounded-lg px-3 py-2 text-sm',
          isOracle
            ? 'bg-blue-50 text-blue-950'
            : isMine
              ? 'bg-primary text-primary-foreground'
              : 'bg-muted',
        )}
      >
        {message.content}
      </div>
    </div>
  );
}
