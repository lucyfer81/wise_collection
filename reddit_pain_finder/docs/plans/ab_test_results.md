# A/B Test Report: Comment-Aware Pain Extraction
**Date:** 2025-12-25 10:43:14
**Test Size:** 10 posts
---

## Overall Metrics

| Metric | Old Method | New Method | Change |
|--------|-----------|-----------|--------|
| Total Pain Events | 2 | 18 | +16 |
| Avg Confidence | 0.087 | 0.514 | +0.426 |
| Avg Problem Length | 8.6 | 67.4 | +58.8 |

## Per-Post Comparison

### 1. I analyzed 3.4 million Reddit comments to build a review sit...

**Subreddit:** SideProject | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 3 |
| Confidence | 0.00 | 0.85 |
| Problem Length | 0 | 100 |
**New Method Sample:**
```
- [post] product reviews are unreliable due to paid commissions, gamed Amazon reviews, sp...
- [comments] Reddit is flooded with bots and fake reviews, making it difficult to trust the i...
```

### 2. Stop building features. Start watching users debug....

**Subreddit:** IndieHackers | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 0 |
| Confidence | 0.00 | 0.00 |
| Problem Length | 0 | 0 |

### 3. A competitor's customer emailed me asking to switch. What I ...

**Subreddit:** SaaS | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 0 |
| Confidence | 0.00 | 0.00 |
| Problem Length | 0 | 0 |

### 4. A game where you learn SQL by solving crimes - SQL CASE FILE...

**Subreddit:** SideProject | **Comments:** 3

| Metric | Old | New |
|--------|-----|-----|
| Events | 2 | 5 |
| Confidence | 0.88 | 0.79 |
| Problem Length | 86 | 90 |
**Old Method Sample:**
```
- using fake company databases with contrived scenarios and questions no one would...
- interface was not smooth and learning progression was not structured...
```
**New Method Sample:**
```
- [post, comments] Existing SQL practice platforms use fake company databases with contrived scenar...
- [post] Some SQL learning tools lack smooth interfaces and structured learning progressi...
```

### 5. Tell HN: AI coding is sexy, but accounting is the real low-h...

**Subreddit:** HN_STORY | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 2 |
| Confidence | 0.00 | 0.88 |
| Problem Length | 0 | 130 |
**New Method Sample:**
```
- [post, comments] repetitive, rule-based tasks like normalizing data from banks/cards/invoices, ap...
- [comments] experiencing 3-4 days of crunch time requiring overstaffing to complete tasks qu...
```

### 6. Show HN: Backlog – a public repository of real work problems...

**Subreddit:** HN_SHOW | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 3 |
| Confidence | 0.00 | 0.90 |
| Problem Length | 0 | 97 |
**New Method Sample:**
```
- [post, comments] forced to sign up or log in just to view problem details, after potentially fill...
- [comments] problem statements on the platform are not useful, with unclear or mismatched de...
```

### 7. Founders: what product are you building, and what’s the real...

**Subreddit:** SaaS | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 0 |
| Confidence | 0.00 | 0.00 |
| Problem Length | 0 | 0 |

### 8. Is this a smart way to pick my next SaaS (copy a proven 8–10...

**Subreddit:** SaaS | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 3 |
| Confidence | 0.00 | 0.85 |
| Problem Length | 0 | 179 |
**New Method Sample:**
```
- [post, comments] seeing only the public-facing 10% of a successful product (the 'iceberg effect')...
- [post, comments] lacking the dedicated development, sales/marketing, and client relations departm...
```

### 9. Become obsessed of your customers (in any business)....

**Subreddit:** Entrepreneur | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 2 |
| Confidence | 0.00 | 0.88 |
| Problem Length | 0 | 79 |
**New Method Sample:**
```
- [post, comments] saying 'yes' to client requests leads to scope creep, resulting in working for f...
- [post, comments] toxic clients drain energy and negatively impact other client relationships...
```

### 10. 📣✅New Human Verification System for our subreddit!...

**Subreddit:** IndieHackers | **Comments:** 5

| Metric | Old | New |
|--------|-----|-----|
| Events | 0 | 0 |
| Confidence | 0.00 | 0.00 |
| Problem Length | 0 | 0 |

## Qualitative Assessment

- **Specificity Improvement:** 6/10 posts show more detailed problem descriptions
- **Evidence Tracking:** 18 pain events now track evidence sources
- **Avg Description Length:** 67 vs 9 chars (+684% change)
