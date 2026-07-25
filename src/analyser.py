"""Extraction and aggregation.

Design rule: a posting we could not analyse is never counted as a positive
result. Failures are tracked and reported, not silently defaulted to True.
"""
import os
import json
import requests
from dotenv import load_dotenv

load_dotenv()
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# Every name from the original 42 is preserved, so labels already recorded stay
# valid. Embedded/Industrial exists because German Werkstudent postings lean
# heavily on automotive and Automatisierungstechnik, which a generic
# web-oriented skill list misses entirely.
SKILL_CATEGORIES = {
    "Languages": [
        "Python", "Java", "JavaScript", "TypeScript", "C", "C++", "C#", "Go",
        "Rust", "Kotlin", "Swift", "PHP", "Ruby", "Scala", "R", "MATLAB",
        "Perl", "Dart", "Julia", "Bash", "PowerShell", "VBA", "ABAP", "SQL",
        "HTML", "CSS",
    ],
    "AI / LLM": [
        "LLM", "RAG", "Prompt Engineering", "Fine-tuning", "Embeddings",
        "Vector Database", "LangChain", "LlamaIndex", "Hugging Face", "OpenAI",
        "Gemini", "Claude", "Transformers", "NLP", "Computer Vision", "OpenCV",
        "Stable Diffusion", "AI Agents", "MLOps",
    ],
    "ML / Data": [
        "scikit-learn", "PyTorch", "TensorFlow", "Keras", "Pandas", "NumPy",
        "SciPy", "XGBoost", "LightGBM", "Matplotlib", "Seaborn", "Plotly",
        "Jupyter", "Machine Learning", "Spark", "Hadoop", "Kafka", "Airflow", "dbt", "ETL",
        "Databricks", "Snowflake", "BigQuery", "Tableau", "Power BI", "Looker",
        "SPSS", "SAS", "Statistics",
    ],
    "Web / Frontend": [
        "React", "Next.js", "Vue.js", "Angular", "Svelte", "Tailwind CSS",
        "Sass", "Bootstrap", "Webpack", "Vite", "Redux", "jQuery",
        "Responsive Design", "Accessibility", "Figma", "UI/UX",
    ],
    "Backend / API": [
        "Node.js", "Express", "NestJS", "FastAPI", "Flask", "Django",
        "Spring Boot", ".NET", "Laravel", "Ruby on Rails", "REST API",
        "GraphQL", "gRPC", "Microservices", "WebSockets", "OAuth",
    ],
    "Cloud / DevOps": [
        "AWS", "Azure", "GCP", "Docker", "Kubernetes", "Terraform", "Ansible",
        "Jenkins", "GitHub Actions", "GitLab CI", "CI/CD", "Nginx",
        "Serverless", "Linux", "Prometheus", "Grafana", "Datadog",
    ],
    "Databases": [
        "PostgreSQL", "MySQL", "MongoDB", "Redis", "Elasticsearch", "SQLite",
        "Oracle", "SQL Server", "Cassandra", "DynamoDB", "Neo4j", "Firebase",
    ],
    "Tools / Practices": [
        "Git", "GitHub", "GitLab", "Bitbucket", "Jira", "Confluence", "Agile",
        "Scrum", "Kanban", "TDD", "Unit Testing", "pytest", "JUnit", "Jest",
        "Selenium", "Cypress", "Postman", "SAP", "Salesforce", "Excel",
        "Code Review", "Design Patterns", "Clean Code",
    ],
    "Embedded / Industrial": [
        "Embedded C", "RTOS", "AUTOSAR", "CAN Bus", "PLC", "TIA Portal",
        "Simulink", "LabVIEW", "Microcontroller", "FPGA", "VHDL", "IoT",
        "ROS", "CAD",
    ],
}
ALL_SKILLS = [s for v in SKILL_CATEGORIES.values() for s in v]

# Variants the model reliably emits, plus German equivalents. "SPS" is the
# German term for a PLC and appears constantly in Automatisierungstechnik ads.
_ALIASES = {
    "js": "JavaScript", "ts": "TypeScript", "node": "Node.js", "nodejs": "Node.js",
    "vue": "Vue.js", "vuejs": "Vue.js", "nextjs": "Next.js", "reactjs": "React",
    "golang": "Go", "c sharp": "C#", "csharp": "C#", "dotnet": ".NET",
    ".net core": ".NET", "asp.net": ".NET",
    "postgres": "PostgreSQL", "psql": "PostgreSQL", "mssql": "SQL Server",
    "mongo": "MongoDB", "elastic": "Elasticsearch", "elk": "Elasticsearch",
    "k8s": "Kubernetes", "sklearn": "scikit-learn", "scikit learn": "scikit-learn",
    "tf": "TensorFlow", "pytorch lightning": "PyTorch", "hf": "Hugging Face",
    "huggingface": "Hugging Face", "gpt": "OpenAI", "chatgpt": "OpenAI",
    "anthropic": "Claude", "langchain.js": "LangChain",
    "large language model": "LLM", "large language models": "LLM",
    "retrieval augmented generation": "RAG", "vector db": "Vector Database",
    "vektordatenbank": "Vector Database", "natural language processing": "NLP",
    "sps": "PLC", "speicherprogrammierbare steuerung": "PLC",
    "matlab/simulink": "Simulink", "can": "CAN Bus", "canbus": "CAN Bus",
    "amazon web services": "AWS", "google cloud": "GCP",
    "google cloud platform": "GCP", "microsoft azure": "Azure",
    "ci cd": "CI/CD", "cicd": "CI/CD", "github action": "GitHub Actions",
    "gitlab-ci": "GitLab CI", "rest": "REST API", "restful": "REST API",
    "restful api": "REST API", "unit tests": "Unit Testing",
    "testing": "Unit Testing", "test driven development": "TDD",
    "datenbanken": "SQL", "datenbank": "SQL", "powerbi": "Power BI",
    "ms excel": "Excel", "microsoft excel": "Excel", "tailwind": "Tailwind CSS",
    "scss": "Sass", "html5": "HTML", "css3": "CSS", "ui": "UI/UX", "ux": "UI/UX",
    "linux/unix": "Linux", "unix": "Linux", "shell": "Bash", "shell scripting": "Bash",
    "embedded-c": "Embedded C", "mikrocontroller": "Microcontroller",
    "ml": "Machine Learning", "maschinelles lernen": "Machine Learning",
    "deep learning": "Machine Learning", "künstliche intelligenz": "Machine Learning",
    "data science": "Statistics", "datenanalyse": "Statistics",
}

_SKILL_LOOKUP = {s.lower(): s for s in ALL_SKILLS}
_SKILL_LOOKUP.update(_ALIASES)

# DESC_CHARS was 1600 and that was the single biggest defect in this pipeline.
# German postings put requirements last ("Dein Profil", "Was du mitbringst"),
# so 42% of skill mentions fell past the cutoff and were never seen. Measured
# via src/tune.py: raising it lifted skills F1 from 0.287 to 0.430 (recall
# 0.174 -> 0.292) with no precision cost. Descriptions run to ~3200 chars, so
# 6000 effectively means "never truncate".
BATCH_SIZE  = 8
DESC_CHARS  = 6000


def call_gemini(prompt: str) -> str:
    models = ["gemini-3.5-flash", "gemini-3.1-flash-lite", "gemini-flash-latest"]
    last = None
    for model in models:
        url = ("https://generativelanguage.googleapis.com"
               f"/v1beta/models/{model}:generateContent?key={GEMINI_API_KEY}")
        try:
            r = requests.post(
                url,
                json={
                    "contents": [{"role": "user", "parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0, "responseMimeType": "application/json"},
                },
                timeout=90,
            )
        except requests.exceptions.Timeout:
            last = "timeout"
            continue
        if r.status_code in (429, 500, 503):
            last = f"http {r.status_code}"
            continue
        r.raise_for_status()
        return r.json()["candidates"][0]["content"]["parts"][0]["text"]
    raise RuntimeError(f"All Gemini models unavailable (last: {last})")


PROMPT = """You are analysing real job postings from the German tech market.

For each posting, return an object with exactly these keys:
- "index": the posting's number, copied from the input
- "skills": technical skills the posting asks for. Choose ONLY from this list, copied verbatim: {skills}
  Most postings are in German — match the German term to the English entry ("Datenbanken" to SQL, "SPS" to PLC, "maschinelles Lernen" to Machine Learning, "Kenntnisse in C++" to C++). Include skills listed as "von Vorteil", "wünschenswert" or "idealerweise". Do not include a technology the company merely mentions about itself if it is not asked of the candidate. Return an empty list rather than guessing.
- "experience_years": minimum years of professional experience required as an integer. Use 0 only when the posting genuinely asks for none (typical for Werkstudent/intern roles). If a range is given, use the lower bound.
- "is_realistic_for_student": true only if an enrolled CS student with 0-2 years of professional experience could plausibly be hired. false for roles requiring a completed degree, 3+ years, or senior/lead scope.
- "salary_mentioned": true only if a concrete figure, range, or pay band appears. Generic phrases like "attraktive Vergütung" are false.

Base every judgement only on the text provided. Do not guess from the title alone.
Return a JSON array of exactly {n} objects, one per posting, and nothing else.

Postings:
{body}"""

# title_matches_content was removed in July 2026. Across 365 postings the model
# flagged exactly zero, and all 22 hand-labelled postings came back honest, so
# there was never a negative case to score against. A judgement that only ever
# returns one value measures nothing and costs tokens on every call.


def _coerce(raw: dict, n: int) -> dict | None:
    """Validate one model result. Returns None if it is not usable."""
    if not isinstance(raw, dict):
        return None
    idx = raw.get("index")
    if not isinstance(idx, int) or not (0 <= idx < n):
        return None

    skills, seen = [], set()
    for s in raw.get("skills") or []:
        canon = _SKILL_LOOKUP.get(str(s).strip().lower())
        if canon and canon not in seen:
            seen.add(canon)
            skills.append(canon)

    try:
        yrs = int(raw.get("experience_years") or 0)
    except (TypeError, ValueError):
        yrs = 0

    return {
        "index": idx,
        "skills": skills,
        "experience_years": max(0, min(yrs, 40)),
        "is_realistic_for_student": bool(raw.get("is_realistic_for_student")),
        "salary_mentioned": bool(raw.get("salary_mentioned")),
    }


def extract_batch(jobs: list[dict]) -> list[dict | None]:
    """Return one result per job, positionally aligned. None means not analysed."""
    n = len(jobs)
    body = "\n\n---\n\n".join(
        f"[{i}] {j['title']} — {j['company'] or 'unknown company'}\n"
        f"{j['description'][:DESC_CHARS]}"
        for i, j in enumerate(jobs)
    )
    prompt = PROMPT.format(skills=json.dumps(ALL_SKILLS), n=n, body=body)

    try:
        raw = call_gemini(prompt)
        start, end = raw.find("["), raw.rfind("]") + 1
        parsed = json.loads(raw[start:end]) if start != -1 else None
    except Exception:
        return [None] * n

    if not isinstance(parsed, list):
        return [None] * n

    # Trust the model's index only when it is a clean permutation.
    out: list[dict | None] = [None] * n
    for item in parsed:
        r = _coerce(item, n)
        if r and out[r["index"]] is None:
            out[r["index"]] = r

    # If indices were unusable but the count matches, fall back to order.
    if all(v is None for v in out) and len(parsed) == n:
        for i, item in enumerate(parsed):
            if isinstance(item, dict):
                item["index"] = i
                out[i] = _coerce(item, n)
    return out


def analyse_market(jobs: list[dict], progress_callback=None) -> dict:
    # Off-topic postings (marketing, sales, production planning) leak in through
    # fuzzy search on the job boards. Excluded from every rate, and counted.
    on_topic   = [j for j in jobs if not j.get("off_topic")]
    off_topic  = len(jobs) - len(on_topic)
    analysable = [j for j in on_topic if j.get("description_ok")]
    skipped    = len(on_topic) - len(analysable)

    batches = [analysable[i:i + BATCH_SIZE] for i in range(0, len(analysable), BATCH_SIZE)]
    for bi, batch in enumerate(batches):
        for job, res in zip(batch, extract_batch(batch)):
            job["analysis"] = res
        if progress_callback:
            progress_callback((bi + 1) / max(len(batches), 1),
                              f"Analysing batch {bi + 1} of {len(batches)}")

    for job in jobs:
        job.setdefault("analysis", None)

    analysed = [j for j in on_topic if j.get("analysis")]
    failed   = len(analysable) - len(analysed)

    skill_c, company_c, location_c = {}, {}, {}
    realistic = salary_llm = 0
    exp_years = []

    for job in analysed:
        a = job["analysis"]
        for s in a["skills"]:
            skill_c[s] = skill_c.get(s, 0) + 1
        if job.get("company"):
            company_c[job["company"]] = company_c.get(job["company"], 0) + 1
        if job.get("location"):
            city = job["location"].split(",")[0].strip()
            if city:
                location_c[city] = location_c.get(city, 0) + 1

        realistic  += a["is_realistic_for_student"]
        salary_llm += a["salary_mentioned"]
        exp_years.append(a["experience_years"])

    # Salary: prefer what the source states over what the model infers.
    ground  = [j for j in analysed if j.get("salary_stated") is not None]
    sal_n   = len(ground) or len(analysed)
    sal_hits = (sum(1 for j in ground if j["salary_stated"]) if ground else salary_llm)
    sal_src = "source-reported" if ground else "model-inferred"

    n = len(analysed)
    pct = lambda x: round(x / n * 100) if n else 0

    return {
        "total_jobs":     len(jobs),
        "analysed_jobs":  n,
        "off_topic":      off_topic,
        "skipped_no_text": skipped,
        "failed_analysis": failed,
        "coverage_pct":   round(n / len(jobs) * 100) if jobs else 0,
        "top_skills":     sorted(skill_c.items(),    key=lambda x: -x[1])[:20],
        "top_companies":  sorted(company_c.items(),  key=lambda x: -x[1])[:10],
        "top_locations":  sorted(location_c.items(), key=lambda x: -x[1])[:10],
        "realistic_pct":  pct(realistic),
        "salary_pct":     round(sal_hits / sal_n * 100) if sal_n else 0,
        "salary_basis":   sal_src,
        "salary_n":       sal_n,
        "avg_exp_required": round(sum(exp_years) / len(exp_years), 1) if exp_years else 0,
        "jobs": jobs,
    }
