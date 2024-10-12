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
    "gemini-1.5-pro-exp-0801": 2097152,
}

PROMPT_CLASSIFICATOR_SYSTEM = """
You are tasked with analyzing a set of code modifications (hunks) and grouping them into logical commits. Your goal is to create a structured representation of these commits that reflects how they would have been created in a real development process.

To complete this task, follow these steps:

1. Analyze each hunk in the context of *all* files contents.
2. Group related hunks together based on the goal they contribute to.
3. Create logical commits from these groups of hunks.
4. Generate a descriptive commit message for each group.
6. Ensure there are no duplicate hunk indices in any commit and that all indexes are used.
7. Avoid small commits with small changes. If there are too many unrelated changes, group them into a single commit at the very end.

Your output should be a JSON structure formatted as follows:

```json
{
    "commits": [
        {
            "message": "commit message here",
            "hunk_indices": [list of hunk indices]
        },
        ...
    ]
}
```

When creating commit messages:
- Use conventional commit format (e.g., "feat:", "fix:", "refactor:", "chore:", etc.)
- Be concise but descriptive
- Focus on the "what" and "why" of the changes, not the "how"

Ensure that the order of commits in your output reflects the likely chronological order in which they would have been created. Earlier, more foundational changes should come before later, more specific changes.

Remember, each commit should contain hunks that are logically related. Try to understand the reason behind each change and group them together if they address the same goal or feature. Make sure you consider the content of each change against other files as well. You can group changes that affect multiple files together.

Provide your final answer ensuring it's a valid JSON structure.
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
