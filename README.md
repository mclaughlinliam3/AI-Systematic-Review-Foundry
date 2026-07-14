# AI Systematic Review Foundry

A desktop application for coordinating, drafting, and verifying systematic
reviews with a human-in-the-loop AI workflow. Retrieve sources from PubMed,
screen them for inclusion, extract evidence by topic, draft every section of
the review, and validate every citation, all from one interface, with an
approval step in front of anything the AI generates.

> **You are the captain of this ship.** Every AI-generated prompt is shown to
> you before it's sent, and every AI-generated response is shown to you before
> it's applied. The Foundry gives you tools to move fast and to check your
> work. It does not replace your judgment. Verifying that the final review is
> accurate is your responsibility.

---

## Table of Contents

- [Installation](#installation)
- [Initial Setup](#initial-setup)
- [Core Concepts](#core-concepts)
- [Workflow](#workflow)
  1. [Set Your Review Topic](#1-set-your-review-topic)
  2. [Gather Sources](#2-gather-sources)
  3. [Screen Sources for Inclusion](#3-screen-sources-for-inclusion)
  4. [Summarize and Assess Sources](#4-summarize-and-assess-sources)
  5. [Extract Topics and Statistics (Optional)](#5-extract-topics-and-statistics-optional)
  6. [Build Your Results Subsections](#6-build-your-results-subsections)
  7. [Write the Review](#7-write-the-review)
  8. [Validate Citations](#8-validate-citations)
  9. [Export](#9-export)
- [Managing Sources Directly](#managing-sources-directly)
- [Customizing Prompts and Model Parameters](#customizing-prompts-and-model-parameters)
- [Sessions, Auto-Save, and Recovery](#sessions-auto-save-and-recovery)
- [Keyboard Shortcuts](#keyboard-shortcuts)
- [Tips for Better Results](#tips-for-better-results)

---

## Installation

### Windows (recommended)

Download the latest installer from the
[Releases page](https://github.com/mclaughlinliam3/AI-Systematic-Review-Foundry/releases/latest)
and run it.

### From source (Windows, macOS, Linux)

1. Install [Python](https://www.python.org/downloads/) 3.10 or later.
2. Download or clone this repository.
3. Install dependencies (PyQt6, `requests`, `openpyxl`, and related packages
   used by the project).
4. Run the app:
   ```bash
   python main_app.py
   ```

---

## Initial Setup

Before you can retrieve sources or use AI features, open **Prompt Settings →
Open Prompt Manager…** and configure your keys.

### 1. NCBI API key (required for source retrieval)

Used to pull sources from PubMed/PMC. It's free.

- Get a key: https://www.ncbi.nlm.nih.gov/datasets/docs/v2/api/api-keys/
- Paste it into the **NCBI API Key** field in Prompt Settings.

### 2. An LLM backend (required for any AI feature)

You need at least one of the following:

**Claude (remote, recommended for quality)**
- Create an account and generate a key at https://platform.claude.com/settings/keys
- Paste it into the **Claude API Key** field, then click **Refresh Models**
  to populate the model dropdown and choose which model to use.
- Click **Test Active API Connection** to confirm it works.
- Note: Claude is a paid API. Running queries costs money based on token
  usage, and you may hit rate limits under heavy use.

**Ollama (local, free, slower)**
- Install [Ollama](https://pypi.org/project/ollama/) and pull a model.
- Set the **Ollama URL** (defaults to `http://localhost:11434`) and select
  your installed model.
- Local models are typically slower and less capable than Claude unless you
  have a powerful GPU.

Switch which backend is active at any time from the **Active API** selector
in Prompt Settings.

### 3. Institutional credentials (optional, experimental)

A field exists in Prompt Settings for institutional login credentials.
Support for using these to unlock full text behind paywalls is still being
investigated and is not yet wired into source retrieval — sources that
aren't open-access may still come back without full text (see
[Managing Sources Directly](#managing-sources-directly) for how to fill
those in by hand).

---

## Core Concepts

A few ideas show up throughout the app and are worth understanding up front:

- **The ✦ icon marks an AI action.** Any button with a ✦ will send a prompt
  to your configured LLM.
- **Prompt approval.** Before an AI prompt is sent, you're shown exactly what
  will be sent and can edit it in place.
- **Output approval.** After the AI responds, you're shown the result and can
  approve it (applying it to your session) or reject it.
- **Context configuration (📋 Context button).** Nearly every AI-writing
  action has a **Context** button next to it. This opens a window where you
  choose exactly what information — which sources, sections, topics, or
  statistics — gets included in that specific prompt. Since AI accuracy drops
  when it's given too much text at once, deliberately limiting context is the
  main tool the Foundry gives you for keeping the AI focused and accurate.
  Many context windows also offer **Auto-Select Top N**, which uses a prior
  relevance rating to pick the best sources for you.
- **Iterative mode.** Available on topic/statistic extraction. When checked,
  the AI reviews sources one at a time, building up its answer incrementally
  instead of seeing everything at once. This is slower and uses more tokens,
  but is generally more accurate about sourcing. Leave it unchecked for small
  numbers of sources to save time.

---

## Workflow

### 1. Set Your Review Topic

In the **Main Review** tab, set your paper topic. Use the **Thesis** button
to write or AI-generate a working thesis statement to anchor the rest of the
review.

### 2. Gather Sources

Switch to the **Sources** tab.

1. Under search terms, either write your own boolean PubMed search strings or
   click **✦ Generate Search Terms** to have the AI propose some. Set how many
   results you want returned per term.
2. Click **🔍 Retrieve Sources** to pull matching records from PubMed/PMC,
   including abstract, full text (when available), and metadata.
3. Some sources won't return an abstract or full text (e.g. the article isn't
   open-access). Click **Fill out All Sources** to retry filling in missing
   metadata via NCBI, or handle individual sources manually — see
   [Managing Sources Directly](#managing-sources-directly).
4. Need something PubMed can't give you? Use **+ Add Manual Source** to enter
   a source by hand, or see [Importing Sources](#managing-sources-directly)
   to bring in sources from a reference manager.

### 3. Screen Sources for Inclusion

Still in the **Sources** tab:

1. Enter your **Inclusion Criteria** and **Exclusion Criteria** at the
   bottom of the tab. This is optional — if you skip it, the AI will use its
   own subjective judgment, which is harder to predict.
2. Choose your **screening mode**: by default screening sends the title and
   abstract to the AI; check **"Use full text instead of abstract"** to send
   the full text instead (slower, more thorough).
3. Click **✦ Screen for Inclusion** to have the AI mark each source as
   included or excluded, with an explanation you can review. You can
   override any verdict manually with the **Include** / **Exclude** buttons,
   or re-run judgment on a single source with **AI Assess ✦**.

### 4. Summarize and Assess Sources

- **✦ Batch Summarize** generates a concise summary for every included
  source that doesn't have one yet. Summaries are what most later steps
  (screening context, topic extraction, section writing) use instead of full
  abstracts/text, to keep prompts short.
- **✦ Risk of Bias** runs a Cochrane RoB 2–based assessment across all
  included sources. This tool is tuned for randomized controlled trials by
  default — for other study types or more specificity, edit the
  `risk_of_bias` prompt (see [Customizing Prompts](#customizing-prompts-and-model-parameters)).
  You can also assess or clear a single source's rating from its detail view.

### 5. Extract Topics and Statistics (Optional)

The review can be written directly from source summaries, but for more
precise control over what evidence goes where, use the **Topics** and
**Statistics (Beta)** tabs. They work almost identically:

- **Topics** are for research questions, e.g. *"What evidence is there that
  SSRIs improve Major Depressive Disorder?"*
- **Statistics** are for pulling specific numerical data points, and offer
  both a **Query (Text Response)** mode and a **Query (Python-parseable)**
  mode for machine-readable output.

For either tab:

1. Write your own topics/questions, or click **✦ Auto-Generate Topics** /
   **✦ AI-Generate Questions Based on Paper Contents** to have the AI propose
   some based on your paper topic and accepted sources.
2. Click **✦ Rate Sources for Topics** (or **for Stats**) to have the AI score
   every source's relevance to every topic. This lets you use **Auto-Select
   Top N** later instead of hand-picking sources each time.
3. Click **✦ AI Write Topic** (or the relevant **Query** button for
   statistics) to have the AI pull information from your configured sources.
   Check **Iterative mode** for higher sourcing accuracy at the cost of
   speed.
4. If a response gets too long, click **✦ Distill** to have the AI condense
   it.
5. Click **🔗 Link to Sections** to have a topic or statistic automatically
   appear in a review section's context whenever you write that section.

### 6. Build Your Results Subsections

Back in **Main Review**, the results section is written piecemeal across
subsections you define. Click **✦ Generate Results Topics** to have the AI
propose subsections, or use **+ Add Subsection** / **- Remove Subsection** to
manage them yourself.

Once subsections exist, return to the **Sources** tab and click **✦ Rate for
Sections** to have the AI score each source's relevance to each subsection —
this feeds the same Auto-Select Top N context tool described above.

### 7. Write the Review

For any section — Abstract, Intro, Methods, each Results subsection,
Discussion, or Conclusion — click **✦ AI Write** to draft it, or **✦ Write
All Sections** at the top to draft everything at once (assuming sources,
criteria, and subsections are already set up).

Default context per section:
- **Intro** and each **Results subsection**: the top 10 rated sources for
  that subsection.
- **Discussion**: the intro and full results.
- **Conclusion** and **Abstract**: the rest of the written paper.

Click **📋 Context** next to any section to override what it sees — for
example, to anchor a section around specific Topics instead of raw sources
(if you do this, also edit that section's prompt so it doesn't reference
context you've removed). Any section can also be edited by hand at any time.
Use the **View** buttons to isolate a single section, or jump to a specific
results subsection with the subsection dropdown and **Go**.

### 8. Validate Citations

The AI can occasionally cite the wrong source for a real piece of
information — this is far more common than outright fabrication, so the
Foundry includes several ways to check citations, format `[x]`.

**Per-citation, right-click a `[x]` in any section's text:**

| Option | What it does |
|---|---|
| View Source(s) | Shows the full source(s) behind the citation |
| ✓ Approve Citation | Marks the citation green |
| ✗ Disapprove Citation | Marks the citation red |
| 🔍 Auto-Detect (regex) | Runs a text-similarity match against the cited source and shows you the best matching passage |
| ✦ AI-Detect | Asks the AI directly whether the citation looks correct |
| 🔄 Find Best Source & Swap | Searches every source's summary for a better match to the cited claim, and shows old vs. proposed new citation side-by-side for you to accept or reject |

**In bulk:** click **Validate All Citations** to auto-detect every
unvalidated citation at once against a similarity threshold you set
(0.0–1.0; lower is more lenient, 0.25–0.40 is a reasonable starting point).
Choose beforehand whether validation should compare against source
**summaries** or **full texts** using the dropdown at the top of the tab.

### 9. Export

Use **File → Export** to produce the final review as:

- **Word Document (.docx)**
- **PDF (.pdf)**
- **LaTeX (.tex)** — you'll need a LaTeX compiler to typeset it

Use **File → Export Spreadsheet** to export your **Sources**, **Topics**, or
**Statistics** tables to `.xlsx` for use outside the app.

If any citations are still unapproved when you export, you'll be warned so
you can double-check them first.

---

## Managing Sources Directly

- **Fixing missing data:** if a source didn't retrieve an abstract or full
  text, open its detail view, use **Open DOI in Browser** to find the
  original article, and paste in the missing information manually.
- **Adding sources by hand:** use **+ Add Manual Source** in the Sources tab.
- **Removing a source:** select it and click **- Remove Source**.
- **Importing from a reference manager:** click **File → Import Sources…**,
  which supports:
  - **RIS files** (`.ris`) — the universal export format from EndNote,
    Zotero, Mendeley, and most databases.
  - **CSV/XLSX with automatic column detection.**
  - **Assisted import** — opens a column-mapper dialog if auto-detection
    doesn't find a good match, letting you manually pair your file's columns
    to the app's source fields.
- **Importing topics or statistics:** use **File → Import CSV/XLSX** for
  either data type.

---

## Customizing Prompts and Model Parameters

Every AI action in the Foundry is backed by an editable prompt template.
Open **Prompt Settings → Open Prompt Manager…** to:

- View and edit the exact wording of any default prompt.
- **Reset to Default** if you want to undo your changes.
- Adjust model parameters (max tokens, temperature, retries, etc.) globally
  or per-prompt.

You'll also see and can edit the fully-assembled prompt immediately before
it's sent, every time you trigger an AI action — so prompt customization
here is for your defaults, not a one-time gate.

---

## Sessions, Auto-Save, and Recovery

- By default, your work is saved to
  `Documents/SystematicReviewFoundry/untitled.json`.
- The app auto-saves to your active session periodically in the background.
- **Ctrl+S** saves immediately; **File → Save As…** changes the name/location
  going forward; **File → Load…** opens a different session and makes it
  active.
- Custom prompts, API keys, and model parameters are stored separately in a
  `config.json` file in your OS's application-data folder, so they persist
  across sessions and projects.

---

## Keyboard Shortcuts

| Shortcut | Action |
|---|---|
| `Ctrl+N` | New project |
| `Ctrl+S` | Save |
| `Ctrl+Shift+S` | Save As… |
| `Ctrl+O` | Load a session |
| `Ctrl+F` | Find (in whichever text field is focused) |
| `Ctrl+Q` | Quit |

---

## Tips for Better Results

- **Keep context small and specific.** The AI's chances of misattributing a
  source or hallucinating rise sharply with how much text it sees at once.
  Use the 📋 Context tools rather than defaulting to "everything."
- **Rate before you write.** Running the relevant "Rate Sources" step before
  writing a section makes Auto-Select Top N genuinely useful, instead of
  hand-picking sources every time.
- **Use Iterative mode for anything source-heavy.** It costs more time and
  tokens, but meaningfully improves sourcing accuracy for topics and
  statistics.
- **Don't skip citation validation.** "Find Best Source & Swap" is the most
  useful single tool here — it catches the common failure mode of a real,
  correct fact attributed to the wrong source, not just outright
  fabrication.
- **Treat AI output as a draft.** Every response is shown to you before it's
  applied, and every section remains manually editable afterward. Use that.
