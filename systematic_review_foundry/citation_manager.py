"""
Citation management and validation for the Systematic Review Foundry.
Handles citation parsing, validation (manual, regex-based, AI-based),
and citation reordering for export.
"""
import re
from typing import List, Tuple, Optional, Dict
from collections import OrderedDict
from difflib import SequenceMatcher

from models import Source, ReviewSession


# Matches a whole citation bracket, single '[5]' or multi '[3, 7, 12]'.
# Group 1 is the inner run of numbers.
CITATION_PATTERN = r'\[(\d+(?:\s*,\s*\d+)*)\]'
_CITATION_RE = re.compile(CITATION_PATTERN)


def extract_bracketed_numbers(text: str) -> List[int]:
    """Extract all integers inside brackets: '[5] and [6]' -> [5, 6]"""
    return [int(m) for m in re.findall(r'\[(\d+)\]', text)]


def separate_bracketed_lists(text: str) -> str:
    """Split combined citations: '[5,6]' -> '[5][6]'

    Only square brackets are touched.  The old implementation also matched
    parentheses, which silently rewrote things like a year '(2020)' into a
    citation '[2020]'.
    """
    def replace_bracket(match):
        numbers = [n.strip() for n in match.group(1).split(',')]
        return ''.join(f'[{n}]' for n in numbers)
    return re.sub(CITATION_PATTERN, replace_bracket, text)


def combine_adjacent_brackets(text: str) -> str:
    """Combine adjacent citations: '[5][6]' -> '[5,6]'"""
    def replace_adjacent(match):
        numbers = sorted(int(n) for n in match.group(0).replace('][', ' ').strip('[]').split())
        return '[' + ','.join(str(x) for x in numbers) + ']'
    return re.sub(r'(?:\[(\d+)\])+', replace_adjacent, text)


def find_citation_spans(text: str) -> List[dict]:
    """
    Find all citation spans in text. Returns list of dicts with:
    - 'match': the full match string like '[5]' or '[3,7,12]'
    - 'numbers': list of ints
    - 'start': start position in text (the '[')
    - 'end': end position in text (just past the ']')
    - 'parts': one dict per number inside the bracket, each with
               'number', 'start', 'end' (absolute offsets of the digits
               themselves) and 'index' (position within the bracket).

    'parts' is what makes a multi-citation addressable element by
    element: '[3,7]' yields two parts, so the caller can act on the 7
    without touching the 3.
    """
    results = []
    for m in _CITATION_RE.finditer(text):
        inner_offset = m.start(1)
        parts = []
        for i, nm in enumerate(re.finditer(r'\d+', m.group(1))):
            parts.append({
                'number': int(nm.group(0)),
                'start': inner_offset + nm.start(),
                'end': inner_offset + nm.end(),
                'index': i,
            })
        results.append({
            'match': m.group(0),
            'numbers': [p['number'] for p in parts],
            'start': m.start(),
            'end': m.end(),
            'parts': parts,
        })
    return results


def span_at_position(text: str, pos: int) -> Optional[dict]:
    """Return the citation span containing `pos`, or None."""
    for span in find_citation_spans(text):
        if span['start'] <= pos <= span['end']:
            return span
    return None


def part_at_position(span: dict, pos: int) -> Optional[dict]:
    """
    Return the individual number within `span` that `pos` falls on.

    If the click landed on a bracket, comma or space rather than on the
    digits, the nearest number wins — so clicking the '[' of '[3,7]'
    targets the 3 rather than failing.
    """
    parts = span.get('parts') or []
    if not parts:
        return None
    for p in parts:
        if p['start'] <= pos <= p['end']:
            return p
    return min(parts,
               key=lambda p: min(abs(pos - p['start']), abs(pos - p['end'])))


def replace_citation_number(text: str, span: dict, part: dict,
                            new_number: int) -> Tuple[str, str]:
    """
    Replace exactly ONE number inside a (possibly multi-) citation,
    leaving every other number in the bracket untouched.

    '[3,7,12]' with part=7 and new_number=9 becomes '[3,9,12]'.
    If the replacement already appears in the bracket the duplicate is
    collapsed, so swapping 7 -> 3 in '[3,7]' yields '[3]' rather than
    '[3,3]'.

    Returns (new_text, new_bracket_string).
    """
    numbers = list(span['numbers'])
    idx = part.get('index', 0)
    if idx >= len(numbers):
        return text, span['match']
    numbers[idx] = new_number

    ordered, seen = [], set()
    for n in numbers:
        if n not in seen:
            seen.add(n)
            ordered.append(n)

    new_bracket = '[' + ','.join(str(n) for n in ordered) + ']'
    return (text[:span['start']] + new_bracket + text[span['end']:],
            new_bracket)


def remap_citation_numbers(text: Optional[str], mapping: Dict[int, int],
                           sort_within_bracket: bool = True) -> Optional[str]:
    """
    Rewrite every citation in `text` according to `mapping`, in a single
    pass so old and new numbers can never collide with each other.

    The previous export-time approach used repeated str.replace() calls
    with a '[N,]' sentinel to dodge collisions; a single regex pass is
    both simpler and safe by construction.
    """
    if not text:
        return text

    def repl(m):
        out, seen = [], set()
        for token in re.split(r'\s*,\s*', m.group(1)):
            n = mapping.get(int(token), int(token))
            if n not in seen:
                seen.add(n)
                out.append(n)
        if sort_within_bracket:
            out.sort()
        return '[' + ','.join(str(n) for n in out) + ']'

    return _CITATION_RE.sub(repl, text)


def get_preceding_text(full_text: str, citation_start: int) -> str:
    """
    Get the text that a citation is attributing.
    This is the text after the preceding citation up to this one,
    but not across paragraph breaks.
    """
    # Find the paragraph containing this citation
    para_start = full_text.rfind('\n', 0, citation_start)
    para_start = para_start + 1 if para_start >= 0 else 0

    # Find preceding citation in this paragraph
    preceding_text = full_text[para_start:citation_start]
    prev_cit = list(re.finditer(r'\[\d+(?:\s*,\s*\d+)*\]', preceding_text))
    if prev_cit:
        last = prev_cit[-1]
        return preceding_text[last.end():].strip()
    return preceding_text.strip()


def get_preceding_sentence(full_text: str, citation_start: int) -> str:
    """
    Get only the sentence immediately preceding a citation.
    Walks backward from citation_start to find the nearest sentence
    terminator (. ! ? or a preceding citation bracket), then returns
    everything between that and the citation.
    """
    # Don't cross paragraph breaks
    para_start = full_text.rfind('\n', 0, citation_start)
    para_start = para_start + 1 if para_start >= 0 else 0

    chunk = full_text[para_start:citation_start]

    # Find the last sentence boundary before the citation.
    # A "boundary" is: a period/exclamation/question followed by a space,
    # OR the end of a previous citation bracket ']'.
    best = -1
    # Sentence terminators
    for m in re.finditer(r'[.!?]\s', chunk):
        if m.end() <= len(chunk):
            best = max(best, m.end())
    # Previous citation bracket
    for m in re.finditer(r'\]\s*', chunk):
        # Make sure this is a citation bracket, not random ]
        preceding_bit = chunk[:m.start() + 1]
        if re.search(r'\[\d+(?:\s*,\s*\d+)*\]$', preceding_bit):
            best = max(best, m.end())

    if best >= 0:
        return chunk[best:].strip()
    return chunk.strip()


def find_best_source_match(preceding_text: str, sources: list, mode: int,
                           exclude_numbers: list = None
                           ) -> Optional[Tuple[int, str, float]]:
    """
    Search ALL source summaries to find the best-matching source for
    a piece of attributed text.

    Args:
        preceding_text: the text to match against
        sources: list of source dicts from session.sources
        mode: informs whether to use full texts or summaries, 0 or 1
        exclude_numbers: source numbers to skip (e.g. the current citation)

    Returns:
        (source_number, best_excerpt, score) or None if nothing found
    """
    if not preceding_text:
        return None

    exclude = set(exclude_numbers or [])
    best_overall = None  # (source_number, excerpt, score)

    for s in sources:
        src = s if isinstance(s, dict) else s
        num = src.get('number', 0)
        if num in exclude:
            continue
        if src.get('rating') is False:
            continue
        if mode == 0:
            source_text = (src.get('summary')
                           or src.get('full_text')
                           or src.get('abstract') or '')
        elif mode == 1:
            source_text = (src.get('full_text') or '')

        if not source_text:
            continue
        is_match, excerpt, score = auto_detect_match(
            preceding_text, source_text)
        if best_overall is None or score > best_overall[2]:
            best_overall = (num, excerpt, score)

    return best_overall


def auto_detect_match(preceding_text: str, source_text: str,
                      threshold: float = 0.3) -> Tuple[bool, str, float]:
    """
    Non-AI citation validation using text similarity matching.
    Uses SequenceMatcher to find the best matching passage in the source.
    
    Returns: (is_match, best_match_excerpt, similarity_score)
    """
    if not preceding_text or not source_text:
        return False, "", 0.0

    preceding_lower = preceding_text.lower().strip()
    source_lower = source_text.lower()

    # Try to find matching windows in the source text
    best_score = 0.0
    best_excerpt = ""
    window_size = len(preceding_lower)

    # Use SequenceMatcher for overall similarity
    words_preceding = preceding_lower.split()

    # Slide a window across the source text
    source_words = source_lower.split()
    window = max(len(words_preceding), 10)

    for i in range(max(1, len(source_words) - window + 1)):
        chunk = ' '.join(source_words[i:i + window])
        score = SequenceMatcher(None, preceding_lower, chunk).ratio()
        if score > best_score:
            best_score = score
            # Get the original-case version
            orig_words = source_text.split()
            start = max(0, i - 2)
            end = min(len(orig_words), i + window + 2)
            best_excerpt = ' '.join(orig_words[start:end])

    is_match = best_score >= threshold
    return is_match, best_excerpt, best_score


def _coerce_number(value) -> Optional[int]:
    """Best-effort int conversion for a source's 'number' field."""
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def get_citation_order_text(session: ReviewSession) -> str:
    """
    The review body, in reading order, used to decide which source is
    cited first.  Abstract and methods are deliberately excluded — they
    are summaries of the body, so letting them drive the numbering would
    make the reference list order disagree with the narrative.
    """
    chunks = []
    if session.intro:
        chunks.append(session.intro)
    for rs in session.results:
        if rs.get('text'):
            chunks.append(rs['text'])
    if session.discussion:
        chunks.append(session.discussion)
    if session.conclusion:
        chunks.append(session.conclusion)
    return "\n".join(chunks)


def get_cited_numbers_in_order(session: ReviewSession) -> List[int]:
    """Every cited source number, deduped, in order of first appearance."""
    order, seen = [], set()
    for span in find_citation_spans(get_citation_order_text(session)):
        for n in span['numbers']:
            if n not in seen:
                seen.add(n)
                order.append(n)
    return order


def build_sequential_renumber_mapping(session: ReviewSession) -> dict:
    """
    Work out a total old_number -> new_number mapping for the session.

    Cited sources are numbered 1..n in order of first appearance in the
    review body.  Every remaining source keeps its current relative order
    and follows on at n+1..N.  With no citations at all this collapses
    the existing numbering to a gap-free 1..N.

    Returns a dict with:
      'mapping'  : {old: new} covering every known number
      'order'    : cited old-numbers, in first-appearance order
      'phantom'  : cited numbers with no matching source
      'unused'   : old-numbers of sources that are never cited
      'is_noop'  : True if every number already maps to itself
    """
    order = get_cited_numbers_in_order(session)

    existing, seen = [], set()
    for s in session.sources:
        n = _coerce_number(s.get('number'))
        if n is not None and n not in seen:
            seen.add(n)
            existing.append(n)

    phantom = [n for n in order if n not in seen]

    mapping = {}
    nxt = 1
    for n in order:
        mapping[n] = nxt
        nxt += 1
    unused = []
    for n in existing:
        if n not in mapping:
            mapping[n] = nxt
            unused.append(n)
            nxt += 1

    return {
        'mapping': mapping,
        'order': order,
        'phantom': phantom,
        'unused': unused,
        'is_noop': all(old == new for old, new in mapping.items()),
    }


def apply_renumbering(session: ReviewSession, mapping: Dict[int, int]) -> dict:
    """
    Apply a renumbering to a session *in place*.

    This touches everything that stores a source number, not just the
    visible text:
      - in-text citations in every section (including abstract/methods,
        so nothing is left pointing at a stale number)
      - each source's 'number' field, and the order of session.sources
      - citation_validations keys
      - the 'summaries' / 'full_texts' source lists in section_contexts

    Entries referring to numbers absent from `mapping` are stale (the
    source no longer exists) and are dropped; dropping them also
    guarantees a remapped key can never collide with a leftover one.

    Returns a summary dict.
    """
    # ── 1. In-text citations ────────────────────────────────────────
    for attr in ('abstract', 'intro', 'methods', 'discussion', 'conclusion'):
        setattr(session, attr,
                remap_citation_numbers(getattr(session, attr, None), mapping))
    for rs in session.results:
        rs['text'] = remap_citation_numbers(rs.get('text'), mapping)

    # ── 2. Source numbers, then reorder the list to match ───────────
    for s in session.sources:
        old = _coerce_number(s.get('number'))
        if old is not None and old in mapping:
            s['number'] = mapping[old]
    session.sources.sort(
        key=lambda s: (_coerce_number(s.get('number')) is None,
                       _coerce_number(s.get('number')) or 0))

    # ── 3. Citation validations ─────────────────────────────────────
    new_validations = {}
    dropped_validations = 0
    for key, val in session.citation_validations.items():
        old = _coerce_number(key)
        if old is None or old not in mapping:
            dropped_validations += 1
            continue
        new_validations[str(mapping[old])] = val
    session.citation_validations = new_validations

    # ── 4. Per-section context configs ──────────────────────────────
    for cfg in session.section_contexts.values():
        for key in ('summaries', 'full_texts'):
            ref_list = cfg.get(key)
            if not isinstance(ref_list, list):
                continue
            cfg[key] = sorted({
                mapping[n] for n in (_coerce_number(v) for v in ref_list)
                if n is not None and n in mapping
            })

    return {
        'sources_renumbered': len(session.sources),
        'dropped_validations': dropped_validations,
    }


def build_reference_list(session: ReviewSession,
                         cited_numbers: List[int]) -> str:
    """Render the numbered reference list for the given source numbers."""
    citations_by_number = {}
    for s in session.sources:
        n = _coerce_number(s.get('number'))
        if n is not None:
            citations_by_number[n] = (s.get('citation')
                                      or f'Source {n} — citation unavailable')
    return "\n".join(
        f"{n}. {citations_by_number.get(n, f'Source {n} — citation not found')}"
        for n in cited_numbers)


def reorder_citations_for_export(session: ReviewSession) -> ReviewSession:
    """
    Return a copy of the session with citations renumbered by order of
    first appearance and the reference list regenerated.

    Kept for the export path.  If the session has already been renumbered
    in-app this is a no-op, and either way both routes now share the same
    ordering rules so the two can no longer disagree.
    """
    import copy
    export_session = copy.deepcopy(session)

    plan = build_sequential_renumber_mapping(export_session)
    if not plan['order']:
        return export_session

    apply_renumbering(export_session, plan['mapping'])

    # Cited sources always occupy 1..n after renumbering.
    cited_new = list(range(1, len(plan['order']) + 1))
    export_session.citations = build_reference_list(export_session, cited_new)
    return export_session
