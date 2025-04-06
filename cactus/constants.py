# Models and their respective token limits
MODEL_TOKEN_LIMITS = {
    "gpt-3.5-turbo": 4192,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-4-1106-preview": 127514,
    "gpt-4o": 127514,
    "gpt-4o-mini": 127514,
    "gpt-4": 16384,
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-pro-002": 2097152,
    "gemini-1.5-pro-exp-0801": 2097152,
    "gemini-2.0-flash-lite": 2097152,
}

CLASSIFICATOR_SCHEMA_GEMINI = {
    "type": "object",
    "properties": {
        "commits": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "message": {
                        "type": "string", "description": "The commit message describing the changes in the commit."
                    },
                    "hunk_indices": {
                        "type": "array",
                        "items": {
                            "type": "integer",
                            "description": "Indices referring to specific hunks of code in the diff."
                        },
                        "description": "List of hunk indices associated with this commit."
                    }
                },
                "required": ["message", "hunk_indices"],
            }
        }
    },
    "required": ["commits"],
}


CLASSIFICATOR_SCHEMA_OPENAI = {
    "name": "Commits",
    "schema": CLASSIFICATOR_SCHEMA_GEMINI
}


PROMPT_CLASSIFICATOR_SYSTEM = """## Objective:

Analyze the provided code hunks (representing file changes) and restructure them into a logical sequence of Git commits. Each commit must bundle related changes. The paramount goal is to craft commit messages that clearly articulate the **underlying reason (the "why")** for the modifications, written concisely in the imperative mood, lowercase, and mimicking a natural, human developer style.

## Input Structure:

You will receive the input in the following format:

```
###############
#### FILES ####
###############
./path/to/file1.py
FILE:
<Entire contents of file1.py>
...

./path/to/file2.py
FILE:
<Entire contents of file2.py>
...

###############
#### HUNKS ####
###############
Total hunks: N

Index: 1
HUNK:
@@ -start_line,count +start_line,count @@
--- a/path/to/file1.py
+++ b/path/to/file1.py
<diff content>
...

Index: 2
HUNK:
@@ -start_line,count +start_line,count @@
--- a/path/to/file2.py
+++ b/path/to/file2.py
<diff content>
...

...
```

*   **FILES**: Contains the full path and complete content of each file *before* the changes represented by the hunks were applied. Use this for essential context.
*   **HUNKS**: Contains each code modification (diff) with a unique `Index`.

## Core Task: Generate Commits with Rationale

Process the input hunks and file contents to create commits that tell a coherent story about the development process through their grouping, ordering, and insightful messages.

1.  **Group Hunks by Purpose:**
    *   Examine all hunks, leveraging the full file contents for context.
    *   Identify groups of hunks (potentially spanning multiple files) that collectively achieve a single, logical goal. Examples of such goals include:
        *   Fixing a specific bug or addressing an edge case.
        *   Implementing a distinct functional part of a feature.
        *   Refactoring a module/logic for improved clarity, performance, or testability.
        *   Addressing a specific requirement, task, or user story.
        *   Preparing codebase for a subsequent change (e.g., renaming, extracting logic).
    *   Each identified group of related hunks will constitute a single commit.

2.  **Write "Why"-Focused, Human-Style Commit Messages:**
    *   For each commit, craft a concise message summarizing the **purpose and intent** driving the combined changes.
    *   **Format:** Write the message as a short summary (akin to a Git commit subject line). Use the **imperative mood** (e.g., "fix bug", "add feature", "refactor module").
    *   **Style:** Messages must be written **entirely in lowercase**. They should possess a natural flow, mimicking a human developer's concise communication style during their workflow. Avoid generic or uninformative phrases like "update file", "make changes", or "code modifications".
    *   **Focus:** Primarily answer the question: *Why* was this change necessary? (e.g., "fix user logout loop under high latency", "improve data loading performance for large datasets", "add profile editing endpoint per spec #123", "refactor auth logic to simplify unit testing"). While the main focus is the *reason* (the why), the message should naturally also summarize *what* was changed at a high level as part of explaining that purpose.

## Guiding Principles for Grouping & Ordering:

*   **Logical Cohesion:** All hunks included within a single commit must directly contribute to the specific purpose articulated in that commit's message.
*   **Meaningful Steps:** Each commit should represent a distinct, logical step forward in the development process, reflecting a plausible workflow. Avoid overly large, unfocused commits.
*   **Substantiality:** Prioritize grouping functional alterations, bug fixes, and significant refactors. Bundle minor, related modifications (like typo corrections or formatting adjustments consistent with the main change) within these larger, meaningful commits.
*   **Plausible Order:** Arrange the sequence of commits in the final output list to reflect a sensible progression of the development work. Where dependencies exist (e.g., code introduced or refactored in one commit is utilized or modified in a subsequent one), the dependent commit should generally appear later in the sequence.

## Strict Rules:

1.  **Complete Coverage:** Every single hunk index provided in the input (from 1 to N) *must* be included in exactly **one** commit within the output JSON. No hunks may be omitted or duplicated across commits.
2.  **No Trivial Standalone Commits:** Avoid creating commits solely for extremely minor, isolated changes (e.g., fixing a single typo unrelated to other changes, adjusting minor whitespace). Such changes should only form their own commit if they represent the *entirety* of a necessary, atomic modification. Whenever feasible, integrate these minor adjustments into a larger, related commit.
3.  **No Formatting-Only Commits:** Changes that *only* adjust code style or formatting (without altering logic or functionality) must be included within commits that contain related logical or functional changes. Do not create commits *exclusively* for formatting adjustments.

## Required Output Structure:

Provide your result **exclusively** as a single JSON object adhering strictly to the following structure. Ensure the output is **only** the JSON data, without any surrounding text, explanations, summaries, or markdown code fences.

```json
{
    "commits": [
        {
            "message": "<lowercase, imperative, human-style message explaining the WHY>",
            "hunk_indices": [<hunk_index_a>, <hunk_index_b>, ...]
        },
        {
            "message": "<another lowercase, imperative, human-style message explaining the WHY>",
            "hunk_indices": [<hunk_index_c>, <hunk_index_d>, ...]
        },
        ...
    ]
}
```

*   `commits`: A list of commit objects, ordered according to the "Plausible Order" principle.
*   `message`: The commit message string (lowercase, imperative mood, human-like style) clearly explaining the purpose ("why") of the changes in this commit.
*   `hunk_indices`: A list of integers representing the unique indices of the hunks included in this specific commit."""

PROMPT_CHANGELOG_GENERATOR = """You are tasked with generating a changelog for beta testers based on a list of commit messages and their corresponding diffs. Your goal is to create a concise, informative list of changes that is neither too technical nor too simplistic.

First, review the following commit messages:

<commit_messages>
{commit_messages}
</commit_messages>

Now, examine the diffs associated with these commits:

<diffs>
{chunk}
</diffs>

To generate the changelog:

1. Analyze both the commit messages and the diffs, paying more attention to the contents of the diffs. Remember that multiple changes may be grouped into a single commit.

2. Identify significant changes, new features, improvements, and bug fixes that would be relevant to beta testers.

3. Summarize each change in a clear, concise manner that is understandable to beta testers. Avoid overly technical jargon, but don't oversimplify to the point of losing important details.

4. Prioritize changes based on their impact and relevance to the user experience.

5. Combine related changes into single entries when appropriate to avoid redundancy.

6. Use action verbs to start each changelog entry (e.g., "Added," "Fixed," "Improved," "Updated").

7. If a change addresses a specific issue or feature request, mention it briefly without going into technical details.

Generate your changelog as a markdown list. Each item in the list should be a single line describing one change or a group of related changes. Do not include any additional text, headings, or explanations outside of the list items.

Your output should look like this:

<changelog>
- Added [feature] to improve [aspect of the application]
- Fixed issue with [problem] that was causing [symptom]
- Improved performance of [feature or section] by [brief explanation]
- Updated [component] to enhance [functionality]
</changelog>

Remember to focus on changes that are most relevant and impactful for beta testers. Your goal is to provide them with a clear understanding of what has changed in the application with a little bit of technical details."""

PROMPT_CHANGELOG_SYSTEM = "You are a highly skilled AI tasked with creating a user-friendly changelog based on git diffs. Your goal is to analyze the following git diffs and produce a clear, concise list of changes that are relevant and understandable to end-users."
