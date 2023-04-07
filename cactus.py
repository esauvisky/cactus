#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "2.0.2"
__license__ = "MIT"

import argparse
import os

os.environ['TF_CPP_MIN_LOG_LEVEL'] = '3'
import pydoc
import re
import subprocess
import sys

import openai
import pick
from loguru import logger
from rich.console import Console
from fuzzywuzzy import fuzz

from grouper import get_hunks, stage_hunks

PROMPT_PREFIX_SINGLE = "Craft a well-structured and concise commit message that accurately encapsulates the changes described in the given git diff, specifically between lines marked with hashtags. The commit message should employ present tense, without punctuation at the end, and be easily comprehensible by the team. "
PROMPT_PREFIX_MULTIPLE = "Craft distinct and concise commit messages that provide an accurate summary of the changes found in the following git diff, specifically targeting the lines marked with hashtags. Each message MUST be in present tense, without punctuation at the end, and be easily comprehensible by the team. "

PROMPT_TEMPLATE_FILENAMES = "For changes related to a particular module, file, or library, start the message with its name or identifier, followed by a colon and a space, not including file extensions, if any (e.g., 'main: add parameters for verbosity')."
PROMPT_TEMPLATE_GITLOG = "To maintain consistency within the repository, review the list of the latest commits found before the diff but after the line with five dashes ('-----') and use the same commit message style as the convention for messages you generate. This ensures generated commit messages adhere to the repository's preferred style. "
PROMPT_TEMPLATE_CONVCOMMITS = "Commits MUST be prefixed with a suiting type from the Conventional Commits styleguide, followed by a colon and a space. An optional scope MAY be provided after a type, describing a section of the codebase, enclosed in parent­hesis, e.g., 'fix(parser): '. "

PROMPT_SUFFIX_SINGLE = "Be aware that the diff contains contextual output to assist in comprehending the alterations, and only lines commencing with '-' or '+' signify the actual modifications. Upon revising the message, confirm that it:\n"
PROMPT_SUFFIX_MULTIPLE = "Be aware that the diff contains contextual output to assist in comprehending the alterations, and only lines commencing with '-' or '+' signify the actual modifications. Create multiple diverse alternatives to account for potential misunderstandings and shuffle the messages order. Upon revising each message, confirm that it:\n"

PROMPT_CHECKLIST_PREFIX = """
    1. Highlights the significance of brevity and precision within commit messages.
    2. Dictates the use of present tense and the absence of punctuation at the end.
    3. Describe all alterations within a single sentence."""
PROMPT_CHECKLIST_FILENAMES = """
    4. Indicates starting commit messages with the module, file, or library's name or identifier for related changes."""
PROMPT_CHECKIST_GITLOG = """
    4. Underscores consistency with the repository's commit message conventions."""
PROMPT_CHECKLIST_CONVCOMMITS = """
    4. Underscores adherence to the Conventional Commits guideline."""
PROMPT_CHECKLIST_SUFFIX_SINGLE = """
    5. Requests only the commit message in the response, in a single line, as it will be assessed by an AI model."""
PROMPT_CHECKLIST_SUFFIX_MULTIPLE = """
    5. Encourages the generation of diverse alternatives for each message to account for potential misunderstandings.
    6. Requests only the commit messages in the response, one per line, as they will be assessed by an AI model."""


def generate_prompt_template(prompt_type, template_type):
    prompt = PROMPT_PREFIX_SINGLE if prompt_type == "single" else PROMPT_PREFIX_MULTIPLE

    if template_type == "filenames":
        prompt += PROMPT_TEMPLATE_FILENAMES
    elif template_type == "gitlog":
        prompt += PROMPT_TEMPLATE_GITLOG
    else:
        prompt += PROMPT_TEMPLATE_CONVCOMMITS

    prompt += PROMPT_SUFFIX_SINGLE if prompt_type == "single" else PROMPT_SUFFIX_MULTIPLE

    prompt += PROMPT_CHECKLIST_PREFIX

    if template_type == "filenames":
        prompt += PROMPT_CHECKLIST_FILENAMES
    elif template_type == "gitlog":
        prompt += PROMPT_CHECKIST_GITLOG
    else:
        prompt += PROMPT_CHECKLIST_CONVCOMMITS

    prompt += PROMPT_CHECKLIST_SUFFIX_SINGLE if prompt_type == "single" else PROMPT_CHECKLIST_SUFFIX_MULTIPLE

    return prompt


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


def get_git_diff_groups():
    # Check if there are staged changes
    # result = subprocess.run("git diff --cached --quiet --exit-code", shell=True)
    # if result.returncode == 0:
    #     # There are not staged changes
    #     logger.error("No staged changes found. Please stage changes first or pass --all.")
    #     sys.exit(1)

    cmd = "git --no-pager diff --ignore-all-space --ignore-all-space --ignore-blank-lines --ignore-space-change "
    cmd += "--ignore-submodules --ignore-space-at-eol --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv "

    cmd = "git diff --minimal --unified=1"
    # cmd += "--ignore-submodules --ignore-space-at-eol --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv "
    # cmd += f"--unified=3"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)
    if result.returncode != 0:
        logger.error("Failed to get git diff: %s", result.stderr.decode().strip())
        sys.exit(1)
    result = result.stdout.decode().strip()
    return get_hunks(result)


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


def filter_similar_lines(lines, threshold=0.8):
    unique_lines = []

    for line in lines:
        # Check for similarity with all unique_lines using fuzz.partial_token_sort_ratio
        similar_lines = [
            unique_line for unique_line in unique_lines if fuzz.partial_token_sort_ratio(line, unique_line) >= threshold * 100
        ]

        # If we find any similar lines, continue to the next line
        if similar_lines:
            continue

        # Otherwise, add the line to unique_lines
        unique_lines.append(line)

    logger.debug(f"Removed {len(lines) - len(unique_lines)} similar lines")
    return unique_lines


def send_request(diff):
    messages = []
    pattern = re.compile(r"^(build|chore|ci|docs|feat|fix|perf|refactor|revert|style|test)(\([a-z0-9_-]+\))?: [a-z].*$",
                         re.IGNORECASE)
    for ammount, temp, model, single_or_multiple in [(2, 0.3, "gpt-3.5-turbo", "single"), (5, 1, "gpt-3.5-turbo", "multiple"), (2, 0.95, "gpt-4", "single")]:
        prompt = generate_prompt_template(single_or_multiple, "convcommits")

        logger.trace(f'Template is: {prompt}')
        prompt += f"\n#####\n{diff}\n#####"
        logger.trace(f'Prompt is: {prompt}')

        response = openai.ChatCompletion.create(
            model=model,
            n=ammount,
            top_p=1,
            temperature=temp,
            stop=None if single_or_multiple == "multiple" else ["\n"],
            max_tokens=50,
            messages=[{
                "role": "system",
                "content": "You are a senior developer with over 30 years of experience dedicated in writing git commit messages following the Conventional Commits guideline.",
            }, {
                "role": "user",
                "content": prompt,
            }])

        # Fix some common issues
        for choice in response.choices:
            content = choice.message.content
            logger.trace(f"am: {ammount}, temp: {temp}, model: {model}, single_or_multiple: {single_or_multiple}, content: {content.splitlines()}")
            for _message in content.splitlines():
                messages.append(_message)

    # Filter out similar commit messages
    fixed_messages = []
    for message in messages:
        if not pattern.match(message):
            continue
        fixed_messages.append(fix_message(message))
    unique_messages = filter_similar_lines(fixed_messages, 0.9)
    return unique_messages


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=Formatter)
    PARSER.add_argument("-d", "--debug", action="store_true", help="Show debug messages")

    sub_parsers = PARSER.add_subparsers(dest="command")
    setup_parser = sub_parsers.add_parser("setup", help="Initial setup of the configuration file")
    pick_parser = sub_parsers.add_parser(
        "pick", help="Generates commit messages for staged changes and lets you choose one (default)")

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
    message, _ = pick.pick(commit_messages, f"Took {time_taken} seconds to generate these commit messages:")

    # Make the commit with the chosen commit message
    subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
