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
  const [presence, setPresence] = useState<PresenceState>({});
  const [showUpload, setShowUpload] = useState(false);
  const presenceChannel = useRef<RealtimeChannel | null>(null);
  const scrollRef = useRef<HTMLDivElement>(null);
  const supabase = useMemo(() => createSupabaseBrowserClient(), []);

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
    try {
      const { data, error } = await supabase
        .from('messages')
        .insert({
          channel_id: channel.id,
          employee_id: me.id,
          role: 'user',
          content: draft,
        })
        .select()
        .single();
      if (error) throw error;
      // Optimistic — the realtime feed will resolve duplicates by id.
      setMessages((cur) => [
        ...cur,
        {
          id: data.id,
          channelId: channel.id,
          employeeId: me.id,
          role: 'user',
          content: draft,
          createdAt: data.created_at,
          authorName: me.name,
        },
      ]);
      setDraft('');
      broadcastTyping(false);

      // Phase 3: if the message mentions @oracle, fire the chat route.
      if (/^\s*(@oracle|oracle,)/i.test(draft)) {
        void fetchOracleReply(channel.id);
      }
    } catch (err) {
      console.error('[send] failed', err);
      alert('Send failed. Are you sure you are in this channel?');
    } finally {
      setSending(false);
    }
  }

  async function fetchOracleReply(channelId: string) {
    try {
      await fetch('/api/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ channelId }),
      });
      // The Oracle's response is persisted server-side; realtime will deliver it.
      router.refresh();
    } catch (err) {
      console.error('[oracle] failed', err);
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

  return (
    <div className="flex h-full flex-col">
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
        </div>
      </div>

      {showUpload ? (
        <div className="border-t bg-muted/30 px-6 py-4">
          <DocumentUpload
            channelId={channel.id}
            employeeId={me.id}
            onDone={() => {
              setShowUpload(false);
              router.refresh();
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
              placeholder="Type a message. Use @oracle to ask the Oracle."
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
