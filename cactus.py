#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions

Usage:

"""
__author__ = "emi"
__version__ = "0.1.0"
__license__ = "MIT"

import argparse
import os
import subprocess
import sys
import termios
import tty
import pick

import openai
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


setup_logging("INFO")


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


def get_git_diff(all_changes=False):
    cmd = "git --no-pager diff --ignore-all-space --minimal --no-color --no-ext-diff --no-indent-heuristic --no-textconv --unified=0"
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
    added_lines = []
    removed_lines = []

    for line in lines:
        if line.startswith("diff --git"):
            if file_name is not None:
                # Save previous file diff
                file_diff.append((file_name, removed_lines, added_lines))
                added_lines = []
                removed_lines = []
            file_name = "".join(line.split(" ")[-1].split("/")[-1:])
        elif line.startswith("+++") or line.startswith("---"):
            pass   # ignore header lines
        elif line.startswith("+"):
            added_lines.append(line)
        elif line.startswith("-"):
            removed_lines.append(line)

    # Save last file diff
    file_diff.append((file_name, removed_lines, added_lines))

    stripped_diff = []
    for file_name, removed_lines, added_lines in file_diff:
        stripped_diff.append(file_name)
        stripped_diff.extend(removed_lines)
        stripped_diff.extend(added_lines)
        stripped_diff.append("")

    # stripped_diff = " ".join(stripped_diff)
    # stripped_diff = "".join(c for c in stripped_diff if c.isalnum() or c in [" ", "'", '"']).strip()

    return "\n".join(stripped_diff)


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(prog="cactus", formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    group = PARSER.add_mutually_exclusive_group()
    group.add_argument("setup", nargs='?', help="Initial setup of your OpenAI token")
    group_model = group.add_mutually_exclusive_group()
    group_model.add_argument("gen", nargs='?', help="Generates a commit message for staged changes and commits it")
    group_model.add_argument("pick", nargs='?', help="Generates five commit messages for staged changes and lets you choose one")
    group_model.add_argument("-m", "--model", default="text-davinci-003", choices=[
        "text-curie-001", "text-babbage-001", "text-davinci-003", "text-ada-001"], help="OpenAI model to use")
    group_model.add_argument(
        "-a", "--all", action="store_true", help="Use all non staged changes instead of staged changes, but don't autocommit afterwards.")

    args = PARSER.parse_args()

    if args.setup:
        setup_openai_token()
        sys.exit(0)

    openai_token = load_openai_token()
    if openai_token is None:
        logger.error("OpenAI token not found. Please run `cactus setup` first.")
        sys.exit(1)

    openai.api_key = openai_token

    if args.all:
        diff = get_git_diff(all_changes=True)
    else:
        # Check if there are staged changes
        result = subprocess.run("git diff --cached --quiet --exit-code", shell=True)
        if result.returncode != 0:
            # There are staged changes
            diff = get_git_diff(all_changes=False)
        else:
            # There are not staged changes
            logger.error("No staged changes found. Please stage changes first or pass --all.")
            sys.exit(1)

        if args.gen:
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt="Using the git diff below, return the most fitting commit message for these changes. "                                          #yapf: disable
                + "The commit messages must begin with one of the following words, followed by a colon, according to what suits the changes better: "  #yapf: disable
                + "build, ci, feat, perf, revert, test, chore, docs, fix, refactor or style. The actual message should begin with a lowercase letter." #yapf: disable
                + "Return ONLY the raw commit message string, and ABSOLUTELY NOTHING ELSE, as the output will "                                        #yapf: disable
                + "be parsed and programatically used later on\n\n" + diff,                                                                            #yapf: disable
                stream=False,
                logprobs=None,
                max_tokens=100,
                temperature=0,
            )

            commit_message = response["choices"][0]["text"].strip().split("\n")[0]

            if not args.all:
                # Make the commit with the returned commit message
                subprocess.run(f"git commit -m '{commit_message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                # Just show the commit message and exit
                print(commit_message)
        else:
            response = openai.Completion.create(
                model="text-davinci-003",
                prompt="Using the git diffs below, return a list of five potential commit messages appropriate for the changes. "                      #yapf: disable
                + "Order them in order of preference, with the most preferred suited commit message at the top."                                       #yapf: disable
                + "The commit messages must begin with one of the following words, followed by a colon, according to what suits the changes better: "  #yapf: disable
                + "build, ci, feat, perf, revert, test, chore, docs, fix, refactor or style. The actual message should begin with a lowercase letter." #yapf: disable
                + "Return ONLY the raw commit messages strings, one per line, and ABSOLUTELY NOTHING ELSE, as this output is "                         #yapf: disable
                + "meant to be programatically parsed later on\n\n" + diff,                                                                            #yapf: disable
                stream=False,
                logprobs=None,
                max_tokens=100,
                temperature=0,
            )

            commit_messages = [choice for choice in response["choices"][0]["text"].strip().split("\n")]
            message, _ = pick.pick(commit_messages, "Pick an automated uncomplicated commit message suggestion:", indicator='=>', default_index=0)

            if not args.all:
                # Make the commit with the chosen commit message
                subprocess.run(f"git commit -m '{message}'", shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            else:
                # Just show the chosen commit message and exit
                print(message)
