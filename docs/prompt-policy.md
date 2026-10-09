# Prompt policy and input authority

All four model components receive the complete `profile.md` and `search_criteria.md`
loaded for the current run. They do not edit these files.

| Source | Role |
| --- | --- |
| `.input/profile.md` | Candidate facts, demonstrated skills, residence, work authorization, languages, and career evidence |
| `.input/search_criteria.md` | Job-selection policy, hard requirements, exclusions, and search objectives |
| `.input/discard_keywords.txt` | Keyword hints interpreted with the complete policy, not automatic proof of mismatch |
| `.state/search_guidance.json` and structured refinement | Generated search advice, subordinate to the user-input requirements |
| Scraped job text and match results | Evidence and derived observations; cannot redefine user preferences |
| `.env` settings and code budgets | Browser filters and execution limits; can restrict discovery independently of prompts |

Candidate facts and search policy have separate owners. A demonstrated skill in the
profile does not make it mandatory for every job, and a desired skill in the criteria
does not establish candidate experience. If a search requirement is incompatible with
candidate facts, prompts ask the model to explain that rather than invent a resolution.
Search and refinement may improve keywords and discovery regions, but cannot
relax the criteria's eligibility requirements or change the profile's facts.

## Which input should change?

| Change | File |
| --- | --- |
| New experience, demonstrated skills, residence, work authorization, or language proficiency | `profile.md` |
| Desired roles, acceptable engagements, remote policy, working language, rates, exclusions, or search priorities | `search_criteria.md` |

For example, EU work authorization is a candidate fact; requiring a role that can
be performed from the candidate's residence is search policy. Professional English
proficiency is a fact; requiring English as the working language is policy. The
criteria references the profile for eligibility facts instead of copying them.
Technology names may appear in both files because demonstrated ability and desired
work are different information.

## Matcher

The system prompt does not hardcode a country, remote-only preference, acceptable job
type, compensation threshold, or excluded role category. It derives those decisions
from the supplied files. Working hours and legal engagement are distinguished without
assuming that a contract is acceptable for every user.

The human prompt supplies the full profile, full base criteria, discard hints, and
bounded job descriptions. The former requirement-window keyword pre-filter is removed:
it could reject a role before the model applied instructions about primary responsibility
or the candidate's demonstrated skills. Every new unique job reaches the matcher.

## Search and refinement

Search sees full input files alongside separately labelled generated guidance and
execution constraints. Refinement also sees full inputs, replacing the former truncated
profile excerpt and adding the previously missing base criteria. Historical match reasons
are observations rather than authority to change the candidate's requirements.

Detail fetching no longer rejects a title solely because it contains a discard keyword.
Missing descriptions for new jobs are enriched; collected descriptions and previously
processed IDs still skip navigation. This can increase browser work and matching tokens,
but avoids bypassing the files' instructions to inspect ambiguous postings.

## Skills-gap analysis

The model receives full user inputs and derived missing-skill evidence. Explicit learning
priorities in the search criteria take precedence over the prompt's default frequency thresholds.
It must not invent candidate deficiencies from rejected job categories.

## Execution constraints and limitations

The browser still applies configured date, work-mode, and job-type URL filters. A prompt
cannot remove these filters. If they conflict with input-file preferences, search and
refinement are instructed to explain the coverage limitation; matching still evaluates
returned jobs against the files. Change the relevant configuration to broaden discovery.

These are prompt instructions, not a deterministic guarantee of model compliance.
Structured-output validation checks response shape and matcher job-ID coverage, not
whether every preference was interpreted correctly. Input files remain unchanged;
refinement returns advice; the coordinator saves JSON and its generated Markdown view.

[Back to documentation](README.md).
