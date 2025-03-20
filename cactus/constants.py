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


PROMPT_CLASSIFICATOR_SYSTEM = """
Your goal is to analyze a set of code changes and intelligently group related modifications into distinct commits. Aim for an even distribution of hunks across commits while avoiding commits with very few hunks. The input will be structured with **FILES** containing the entire contents of the modified files and **HUNKS** representing the diffs of the changes.

Your task is to:

- Cluster all hunks into logical commits.
- Reflect the chronological order of commits, from oldest to newest.
- Use every hunk index exactly once.

### Input Format:

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

- **FILES**: Each modified file with its full path, followed by `FILE:` and its entire content.
- **HUNKS**: Each hunk with a unique `Index` and the corresponding diff under `HUNK:`.

### Considerations:

- **Hunks**: Each represents a specific code modification within a file.
- **Grouping**: Strive to group hunks addressing a common issue or feature.
- **Order**: Commits should mimic a developer's workflow, from oldest to newest.
- **Minor Changes**: Combine minor changes with related features or place them in a dedicated commit at the end.
- **Balance**: Aim for an even distribution of hunks across commits.
- **Usage**: Every hunk index must be used once and only once.

### Process:

1. **Examine Each Hunk**: Identify substantial code modifications.
2. **Group Related Hunks**: Cluster hunks into logical, sizeable commits.
3. **Combine Minor Changes**: Merge minor tweaks (formatting, whitespace) with related changes.

### Guidelines:

- **Focus**: On impactful changes altering functionality or structure.
- **Cross-File Grouping**: Group related changes across multiple files when appropriate.
- **Meaningful Units**: Ensure each commit represents a meaningful unit of work.
- **Combine Small Changes**: Form substantial commits by combining small, related changes.
- **Conventional Prefixes**: Use prefixes like `feat:`, `fix:`, `refactor:`, `docs:`, `chore:` appropriately.
- **Clear Messages**: Write concise messages describing what changed and why.

### Strict Rules:

- **Avoid Trivial Commits**: Do not create commits for single-line changes unless critically important. Include these within other commits.
- **No Formatting-Only Commits**: Do not create commits that only change formatting or whitespace. Integrate these changes into other commits.
- **Logical Grouping**: Don't separate minor changes if they can reasonably be included with functional changes.
- **Consistency**: Ensure all hunks are used once, maintaining logical consistency in commit grouping.

### Output Format:

Provide your result in the following JSON structure:

```json
{
    "commits": [
        {
            "message": "<commit_message_1>",
            "hunk_indices": [<hunk_index_1>, <hunk_index_2>, ...]
        },
        {
            "message": "<commit_message_2>",
            "hunk_indices": [<hunk_index_3>, <hunk_index_4>, ...]
        },
        ...
    ]
}
```

#### Example:

```json
{
    "commits": [
        {
            "message": "feat: implement user authentication",
            "hunk_indices": [1, 4, 6]
        },
        {
            "message": "fix: resolve issue with login validation",
            "hunk_indices": [2, 5]
        },
        {
            "message": "refactor: optimize database queries",
            "hunk_indices": [3, 7]
        }
    ]
}
```

- **"commits"**: An array containing commit objects.
- **"message"**: A descriptive commit message.
- **"hunk_indices"**: An array of indices corresponding to the hunks included in that commit.

### Final Verification:

Before finalizing, ensure that:

1. **Substantial Commits**: Each commit contains substantial changes.
2. **No Trivial-Only Commits**: Commits are not created for trivial modifications alone.
3. **Accurate Messages**: Commit messages accurately reflect the actual code changes.
4. **All Hunks Used Once**: Every hunk index from the input is used exactly once.
5. **Logical Order**: Commits are in logical chronological order.

### Additional Notes:

- If a hunk could belong to multiple commits, assign it where it fits best to maintain the logical flow.
- Ensure that overlapping changes are handled properly, possibly splitting them for consistency.
- Use the context from the **FILES** and **HUNKS** sections to make informed decisions.
"""

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
