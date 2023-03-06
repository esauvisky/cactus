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


def send_request(model, diff, category):
    prompt = """
Below, between lines containing hashtags, there's a git diff, consisting of the changes in files staged for a particular commit in a git repository.

Your output must consist of five lines, each one containing a different commit message suggestion. The suggestions must be viable messages to be used as the git commit message that will describe the changes in the files, and must be related and appropriate for the changes in the diff. They should be written in imperative mood and in the present tense, should not contain any punctuation marks, special characters or emojis. The messages should be ordered from the most likely to the least likely alternative.\n"""
    if category:
        prompt += f"These changes fall into changes of type '{category}', therefore, all suggestions for commit messages must be related to this category. The messages should also begin with the category name, followed by a colon and a space, i.e. '{category}: '.\n"
    # else:
    # prompt += "Here are some examples, in the format \"type of change\": \"example commit message\":\n"
    # prompt += '- "fixes a bug on XXX": "fix: stop calling get_protos() on every cycle in XXX"\n'
    # prompt += '- "dependencies were updated or installed": "chore: add requirements and update lib to 2.3"\n'
    # prompt += '- "improves styling, fixes a typo or does general code cleanup in XXX": "style: fix typo, lint and small tweaks in XXX"\n'
    # prompt += '- "adds documentation about XXX": "docs: add documentation for XXX"\n'
    # prompt += 'If the diff consists of several major "operations", you can specify multiple categories and changes. For example:\n'
    # prompt += '  - "fixes a bug *and* adds a new feature called XXX": "fix, feat: fix get_protos() bug and add new feat XXX"\n'
    # prompt += '  - "adds *two* new features": "feat: update prompt with clearer examples for commit messages, suggest using both simultaneously"\n'

    prompt += '\nIMPORTANT: YOU MUST RETURN ONLY FIVE LINES with the COMMIT MESSAGES, ONE PER LINE, and ABSOLUTELY NOTHING ELSE.\n\n##########\n'
    prompt += diff
    prompt += "##########\n"

    logger.debug(f'Prompt is: {prompt}')
    response = openai.ChatCompletion.create(
        model="gpt-3.5-turbo",
        messages=[{"role": "system", "content": "You are a helpful assistant"}, {"role": "user", "content": prompt}],
        temperature=0.8,
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

    logger.debug(f'Assistant raw answer:\n{response}')

    clean_response = re.sub(r'(\s)+', r'\1', response)
    commit_messages = [choice.lower().strip() for choice in clean_response.splitlines()]
    message, _ = pick.pick(commit_messages, "Pick an automated uncomplicated commit message suggestion:", indicator='=>', default_index=0)

    if not args.all:
        # Make the commit with the chosen commit message
        subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    else:
        # Just show the chosen commit message and exit
        print(message)
