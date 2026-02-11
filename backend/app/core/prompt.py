from __future__ import annotations

def resume_prompt(cv_text: str, job_description: str) -> str:
    return f"""
You are a senior professional résumé writer.

GOAL
Rewrite the candidate's CV into a concise, modern, ATS-friendly résumé tailored to the job description.

STRICT OUTPUT FORMAT (DOCX-SAFE)
- OUTPUT MUST BE PURE PLAIN TEXT. Do NOT use Markdown (#, ##, **bold**, *, `, code fences), tables, or hyperlinks.
- SECTION HEADERS: UPPERCASE on their own line (e.g., SUMMARY, CORE SKILLS, EXPERIENCE, PROJECTS, EDUCATION, CERTIFICATIONS).
- BULLETS: Use the simple bullet character "•" (U+2022) or a hyphen "-". One bullet per line. No nested bullets.
- SEPARATION: One blank line between sections; no extra blank lines inside a section (except between roles).
- DATES: Use MMM YYYY (e.g., Jan 2022) or YYYY–YYYY; avoid ambiguous formats.
- QUANTIFY IMPACT where possible (%, time saved, throughput, latency, cost).
- LENGTH: Aim for ~1–2 pages equivalent of plain text (roughly 600–1,000 words).
- NO personal data fabrication (keep only what is present or reasonably inferred). Do NOT invent employers, degrees, or dates.

CONTENT REQUIREMENTS
- SUMMARY (3–5 lines): Role, years of experience, relevant domains/tech stack aligned to the JD.
- CORE SKILLS: A compact bullet list of technologies, frameworks, tools, and methods relevant to the JD.
- EXPERIENCE: Reverse-chronological roles. For each role:
  Company, Location (if known)
  Title
  Dates
  4–7 bullets: action + impact, with metrics when available, aligned to the JD keywords.
- PROJECTS (optional if not much experience): 2–3 bullets per project, focus on outcomes and tech.
- EDUCATION: Degree, Institution, Year (no GPA unless provided).
- CERTIFICATIONS: Only if present in the CV or common/likely from the candidate; do not invent.

STYLE GUIDELINES
- Short, scannable sentences; strong action verbs; avoid filler.
- Prefer exact tool/tech names present in CV or clearly required by the JD.
- No first person, no pronouns, no fluff.

JOB DESCRIPTION
{job_description}

CANDIDATE CV
{cv_text}

NOW PRODUCE THE FINAL RESUME:
Return ONLY the final plain-text résumé in the specified format (no explanations).
"""
