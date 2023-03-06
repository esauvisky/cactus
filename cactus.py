#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions

Usage:

"""
__author__ = "emi"
__version__ = "1.0.0"
__license__ = "MIT"

import argparse
import os
import subprocess
import sys

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
    openai_token = input("Enter your OpenAI token: ")
    config_dir = os.path.expanduser("~/.config/cactus")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, "openai_token"), "w") as f:
        f.write(openai_token)
    logger.success("OpenAI token saved.")


def load_openai_token():
    config_dir = os.path.expanduser("~/.config/cactus")
    try:
        with open(os.path.join(config_dir, "openai_token"), "r") as f:
            openai_token = f.read().strip()
        return openai_token
    except FileNotFoundError:
        return None


def get_git_diff(all_changes=False, complexity=3):
    # Check if there are staged changes
    result = subprocess.run("git diff --cached --quiet --exit-code", shell=True)
    if result.returncode == 0:
        # There are not staged changes
        logger.error("No staged changes found. Please stage changes first or pass --all.")
        sys.exit(1)

    cmd = f"git --no-pager diff --ignore-all-space --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv --unified={complexity if complexity > 0 else 0}"
    if not all_changes:
        cmd += " --staged"
    result = subprocess.run(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        logger.error("Failed to get git diff: %s", result.stderr.decode().strip())
        sys.exit(1)
    diff = result.stdout.decode().strip()
    lines = diff.splitlines()

    file_diff = []
    file_name = None
    changed_lines = []

    for line in lines:
        if line.startswith("diff --git"):
            if file_name is not None and "yarn.lock" not in file_name:
                # Save previous file diff
                file_diff.append((file_name, changed_lines))
                changed_lines = []
            file_name = ">> " + "".join(line.split(" ")[-1].split("/")[-1:])
        elif line.startswith("+++") or line.startswith("---"):
            pass   # ignore header lines
        elif line.startswith("+") or line.startswith("-"):
            changed_lines.append(line)
        elif line.startswith("@@"):
            changed_lines.append("@@")

    # Save last file diff
    if "yarn.lock" not in file_name:
        file_diff.append((file_name, changed_lines))

    stripped_diff = []
    for file_name, changed_lines in file_diff:
        stripped_diff.append(file_name)
        stripped_diff.extend(changed_lines)
        stripped_diff.append("")

    # stripped_diff = " ".join(stripped_diff)
    # stripped_diff = "".join(c for c in stripped_diff if c.isalnum() or c in [" ", "'", '"']).strip()
    stripped_diff = "\n".join(stripped_diff)

    # TODO: implement better trimming on the population side
    if complexity < 0:
        for _ in range(abs(complexity)):
            stripped_diff = trim_git_diff(stripped_diff)

    # TODO: count tokens instead of words
    # SEE: https://platform.openai.com/tokenizer?view=bpe
    if len(stripped_diff.split()) < 8:
        logger.error("Diff is too small.")
        sys.exit(1)
    elif len(stripped_diff.split()) > 3000:
        logger.error("Diff is too large.")
        sys.exit(1)
    else:
        logger.success(f"Diff has {len(stripped_diff.split())} words.")

    return stripped_diff


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


def send_request(model, diff, category):
    prompt = """
Below, between lines containing "##########", there's a git diff. The diff consists of the changes in files for a git repository.

Your output must consist of five lines, each one containing a different commit message suggestion. The messages should be written in imperative mood and in the present tense, should not contain any punctuation marks, special characters or emojis. The messages should be ordered from the most likely to the least likely alternative.\n"""
    if category:
        prompt += f"These changes fall into changes of type '{category}', therefore, all suggestions for commit messages must be related to this category. The messages should also begin with the category name, followed by a colon and a space, i.e. '{category}: '."
    else:
        prompt += "Here are some examples:"
        prompt += '- if a file was renamed, the commit message must not be simply "refactor", but rather "chore: rename file A to file B";'
        prompt += '- if the diff contains a bug fix and a new feature called XXX, the commit messages must not be "fix bug" or "add feature", but rather "fix, feat: fix bug and add new feat XXX";'
        prompt += '- if the diff fixes a typo or tweaks/improves styling, the commit message could be "style: fix typo and small tweaks";'
        prompt += '- if the diff is adding documentation about XXX, the commit message could be "docs: add documentation for XXX";'
        prompt += '- if the diff adds a new dependency called XXX, the commit message could be "chore: add new dependency XXX";'
        prompt += '- if the diff makes changes to a build script, the commit message could be "build: change XXX to YYY";'
        prompt += '- if the diff makes changes to a CI script, the commit message could be "ci: change XXX to YYY";\n\n'

    prompt += 'IMPORTANT: as the output you generate is meant to be parsed later on, RETURN ONLY FIVE LINES with the COMMIT MESSAGES strings, ONE PER LINE, and ABSOLUTELY NOTHING ELSE.\n\n##########\n'
    prompt += diff.replace("@@", "")
    prompt += "##########\n"

    logger.debug(f'Prompt is: {prompt}')
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{
            "role": "system", "content": "You are a helpful assistant that generates commit messages for a subset of changes within a git repository." +
            "The generated messages must be viable messages to be used as the git commit message that will describe the changes in the files." +
            "The messages must be related and appropriate for the changes in the diff."}, {
            "role": "user", "content": prompt}],
        temperature=0.5,
    )
    logger.debug(f'Response is: {response}')
    return response['choices'][0]['message']['content']


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    PARSER.add_argument("-d", "--debug", action="store_true", help="Show debug messages")
    group = PARSER.add_mutually_exclusive_group()
    group.add_argument("setup", nargs='?', help="Initial setup of your OpenAI token")
    group_model = group.add_mutually_exclusive_group()
    group_model.add_argument("pick", nargs='?', help="Generates five commit messages for staged changes and lets you choose one (default)")
    group_model.add_argument("-m", "--model", default="text-davinci-003", choices=[
        "text-curie-001", "text-babbage-001", "text-davinci-003", "text-ada-001"], help="OpenAI model to use")
    group_model.add_argument(
        "-c", "--categories", default=None, help="Ask user to pick a restrictive main category from a list (comma separated, example: 'fix,feat,chore,refactor,style,docs,build,ci,perf')")
    group_model.add_argument(
        "-a", "--all", action="store_true", help="Use all non staged changes instead of staged changes, but don't autocommit afterwards.")

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
        logger.error("OpenAI token not found. Please run `cactus setup` first.")
        sys.exit(1)
    openai.api_key = openai_token

    category = None
    if args.categories:
        categories = args.categories.split(",")
        category, _ = pick.pick(categories, "Pick a category:", indicator='=>', default_index=0)

    response = None
    complexity = 3
    while not response:
        try:
            diff = get_git_diff(all_changes=args.all, complexity=complexity)
            response = send_request(args.model, diff, category)
        except Exception as e:
            if "This model's maximum context length is " in str(e):
                logger.warning("Too many tokens! Trimming it down...")
                complexity -= 2
            elif "Diff is too large" in str(e):
                logger.warning("Diff too large! Trimming it down...")
                complexity -= 1
            else:
                raise e

    logger.debug(f'Response for: {response}')

    trans_table = str.maketrans({key: None for key in ["\t", "\r", "\n", "\"", "\\", "\'", "\b", "\f", "\a", "\v"]})
    commit_messages = [
        str(choice).translate(trans_table) for choice in response.strip().split("\n")]
    commit_messages = [message.lower() for message in commit_messages]
    message, _ = pick.pick(commit_messages, "Pick an automated uncomplicated commit message suggestion:", indicator='=>', default_index=0)

    if not args.all:
        # Make the commit with the chosen commit message
        subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        # Just show the chosen commit message and exit
        print(message)
