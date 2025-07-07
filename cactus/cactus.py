#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__version__ = "4.6.1"

import argparse
from functools import partial
import json
import re
import sys
import time
from loguru import logger

import openai
import google.generativeai as genai

import os  # Added to handle relative imports

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))  # Add

from api import get_clusters_from_gemini, get_clusters_from_openai, load_api_key, setup_api_key
from changelog import generate_changelog
from utils import setup_logging
from git_utils import run, get_git_diff, restore_changes, parse_diff, stage_changes
from grouper import parse_diff, stage_changes

from unidiff import PatchSet
from loguru import logger

from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.formatted_text import FormattedText
from prompt_toolkit.styles import Style
from prompt import display_clusters, handle_user_input


def extract_patches(diff_data):
    """
    Extracts individual hunks from the diff data and returns a list of binary patches.
    Correctly formats the diff headers, handling scenarios like added or deleted files.
    """
    diff_text = diff_data.decode('latin-1')
    patches = []

    try:
        patch_set = PatchSet.from_string(diff_text)
    except Exception as e:
        logger.error(f"Failed to parse diff data: {e}")
        return []

    for patched_file in patch_set:

        file_headers = []
        file_headers.append(str("".join(list(patched_file.patch_info)[:-1])).strip())

        if patched_file.is_modified_file:
            file_headers.append(f'--- {patched_file.source_file}')
            file_headers.append(f'+++ {patched_file.target_file}')

        file_header_text = '\n'.join(file_headers)

        if patched_file.is_binary_file:
            logger.info(f"Skipping binary file {patched_file.path}")
            patch_bytes = file_header_text.encode('latin-1')
            patches.append(patch_bytes)
            continue  # Skip binary files

        if len(patched_file) == 0:
            logger.info(f"No hunks found for {patched_file.path}.")
            patch_bytes = file_header_text.encode('latin-1')
            patches.append(patch_bytes)
            continue

        for hunk in patched_file:
            hunk_text = str(hunk)
            patch_text = file_header_text + '\n' + hunk_text
            patch_bytes = patch_text.encode('latin-1')
            patches.append(patch_bytes)

    return patches



def prepare_prompt_data(diff_data):
    """
    Prepares the prompt data in specific format from the diff data.
    """
    diff_text = diff_data.decode('latin-1')
    file_data = []
    hunk_data = []

    try:
        patch_set = PatchSet.from_string(diff_text)
    except Exception as e:
        logger.error(f"Failed to parse diff data: {e}")
        return ""

    hunk_index = 1
    # Prepare files and hunks section
    for patched_file in patch_set:
        file_path = patched_file.path
        file_data.append(f"\n# FILE: {file_path}")
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content_lines = f.readlines()
        except UnicodeDecodeError:
                logger.warning(f"Failed to read file {file_path} due to binary content.")
                content_lines = ["### [BINARY FILE]"]
        except FileNotFoundError:
                logger.warning(f"File not found: {file_path}")
                content_lines = ["### File Not Found"]

        for line in content_lines:
            line = line.rstrip('\n')
            file_data.append(f"FILE: {line}")

        for hunk in patched_file:
            hunk_lines = [line.encode('latin-1').decode('utf-8', errors='replace') for line in str(hunk).splitlines()]
            hunk_data.append(f"\n## HUNK {hunk_index} ({file_path})")
            for line in hunk_lines:
                hunk_data.append(f"HUNK: {line}")
            hunk_index += 1

    prompt_data = file_data + hunk_data
    return "\n".join(prompt_data)


def generate_commits(all_hunks, clusters, previous_sha, full_diff):
    for cluster in clusters:
        try:
            stage_changes([all_hunks[i - 1] for i in cluster["hunk_indices"]])
        except Exception as e:
            logger.error(f"Failed to stage changes: {e}. Restoring changes.")
            # TODO: this is wrong, we should be restoring the entire
            #       repository to the original state before cactus ran
            #       if some commits worked and this failed afterwards
            run(f"git reset {previous_sha}")
            restore_changes(full_diff)
            sys.exit(1)

        logger.info(f"Auto-committing: {cluster['message']}")
        if run(f"git commit -m '{cluster['message']}'").returncode != 0:
            logger.error("Failed to commit changes. Restoring changes.")
            run(f"git reset {previous_sha}")
            restore_changes(full_diff)
            sys.exit(1)


def generate_changes(args):
    previous_sha = run("git rev-parse --short HEAD").stdout
    full_diff = get_git_diff(args.context_size)
    patches = extract_patches(full_diff)
    prompt_data = prepare_prompt_data(full_diff)

    if "gemini" in args.model:
        get_clusters_func=partial(get_clusters_from_gemini, hunks_n=len(patches), model=args.model)
    else:
        get_clusters_func=partial(get_clusters_from_openai, hunks_n=len(patches), model=args.model)

    clusters = handle_user_input(prompt_data, args.n, get_clusters_func)

    # Unstage all staged changes
    logger.warning("Unstaging all staged changes and applying individual diffs...")
    run("git restore --staged .")

    generate_commits(patches, clusters, previous_sha, full_diff)


def main():
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
        default="gemini-2.5-flash-preview-05-20",
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

    logger.info(f"Running cactus version {__version__}")


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
        logger.info(f"Using {args.model} to generate " + (f"{args.n} commits..." if args.n else "commit messages..."))
        generate_changes(args)
    elif args.action == "changelog":
        generate_changelog(args, args.model)


if __name__ == "__main__":
    main()
