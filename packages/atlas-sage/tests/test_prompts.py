import string

from atlas_sage import prompts
from atlas_sage.prompts import (
    CRITIC_USER_TEMPLATE,
    INTERVIEW_REVISE_USER_TEMPLATE,
    INTERVIEW_WRITER_USER_TEMPLATE,
    REVISE_USER_TEMPLATE,
    SCREENING_REVISE_USER_TEMPLATE,
    SCREENING_WRITER_USER_TEMPLATE,
    WRITER_USER_TEMPLATE,
)


def test_writer_template_demands_inline_citations():
    out = WRITER_USER_TEMPLATE.format(topic="t", nicho="java", sources_block="[1] u")
    assert "[^" in out  # instructs footnote citations


def test_critic_template_mentions_citation_check():
    out = CRITIC_USER_TEMPLATE.format(
        sources_block="[1] u", writer_output="draft", nicho="java"
    )
    assert "[^n]" in out
    assert '"approved"' in out  # JSON schema preserved


def test_revise_template_formats_with_issues():
    out = REVISE_USER_TEMPLATE.format(
        sources_block="[1] u",
        draft="---\n## Summary\nx [^1]\n## Interview Q&A\nq [^1]",
        issues="- Summary: wrong claim about Unigram",
        nicho="llms",
    )
    assert "wrong claim about Unigram" in out
    assert "## Summary" in out


def extract_skeleton(template: str) -> str:
    parts = template.split("---", 2)
    return "---" + parts[1] + "---"


def test_revise_templates_include_skeletons():
    interview_skeleton = extract_skeleton(INTERVIEW_WRITER_USER_TEMPLATE)
    screening_skeleton = extract_skeleton(SCREENING_WRITER_USER_TEMPLATE)

    assert interview_skeleton != screening_skeleton

    assert interview_skeleton in INTERVIEW_REVISE_USER_TEMPLATE
    assert screening_skeleton in SCREENING_REVISE_USER_TEMPLATE


# Placeholders that carry a whole document rather than a short label. A short
# label may legitimately repeat: VOICE_INTERVIEW_TEMPLATE puts {title} in the
# frontmatter and again in a heading, which is correct.
DOCUMENT_FIELDS = {
    "profile",
    "jd",
    "draft",
    "writer_output",
    "sources",
    "transcript",
    "plan_block",
}


def test_no_template_pastes_a_whole_document_twice():
    """A placeholder named inside the instructions is substituted, not quoted.

    The revise prompt gained "reproduce the frontmatter from your previous draft
    (`{draft}`)". These are format strings, so that parenthetical expanded into a
    second full copy of the document: double the input bill, and an instruction
    with a 7000-character document wedged into the middle of its own sentence.
    Nothing caught it, because every other test in this file reads the template
    raw and never formats it.
    """
    templates = {
        name: value
        for name, value in vars(prompts).items()
        if name.endswith("_TEMPLATE") and isinstance(value, str)
    }
    assert templates, "no templates found - did the naming convention change?"

    for name, template in templates.items():
        fields = {f for _, f, _, _ in string.Formatter().parse(template) if f}
        out = template.format(**{f: f"<<{f}>>" for f in fields})
        for field in fields & DOCUMENT_FIELDS:
            count = out.count(f"<<{field}>>")
            assert count == 1, f"{name} substitutes {{{field}}} {count} times"


def test_technical_critic_judges_coverage_of_the_posting_not_only_each_question():
    """Ten excellent RAG questions for a posting that also demands fine-tuning
    is a failed interview, and nothing caught it.

    The technical critic judged question by question - recitable, no number, no
    consequence, off-target, ungrounded - and never asked whether the set as a
    whole covered what the posting requires. The screening critic already checks
    its set; this is the same check on the other track.

    The rule matters most where the candidate is weakest: a demand the posting
    makes and the profile does not evidence must still be asked, precisely
    because there is no experience to fall back on.
    """
    from atlas_sage.prompts import INTERVIEW_CRITIC_USER_TEMPLATE

    out = INTERVIEW_CRITIC_USER_TEMPLATE.format(
        profile="Java-first, no LoRA", jd="LoRA, RAG, observability", writer_output="d"
    )
    lowered = out.lower()
    assert "as a whole" in lowered, "the set must be judged, not only each question"
    assert "uncovered" in lowered or "coverage" in lowered
    assert '"approved"' in out, "JSON schema preserved"


def test_technical_critic_will_not_accept_skipping_a_gap():
    from atlas_sage.prompts import INTERVIEW_CRITIC_USER_TEMPLATE

    out = INTERVIEW_CRITIC_USER_TEMPLATE.format(profile="p", jd="j", writer_output="d")
    assert "does not evidence" in out.lower()


def test_revise_handles_a_coverage_issue_by_replacing_not_rewording():
    """A "set" issue is not fixed by making an existing question harder.

    The critic can now reject because the posting demands something no question
    touches. Left alone, the revise instruction ("make each rejected question
    harder") would answer that by sharpening what is already there, and the
    uncovered demand would stay uncovered through both passes.
    """
    from atlas_sage.prompts import INTERVIEW_REVISE_USER_TEMPLATE

    out = INTERVIEW_REVISE_USER_TEMPLATE.format(
        profile="p", jd="j", draft="d", issues="- set: no question on fine-tuning"
    )
    lowered = out.lower()
    assert '"set"' in lowered
    assert "replacing" in lowered or "replace" in lowered
    assert "rewording" in lowered or "reword" in lowered
