"""Extract explicit engagement evidence without treating hours as employment status."""

import re

_LABEL = re.compile(
    r"(?:^|\n)\s*(?:contract|employment|engagement|job type|employment type|"
    r"contract type|dienstverband)\s*[:\-]\s*([^\n]{1,160})",
    re.IGNORECASE,
)
_CONTRACT = re.compile(r"\b(?:contract(?:or)?|freelance|freelancer|zzp|b2b|interim)\b", re.I)
_PERMANENT = re.compile(r"\b(?:permanent|indefinite|vast|onbepaalde tijd)\b", re.I)
_ROLE = re.compile(
    r"\b(?:contractor assignment|b2b contract|freelance (?:role|position|assignment)|"
    r"zzp opdracht|interim (?:role|assignment)|permanent (?:role|position)|"
    r"(?:this|the) (?:role|position|engagement|assignment) is "
    r"(?:a |an )?(?:contract|freelance|permanent)(?:or)?\b[^.\n]{0,80})",
    re.I,
)
_NEGATION = re.compile(r"\b(?:not|no|non[- ]?|geen)\s*(?:a\s+|an\s+)?$", re.I)


def _affirmed(text: str, pattern: re.Pattern) -> bool:
    return any(
        not _NEGATION.search(text[max(0, match.start() - 30) : match.start()])
        for match in pattern.finditer(text)
    )


def engagement_evidence(description: str, job_type: str) -> tuple[str, str]:
    """Return contract/permanent only when supported by role-specific evidence.

    Bare full-time metadata describes commitment. General mentions of contracts
    or contractors elsewhere in the description are not engagement evidence.
    Contradictory explicit statements remain unresolved for the matcher to assess.
    """
    candidates = [match.group(1).strip() for match in _LABEL.finditer(description)]
    # Keep preceding words so "not a contractor assignment" is not affirmative evidence.
    candidates += [
        description[max(0, match.start() - 30) : match.end()].strip()
        for match in _ROLE.finditer(description)
    ]
    contract = next((text for text in candidates if _affirmed(text, _CONTRACT)), "")
    permanent = next((text for text in candidates if _affirmed(text, _PERMANENT)), "")
    if contract and permanent:
        return "", f"Conflicting engagement evidence: {contract}; {permanent}"
    if contract:
        return "contract", contract
    if permanent:
        return "permanent", permanent
    if job_type.strip().lower() == "contract":
        return "contract", "LinkedIn job type: contract"
    return "", ""
