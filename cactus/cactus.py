#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""

import argparse
import json
import re
import sys
import time
from loguru import logger

import openai
import google.generativeai as genai

from .api import get_clusters_from_gemini, get_clusters_from_openai, load_api_key, setup_api_key
from .changelog import generate_changelog
from .utils import setup_logging
from .git_utils import run, get_git_diff, restore_changes, parse_diff, stage_changes
from .grouper import parse_diff, stage_changes
import os
import re
import json
from unidiff import PatchSet
from loguru import logger

from inquirer import prompt
from prompt_toolkit.shortcuts import print_formatted_text
from prompt_toolkit.formatted_text import HTML
from prompt_toolkit.key_binding import KeyBindings


def extract_patches(diff_data):
    """
    Extracts individual hunks from the diff data and returns a list of binary patches.
    """
    diff_text = diff_data.decode('latin-1')
    patches = []

    try:
        patch_set = PatchSet.from_string(diff_text)
    except Exception as e:
        logger.error(f"Failed to parse diff data: {e}")
        return []

    for patched_file in patch_set:
        if patched_file.is_binary_file:
            logger.warning(f"Skipping binary file {patched_file.path}")
            continue    # Skip binary files

        file_headers = []
        # Build file headers
        file_headers.append(f'diff --git a/{patched_file.source_file} b/{patched_file.target_file}')
        if patched_file.is_rename:
            file_headers.append(f'rename from {patched_file.source_file}')
            file_headers.append(f'rename to {patched_file.target_file}')
        else:
            # if patched_file.source_revision and patched_file.target_revision:
            #     file_headers.append(f'index 000000..000000 {patched_file.source_mode}')
            if patched_file.source_file and patched_file.target_file:
                file_headers.append(f'--- {patched_file.source_file}')
                file_headers.append(f'+++ {patched_file.target_file}')

        file_header_text = '\n'.join(file_headers) + '\n'

        for hunk in patched_file:
            hunk_text = str(hunk)
            patch_text = file_header_text + hunk_text
            patch_bytes = patch_text.encode('latin-1')
            patches.append(patch_bytes)

    return patches


def prepare_prompt_data(diff_data):
    """
    Prepares the prompt data for the language model from the diff data.
    """
    diff_text = diff_data.decode('latin-1')
    prompt_data = {"files": {}, "hunks": []}
    hunk_index = 0

    try:
        patch_set = PatchSet.from_string(diff_text)
    except Exception as e:
        logger.error(f"Failed to parse diff data: {e}")
        return json.dumps(prompt_data)

    for patched_file in patch_set:
        file_path = patched_file.path
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
        except (UnicodeDecodeError, FileNotFoundError) as e:
            logger.warning(f"Failed to read file {file_path}: {str(e)}")
            content = "[BINARY FILE]" if isinstance(e, UnicodeDecodeError) else "File Not Found (Probably Renamed)"
        prompt_data["files"][file_path] = {"content": content}

        for hunk in patched_file:
            hunk_content = str(hunk)
            # Decode hunk content for the language model, replacing errors
            hunk_content_decoded = hunk_content.encode('latin-1').decode('utf-8', errors='replace')
            prompt_data["hunks"].append({"hunk_index": hunk_index, "content": hunk_content_decoded})
            hunk_index += 1

    return prompt_data


def generate_commits(all_hunks, clusters, previous_sha, full_diff):
    for cluster in clusters:
        stage_changes([all_hunks[i] for i in cluster["hunk_indices"]])
        logger.info(f"Auto-committing: {cluster['message']}")
        if run(f"git commit -m '{cluster['message']}'").returncode != 0:
            logger.error("Failed to commit changes. Restoring changes.")
            run(f"git reset {previous_sha}")
            restore_changes(full_diff)
            sys.exit(1)


def generate_changes(args, model):
    previous_sha = run("git rev-parse --short HEAD").stdout
    full_diff = get_git_diff(args.context_size)
    patches = extract_patches(full_diff)
    prompt_data = prepare_prompt_data(full_diff)

    if "gemini" in model:
        clusters = get_clusters_from_gemini(prompt_data, args.n, model)
    else:
        clusters = get_clusters_from_openai(prompt_data, args.n, model)

    def display_clusters():
        message = f"Separated into {len(clusters)} groups of changes from {len(patches)} hunks:\n"
        for ix, cluster in enumerate(clusters):
            message += f"- Commit {ix} ({len(cluster['hunk_indices'])} hunks): {cluster['message']}\n"
        logger.success(message)

    display_clusters()

    # Define choices and their corresponding shortcut keys
    choices = [
        {
            'name': 'Accept', 'value': 'accept', 'key': 'c'
        },
        {
            'name': 'Regenerate', 'value': 'regenerate', 'key': 'r'
        },
        {
            'name': 'Increase #', 'value': 'increase', 'key': 'i'
        },
        {
            'name': 'Decrease #', 'value': 'decrease', 'key': 'd'
        },
        {
            'name': 'Quit', 'value': 'quit', 'key': 'q'
        },
    ]

    # Create a key bindings object
    kb = KeyBindings()

    # Variable to store the user's choice
    user_choice = {'value': None}

    # Define key bindings for each choice
    for choice in choices:

        @kb.add(choice['key'])
        def _(event, choice=choice):
            user_choice['value'] = choice['value']
            event.app.exit()

    # Handle Ctrl+C as Quit
    @kb.add('c-c')
    def _(event):
        user_choice['value'] = 'quit'
        event.app.exit()

    # Start a loop to keep prompting the user
    while True:
        print_formatted_text(HTML('<b>Select an option (press c/r/i/d/q):</b>'))
        for choice in choices:
            print_formatted_text(f"{choice['key']}: {choice['name']}")

        try:
            # Wait for user input (key press)
            from prompt_toolkit.shortcuts import PromptSession
            session = PromptSession(key_bindings=kb)
            session.prompt('') # Empty prompt to capture key press
        except KeyboardInterrupt:
            logger.error("Aborted by user via Ctrl+C.")
            sys.exit(1)

        response = user_choice['value']

        if response == 'accept':
            break
        elif response == 'regenerate':
            if "gemini" in model:
                clusters = get_clusters_from_gemini(prompt_data, args.n, model)
            else:
                clusters = get_clusters_from_openai(prompt_data, args.n, model)
            display_clusters()
        elif response == 'increase':
            args.n = len(clusters) + 1 if args.n is None else args.n + 1
            if "gemini" in model:
                clusters = get_clusters_from_gemini(prompt_data, args.n, model)
            else:
                clusters = get_clusters_from_openai(prompt_data, args.n, model)
            display_clusters()
        elif response == 'decrease':
            args.n = len(clusters) if args.n is None else args.n
            if args.n <= 1:
                logger.warning("Cannot decrease further. Minimum number of clusters is 1.")
            else:
                args.n -= 1
                if "gemini" in model:
                    clusters = get_clusters_from_gemini(prompt_data, args.n, model)
                else:
                    clusters = get_clusters_from_openai(prompt_data, args.n, model)
                display_clusters()
        elif response == 'quit':
            logger.error("Aborted by user.")
            sys.exit(1)
        else:
            logger.error("Invalid option.")

        # Reset user_choice for the next iteration
        user_choice['value'] = None

    # Unstage all staged changes
    logger.warning("Unstaging all staged changes and applying individual diffs...")
    run("git restore --staged .")
    time.sleep(1)

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


if __name__ == "__main__":
    main()
