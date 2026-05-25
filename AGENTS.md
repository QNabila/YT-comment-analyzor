# AGENTS.md

## Project Context

This project is `yt-audience-report`, a local agentic pipeline for turning YouTube audience comments into a structured research report.

It is built specifically for psychology and mental health creators on YouTube. The tool should help these creators understand what their audience is actually going through, not just which videos get views, clicks, or surface-level engagement.

Existing tools like YouTube Studio, TubeBuddy, and similar platforms focus on analytics such as impressions, views, CTR, retention, and subscriber behavior. This project focuses on the audience's lived experience: the struggles, emotional states, unmet needs, questions, stigma signals, and content gaps revealed through comments.

The expected input is a YouTube channel link or handle. The expected outputs are a structured PDF report, Excel workbook, and JSON artifact containing evidence-backed audience insights and video ideas.

The reusable local trigger pattern is:

```bash
python main.py --channel @channelhandle
```

The channel handle or URL should be the only required input for the complete flow. The pipeline should fetch recent videos and comments, run the audience analysis, generate the PDF report, and save it with the channel name and current date in the filename.
The same run should also generate an Excel workbook and JSON artifact with the same channel name and current date in the filename.

## End Goal

Build a local tool where the user can provide a YouTube channel link or handle and receive a PDF audience report.

The finished workflow should support:

- Running a report immediately.
- Running automatically every 2 days.
- Running automatically every 7 days.
- Producing the PDF report without additional manual steps after configuration.

The core product promise is:

```text
YouTube channel link or handle in -> fetched videos and comments -> multi-pass AI analysis -> structured PDF report out
```

## High-Level Pipeline

The pipeline should be designed around these stages:

1. Accept a YouTube channel link or handle.
2. Resolve the input into a channel identity that can be used with the YouTube Data API.
3. Fetch recent videos for that channel.
4. Fetch relevant comment threads and comments for those videos.
5. Normalize and store the fetched source data locally.
6. Run multi-pass AI analysis over the data.
7. Classify comments into useful mental health and audience-research categories.
8. Cluster repeated themes, questions, objections, desires, pain points, and lived experiences.
9. Compare comment themes against the creator's recent video history to detect content blind spots.
10. Synthesize audience insights from the clustered data.
11. Generate practical video ideas grounded in specific comment evidence.
12. Render the final structured report as a PDF.
13. Render a companion Excel workbook for tabular review and reuse.
14. Render a companion JSON artifact for dashboard use.
15. Save or deliver the report files through the configured local workflow.

## Report Data Types

The report should surface insight types that typical analytics platforms do not show mental health creators.

Required report sections or data categories include:

- Who is actually watching: viewer segments by condition or struggle, inferred from what commenters reveal about themselves. Examples include ADHD, OCD, anxiety, burnout, grief, relationship trauma, depression, panic, loneliness, and related lived experiences.
- Core audience profile: synthesize the primary audience from comment evidence, including revealed struggles, life-stage signals, likely age-range indicators when available, and why viewers appear to choose this creator over therapy, generic advice, or other mental health content.
- Emotional state of the audience: whether viewers are arriving hopeful, desperate, frustrated, overwhelmed, confused, ashamed, or in crisis, and how that emotional state shifts across videos.
- Creator trust signals: identify comments explaining why the creator feels clear, safe, practical, accessible, credible, or different from other sources.
- Unmet needs: repeated questions or needs that the audience keeps raising and that have not been clearly answered in the creator's existing video history.
- Specific help requests: direct requests such as "I wish you made a video about...", "Can you explain...", "Nothing out there covers...", or equivalent language.
- High-signal viewers: commenters sharing detailed lived experiences that likely represent a larger silent audience.
- Loyalty and return signals: flag comments showing repeated use, ongoing reliance, saving or screenshotting, returning to videos, or treating the channel as a continuing mental health resource.
- Stigma signals: topics the audience hints at indirectly or cautiously because they may feel shame, fear, embarrassment, or social risk around saying them clearly.
- Content blind spots: themes that repeatedly appear in comments but are absent or underrepresented in the creator's video history.
- Evidence-grounded video ideas: video ideas tied to real comment IDs, not assumptions or generic content strategy advice.

## Required Report Structure

The final PDF report should use this structure unless the user explicitly changes it:

1. Executive Insight Snapshot.
2. Dataset Coverage.
3. Core Audience Profile.
4. Who Is Actually Watching.
5. Emotional Temperature, including a "Why They Trust This Creator" subsection.
6. Top Unmet Needs.
7. Direct Requests Inbox.
8. Stigma And Shame Signals.
9. High-Signal Viewer Stories, including a "Loyalty and Return Signals" note.
10. Content Blind Spots.
11. Evidence-Grounded Video Ideas.
12. Evidence Appendix.

The Core Audience Profile must appear near the top of the report, after Dataset Coverage. It should synthesize who the primary audience appears to be from comment evidence, including:

- Main struggles such as anxiety, fear, emotional regulation, habits, procrastination, sleep or safety, low energy, self-worth, lack of support, neurodivergence, and trauma-aware needs.
- Life-stage signals such as working adults, parents or caregivers, people in therapy or therapy-adjacent contexts, people with limited support, and people managing chronic fatigue or health constraints.
- Likely age-range signals only when comments support them, such as work references, grown children, parenting, therapy-seeking language, or similar explicit signals.
- Why viewers appear to choose the creator, such as concise visuals, clear language, practical tools, direct "no fluff" explanations, professional credibility, or approachable CBT-style teaching.

The Emotional Temperature section must include a "Why They Trust This Creator" subsection. This should surface comments where viewers explain why the content feels different, safer, clearer, more credible, or more accessible than other sources.

The High-Signal Viewer Stories section must include a "Loyalty and Return Signals" note. This should flag comments where viewers mention watching multiple videos, saving or screenshotting content, wanting PDFs or posters, needing recurring reminders, returning during hard periods, or treating the channel as an ongoing resource.

## Report Design Conventions

Keep the final deliverables as a PDF and companion Excel workbook, with a JSON artifact for dashboard use. Do not replace them with a web dashboard unless the user explicitly asks for that.

The PDF should be immediately scannable for a busy creator:

- Follow the visual structure of the mock "Psychology Niche Analysis Suite" report: cover page, segment breakdown, audience voice, patterns and surprises, next video strategy, and evidence appendix.
- Page 1 must include an at-a-glance header card showing total comments analyzed, urgent signals, video ideas, and report date.
- Unmet needs, stigma signals, and content blind spots must use visual severity indicators such as high, medium, and low.
- Video ideas must be styled as distinct cards. Each card should include title, hook, audience need, and comment-ID evidence.
- The evidence appendix must be compact and table-based, not a paragraph list.
- The Excel workbook must show the same data as the PDF in scannable tabs. Use tabs that mirror the PDF structure: Cover Summary, Audience Segments, Audience Voice, Patterns, Video Ideas, and Evidence Appendix.
- The workbook should preserve comment-ID traceability and be useful for sorting, filtering, and reviewing evidence outside the PDF.
- Use only the approved mock report palette for report and dashboard UI: Ink `#203B38`, Deep teal `#31524C`, Sage `#6F9F92`, Olive `#8DA56A`, Clay `#D09B6B`, Lavender `#9F8FB4`, Blue-gray `#6D95AD`, Cream `#F6F3EE`, Card `#FFFDF8`, Soft panel `#E8ECE6`, Border `#D9DED6`, Muted text `#61726E`, High `#B35C4B`, Medium `#B58A45`, Low `#5F8F83`.
- Visuals should support decisions, not decoration. Each visual should help the creator identify what to make, who needs it, why it matters, or what evidence supports it.

## Dashboard Design Conventions

When the user asks for the local dashboard, it should run on localhost with:

```bash
python -m yt_audience_report.dashboard --db-path data/yt-audience-report.sqlite3 --reports-dir reports --port 8000
```

The dashboard should be read-only, unauthenticated, and backed by SQLite plus the generated report JSON. It must not fetch YouTube data during startup. It should show audience segments, emotional temperature, unmet needs, content blind spots, video ideas, high-signal viewer stories, direct requests, and comment volume per video.

## Evidence Standard

Every substantive insight must cite comment IDs.

No vibe-based output. This is a research tool, not a vanity metrics dashboard.

Future agents should treat comment IDs as required evidence links between raw source data, intermediate analysis, final insights, and generated video ideas.

The final report should make it possible to trace each major claim back to the underlying comments that support it.

Do not infer demographics beyond what comments support. Age range, life stage, creator trust, loyalty, and positioning claims must be evidence-qualified and tied to comment IDs.

Label age and life-stage conclusions as weak, moderate, or strong evidence. Weak evidence means a comment only hints at a signal. Moderate evidence means a comment directly mentions one signal, such as work, parenting, therapy, or family role. Strong evidence means multiple comments support the same conclusion.

Separate "viewer says this directly" from "inferred positioning." For example, a viewer saying the creator is clear and concise is direct evidence; concluding that the creator wins on accessible visual teaching is an interpretation that must cite the direct comments supporting it.

## AI Analysis Passes

Future agents should treat the analysis as a multi-pass process, not one large prompt.

Expected passes include:

- Comment classification.
- Viewer segment inference.
- Core audience profile synthesis.
- Emotional state detection.
- Creator trust signal extraction.
- Specific help request extraction.
- Loyalty and return signal extraction.
- Theme clustering.
- Stigma signal detection.
- Content blind spot detection.
- Insight synthesis.
- Evidence-backed video idea generation.
- Report section drafting.

Prefer clear intermediate artifacts between passes so results are debuggable, testable, auditable, and reusable.

## Scheduling

The tool must support three scheduling modes:

- `run_now`: generate a report immediately.
- `every_2_days`: generate a report automatically every 2 days.
- `every_7_days`: generate a report automatically every 7 days.

Future implementations should keep these options explicit in the user-facing flow and internal configuration. Do not replace them with vague intervals or hidden defaults.

## Decisions Future Agents Should Respect

- The project name is `yt-audience-report`.
- The main workflow is local-first.
- The tool is specifically for psychology and mental health YouTube creators.
- The main input is a YouTube channel link or handle.
- The main outputs are a structured PDF report, companion Excel workbook, and JSON artifact.
- The pipeline depends on the YouTube Data API for videos and comments.
- The report should focus on audience lived experience, unmet needs, emotional state, content blind spots, and video ideas.
- The report structure must include Core Audience Profile, Why They Trust This Creator, and Loyalty and Return Signals.
- The report design must include an at-a-glance first page, severity indicators, distinct video idea cards, and a compact evidence appendix.
- The Excel workbook and JSON artifact must preserve the same evidence-backed structure.
- The product is a research and insight tool, not a vanity metrics dashboard.
- Every substantive insight and video idea must cite real comment IDs.
- Audience profile, trust, loyalty, life-stage, age-range, blind spot, and video idea claims must cite real comment IDs.
- The AI workflow should be multi-pass, structured, and auditable.
- Scheduling must include run now, every 2 days, and every 7 days.
- The system should minimize manual work after initial setup.

## Decisions Future Agents Should Not Change Without User Approval

- Do not change the product from a local tool into a hosted SaaS product.
- Do not broaden the target audience beyond psychology and mental health creators.
- Do not change the primary output from PDF to another format.
- Do not remove scheduled runs.
- Do not remove the YouTube Data API dependency unless the user explicitly approves a different data source.
- Do not collapse the analysis into a single opaque AI prompt.
- Do not produce insights without comment ID citations.
- Do not present demographic, age-range, or life-stage claims as certain when the comments only provide signals.
- Do not merge direct viewer statements and inferred creator positioning without clearly distinguishing them.
- Do not turn the product into a generic YouTube analytics, SEO, or growth dashboard.
- Do not prioritize dashboards or visual explorers before the core link-in to PDF-out workflow exists.
- Do not replace the PDF and workbook with a web dashboard.
- Do not make the report text-heavy when the same information can be made more scannable with cards, tables, severity labels, or concise evidence chips.
- Do not generate video ideas from assumptions when comment evidence is missing.

## Implementation Bias

Build in small, verifiable stages. Prefer simple local components before adding infrastructure.

Future agents should make technical decisions that preserve:

- Reproducibility.
- Inspectable intermediate outputs.
- Comment-ID traceability.
- Clear separation between fetching, analysis, scheduling, and rendering.
- A path to testing each pipeline stage independently.
- A final report structure that distinguishes evidence from interpretation.
