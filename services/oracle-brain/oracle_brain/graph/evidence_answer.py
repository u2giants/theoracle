"""Graph-grounded S03 answer path on FalkorDB.

Source blocks are stored as ``(:Source)-[:HAS_SENTENCE]->(:Sentence)-[:MENTIONS]->(:Term)``
inside one isolated graph per evidence corpus. A question is answered only from
the source(s) the graph ranks as clearly relevant (rarity-weighted term overlap),
every factual clause is cited to its exact source block, and the answer states
"No source evidence" when nothing in the graph supports the question, or when
the only relevant source explicitly marks the asked-for decision as unresolved.

Deterministic and provider-free: no model call, no network beyond FalkorDB.
"""

from __future__ import annotations

import math
import os
import re
import tempfile
from dataclasses import dataclass
from urllib.parse import urlparse
from uuid import UUID

from falkordb import FalkorDB

from ..consultant.pilot import Citation, HypotheticalExperiment, PilotAnswer

NO_EVIDENCE = "No source evidence was found for this question."
STOP = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "after", "before",
    "with", "is", "are", "be", "by", "not", "do", "does", "did", "what", "who", "whom",
    "which", "when", "where", "how", "why", "can", "could", "should", "would", "will",
    "may", "might", "must", "we", "our", "us", "it", "its", "this", "that", "these",
    "those", "there", "from", "at", "as", "was", "were", "has", "have", "had", "any",
    "about", "into", "only", "than", "then", "same", "usual", "small", "new", "going",
}
_SUFFIXES = ("ations", "ation", "ions", "ion", "ings", "ing", "als", "al", "ed", "es", "s", "e")
# Small business-vocabulary equivalences applied on the question side.
ALIASES = {"live": ("launch", "publish"), "launch": ("publish",), "owner": ("own",),
           "buy": ("purchase",), "purchase": ("buy",), "blocks": ("dependency",),
           "block": ("dependency",)}
_GAP = re.compile(
    r"\b(blank|pending|unresolved|undecided|proposed|has no|have no|lacks?|"
    r"no [a-z-]+(?:[ ,]+(?:or |and )?[a-z-]+)* (?:is|are) supplied)\b",
    re.IGNORECASE,
)
_DETERMINATION = re.compile(r"^\s*(who|whom|was|were|is|are|should|did|does|do|has|have)\b",
                            re.IGNORECASE)
_IMPROVEMENT = re.compile(r"\b(improve|reduce|shorten|experiment|speed up|faster)\b",
                          re.IGNORECASE)
_NUMBER = (r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
           r"twenty)\b")
_COUNT = re.compile(_NUMBER, re.IGNORECASE)
_INTENT = {"improve", "reduce", "shorten", "experiment", "could", "trial", "faster"}
_DEPENDENCY_Q = re.compile(r"\b(blocks?|prevents?|holds? up|required before|needed before)\b",
                           re.IGNORECASE)
_DEPENDENCY_E = re.compile(r"\b(only after|before|until|requires?|needs?|depends? on)\b",
                           re.IGNORECASE)
_SUPERSEDES = re.compile(r"\b(supersed(?:e|es|ed)|replac(?:e|es|ed)|correction|corrected)\b", re.IGNORECASE)
_REVISION = re.compile(r"\brevision\s+(\d+)", re.IGNORECASE)
_CONDITION = re.compile(r"^\s*if\s+(.+?),\s*(.+?)\s+until\s+(.+?)\.?$", re.IGNORECASE)
_THRESHOLD = re.compile(r"\b(over|above|under|below|more than|less than|at least|at most|"
                        r"exceeds?|within|up to)\s+\$?\d", re.IGNORECASE)
_EXCEPTION = re.compile(r"\b(only|except|unless|but|instead|otherwise|exception)\b", re.IGNORECASE)
_OBSERVATION = re.compile(r"\b(\d+|two|three|four|five|six|seven|eight|nine|ten)\b"
                          r"[^.]*\b(of|took|waited|lack|missing|repeat)\b", re.IGNORECASE)


def stem(word: str) -> str:
    word = word.lower()
    for suffix in _SUFFIXES:
        if word.endswith(suffix) and len(word) - len(suffix) >= 4:
            return word[: -len(suffix)]
    return word


def terms(text: str) -> set[str]:
    return {stem(w) for w in re.findall(r"[a-z0-9]+", text.lower())
            if len(w) > 2 and w not in STOP}


def question_terms(question: str) -> dict[str, set[str]]:
    """Each question concept mapped to the graph stems that satisfy it."""
    out: dict[str, set[str]] = {}
    for w in re.findall(r"[a-z0-9]+", question.lower()):
        if len(w) <= 2 or w in STOP or w in _INTENT:
            continue
        out.setdefault(stem(w), {stem(w)}).update(stem(a) for a in ALIASES.get(w, ()))
    return out


def sentences(text: str) -> list[tuple[int, int, str]]:
    out = []
    for match in re.finditer(r"[^.!?]+[.!?]?", text):
        chunk = match.group(0)
        stripped = chunk.strip()
        if stripped:
            start = match.start() + (len(chunk) - len(chunk.lstrip()))
            out.append((start, start + len(stripped), stripped))
    return out


@dataclass(frozen=True)
class GraphEvidence:
    source_id: UUID
    block_id: UUID
    span_start: int
    span_end: int
    text: str
    score: float
    gap_sentences: tuple[str, ...]
    sentences: tuple[str, ...]


_TLS_FILES: dict[tuple, list[str]] = {}


def graph_tls_options(scheme: str) -> dict:
    """Optional client-certificate TLS for a hosted graph (PEM values from env).

    All three of ORACLE2_GRAPH_TLS_CA_PEM, _CERT_PEM and _KEY_PEM must be set
    together, and only with a rediss:// URL. Cert and key go to 0600 temp files.
    """
    names = ("ORACLE2_GRAPH_TLS_CA_PEM", "ORACLE2_GRAPH_TLS_CERT_PEM", "ORACLE2_GRAPH_TLS_KEY_PEM")
    values = [os.getenv(n) for n in names]
    if not any(values):
        return {}
    if not all(values) or scheme != "rediss":
        raise ValueError("graph client TLS needs CA, certificate and key with rediss://")
    key = tuple(values)
    paths = _TLS_FILES.get(key)
    if paths is None:
        # Written once per process and reused, so key copies do not accumulate.
        paths = []
        for value in values[1:]:
            fd, path = tempfile.mkstemp(prefix="oracle2-graph-", suffix=".pem")
            with os.fdopen(fd, "w") as handle:
                handle.write(value)
            paths.append(path)
        _TLS_FILES[key] = paths
    return {"ssl_ca_data": values[0], "ssl_certfile": paths[0], "ssl_keyfile": paths[1],
            "ssl_cert_reqs": "required", "ssl_check_hostname": True}


class FalkorEvidenceGraph:
    """Evidence graph for one isolated corpus (one FalkorDB graph name)."""

    def __init__(self, url: str, graph_name: str):
        parsed = urlparse(url)
        if parsed.scheme not in {"redis", "rediss"} or not parsed.hostname:
            raise ValueError("invalid FalkorDB URL")
        if not re.fullmatch(r"oracle2_evidence_[a-z0-9_]{1,64}", graph_name):
            raise ValueError("evidence graph name must be oracle2_evidence_<id>")
        client = FalkorDB(host=parsed.hostname, port=parsed.port or 6379,
                          password=parsed.password, ssl=parsed.scheme == "rediss",
                          **graph_tls_options(parsed.scheme))
        self.graph = client.select_graph(graph_name)

    def reset(self) -> None:
        self.graph.query("MATCH (n) DETACH DELETE n")

    def ingest(self, blocks: list[dict]) -> None:
        """Store each block (source_id, block_id, span_start, span_end, text, title?).

        ``title`` is document metadata (e.g. process name); it steers retrieval
        but is never quoted or cited as evidence.
        """
        for block in blocks:
            rows = []
            for i, (start, end, text) in enumerate(sentences(block["text"])):
                rows.append({"idx": i, "start": start, "end": end, "text": text,
                             "gap": bool(_GAP.search(text)), "terms": sorted(terms(text))})
            self.graph.query(
                """MERGE (src:Source {id:$source_id})
                   MERGE (b:Block {id:$block_id})
                   SET b.span_start=$span_start, b.span_end=$span_end, b.text=$text
                   MERGE (src)-[:HAS_BLOCK]->(b)
                   WITH src, b
                   UNWIND (CASE WHEN size($title_terms) = 0 THEN [null] ELSE $title_terms END) AS tt
                   FOREACH (_ IN CASE WHEN tt IS NULL THEN [] ELSE [1] END |
                     MERGE (t0:Term {stem:tt})
                     MERGE (src)-[:TITLE_MENTIONS]->(t0))
                   WITH DISTINCT b
                   WITH b UNWIND $rows AS r
                   MERGE (s:Sentence {id:$block_id + ':' + toString(r.idx)})
                   SET s.text=r.text, s.idx=r.idx, s.gap=r.gap
                   MERGE (b)-[:HAS_SENTENCE]->(s)
                   WITH s, r UNWIND r.terms AS stem
                   MERGE (t:Term {stem:stem})
                   MERGE (s)-[:MENTIONS]->(t)""",
                params={"source_id": str(block["source_id"]), "block_id": str(block["block_id"]),
                        "span_start": int(block["span_start"]), "span_end": int(block["span_end"]),
                        "text": block["text"], "rows": rows,
                        "title_terms": sorted(terms(block.get("title") or ""))},
            )

    def retrieve(self, question: str, *, min_coverage: float = 0.34,
                 tie_ratio: float = 0.85) -> list[GraphEvidence]:
        """Return only blocks whose rarity-weighted question coverage is clearly highest."""
        if not question.strip():
            raise ValueError("question must be non-empty")
        concepts = question_terms(question)
        if not concepts:
            return []
        stems = sorted({x for v in concepts.values() for x in v})
        total_sources = self.graph.query("MATCH (s:Source) RETURN count(s)").result_set[0][0]
        if not total_sources:
            return []
        rows = self.graph.query(
            """MATCH (t:Term) WHERE t.stem IN $stems
               OPTIONAL MATCH (t)<-[:MENTIONS]-(:Sentence)<-[:HAS_SENTENCE]-(b:Block)
               WITH t, collect(DISTINCT b.id) AS body
               OPTIONAL MATCH (t)<-[:TITLE_MENTIONS]-(:Source)-[:HAS_BLOCK]->(b2:Block)
               RETURN t.stem, body, collect(DISTINCT b2.id)""",
            params={"stems": stems}).result_set
        body = {row[0]: set(row[1]) for row in rows}
        title = {row[0]: set(row[2]) for row in rows}
        weight_by_block: dict[str, dict[str, float]] = {}
        df: dict[str, int] = {}
        for concept, alts in concepts.items():
            body_ids = set().union(*(body.get(a, set()) for a in alts))
            title_ids = set().union(*(title.get(a, set()) for a in alts))
            df[concept] = len(body_ids | title_ids)
            for bid in body_ids | title_ids:
                # Title (document metadata) steers, body evidence counts fully.
                weight_by_block.setdefault(bid, {})[concept] = 1.0 if bid in body_ids else 0.5
        idf = {c: math.log(1 + total_sources / (1 + df[c])) for c in concepts}
        total_weight = sum(idf.values())
        scored = sorted(((sum(idf[c] * w for c, w in hit.items()) / total_weight, bid)
                         for bid, hit in weight_by_block.items()), reverse=True)
        candidates = [self._evidence(bid, score) for score, bid in scored
                      if score >= min_coverage]
        if _IMPROVEMENT.search(question):
            # An improvement question needs observed data, not only a procedure.
            observed = [e for e in candidates if any(_COUNT.search(x) for x in e.sentences)]
            candidates = observed or candidates
        if _DEPENDENCY_Q.search(question):
            # "What blocks X" needs evidence that states a dependency.
            gated = [e for e in candidates if any(_DEPENDENCY_E.search(x) for x in e.sentences)]
            candidates = gated or candidates
        if not candidates:
            return []
        top = candidates[0].score
        return [e for e in candidates if e.score >= top * tie_ratio]

    def _evidence(self, block_id: str, score: float) -> GraphEvidence:
        row = self.graph.query(
            """MATCH (src:Source)-[:HAS_BLOCK]->(b:Block {id:$id})-[:HAS_SENTENCE]->(s:Sentence)
               WITH src, b, s ORDER BY s.idx
               RETURN src.id, b.span_start, b.span_end, b.text,
                      collect(s.text), collect(CASE WHEN s.gap THEN s.text END)""",
            params={"id": block_id}).result_set[0]
        return GraphEvidence(
            source_id=UUID(row[0]), block_id=UUID(block_id), span_start=int(row[1]),
            span_end=int(row[2]), text=row[3], score=round(score, 4),
            sentences=tuple(row[4]), gap_sentences=tuple(g for g in row[5] if g))


def _improvement(question: str, evidence: list[GraphEvidence]) -> HypotheticalExperiment | None:
    if not _IMPROVEMENT.search(question):
        return None
    all_sentences = [s for e in evidence for s in e.sentences]
    observed = next((s for s in all_sentences if _OBSERVATION.search(s)
                     and re.search(r"\b(missing|lack|repeat|waited)", s, re.I)), None)
    if observed is None:
        observed = next((s for s in all_sentences if _OBSERVATION.search(s)), None)
    if observed is None:
        observed = next((s for s in all_sentences if not _GAP.search(s)), all_sentences[0])
    proposal = "a narrowly scoped process check aimed at the observed issue"
    late = next((s for s in all_sentences if re.search(r"\bonly after\b", s, re.I)), None)
    lacking = re.search(r"\b(?:missing|lack(?:s|ing)?(?: an?)?)\s+([a-z -]+?)(?:[.,]|$)",
                        observed, re.IGNORECASE)
    if late:
        item = re.match(r"\s*(?:an?\s+|the\s+)?([a-z -]+?)\s+(?:exists|is)\b", late, re.I)
        thing = item.group(1) if item else "the step"
        proposal = f"sending {thing} at intake instead of only after a later step"
    elif lacking:
        thing = lacking.group(1).strip()
        proposal = (f"try making the {thing} a required field at intake "
                    f"(a completeness check or reminder for the {thing})")
    missing = [g for e in evidence for g in e.gap_sentences] or ["baseline volume and cycle time"]
    return HypotheticalExperiment(
        label="Hypothetical improvement experiment (not established fact)",
        description=(f"Observed contributor in the source: {observed} "
                     f"Hypothesis to test: {proposal}."),
        measure=("Measure how often the observed issue recurs (repeat-request rate) and the "
                 "wait, review and delay time, before and after the test, on the same scope."),
        missing_inputs=missing,
    )


def _rule_parts(sents: list[str]) -> str | None:
    """Label a numeric threshold and its exception clause, quoting source words only."""
    parts = []
    for x in sents:
        for clause in re.split(r";\s*|,\s*(?=(?:but|except|unless|otherwise)\b)", x.rstrip(".")):
            clause = clause.strip()
            if not clause:
                continue
            if _THRESHOLD.search(clause):
                parts.append(f"threshold: {clause}")
            elif _EXCEPTION.search(clause):
                parts.append(f"exception: {clause}")
    if any(p.startswith("threshold") for p in parts):
        return "; ".join(parts) + "."
    return None


def _summary(sents: list[str]) -> str | None:
    """Restate conditional or superseding evidence without adding facts."""
    rule = _rule_parts(sents)
    if rule:
        return rule
    for x in sents:
        m = _CONDITION.match(x)
        if m:
            return (f"condition: {m.group(1)}; outcome: {m.group(2)}, "
                    f"pending {m.group(3).rstrip('.')}.")
    current = [x for x in sents if _SUPERSEDES.search(x)]
    prior = [x for x in sents if x not in current]
    if not current:
        revs = [(int(m.group(1)), x) for x in sents for m in [_REVISION.search(x)] if m]
        if len(revs) >= 2:
            latest = max(revs)[1]
            current, prior = [latest], [x for _, x in revs if x != latest]
    if current and prior:
        return (f"current: {' '.join(current)} Prior, historical (superseded): {' '.join(prior)}")
    return None


def answer_from_graph(question: str, evidence: list[GraphEvidence]) -> PilotAnswer:
    """Compose a cited answer strictly from graph-retrieved evidence."""
    if not evidence:
        return PilotAnswer(answer_text=NO_EVIDENCE, citations=[], hypothetical=None,
                           is_established_fact=False)
    citations = [Citation(source_id=e.source_id, span_start=e.span_start,
                          span_end=e.span_end, quote=e.text) for e in evidence]
    gaps = [g for e in evidence for g in e.gap_sentences]
    if gaps and _DETERMINATION.search(question):
        known = " ".join(s for e in evidence for s in e.sentences if s not in gaps)
        text = ("No source evidence resolves this question. The source leaves it open: "
                + " ".join(gaps))
        if known:
            text += f" Known from the same source: {known}"
        return PilotAnswer(answer_text=text, citations=citations, hypothetical=None,
                           is_established_fact=False)
    text = "According to the source: " + " ".join(e.text for e in evidence)
    summary = _summary([x for e in evidence for x in e.sentences])
    if summary:
        text += f"\nIn short: {summary}"
    hypothetical = _improvement(question, evidence)
    if hypothetical is not None:
        text += f"\n{hypothetical.label}: {hypothetical.description} {hypothetical.measure}"
    return PilotAnswer(answer_text=text, citations=citations, hypothetical=hypothetical,
                       is_established_fact=True)
