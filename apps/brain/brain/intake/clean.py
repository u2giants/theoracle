"""Free cleaning and thread assembly (plan_pm_message_intake.md step 1.4, issue #607).

Pure functions, no network. Two stages:

1. ``html_to_text`` is format conversion (tags removed, entities decoded,
   mentions kept as their names). Its output is the stored text that quotes
   are checked against; the original stays in ``raw``.
2. Everything after that is DROP-ONLY: whole lines or whole messages are
   removed, never reworded. Every kept line is a byte-identical substring of
   the converted text (proved by tests/test_intake_clean.py).

Signatures and sign-offs are removed only by an exact allowlist of blocks
supplied by the caller (built privately from the managers' real signatures),
never by a loose pattern.
"""

from __future__ import annotations

import hashlib
import html
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any

from brain.read.chunk import count_tokens

MIN_THREAD_TOKENS = 40

# --- stage 1: format conversion -------------------------------------------

_DROP_ELEMENTS = re.compile(
    r"<(script|style|head|title|template|noscript)\b[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_HIDDEN = re.compile(
    r"<(\w+)\b[^>]*style\s*=\s*(?:\"[^\"]*display\s*:\s*none[^\"]*\"|'[^']*display\s*:\s*none[^']*')[^>]*>.*?</\1\s*>",
    re.IGNORECASE | re.DOTALL,
)
_COMMENT = re.compile(r"<!--.*?-->", re.DOTALL)
_BREAK = re.compile(r"<\s*(br|/p|/div|/li|/tr|/h[1-6])\b[^>]*>", re.IGNORECASE)
_TAG = re.compile(r"<[^>]*>")
_DATA_URI = re.compile(r"data:[\w/+.-]+;base64,[A-Za-z0-9+/=]+")
_SPACES = re.compile(r"[ \t ]+")


def html_to_text(body: str) -> str:
    """HTML to plain text: one line per block, mentions kept as names.

    Script, style and hidden elements and inline data URIs are removed whole.
    """
    s = _COMMENT.sub("", body or "")
    s = _DROP_ELEMENTS.sub("", s)
    s = _HIDDEN.sub("", s)
    s = _BREAK.sub("\n", s)
    s = _TAG.sub("", s)
    s = html.unescape(s)
    s = _DATA_URI.sub("", s)
    lines = [_SPACES.sub(" ", ln).strip() for ln in s.replace("\r\n", "\n").split("\n")]
    out: list[str] = []
    for ln in lines:
        if ln or (out and out[-1]):
            out.append(ln)
    return "\n".join(out).strip()


# --- stage 2: drop-only rules ----------------------------------------------

_QUOTED = re.compile(r"^\s*>")
# English and Spanish reply headers (the managers' mail mixes both).
_HISTORY_HEADER = re.compile(
    r"^\s*\*?(From|Sent|To|Cc|Subject|Date|De|Para|Enviado|Asunto|Fecha|CC)\*?\s*:",
    re.IGNORECASE,
)
_ON_WROTE = re.compile(r"^\s*(On .{3,200} wrote|El .{3,200} escribi[oó])\s*:\s*$")
_ORIGINAL = re.compile(
    r"^\s*-{2,}\s*(Original Message|Forwarded message)\s*-{2,}\s*$", re.I
)
_SIG_DELIM = "-- "
_DISCLAIMER = re.compile(
    r"(this (e-?mail|message)( and any attachments)? (is|are|may be) "
    r"(confidential|intended solely)|if you (are not|have received this) .{0,40}"
    r"(intended recipient|in error)|please consider the environment before printing)",
    re.IGNORECASE,
)
_TRACKING = re.compile(
    r"(unsubscribe|view (this|it) in your browser|manage (your )?(email )?preferences)",
    re.IGNORECASE,
)
_REACTION = re.compile(r"^[\W_]{0,8}$")
_SECRET = re.compile(
    r"(-----BEGIN [A-Z ]*PRIVATE KEY-----"
    r"|\bAKIA[0-9A-Z]{16}\b"
    r"|\b(sk|rk|pk)[-_](live|test|proj|or)?[-_]?[A-Za-z0-9_-]{20,}"
    r"|\bgh[pousr]_[A-Za-z0-9]{30,}"
    r"|\bxox[abpr]-[A-Za-z0-9-]{10,}"
    r"|\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"
    r"|\b(password|passwd|pwd|passcode|api[ _-]?key|secret|token)\b\s*[:=]\s*\S{4,})",
    re.IGNORECASE,
)
_NOREPLY = re.compile(
    r"(no[_-]?reply|do[_-]?not[_-]?reply|notifications?@|mailer-daemon"
    r"|postmaster@|bounces?@|microsoftexchange[0-9a-f]{16,})",
    re.I,
)
_MARKETING_SENDER = re.compile(
    r"(newsletter|marketing|promo@|promotions@|offers@|digest@|clickupdates@"
    r"|team@mail\.clickup\.com|microsoftcopilotupdates@"
    r"|informa markets|license global|brand licensing (europe|expo)"
    r"|furniture today|writeclick|rvcf\.com"
    r"|email\.1\.asana\.com|mails\.teamviewer\.com)",
    re.I,
)
_BULK_BODY = re.compile(
    r"(unsubscribe|manage (your )?(email )?preferences|update your preferences"
    r"|view (this|it) in (your )?browser|opt[ -]?out"
    r"|you are receiving this (email|message)|why did i get this"
    r"|add us to your address book|mailing list)",
    re.I,
)
_INTERNAL_DOMAINS = (
    "@popcre.com",
    "@popcreations.com",
    "@spruceline.com",
)
_PROTECTED_PARTNER_DOMAINS = (
    "disney.com",
    "wbd.com",
    "warnerbros.com",
    "nbcuni.com",
    "universalstudios.com",
    "paramount.com",
    "sega.com",
    "segaamerica.com",
    "mymediabox.com",
    "brandcomply.com",
    "designflow.app",
    "lidl.us",
    "walmart.com",
    "target.com",
    "rossstores.com",
    "coldlion.com",
    "boxstoragepro.com",
)
_PORTAL_TEMPLATE_DOMAINS = (
    "designflow.app",
    "disney.com",
    "mymediabox.com",
    "brandcomply.com",
    "mail.gofreight.com",
    "oocllogistics.com",
)
_CAMPAIGN_HEADER_NAMES = frozenset(
    {
        "x-campaign-id",
        "x-mc-user",
        "x-mailgun-variables",
        "x-sg-eid",
        "x-hubspot-email-id",
        "x-sfmc-stack",
        "x-marketoid",
    }
)
_BULK_HEADER_NAMES = frozenset(
    {
        "list-unsubscribe",
        "list-unsubscribe-post",
        "list-id",
        *_CAMPAIGN_HEADER_NAMES,
    }
)
_CALENDAR_SUBJECT = re.compile(
    r"^(Accepted|Declined|Tentative|Canceled|Cancelled|Invitation|Updated invitation):",
    re.I,
)
_OOO_SUBJECT = re.compile(
    r"^(Automatic reply|Auto[- ]?Reply|Out of Office|Respuesta autom[aá]tica)\s*:",
    re.I,
)
_TEAMS_ADD_SUBJECT = re.compile(
    r"^(you (were|have been) added to (a team|the .+ team)|te agregaron a un equipo en microsoft teams)",
    re.I,
)
_TEAMS_ADD_BODY = re.compile(
    r"(added you to the team|te agreg[oó] al equipo|teams\.microsoft\.com/l/team/)",
    re.I,
)
_LOOP_MENTION_SUBJECT = re.compile(r"^mentioned you in\b", re.I)
_LOOP_MENTION_BODY = re.compile(
    r"(mentioned you in a loop component|LoopAppData|\.sharepoint\.com/.+\.loop)",
    re.I,
)
_M365_CONTROLLED_FOOTER = re.compile(
    r"(generated through .+ use of microsoft 365|genera mediante el uso de .+ de microsoft 365)",
    re.I,
)

REMOVED_MARKER = "[message removed]"


def strip_lines(
    text: str, signatures: Iterable[str] = ()
) -> tuple[list[str], dict[str, int]]:
    """Kept lines of one message and a count of dropped lines per rule.

    Drops: quoted history (``>`` lines; everything from an ``On ... wrote:``
    line, an ``Original Message`` rule, or a ``From:`` header block onward),
    everything after a ``-- `` signature delimiter, exact allowlisted
    signature blocks, legal disclaimers and tracking boilerplate.
    """
    lines = text.split("\n")
    dropped: dict[str, int] = {}

    def drop(rule: str, n: int = 1) -> None:
        dropped[rule] = dropped.get(rule, 0) + n

    # Cut points: the first line where history or a signature begins.
    cut = len(lines)
    for i, ln in enumerate(lines):
        if ln == _SIG_DELIM or ln.rstrip() == "--":
            cut, rule = i, "signature"
            break
        if _ON_WROTE.match(ln) or _ORIGINAL.match(ln):
            cut, rule = i, "quoted_history"
            break
        if (
            _HISTORY_HEADER.match(ln)
            and i + 1 < len(lines)
            and _HISTORY_HEADER.match(lines[i + 1])
        ):
            cut, rule = i, "quoted_history"
            break
    if cut < len(lines):
        drop(rule, len(lines) - cut)
    lines = lines[:cut]

    keep = [True] * len(lines)
    for block in signatures:
        blines = block.split("\n")
        n = len(blines)
        if not n or not block.strip():
            continue
        for i in range(len(lines) - n + 1):
            if all(keep[i + k] for k in range(n)) and lines[i : i + n] == blines:
                for k in range(n):
                    keep[i + k] = False
                drop("signature", n)
    for i, ln in enumerate(lines):
        if not keep[i]:
            continue
        if _QUOTED.match(ln):
            keep[i] = False
            drop("quoted_history")
        elif _DISCLAIMER.search(ln):
            keep[i] = False
            drop("disclaimer")
        elif _TRACKING.search(ln):
            keep[i] = False
            drop("tracking")
    kept = [ln for ln, k in zip(lines, keep, strict=True) if k]
    while kept and not kept[-1].strip():
        kept.pop()
    while kept and not kept[0].strip():
        kept.pop(0)
    return kept, dropped


def is_secret(text: str) -> bool:
    return bool(_SECRET.search(text))


def _sender_fields(item: dict[str, Any]) -> tuple[str, str]:
    raw = item.get("raw") or {}
    from_ea = (raw.get("from") or {}).get("emailAddress") or {}
    sender_ea = (raw.get("sender") or {}).get("emailAddress") or {}
    address = str(
        from_ea.get("address")
        or sender_ea.get("address")
        or item.get("author_ref")
        or ""
    ).strip()
    name = str(from_ea.get("name") or sender_ea.get("name") or "").strip()
    return address, name


def _is_internal_human(address: str) -> bool:
    low = address.lower()
    if not low or _NOREPLY.search(low):
        return False
    return any(low.endswith(dom) for dom in _INTERNAL_DOMAINS)


def sender_domain(address: str) -> str:
    """Lowercase domain part of an email address, else empty string."""
    addr = (address or "").strip().lower()
    if "@" not in addr:
        return ""
    return addr.rsplit("@", 1)[1].strip("> ")


def _domain_matches(domain: str, candidates: tuple[str, ...]) -> bool:
    if not domain:
        return False
    return any(domain == cand or domain.endswith("." + cand) for cand in candidates)


def is_protected_partner_domain(address: str) -> bool:
    """True when sender belongs to a known licensor, portal, or key retailer domain."""
    return _domain_matches(sender_domain(address), _PROTECTED_PARTNER_DOMAINS)


def portal_template_domain(domains: Iterable[str]) -> str | None:
    """Return the first matching high-volume portal/logistics template domain."""
    for raw in domains:
        dom = (raw or "").strip().lower()
        for portal in _PORTAL_TEMPLATE_DOMAINS:
            if dom == portal or dom.endswith("." + portal):
                return portal
    return None


def is_notification(item: dict[str, Any]) -> bool:
    """Automated notices: no-reply senders, calendar/OOO traffic, M365 alerts."""
    raw = item.get("raw") or {}
    address, _name = _sender_fields(item)
    if address and _NOREPLY.search(address):
        return True
    if raw.get("meetingMessageType") not in (None, "none"):
        return True
    if str(raw.get("@odata.type", "")).endswith("eventMessage"):
        return True
    subject = str(raw.get("subject") or "").strip()
    if _CALENDAR_SUBJECT.match(subject) or _OOO_SUBJECT.match(subject):
        return True
    if raw.get("messageType") not in (None, "message"):
        return True  # Teams system events
    if (raw.get("from") or {}).get("application"):
        return True
    text = item.get("body_text") or ""
    # Ruling #3: automated Microsoft Teams team-add emails carry M365 boilerplate only.
    if _TEAMS_ADD_SUBJECT.match(subject) and (
        _TEAMS_ADD_BODY.search(text) or _M365_CONTROLLED_FOOTER.search(text)
    ):
        return True
    # Ruling #13: automated Microsoft Loop / SharePoint @mention emails carry links only.
    if _LOOP_MENTION_SUBJECT.match(subject) and _LOOP_MENTION_BODY.search(text):
        return True
    return False


def is_bulk_marketing(item: dict[str, Any]) -> bool:
    """Mass-marketing emails, newsletters, and mailing-list blasts.

    Uses RFC headers when collected (``List-Unsubscribe``, ``List-Id``,
    ``Precedence: bulk|list|junk``, ``Auto-Submitted``), bulk sender patterns,
    and external unsubscribe/newsletter footers so marketing blasts are dropped
    whole instead of having only their footer line stripped. Known licensor,
    portal, and active retailer domains are protected from footer/unsubscribe
    false positives.
    """
    raw = item.get("raw") or {}
    address, name = _sender_fields(item)
    if _is_internal_human(address):
        return False
    headers = [
        (
            str(hdr.get("name") or "").strip().lower(),
            str(hdr.get("value") or "").strip().lower(),
        )
        for hdr in (raw.get("internetMessageHeaders") or ())
        if isinstance(hdr, dict)
    ]
    if any(hname in _CAMPAIGN_HEADER_NAMES for hname, _hval in headers):
        return True
    if (address and _MARKETING_SENDER.search(address)) or (
        name and _MARKETING_SENDER.search(name)
    ):
        return True
    if is_protected_partner_domain(address):
        return False
    for hname, hval in headers:
        if hname in _BULK_HEADER_NAMES:
            return True
        if hname == "precedence" and hval in {"bulk", "list", "junk"}:
            return True
        if hname == "auto-submitted" and hval.startswith(("auto-generated", "auto-replied")):
            return True
    text = item.get("body_text") or ""
    is_email = (
        item.get("origin") == "email"
        or bool(address)
        or bool(name)
        or "subject" in raw
        or "internetMessageId" in raw
    )
    return bool(is_email and text and _BULK_BODY.search(text))


@dataclass
class Cleaned:
    """One message after cleaning. ``text`` is None when the whole message drops."""

    item: dict[str, Any]
    text: str | None
    drop_reason: str | None = None
    lines_dropped: dict[str, int] = field(default_factory=dict)


MIN_REPEAT_CHARS = 30  # shorter lines ("Thanks", "Hi all") are never deduplicated


def _drop_repeated(
    kept: list[str], seen_lines: set[str], dropped: dict[str, int]
) -> list[str]:
    """Drop lines an earlier message of the same chain already said (whole lines only).

    Email replies carry the whole earlier chain; keeping each line only where
    it first appeared keeps one copy of every word, with its real author and
    time. Lines under MIN_REPEAT_CHARS are left alone.
    """
    out: list[str] = []
    for ln in kept:
        key = ln.strip()
        if len(key) >= MIN_REPEAT_CHARS and key in seen_lines:
            dropped["repeated_line"] = dropped.get("repeated_line", 0) + 1
            continue
        out.append(ln)
    seen_lines.update(ln.strip() for ln in out if len(ln.strip()) >= MIN_REPEAT_CHARS)
    return out


def clean_item(
    item: dict[str, Any],
    seen: set[str],
    signatures: Iterable[str] = (),
    seen_lines: set[str] | None = None,
) -> Cleaned:
    """Clean one message. ``item['body_text']`` must already be converted text.

    ``seen`` holds content hashes of earlier kept messages (exact duplicates drop).
    ``seen_lines``, when given, holds long lines earlier messages of the same
    chain already kept; repeats of them are dropped.
    """
    text = item.get("body_text") or ""
    if is_secret(text):
        return Cleaned(item, None, "secret")
    if is_notification(item):
        return Cleaned(item, None, "notification")
    if is_bulk_marketing(item):
        return Cleaned(item, None, "marketing")
    kept, dropped = strip_lines(text, signatures)
    if seen_lines is not None:
        kept = _drop_repeated(kept, seen_lines, dropped)
        while kept and not kept[-1].strip():
            kept.pop()
    body = "\n".join(kept)
    if not body.strip():
        return Cleaned(item, None, "empty", dropped)
    if _REACTION.match(body.strip()):
        return Cleaned(item, None, "reaction", dropped)
    h = hashlib.sha256(body.encode("utf-8")).hexdigest()
    if h in seen:
        return Cleaned(item, None, "duplicate", dropped)
    seen.add(h)
    return Cleaned(item, body, None, dropped)


@dataclass
class AssembledThread:
    thread_key: str
    messages: list[Cleaned]
    tokens: int
    drop_reason: str | None  # 'too_short' or None


_REPLY_PREFIX = re.compile(r"^\s*((re|fw|fwd|aw)\s*:\s*)+", re.IGNORECASE)


def subject_chain(item: dict[str, Any]) -> str | None:
    """Chain key for email line dedupe: the subject without Re:/Fw: prefixes."""
    subject = (item.get("raw") or {}).get("subject")
    if not subject:
        return None
    return _REPLY_PREFIX.sub("", subject).strip().lower() or None


def assemble(
    items: list[dict[str, Any]],
    signatures: Iterable[str] = (),
    chain_of: Any = None,
) -> list[AssembledThread]:
    """Group cleaned items by ``thread_key`` in the order given (oldest first).

    Thread boundaries were set by the collectors (ClickUp: task; Teams: chat
    and four-hour silence; email: conversationId). A thread whose kept text is
    under MIN_THREAD_TOKENS is marked ``too_short``; it is never merged into a
    neighbour.

    ``chain_of(item)``, when given, names the chain an item belongs to (email:
    ``subject_chain``); inside a chain, long lines repeated from an earlier
    message are dropped. Items must then be in time order across threads.
    """
    sigs = tuple(signatures)
    seen: set[str] = set()
    chains: dict[str, set[str]] = {}
    by_key: dict[str, list[Cleaned]] = {}
    for it in items:
        lines = None
        if chain_of is not None:
            lines = chains.setdefault(
                chain_of(it) or f"thread:{it['thread_key']}", set()
            )
        by_key.setdefault(it["thread_key"], []).append(
            clean_item(it, seen, sigs, lines)
        )
    out: list[AssembledThread] = []
    for key, msgs in by_key.items():
        tokens = sum(count_tokens(m.text) for m in msgs if m.text)
        out.append(
            AssembledThread(
                key, msgs, tokens, "too_short" if tokens < MIN_THREAD_TOKENS else None
            )
        )
    return out


def apply(conn: Any, origin: str, signatures: Iterable[str] = ()) -> dict[str, int]:
    """Clean every staged item of one origin in place; return counts per drop reason.

    Kept items get their cleaned text in ``body_text``; dropped items get a
    ``drop_reason``. A secret item has ``body_text`` and ``raw`` blanked.
    Threads under the floor become verdict ``dropped`` with gate_scores
    ``{"rule": "too_short"}``. Re-running is harmless.
    """
    counts: dict[str, int] = {}
    with conn.cursor() as cur:
        cur.execute(
            "SELECT id, thread_key, body_text, raw FROM cmap.intake_item "
            "WHERE origin = %s AND drop_reason IS NULL ORDER BY sent_at, id",
            (origin,),
        )
        rows = [
            {"id": r[0], "thread_key": r[1], "body_text": r[2], "raw": r[3]}
            for r in cur.fetchall()
        ]
        chain = subject_chain if origin == "email" else None
        for th in assemble(rows, signatures, chain):
            for m in th.messages:
                if m.drop_reason == "secret":
                    cur.execute(
                        "UPDATE cmap.intake_item SET drop_reason = 'secret', body_text = '', "
                        "raw = '{}'::jsonb WHERE id = %s",
                        (m.item["id"],),
                    )
                elif m.drop_reason:
                    cur.execute(
                        "UPDATE cmap.intake_item SET drop_reason = %s WHERE id = %s",
                        (m.drop_reason, m.item["id"]),
                    )
                elif m.text != m.item["body_text"]:
                    cur.execute(
                        "UPDATE cmap.intake_item SET body_text = %s, content_hash = %s WHERE id = %s",
                        (
                            m.text,
                            hashlib.sha256(m.text.encode()).hexdigest(),
                            m.item["id"],
                        ),
                    )
                key = m.drop_reason or "kept"
                counts[key] = counts.get(key, 0) + 1
            if th.drop_reason:
                counts["too_short_thread"] = counts.get("too_short_thread", 0) + 1
                cur.execute(
                    "UPDATE cmap.intake_thread SET verdict = 'dropped', "
                    'gate_scores = \'{"rule": "too_short"}\'::jsonb, token_count = %s, '
                    "updated_at = now() WHERE origin = %s AND thread_key = %s AND verdict = 'pending'",
                    (th.tokens, origin, th.thread_key),
                )
            else:
                cur.execute(
                    "UPDATE cmap.intake_thread SET token_count = %s, "
                    "verdict = CASE WHEN verdict = 'dropped' AND gate_scores->>'rule' = 'too_short' "
                    "THEN 'pending' ELSE verdict END, "
                    "gate_scores = CASE WHEN verdict = 'dropped' AND gate_scores->>'rule' = 'too_short' "
                    "THEN '{}'::jsonb ELSE gate_scores END, "
                    "updated_at = now() WHERE origin = %s AND thread_key = %s",
                    (th.tokens, origin, th.thread_key),
                )
    conn.commit()
    return counts


def load_signatures(path: str | None) -> list[str]:
    """Signature blocks from the private allowlist file (JSON list of strings)."""
    if not path:
        return []
    import json

    with open(path, encoding="utf-8") as f:
        blocks = json.load(f)
    return [b for b in blocks if isinstance(b, str) and b.strip()]


def main(argv: list[str] | None = None) -> None:
    """``python -m brain.intake.clean --origin email`` - clean staged rows; print counts."""
    import argparse
    import os

    import psycopg

    from brain.config import get_settings

    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--origin", required=True, choices=["clickup", "teams_chat", "email"]
    )
    a = ap.parse_args(argv)
    sigs = load_signatures(os.environ.get("BRAIN_INTAKE_SIGNATURES_FILE"))
    with psycopg.connect(get_settings().database_url) as conn:
        counts = apply(conn, a.origin, sigs)
    print(f"# cleaned {a.origin} (signature blocks {len(sigs)})")
    for k, v in sorted(counts.items()):
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
