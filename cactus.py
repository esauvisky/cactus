#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "1.1.0"
__license__ = "MIT"

import argparse
import difflib
import os
import re
import subprocess
import sys
import textwrap

import openai
import pick
from loguru import logger
PROMPT_TEMPLATE_FILENAMES = """Craft a commit message that provide an accurate summary of the changes found in the provided git diff, specifically targeting the lines marked with hashtags. Arrange Each message must be in present tense, without punctuation at the end, and easily comprehensible by the team. For changes related to a particular module, file, or library, start the message with its name or identifier, followed by a colon and a space, not including file extensions, if any (e.g., 'main: add parameters for verbosity'). Create multiple diverse alternatives to account for potential misunderstandings. Be aware that the diff contains contextual output to assist in comprehending the alterations, and only lines commencing with "-" or "+" signify the actual modifications. Upon revising the prompt, confirm that it:

    1. Highlights the significance of brevity and precision within commit messages.
    2. Dictates the use of present tense and the absence of punctuation at the end.
    3. Indicates starting commit messages with the module, file, or library's name or identifier for related changes.
    4. Encourages the generation of diverse alternatives for each message to account for potential misunderstandings.
    5. Requests only the commit message in the response, as it will be assessed by an AI model."""

PROMPT_TEMPLATE_GITLOG = """Craft a commit message that provide an accurate summary of the changes found in the provided git diff, specifically targeting the lines marked with hashtags. Arrange Each message must be in present tense, without punctuation at the end, and easily comprehensible by the team. To maintain consistency within the repository, review the list of the latest commits found before the diff but after the line with five dashes ("-----") and use the same commit message style as the convention for the message you generate. This ensures generated commit messages adhere to the repository's preferred style. Create multiple diverse alternatives to account for potential misunderstandings. Be aware that the diff contains contextual output to assist in comprehending the alterations, and only lines commencing with "-" or "+" signify the actual modifications. Upon revising the prompt, confirm that it:

    1. Highlights the significance of brevity and precision within commit messages.
    2. Dictates the use of present tense and the absence of punctuation at the end.
    3. Underscores consistency with the repository's commit message conventions.
    4. Encourages the generation of diverse alternatives for each message to account for potential misunderstandings.
    5. Requests only the commit message in the response, as it will be assessed by an AI model."""

PROMPT_TEMPLATE_CONVCOMMITS = """Craft a commit message that provide an accurate summary of the changes found in the provided git diff, specifically targeting the lines marked with hashtags. Each message must be in present tense, without punctuation at the end, and easily comprehensible by the team. Begin every message with a relevant keyword from the Conventional Commits styleguide, such as "fix:", "feat:", "chore:", "docs:", "style:", "refactor:", "perf:", or "test:". Create multiple diverse alternatives to account for potential misunderstandings. Be aware that the diff contains contextual output to assist in comprehending the alterations, and only lines commencing with "-" or "+" signify the actual modifications. Upon revising the prompt, confirm that it:

    1. Highlights the significance of brevity and precision within commit messages.
    2. Dictates the use of present tense and the absence of punctuation at the end.
    3. Underscores adherence to the Conventional Commits styleguide.
    4. Encourages the generation of diverse alternatives for each message to account for potential misunderstandings.
    5. Requests only the commit message in the response, as it will be assessed by an AI model."""


def sort_strings_by_similarity(string_list):
    similarity = {}

    for i, string1 in enumerate(string_list):
        max_similarity = 0

        for j, string2 in enumerate(string_list):
            if i != j:
                dist = difflib.SequenceMatcher(string1, string2).get_matching_blocks()
                similarity.setdefault(i, {})[j] = dist
                if dist > max_similarity:
                    max_similarity = dist

        similarity[i]["max_similarity"] = max_similarity

    sorted_idx = sorted(similarity, key=lambda k: similarity[k]["max_similarity"], reverse=False)
    sorted_strings = [string_list[idx] for idx in sorted_idx]
    return sorted_strings


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


def get_git_diff(complexity=3):
    # Check if there are staged changes
    result = subprocess.run("git diff --cached --quiet --exit-code", shell=True)
    if result.returncode == 0:
        # There are not staged changes
        logger.error("No staged changes found. Please stage changes first or pass --all.")
        sys.exit(1)

    cmd = f"git --no-pager diff --staged --ignore-all-space --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv --unified={complexity if complexity > 0 else 0}"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if result.returncode != 0:
        logger.error("Failed to get git diff: %s", result.stderr.decode().strip())
        sys.exit(1)
    result = result.stdout.decode().strip()
    lines = result.splitlines()

    diff_files = []
    file_header = None
    file_blocks = []
    block_header = None
    block_lines = []

    for line in lines:
        if line.startswith("diff --git"):
            if block_header:
                file_blocks.append((block_header, block_lines))
                block_lines = []
            if file_header:
                diff_files.append((file_header, file_blocks))
                file_blocks = []
                block_lines = []
            file_header = line
        elif line.startswith("@@"):
            if block_header:
                file_blocks.append((block_header + "\n", block_lines))
                block_lines = []
            block_header = line
        elif line.startswith("---") or line.startswith("+++") or line.startswith("index"):
            continue
        else:
            block_lines.append(line)

    # Append the last block and file
    file_blocks.append((block_header, block_lines))
    diff_files.append((file_header, file_blocks))

    final_diff = []
    for file_header, blocks in diff_files:
        final_diff.append(file_header)
        for block_header, block_lines in blocks:
            final_diff.append(block_header)
            for line in block_lines:
                final_diff.append(line)

    final_diff = "\n".join(final_diff)
    if complexity < 0:
        # FIXME: implement better trimming on the population side
        for _ in range(abs(complexity)):
            final_diff = trim_git_diff(final_diff)

    # TODO: count tokens instead of words
    # SEE: https://platform.openai.com/tokenizer?view=bpe
    if len(final_diff.split()) < 8:
        logger.error("Diff is too small! Check the output of `git diff --staged`.")
        sys.exit(1)
    elif len(final_diff.split()) > 3000:
        raise Exception("Diff is too large.")
    else:
        logger.success(f"Diff has {len(final_diff.split())} words.")

    return final_diff


def trim_git_diff(diff):
    lines = diff.splitlines()
    files = []
    file_ = []
    for line in lines:
        if line.startswith(">"):
            if file_:
                files.append(file_)
                file_ = []
            file_.append(line)
        else:
            file_.append(line)
    files.append(file_)

    trimmed_files = []
    for file_ in files:
        chunks = []
        chunk = []
        for line in file_:
            if line == "@@":
                if chunk:
                    chunks.append(chunk)
                    chunk = []
                chunk.append(line)
            else:
                chunk.append(line)
        chunks.append(chunk)

        chunks = sorted(chunks, key=len)
        if len(chunks) > 2:
            chunks = chunks[2:]
        trimmed_file = "\n".join(["\n".join(chunk) for chunk in chunks])
        trimmed_files.append(trimmed_file)
    return "\n".join(trimmed_files)


def send_request(diff):
    prompt = PROMPT_TEMPLATE_CONVCOMMITS

    result = subprocess.run(
        "git log -n 10 --pretty=format:'%s'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True
    )
    last_commits = result.stdout.decode().strip()
    prompt += f"\n\n-----\n{last_commits}"
    prompt += f"\n\n#####\n{diff}\n#####"
    logger.debug(f'Prompt is: {prompt}')
    response = openai.ChatCompletion.create(
        model="gpt-4",
        n=5,
        top_p=1,
        max_tokens=100,
        messages=[{
            "role": "system", "content": "You are a senior developer specialized in writing git commit messages."
        }, {
            "role": "user", "content": prompt
        }])

    # TODO: automatically split a big diff into several commits,
    # asking the bot to summarize each major change, create a commit message for each,
    # then for each block of changes, we ask it to return which commit message it belongs to.
    logger.debug(f'Response is: {response}')
    return [choice.message.content for choice in response.choices]


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=Formatter)
    PARSER.add_argument("-d", "--debug", action="store_true", help="Show debug messages")

    sub_parsers = PARSER.add_subparsers(dest="command")
    setup_parser = sub_parsers.add_parser("setup", help="Initial setup of the configuration file")
    pick_parser = sub_parsers.add_parser(
        "pick", help="Generates 5 commit messages for staged changes and lets you choose one (default)")

    sub_parsers.default = "pick"
    args = PARSER.parse_args()

    if args.debug:
        setup_logging("DEBUG")
    else:
        setup_logging("INFO")

    if args.command == "setup":
        setup_openai_token()
        sys.exit(0)

    openai_token = load_openai_token()
    if openai_token is None:
        logger.error("OpenAI token not found. Please run `cactus setup` first.")
        sys.exit(1)
    openai.api_key = openai_token

    responses = None
    complexity = 3
    while not responses:
        try:
            diff = get_git_diff(complexity=complexity)
            responses = send_request(diff)
        except Exception as e:
            if "This model's maximum context length is " in str(e):
                logger.warning("Too many tokens! Trimming it down...")
                complexity -= 2
            elif "Diff is too large" in str(e):
                logger.warning("Diff too large! Trimming it down...")
                complexity -= 1
            else:
                raise e

    logger.debug(f'Assistant raw answer:\n{responses}')
    clean_responses = set([re.sub(r'(\s)+', r'\1', re.sub(r'\.$', '', r)) for r in responses])
    commit_messages = [choice for choice in clean_responses]
    message, _ = pick.pick(commit_messages, "Pick a suggestion:", indicator='=>', default_index=0)

    # Make the commit with the chosen commit message
    subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
