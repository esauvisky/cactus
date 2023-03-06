#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "1.1.0"
__license__ = "MIT"

import argparse
import os
import re
import subprocess
import sys
import textwrap

import openai
import pick
from loguru import logger


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

    cmd = f"git --no-pager diff --ignore-all-space --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv --unified={complexity if complexity > 0 else 0}"
    cmd += " --staged"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
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
                file_blocks.append((block_header, block_lines))
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


def send_request(diff, category):
    prompt = textwrap.dedent("""Below, between lines containing hashtags, there's a git diff, consisting of the changes in files staged for a particular commit in a git repository.

    Read the diff and write one potential commit messages that would describe the changes. The commit message must be short and concise, and should be understandable by someone who is not familiar with the codebase. It must be written in the present tense, and must not contain any punctuation at the end. Commit messages must describe all the changes at once, so they cannot be too specific. Instead a commit message should describe the overall change at once with a single sentence. Commit messages must begin with the type of change introduced by the commit, followed by a colon, a space, and the message itself. """) # yapf: disable
    if category:
        prompt += "In this case, the type of change is: " + category + "."
    else:
        # TODO: fix this and pass all the possible categories in case the user specifies them
        prompt += 'The possible types of changes are: "fix", "feat", "chore", "docs", "refactor", "style", "test", "per", "build", "ci", "wip", "misc".'

    prompt += "\nIMPORTANT: your output will be evaluated by a machine learning model, so please make sure that you only return the messages themselves, one per line, without any other text."
    prompt += f"\n\n###\n{diff}\n###\n"
    logger.debug(f'Prompt is: {prompt}')
    response = openai.ChatCompletion.create(model="gpt-3.5-turbo",
                                            n=5,
                                            top_p=0.5,
                                            max_tokens=30,
                                            messages=[
                                                {"role": "system", "content": "You are a helpful assistant generating content that will be parsed by another machine."},
                                                {"role": "user", "content": prompt},])

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
    setup_parser = sub_parsers.add_parser("setup", help="Initial setup of your OpenAI token")
    pick_parser = sub_parsers.add_parser("pick",
                                         help="Generates five commit messages for staged changes and lets you choose one")

    pick_parser.add_argument("-m",
                             "--model",
                             default="text-davinci-003",
                             choices=["text-curie-001", "text-babbage-001", "text-davinci-003", "text-ada-001"],
                             help="OpenAI model to use")

    pick_parser.add_argument("-c",
                             "--categories",
                             default=[],
                             nargs='?',
                             help="Ask user to pick a restrictive main category from a list. "
                                 + "If not specified, the bot will try to guess the main category."
                                 + "If no list is provided but the flag is specified, cactus will use a default list of categories.") # yapf: disable

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

    category = None
    if "categories" in args:
        if args.categories is None:
            categories = "fix,feat,chore,refactor,style,docs,build,ci,perf".split(",")
            category, _ = pick.pick(categories, "Pick a category:", indicator='=>', default_index=0)
        elif len(args.categories) != 0:
            categories = args.categories.split(",")
            category, _ = pick.pick(categories, "Pick a category:", indicator='=>', default_index=0)
        else:
            categories = []

    responses = None
    complexity = 3
    while not responses:
        try:
            diff = get_git_diff(complexity=complexity)
            responses = send_request(diff, category)
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
    clean_responses = [re.sub(r'(\s)+', r'\1', r) for r in responses]
    commit_messages = [choice.lower().strip() for choice in clean_responses]
    message, _ = pick.pick(commit_messages, "Pick a suggestion:", indicator='=>', default_index=0)

    # Make the commit with the chosen commit message
    subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
