# C4: Citation Enforcement for the Grounded Co-Pilot

## TL;DR

Use a **layered approach**: the LLM call uses Anthropic's Citations API (grounded
char-offset pointers, no hallucinated references), the raw response is assembled
into a typed Pydantic/Zod answer object that requires a non-empty `citations`
list, and a post-processing validator confirms every cited `document_index` maps
to a real historian row ID before the reply is returned to the operator. If
validation fails, the system returns a safe fallback: "I cannot answer that
without sufficient data — please broaden the time range."

---

## Background

Phase 3 carries a zero-tolerance hallucination requirement: every claim must be
traceable to a specific timestamp, component, and run ID in the historian. Three
failure modes exist: (1) the model invents a fact with no source, (2) the model
cites a source that does not exist in the DB, (3) the model cites a source that
exists but does not actually support the claim. The chosen approach must close
all three.

---

## Options Considered

### 1. System-prompt-only contract

A system prompt rule such as "Never state a fact not supported by a retrieved
row; always append [row_id, timestamp] after each claim" is easy to implement
but relies entirely on the model's compliance. Jailbreaks, long contexts, and
edge cases erode reliability. It closes failure mode (1) probabilistically but
leaves (2) and (3) open. Not sufficient on its own.

### 2. Structured output (JSON schema enforcement)

Claude's `output_config.format` constrains generation to a strict JSON schema,
making it impossible to emit a response that lacks required fields. A schema
requiring `citations: [{row_id, component, timestamp}]` would enforce structure.
**Critical limitation:** Anthropic's API returns a 400 error if both
`citations.enabled` and `output_config.format` are set simultaneously — they are
architecturally incompatible because citations interleave citation blocks with
free text. Structured output alone also does not verify that the cited row_id
actually exists in the DB.

### 3. Post-hoc validator

After the LLM responds, a separate validation step checks every citation
reference against the historian. Catches failure modes (2) and (3), but relies
on the model producing citations in the first place (failure mode 1). Works best
as a second layer on top of something that forces citation generation.

### 4. Anthropic Citations API

Documents are passed as `document` content blocks with `citations: {enabled:
true}`. Claude then returns interleaved text/citation blocks; each citation
carries `document_index` (0-indexed over the provided docs), `cited_text`
(extracted verbatim, not billed as output tokens), and character or block
offsets. This closes failure mode (1): Claude cannot cite text that was not
physically present in the supplied document blocks. Incompatible with structured
outputs, but the response structure is itself deterministic and parseable.

---

## Recommendation: Layered Approach

Three layers applied in sequence:

**Layer 1 — System-prompt contract** (defense in depth)

```
You are a grounded diagnostic assistant. You MUST cite every factual claim
using only the historian rows provided in the document blocks. If the retrieved
rows do not support an answer, reply exactly: INSUFFICIENT_DATA.
```

**Layer 2 — Anthropic Citations API** (structural guarantee on Layer 1)

Each retrieved historian row is injected as a `custom content` document block
(one block per row, using `type: content`). `citations: {enabled: true}` is set
on every block. Claude's response is a sequence of text + citation objects. The
`document_index` in each citation maps back to the position of the historian row
in the request array.

**Layer 3 — Post-processing validator** (closes failure modes 2 and 3)

```python
def validate_response(response_blocks, historian_rows: list[dict]) -> bool:
    """
    Returns True if every citation points to a row that exists and whose
    content substring-matches the cited_text.
    """
    for block in response_blocks:
        if block.get("type") != "text":
            continue
        for citation in block.get("citations", []):
            idx = citation["document_index"]
            if idx >= len(historian_rows):
                return False          # (2) out-of-range index
            row_text = historian_rows[idx]["raw_text"]
            if citation["cited_text"] not in row_text:
                return False          # (3) text mismatch
    # check at least one citation exists in the whole response
    all_citations = [c for b in response_blocks
                       for c in b.get("citations", [])]
    return len(all_citations) > 0     # (1) no citations at all → reject
```

**Fallback when validator rejects**

```python
FALLBACK = (
    "I cannot answer that question without sufficient historian data. "
    "Please broaden the time range or check that the relevant component "
    "has recorded data in this period."
)
```

**Answer JSON schema** (assembled after validation, for the UI layer)

```json
{
  "answer_text": "string",
  "severity": "INFO | WARNING | CRITICAL",
  "citations": [
    {
      "row_id": "string",
      "component": "string",
      "timestamp": "ISO8601",
      "cited_text": "string"
    }
  ]
}
```

The citations list is populated from the validated Citation API objects, mapping
`document_index` back to the historian row metadata.

---

## Open Questions

- Custom content documents (one block per historian row) vs. a single large plain
  text document: custom content is preferred because it gives exact block-level
  citation indices aligned with row IDs, avoiding sentence-chunking ambiguity.
- How many rows to inject per query: must stay within the context window; suggest
  a retrieval cap of 20-50 rows with a relevance ranking step (BM25 or cosine)
  before the Citations API call.
- Streaming: citations arrive as `citations_delta` events; the validator must run
  after the stream closes, not mid-stream.
- Whether to surface `cited_text` verbatim in the UI or only the row metadata;
  verbatim is more trustworthy for judges.

---

## References

- [Anthropic Citations API docs](https://platform.claude.com/docs/en/build-with-claude/citations)
- [Introducing Citations on the Anthropic API](https://www.anthropic.com/news/introducing-citations-api)
- [Simon Willison — Anthropic's new Citations API](https://simonwillison.net/2025/Jan/24/anthropics-new-citations-api/)
- [Structured Outputs incompatibility note](https://platform.claude.com/docs/en/build-with-claude/structured-outputs)
- [Citation-Enhanced Generation for LLM-based Chatbots (ACL 2024)](https://aclanthology.org/2024.acl-long.79.pdf)
- [CiteGuard: Faithful Citation Attribution via RAG Validation](https://arxiv.org/html/2510.17853v3)
- [Detecting and Correcting Reference Hallucinations in Deep Research Agents](https://arxiv.org/html/2604.03173)
- [Zod + LLMs: Validate AI Responses](https://dev.to/pavelespitia/zod-llms-how-to-validate-ai-responses-without-losing-your-mind-4c5j)
- [7 Ways to Reduce Hallucinations in Production LLMs](https://www.kdnuggets.com/7-ways-to-reduce-hallucinations-in-production-llms)
