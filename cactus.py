#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "2.1.0"
__license__ = "MIT"

import argparse
import os
import time

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import re
import subprocess
import sys

import openai
import pick
from loguru import logger
from rich.console import Console
from thefuzz import fuzz

from grouper import get_modified_lines, group_hunks, stage_changes

SIMILARITY_THRESHOLD = 70

PROMPT_MULTIPLE_SYSTEM = """As a highly skilled AI, I will analyze the provided code diff and generate a list of 5 distinct commit messages that summarize all the changes made in a single message. I will use the Conventional Commits guidelines as a reference, but prioritize creating messages that encompass all changes. The generated commit messages will be ordered from best to worst."""
PROMPT_MULTIPLE_START = """Analyze the following diff and generate a list of 5 commit messages, each summarizing all the changes made. Use the Conventional Commits guidelines as a reference but prioritize encompassing all changes in one message. Provide the commit messages as a descending-ordered list from best to worst, and nothing else.

Conventional Commits guidelines:
1. Commit messages should start with a type (e.g., feat, fix, chore, docs).
2. Optionally, include a scope in parentheses after the type, describing the area of the code affected.
3. The commit message subject must be separated from the type (and scope, if included) by a colon and a space.
4. The subject should be a concise description of the changes.

--- Begin diff ---
"""

PROMPT_MULTIPLE_END = """
--- End diff ---

Best to Worst Commit Messages:
1.
2.
3.
4.
5."""
PROMPT_SINGLE_SYSTEM = """As a highly skilled AI, I will analyze the provided code diff and generate a single commit message that summarizes all the changes made. I will use the Conventional Commits guidelines as a reference, but prioritize creating a message that encompasses all changes."""
PROMPT_SINGLE_START = """Please generate a single commit message that describes all the changes made in the following diff, using the Conventional Commits guidelines as a reference:

--- Begin diff ---
"""

PROMPT_SINGLE_END = """
--- End diff ---

Commit Message: """


def setup_logging(level="DEBUG", show_module=False):
    """
    Setups better log format for loguru
    """
    logger.remove(0)    # Remove the default logger
    log_level = level
    log_fmt = u"<green>["
    log_fmt += u"{file:10.10}…:{line:<3} | " if show_module else ""
    log_fmt += u"{time:HH:mm:ss.SSS}]</green> <level>{level: <8}</level> | <level>{message}</level>"
    logger.add(sys.stderr, level=log_level, format=log_fmt, colorize=True, backtrace=True, diagnose=True)


def setup_openai_token():
    token = input("Enter your OpenAI token: ")
    config_dir = os.path.expanduser("~/.config/cactus")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "openai_token"), "w") as f:
        f.write(token)
    logger.success("OpenAI token saved.")


def load_openai_token():
    config_dir = os.path.expanduser("~/.config/cactus")
    try:
        with open(os.path.join(config_dir, "openai_token"), "r") as f:
            token = f.read().strip()
        return token
    except FileNotFoundError:
        return None


def preprocess_diff(diff):
    lines = diff.split('\n')
    processed_lines = []

    for line in lines:
        # Skip file name and index lines
        if line.startswith('---') or line.startswith('+++') or line.startswith('index'):
            continue
        elif line.startswith('@@'):
            # Extract line numbers and count from the @@ line
            numbers = re.findall(r'\d+', line)
            if len(numbers) == 4:
                from_line, from_count, to_line, to_count = numbers
                processed_lines.append(f'Changed lines {from_line}-{int(from_line) + int(from_count) - 1} to lines {to_line}-{int(to_line) + int(to_count) - 1}')
        elif line.startswith('-'):
            processed_lines.append(f'Removed: "{line[1:].strip()}"')
        elif line.startswith('+'):
            processed_lines.append(f'Added: "{line[1:].strip()}"')

    # Combine processed lines into a single string
    joined_lines = '; '.join(processed_lines)

    return joined_lines


def run(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result.stdout = result.stdout.decode("utf-8").strip()
    result.stderr = result.stderr.decode("utf-8").strip()
    return result

def get_git_diff(context_size):
    # Check if there are staged changes
    result = run("git diff --cached --quiet --exit-code")
    if result.returncode == 0:
        # There are not staged changes
        logger.error("No staged changes found, please stage the desired changes.")
        sys.exit(1)

    # cmd = f"git --no-pager diff --staged --ignore-all-space --ignore-all-space --ignore-blank-lines --ignore-space-change --inter-hunk-context={context_size} "
    # cmd += f"--ignore-submodules --ignore-space-at-eol --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv --unified={context_size}"

    # cmd += "--ignore-submodules --ignore-space-at-eol --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv "
    cmd = f"git diff --inter-hunk-context={context_size} -U2 --minimal -p --staged"
    # cmd += f"--unified=3"
    result = run(cmd)
    if result.returncode != 0:
        logger.error("Failed to get git diff: %s", result.stderr.decode().strip())
        sys.exit(1)
    result = result.stdout
    return result


def fix_message(message):
    pattern_type = "^(([a-zA-Z]+)(\(.*?\))?:\s+)"
    pattern_no_period = "\.$"
    pattern_first_letter = "^[a-zA-Z]+\([a-zA-Z]+\): ([A-Z])"
    pattern_numeric_prefix = "^\d+\s*[-.:\)]\s*"

    # Remove numeric prefixes
    message = re.sub(pattern_numeric_prefix, "", message)
    message = message.strip(" .,\n")

    # Correct the commit type (lowercase)
    match = re.search(pattern_type, message)
    if match:
        commit_type = match.group(0)
        message = message[len(commit_type):]
        message = commit_type.lower() + message[0].lower() + message[1:]

    # Remove periods at the end of the message
    message = re.sub(pattern_no_period, "", message)

    return message


def filter_and_sort_similar_strings(strings, similarity_threshold=90):
    # Sorting the strings based on total similarity scores
    string_scores = []
    for s in strings:
        total_score = sum(fuzz.partial_ratio(s, other_s) for other_s in strings)
        string_scores.append((s, total_score))
    sorted_strings = sorted(string_scores, key=lambda x: x[1], reverse=True)

    # Filtering out similar strings
    unique_strings = []
    for s, _ in sorted_strings:
        if not any(fuzz.partial_ratio(s, unique_s) >= similarity_threshold for unique_s in unique_strings):
            unique_strings.append(s)
    return unique_strings


def send_request(diff):
    messages = []
    pattern = re.compile(r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9_-]+\))?: [a-z].*$",
                         re.IGNORECASE)
    # for ammount, temp, model, single_or_multiple in [(3, 0.6, "gpt-3.5-turbo", "single"), (2, 1.1, "gpt-3.5-turbo", "multiple")]: #(1, 0.95, "gpt-4", "multiple")]:
    for ammount, temp, model, single_or_multiple in [(5, 0.8, "gpt-3.5-turbo", "single")]:
        response = openai.ChatCompletion.create(
            model=model,
            n=ammount,
            top_p=1,
            temperature=temp,
            stop=None if single_or_multiple == "multiple" else ["\n"],
            max_tokens=100,
            messages=[
                {
                    "role": "system",
                    "content": PROMPT_SINGLE_SYSTEM if single_or_multiple == "single" else PROMPT_MULTIPLE_SYSTEM
                },
                {
                    "role": "user",
                    "content": PROMPT_SINGLE_START + diff + PROMPT_SINGLE_END
                               if single_or_multiple == "single" else PROMPT_MULTIPLE_START + diff + PROMPT_MULTIPLE_END
                },
            ],
        )

        # Fix some common issues
        for choice in response.choices:
            content = choice.message.content
            logger.debug(f"am: {ammount}, temp: {temp}, model: {model}, single_or_multiple: {single_or_multiple}, content: {content.splitlines()}")
            lines = content.splitlines()
            if single_or_multiple == "multiple":
                lines = content.splitlines()[:-1]
            for _message in lines:
                messages.append(_message)

    # Filter out similar commit messages
    fixed_messages = []
    for message in messages:
        fixed_message = fix_message(message)
        if not pattern.match(fixed_message):
            continue
        fixed_messages.append(fixed_message)
    unique_messages = filter_and_sort_similar_strings(fixed_messages, SIMILARITY_THRESHOLD)
    return unique_messages


def restore_changes(full_diff):
    with open("/tmp/cactus.diff", "w") as f:
        f.write(full_diff)
        f.write("\n")
    run("git apply --cached --unidiff-zero /tmp/cactus.diff")


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=Formatter)
    PARSER.add_argument("-d", "--debug", action="store_true", help="Show debug messages")

    PARSER.add_argument("n", nargs="?", type=int, default=None, help="Number of commit messages to generate")
    PARSER.add_argument("-a", "--affinitty", type=float, default=0.1, help="Affinity of the model used to group the commit messages (lower is more commits)")
    PARSER.add_argument(
        "-c",
        "--context-size",
        nargs="?",
        type=int,
        default=0,
        help="Context size of the git diff (lines before and after each hunk)")
    PARSER.add_argument("--setup", action="store_true", help="Initial setup of the configuration file")

    args = PARSER.parse_args()

    if args.debug:
        setup_logging("DEBUG")
    else:
        setup_logging("INFO")

    if args.setup:
        setup_openai_token()
        sys.exit(0)

    openai_token = load_openai_token()
    if openai_token is None:
        logger.error("OpenAI token not found. Please run `cactus --setup` first.")
        sys.exit(1)
    openai.api_key = openai_token

    responses = None

    previous_sha = run("git rev-parse --short HEAD").stdout
    full_diff = get_git_diff(args.context_size)
    groups = group_hunks(full_diff, args.n, args.affinitty)

    patches = []
    logger.info(f"Separated into {len(groups)} groups of changes from {sum([len(g) for g in groups.values()])} hunks")
    for n, hunks in enumerate(groups.values(), 1):
        diff = "\n".join([hunk[1] for hunk in hunks])
        responses = send_request(diff)
        clean_responses = set([re.sub(r'(\s)+', r'\1', re.sub(r'\.$', '', r)) for r in responses])
        commit_messages = [choice for choice in clean_responses]
        logger.info(f"Generated commit messages for group {n} with {len(hunks)} hunks: {commit_messages}")
        patches.append((hunks, commit_messages))

    logger.debug(f"Generated {len(patches)} commits for {len(groups)} groups (sizes: {', '.join([str(len(g)) for g in groups.values()])})")

    # unstage all staged changes
    logger.info("Unstaging all staged changes and applying individual diffs...")
    run("git restore --staged .")
    time.sleep(1)

    try:
        for hunks, commit_messages in patches:
            diff = "\n".join([hunk[1] for hunk in hunks])
            stage_changes(hunks)
            os.system('echo -e "\e[1;35mInspect the diff below and press Q when done.\n\n$(git diff --staged --color=always)" | less -R ')

            message, _ = pick.pick(commit_messages, r'\e[1;35m' + "Choose a commit message for the preceding differences. Press Ctrl+C to quit and restore all current changes.", indicator='=>', default_index=0)
            run(f"git commit -m '{message}'")
    except Exception as e:
        logger.error(f"Failed to stage changes: {e}. Will restore the changes and exit.")
        run(f"git reset {previous_sha}")
        restore_changes(full_diff)
        sys.exit(1)
    except KeyboardInterrupt:
        logger.error("Aborted by user. Will restore the changes and exit.")
        run(f"git reset {previous_sha}")
        restore_changes(full_diff)
        sys.exit(1)
