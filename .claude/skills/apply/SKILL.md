---
name: apply
description: Draft and iterate on a tailored resume/CV or cover letter for a job, using the user's rules and evidence. Use for /apply, and whenever the user signals any intent to work on a resume, CV, cover letter, job application, bio, LinkedIn summary or application answers, even indirectly (e.g. "help me apply to this", "should I go for this role?", "can you tighten this bullet?", a pasted job link or job description, or a picked listing from the brief).
argument-hint: "[listing number | job URL | pasted job description]"
---

# Resume and cover letter drafting loop

Help the user produce an honest, tailored resume or cover letter, then keep improving both the draft and the rules behind it. The user approves everything and submits everything. Never submit an application.

## Step 0: Offer first when the user didn't ask directly

- If the user ran `/apply` or explicitly asked for a draft, go to Step 1.
- If you detected intent from their message, make a one-line offer first, then wait: "I can help with this using your resume rules and evidence: want me to start a draft?" Do what they originally asked as well, if it stands alone (e.g. tightening one bullet).
- If they decline, drop it. Don't offer again this session unless they raise a new role.

Read `persona` from `state/profile.json`. Use the persona's voice for offers and chat around the work. **Resume and cover letter text is always neutral and professional, never in persona.**

## Step 1: Load context

Read, in this order. Later files override earlier ones:

1. `rules/global_cv_rules.md`: the default rules
2. `state/cv/rules.md`: this user's rules (private)
3. `state/cv/evidence.md`: this user's confirmed facts, metrics and contact details (private)
4. Any matching file in `state/applications/`

If `state/cv/` doesn't exist, this is a first run. Ask for the user's current resume, or use what onboarding captured. Then create `state/cv/evidence.md` with what you can confirm and an empty `state/cv/rules.md`. `state/` holds personal data and must never be committed.

## Step 2: Identify the role and the output

- **Listing number:** find it in today's brief in this conversation. If it isn't there, read `state/morning_report_ready.json` or ask for the link.
- **URL:** read the full posting. If the page is empty because it renders in JavaScript, try fetching the raw HTML, then ask the user to paste it.
- **Pasted description:** use it as given.
- **No role:** offer a general-purpose draft.

Never score or draft from a job title alone. Ask whether they want a resume, cover letter, or both, unless they already said.

## Step 3: Fit check before drafting

Show a short table of every minimum and preferred qualification, the evidence, and a status of Met, Partial or Gap. Add level, location and pay if the posting gives them.

Lead with the verdict. If a minimum qualification is a real gap, say so plainly before any drafting, and let the user decide whether to continue. Never hide a gap or word around it.

## Step 4: Fill evidence gaps

Search `state/cv/evidence.md`, past applications, and any connected documents the user has pointed to. Ask for what's still missing in one batch, and only for facts that would change the draft. Record confirmed answers in `state/cv/evidence.md` straight away, with the date. Unconfirmed claims go in the draft as `[bracketed placeholders]`, never as stated facts.

## Step 5: Draft in chat

Show the complete draft in the reply, including unchanged sections. Never write "same as before". Save it to `state/applications/<company>_<role>.md` with the fit table, a known-gaps list, and a status line.

Cover letter: finish the resume first, then research the company and share what you found. Motivation must come from the user, so ask them for it. Never invent it.

## Step 6: Iterate on the draft and the rules

After each draft, ask what's next: **change the draft, change the rules, or make the PDF**.

When the user corrects something, work out what kind of change it is:

- **One-off:** change this draft only.
- **New or corrected fact:** update `state/cv/evidence.md` and every open draft it affects.
- **Lasting preference:** propose a rule in one sentence, and ask before adding it. On approval, add it to `state/cv/rules.md` with the date and why. Don't change rules silently.

If the same kind of correction or gap comes up across applications, point it out and suggest something concrete: a new rule, a piece of evidence to gather, or a project that would close the gap.

Only edit `rules/global_cv_rules.md` if the user says they're improving the public defaults. It must never contain personal facts.

## Step 7: Produce the PDF

Once the user approves, write the content as JSON next to the application file, following the schema at the top of `tools/render_cv.py`, then run:

```
python3 tools/render_cv.py state/applications/<name>.cv.json --out state/applications/<Resume_Name_Company>.pdf --final
```

- `--final` refuses to render while any `[placeholder]` remains. Resolve them with the user. Never delete one just to get past the check.
- Leave out `--final` for a review copy, with placeholders highlighted.
- If Chrome isn't available, the script writes HTML and says so. Tell the user to print it to PDF.

Then open the PDF, update the status line, and remind the user to read it before submitting.
