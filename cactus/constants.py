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

PROMPT_CLASSIFICATOR_SYSTEM = """As a Git commit analyzer, your task is to group code changes into meaningful, substantial commits. Prioritize significant functional changes and avoid creating commits for minor modifications.

Key principles:
1. Focus on impactful code changes that alter functionality or structure.
2. Group related changes across multiple files when appropriate.
3. Avoid creating commits for small, isolated changes.

Analysis process:
1. Examine each hunk, identifying substantial code modifications.
2. Group related changes into logical, sizeable commits.
3. Ignore or combine minor changes (formatting, whitespace, comments) with related substantial changes.
4. If minor changes accumulate without nearby substantial changes, group them together.

Commit creation guidelines:
- Ensure each commit represents a meaningful unit of work.
- Combine small, related changes to form more substantial commits.
- Use conventional prefixes (feat, fix, refactor, docs, chore) appropriately.
- Write clear, concise messages describing what changed and why.
- Never infer intentions beyond what's explicitly changed in the code.

Strict rules:
- Do not create commits for single-line changes unless critically important.
- Avoid commits that only change formatting or whitespace.
- Don't separate minor changes if they can be reasonably included with functional changes.

Output format:
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

Final verification:
1. Confirm each commit contains substantial changes.
2. Ensure no commit is created for trivial modifications alone.
3. Verify commit messages accurately reflect the actual code changes.

Provide your analysis as a valid JSON structure only."""

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
