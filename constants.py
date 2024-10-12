PROMPT_CLASSIFICATOR_SYSTEM = """Your goal is to analyze a set of code changes and intelligently group related modifications into distinct commits, ensuring an even distribution of hunks across commits and avoiding commits with very few hunks. Given a JSON object containing the contents of modified files and a list of hunks (individual code modifications) with unique indices, your task is to cluster these hunks into logical commits. The order of the commits should reflect the chronological order in which they would have been created, from the oldest to the newest.

Consider the following:

- **Each hunk represents a specific code modification within a file.**
- **You should strive to group hunks that address a common issue or feature into the same commit.**
- **The order of commits should reflect a logical workflow, mimicking a developer's process, starting with the oldest commit and progressing to the newest.**
- **Minor changes (e.g., adding imports, fixing typos) should be grouped with related features or placed in a dedicated commit at the end.**
- **Aim for a balanced distribution of hunks across commits.**
- **Every hunk index should be used once and only once.**

Your output should be a JSON structure formatted as follows:

```json
{
    "commits": [
        {
            "message": "refactor: prepare things for new version",
            "hunk_indices": [0, 1, 5, 11, 12, 13]
        },
        {
            "message": "refactor: cleanup code, improve readability and move things around",
            "hunk_indices": [4, 9]
        },
        {
            "message": "feat: implement support for X",
            "hunk_indices": [3, 2, 6, 7, 8]
        },
        {
            "message": "chore: random tweaks, bump version, etc.",
            "hunk_indices": [10, 14]
        ...
    ]
}
```

Within this structure:
   - `"commits"`: This is the top-level key containing an array of commit objects.
   - Each object within `"commits"` represents a single commit and includes:
      - `"message"`: A concise and descriptive commit message summarizing the changes within this commit.
      - `"hunk_indices"`:  An array of indices, each pointing to a specific hunk belonging to this commit.
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
