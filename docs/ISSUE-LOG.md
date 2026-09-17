# Issue log

Anything that took the developer and their agent more than one attempt to
work out. This is the record of *how* an answer was reached, not just what
the answer was — if the project lead has to understand a complex issue
later, this is where that reasoning lives. See
[`TEAM-AGENT-BRIEF.md`](./TEAM-AGENT-BRIEF.md) §6. Newest entries at the top.
Never delete an entry, even a wrong turn — a dead end is worth recording too.

---

## Entry template

Copy this for each issue:

```
### <YYYY-MM-DD> — <short title>

**Reported by:** developer / agent
**Where:** <file, endpoint, or command>

**What was expected:**
<one or two lines>

**What actually happened:**
<paste the real output or behaviour, not a paraphrase>

**What was tried, in order:**
1. <attempt> → <what that showed, even if it didn't fix it>
2. <attempt> → <what that showed>
...

**Root cause:**
<once found — if the session ended without finding it, say so plainly
instead of guessing>

**Fix (or: still open, handed off because ___):**
<what changed, or the honest state it was left in>

**Where this is covered going forward:**
<a test that now catches this, or "nothing yet — flagged for follow-up">
```

---

<!-- Newest entries go here, above this line. -->
