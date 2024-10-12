#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "4.0.0"
__license__ = "MIT"

import argparse
import json
import re
import sys
import time
from loguru import logger

import openai
import google.generativeai as genai

from api import get_clusters_from_gemini, get_clusters_from_openai, load_api_key, setup_api_key
from changelog import generate_changelog
from utils import setup_logging
from git_utils import run, get_git_diff, restore_changes, parse_diff, stage_changes
from grouper import parse_diff, stage_changes


def get_patches_and_prompt(diff_to_apply):
    patch_set = parse_diff(diff_to_apply)

    i = 0
    patches = []
    prompt_data = {"files": {}, "hunks": []}

    for patched_file in patch_set:
        try:
            prompt_data["files"][patched_file.path] = {"content": open(patched_file.path, "r", encoding="utf-8").read()}
        except (UnicodeDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to read file {patched_file.path}: {str(e)}")
            prompt_data["files"][patched_file.path] = {"content": "[BINARY FILE]" if isinstance(e, UnicodeDecodeError) else "File Not Found (Probably Renamed)"}

        for hunk in patched_file:
            prompt_data["hunks"].append({"hunk_index": i, "content": str(hunk)})
            patches.append(f"--- {patched_file.source_file}{os.linesep}+++ {patched_file.target_file}{os.linesep}{str(hunk)}{os.linesep}")
            i += 1

    return patches, json.dumps(prompt_data)


def generate_commits(all_hunks, clusters, previous_sha, diff_to_apply):
    for cluster in clusters:
        stage_changes([all_hunks[i] for i in cluster["hunk_indices"]])
        logger.info(f"Auto-committing: {cluster['message']}")
        if run(f"git commit -m '{cluster['message']}'").returncode != 0:
            logger.error("Failed to commit changes. Restoring changes.")
            run(f"git reset {previous_sha}")
            restore_changes(diff_to_apply)
            sys.exit(1)


def generate_changes(args, model):
    previous_sha = run("git rev-parse --short HEAD").stdout
    diff_to_apply = get_git_diff(args.context_size)
    patches, prompt_data = get_patches_and_prompt(diff_to_apply)

    if "gemini" in model:
        clusters = get_clusters_from_gemini(prompt_data, args.n, model)
    else:
        clusters = get_clusters_from_openai(prompt_data, args.n, model)

    message = f"Separated into {len(clusters)} groups of changes from {len(patches)} hunks:\n"
    for ix, cluster in enumerate(clusters):
        message += f"- Commit {ix} ({len(cluster['hunk_indices'])} hunks): {cluster['message']}\n"
    logger.success(message)

    logger.warning("Is this fine? [Y/n]")
    response = input()
    if response.lower() != "y" and response != "":
        logger.error("Aborted by user.")
        sys.exit(1)

    # unstage all staged changes
    logger.warning("Unstaging all staged changes and applying individual diffs...")
    run("git restore --staged .")
    time.sleep(1)

    generate_commits(patches, clusters, previous_sha, diff_to_apply)


if __name__ == "__main__":

    class Formatter(argparse.RawTextHelpFormatter, argparse.ArgumentDefaultsHelpFormatter):
        pass

    PARSER = argparse.ArgumentParser(
        prog="cactus",
        formatter_class=Formatter,
        allow_abbrev=True,
        description="Without arguments, generates commit messages for all the currently staged changes.")
    # PARSER.add_argument(nargs="?", type=int, help="")
    PARSER.add_argument("-d", "--debug", action="store_true", help="Show debug messages")
    PARSER.add_argument(
        "-c",
        "--context-size",
        nargs="?",
        type=int,
        default=1,
        help="Context size of the git diff (lines before and after each hunk)")
    PARSER.add_argument(
        "-m",
        "--model",
        action="store",
        default="gpt-4o-mini",
        help="Model used for the generations",
    )
    PARSERS = PARSER.add_subparsers(title="subcommands", dest="action")
    GENERATE_PARSER = PARSERS.add_parser(
        "generate",
        formatter_class=Formatter,
        add_help=False,
        help="Generates commit messages for all the currently staged changes")
    GENERATE_PARSER.add_argument("n", nargs="?", type=int, default=0, help="Number of separate commits to generate")
    CHANGELOG_PARSER = PARSERS.add_parser(
        "changelog",
        formatter_class=Formatter,
        add_help=False,
        help="Generates a changelog between the HEAD commit and a target commit")
    CHANGELOG_PARSER.add_argument(
        "-p", "--pathspec", action="store", nargs="?", help="Get changelogs for these pathspecs only")
    CHANGELOG_PARSER.add_argument("sha", nargs="?", help="Target commit SHA from which to generate the changelog")
    SETUP_PARSER = PARSERS.add_parser(
        "setup", help="Performs the initial setup for setting the API token", formatter_class=Formatter)
    SETUP_PARSER.add_argument("api", choices=["OpenAI", "Gemini"], help="The API to set up.")

    for subparsers_action in [action for action in PARSER._actions if isinstance(action, argparse._SubParsersAction)]:
        for choice, subparser in subparsers_action.choices.items():
            help_lines = subparser.format_help().splitlines()
            help_lines[0] = "\n\u001b[34;01m" + help_lines[0].replace("usage: ", "")
            help_lines.pop(1)
            help_lines[1] = "\u001b[34m" + help_lines[1] + "\u001b[00m"
            PARSER.epilog = (PARSER.epilog or "") + ("\u001b[00m\n\u001b[36;00m".join(help_lines[0:2]) + "\n" + ("\n  ").join(help_lines[2:]))

    # try to make the first argument a subcommand if it's a number
    # this is useful for running `cactus 1` instead of `cactus generate 1`
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        sys.argv.insert(1, "generate")
    args = PARSER.parse_args()

    if args.debug:
        setup_logging("DEBUG", {"function": True})
    else:
        setup_logging("INFO")

    if args.action == "setup":
        setup_api_key(args.api)
        sys.exit(0)

    if "gemini" in args.model:
        gemini_api_key = load_api_key("Gemini")
        if gemini_api_key is None:
            logger.error("Gemini API key not found. Please run `cactus setup Gemini` first.")
            sys.exit(1)
        genai.configure(api_key=gemini_api_key)
    else:
        openai_token = load_api_key("OpenAI")
        if openai_token is None:
            logger.error("OpenAI token not found. Please run `cactus setup OpenAI` first.")
            sys.exit(1)
        openai.api_key = openai_token

    if isinstance(args.action, int):
        args.n = args.action
        args.action = "generate"
    elif not args.action:
        args.action = "generate"

    if args.action == "generate":
        if "n" not in args:
            args.n = None
        logger.info(f"Generating commit messages using {args.model}...")
        generate_changes(args, args.model)
    elif args.action == "changelog":
        generate_changelog(args, args.model)
