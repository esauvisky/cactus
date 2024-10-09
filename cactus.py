#!/usr/bin/env python3
"""
CACTUS Automates Commits Through Uncomplicated Suggestions
"""
__author__ = "emi"
__version__ = "3.0.0"
__license__ = "MIT"

import argparse
import os
import pprint
import time
import json
import subprocess
import sys

import openai
from loguru import logger
import tiktoken

from constants import PROMPT_CLASSIFICATOR_SYSTEM

client = None

import google.generativeai as genai
from google.generativeai import protos
from google.generativeai.types import HarmCategory, HarmBlockThreshold

# Create the model
gemini_config = {
    "temperature": 1,
    "top_p": 0.8,
    "top_k": 64,
    "max_output_tokens": 1024,
    "response_mime_type": "application/json",
}
from grouper import parse_diff, stage_changes

# Models and their respective token limits
MODEL_TOKEN_LIMITS = {
    "gpt-3.5-turbo": 4192,
    "gpt-3.5-turbo-16k": 16384,
    "gpt-4-1106-preview": 127514,
    "gpt-4o": 127514,
    "gpt-4": 16384,
    "gemini-1.5-pro": 1048576,
    "gemini-1.5-flash": 1048576,
    "gemini-1.5-pro-exp-0801": 2097152,
}


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


def setup_api_key(api_type):
    api_key = input(f"Enter your {api_type} API key: ")
    config_dir = os.path.expanduser("~/.config/cactus")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, f"{api_type.lower()}_api_key"), "w", encoding='utf-8', newline='\n') as f:
        f.write(api_key)
    logger.success(f"{api_type} API key saved.")


def load_api_key(api_type):
    config_dir = os.path.expanduser("~/.config/cactus")
    try:
        with open(os.path.join(config_dir, f"{api_type.lower()}_api_key"), "r", encoding='utf-8') as f:
            api_key = f.read().strip()
        return api_key
    except FileNotFoundError:
        return None


def run(cmd):
    result = subprocess.run(
        cmd,
        shell=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    result.stdout = result.stdout.decode("utf-8").strip() # type: ignore
    result.stderr = result.stderr.decode("utf-8").strip() # type: ignore
    return result


def get_git_diff(context_size):
    # Check if there are staged changes
    result = run("git diff --cached --quiet --exit-code")
    if result.returncode == 0:
        # There are not staged changes
        logger.error("No staged changes found, please stage the desired changes.")
        sys.exit(1)

    cmd = f"git diff --inter-hunk-context={context_size} --unified={context_size} --minimal -p --staged"
    result = run(cmd)
    if result.returncode != 0:
        logger.error("Failed to get git diff: %s", result.stderr.decode().strip())
        sys.exit(1)
    diff_to_apply = result.stdout

    return diff_to_apply


def restore_changes(full_diff):
    with open("/tmp/cactus.diff", "w", encoding='utf-8', newline='\n') as f:
        f.write(full_diff)
        f.write("\n")
    run("git apply --cached --unidiff-zero /tmp/cactus.diff")


def get_patches_and_prompt(diff_to_apply):
    patch_set = parse_diff(diff_to_apply)

    i = 0
    patches = []
    prompt_data = {"files": {}, "hunks": []}

    for patched_file in patch_set:
        try:
            file_contents = open(patched_file.path, "r", encoding='utf-8').read()
            prompt_data["files"][patched_file.path] = {
                "content": file_contents
            }
        except UnicodeDecodeError:
            logger.warning(f"Failed to read file {patched_file.path}. This is probably a binary file.")
            prompt_data["files"][patched_file.path] = {
                "content": "[BINARY FILE]"
            }
        except FileNotFoundError:
            logger.warning(f"File not found. This was probably renamed.")
            prompt_data["files"][patched_file.path] = {
                "content": "File Not Found (Probably Renamed)"
            }


        for hunk in patched_file:
            prompt_data["hunks"].append({
                "hunk_index": i,
                "content": str(hunk)
            })
            newhunk = f"--- {patched_file.source_file}\n"
            newhunk += f"+++ {patched_file.target_file}\n"
            newhunk += str(hunk) + "\n"
            patches.append(newhunk)
            i += 1

    return patches, json.dumps(prompt_data)


def get_clusters_from_openai(prompt_data, clusters_n, model):
    response = openai.chat.completions.create(
        model=model,
        top_p=1,
        temperature=1,
        max_tokens=1024,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "system", "content": PROMPT_CLASSIFICATOR_SYSTEM
            },
            {
                "role": "user", "content": prompt_data
            },
            {
                "role": "user", "content": f"Return a JSON with {clusters_n} commits for the hunks above."
                                         if clusters_n else "Return the JSON for the hunks above."
            },
        ])
    content = json.loads(response.choices[0].message.content) # type: ignore
    clusters = content["commits"]
    return clusters


def get_clusters_from_gemini(prompt_data, clusters_n, model):
    model = genai.GenerativeModel(
        model_name=model,
        generation_config=gemini_config,                                                   # type: ignore
        safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE,
        },
        system_instruction=PROMPT_CLASSIFICATOR_SYSTEM,
    )

    chat_session = model.start_chat(history=[
        {
            "role": "user",
            "parts": prompt_data,
        },
    ])

    response = chat_session.send_message(f"Return a JSON with {clusters_n} commits for the hunks above."
                                         if clusters_n else "Return the JSON for the hunks above.")
    content = json.loads(response.text)
    clusters = content["commits"]
    return clusters


def generate_commits(all_hunks, clusters, previous_sha, diff_to_apply):
    for cluster in clusters:
        hunks_in_cluster = [all_hunks[i] for i in cluster["hunk_indices"]]
        diff = "\n".join(hunks_in_cluster)
        message = cluster["message"]

        try:
            stage_changes(hunks_in_cluster)
            logger.info(f"Auto-commiting: {message}")
            run(f"git commit -m '{message}'")
        except Exception as e:
            logger.error(f"Failed to stage changes: {e}. Will restore the changes and exit.")
            run(f"git reset {previous_sha}")
            restore_changes(diff_to_apply)
            sys.exit(1)


def num_tokens_from_string(text, model):
    """Return the number of tokens used by a list of messages."""
    try:
        encoding = tiktoken.encoding_for_model(model)
    except KeyError:
        # print("Warning: model not found. Using gpt-4-0613 encoding.")
        model = "gpt-4-0613"
        encoding = tiktoken.encoding_for_model(model)

    tokens_per_message = 4 # every message follows <|start|>{role/name}\n{content}<|end|>\n
    tokens_per_name = 1    # if there's a name, the role is omitted
                           # raise NotImplementedError(f"num_tokens_from_messages() is not implemented for model {model}. See https://github.com/openai/openai-python/blob/main/chatml.md for information on how messages are converted to tokens.")
    num_tokens = len(encoding.encode(text))
    num_tokens += 3        # every reply is primed with <|start|>assistant<|message|>
    num_tokens += tokens_per_message + tokens_per_name
    return num_tokens


def split_into_chunks(text, model="gpt-4o"):
    max_tokens = MODEL_TOKEN_LIMITS.get(model, 127514) - 64 # Default to 127514 if model not found
    """
    Split the text into chunks of the specified size.
    """
    tokens = text.split('\n')
    chunks = []
    chunk = ''
    for token in tokens:
        if num_tokens_from_string(chunk + '\n' + token, model) > max_tokens:
            chunks.append(chunk)
            chunk = ''
        chunk += '\n' + token
    chunks.append(chunk)
    return chunks


def generate_changelog(args, model):
    # get list of commit messages from args.sha to HEAD
    commit_messages = run(f"git log --pretty=format:'%s' {args.sha}..HEAD").stdout.split("\n")

    # prepare exclude patterns for git diff
    pathspec = f"-- {args.pathspec}" if args.pathspec else ''

    # get git diff from args.sha to HEAD
    diff = run(f"git diff --ignore-all-space --ignore-blank-lines -U{args.context_size} {args.sha} {pathspec}").stdout
    err = run(f"git diff --ignore-all-space --ignore-blank-lines -U{args.context_size} {args.sha} {pathspec}").stderr

    if err:
        logger.error(f"An error occurred while getting git diff: {err}")
        sys.exit(1)

    # Split the diff into chunks if it exceeds the token limit
    chunks = split_into_chunks(diff, model)

    logger.debug(diff)

    if len(chunks) > 1:
        logger.warning(f"Diff went over max token limit ({num_tokens_from_string(diff, model)} > {MODEL_TOKEN_LIMITS.get(model)}). Splitted into {len(chunks)} chunks.")

    changelog = ''
    for chunk in chunks:
        # send request and append result to changelog
        if "gemini" in model:
            # Create the model
            generation_config = {
              "temperature": 1,
              "top_p": 0.95,
              "top_k": 64,
              "max_output_tokens": 8192,
              "response_mime_type": "text/plain",
            }

            gemini_model = genai.GenerativeModel(
                model_name=model,
                generation_config=generation_config,                                                                                                                                              # type: ignore
                                                                                                                                                                                                  # safety_settings=Adjust safety settings
                                                                                                                                                                                                  # See https://ai.google.dev/gemini-api/docs/safety-settings
                system_instruction="""
                You are a highly skilled AI tasked with creating a user-friendly changelog based on git diffs. Your goal is to analyze the following git diffs and produce a clear, concise list of changes that are relevant and understandable to end-users.""",
            )
            chat_session = gemini_model.start_chat()
            response = chat_session.send_message(
                        f"""You are tasked with generating a changelog for beta testers based on a list of commit messages and their corresponding diffs. Your goal is to create a concise, informative list of changes that is neither too technical nor too simplistic.

First, review the following commit messages:

<commit_messages>
{commit_messages}
</commit_messages>

Now, examine the diffs associated with these commits:

<diffs>
{chunk}
</diffs>

To generate the changelog:

1. Analyze both the commit messages and the diffs, paying more attention to the contents of the diffs. Remember that multiple changes may be grouped into a single commit.

2. Identify significant changes, new features, improvements, and bug fixes that would be relevant to beta testers.

3. Summarize each change in a clear, concise manner that is understandable to beta testers. Avoid overly technical jargon, but don't oversimplify to the point of losing important details.

4. Prioritize changes based on their impact and relevance to the user experience.

5. Combine related changes into single entries when appropriate to avoid redundancy.

6. Use action verbs to start each changelog entry (e.g., "Added," "Fixed," "Improved," "Updated").

7. If a change addresses a specific issue or feature request, mention it briefly without going into technical details.

Generate your changelog as a markdown list. Each item in the list should be a single line describing one change or a group of related changes. Do not include any additional text, headings, or explanations outside of the list items.

Your output should look like this:

<changelog>
- Added [feature] to improve [aspect of the application]
- Fixed issue with [problem] that was causing [symptom]
- Improved performance of [feature or section] by [brief explanation]
- Updated [component] to enhance [functionality]
</changelog>

Remember to focus on changes that are most relevant and impactful for beta testers. Your goal is to provide them with a clear understanding of what has changed in the application with a little bit of technical details.""")
            changelog += response.text
        else:
            import openai
            response = openai.chat.completions.create(
                model=model,
                n=1,
                top_p=0.8,
                temperature=0.8,
                stop=None,
                max_tokens=1000,
                messages=[
                    {
                        "role": "system",
                        "content": "As a highly skilled AI, you will provide me with a properly formatted changelog targeting the final user, in a list form using Markdown, and nothing else."
                    },
                    {
                        "role": "user",
                        "content": f"\n\n# COMMIT MESSAGES:\n{commit_messages}\n\n# DIFF:\n" + chunk + "\n\n# CHANGELOG:\n"
                                                                                                                                                                                                  # "content": PROMPT_CHANGELOG + "\n\nDIFF:\n" + chunk
                    },
                ])
            changelog += response.choices[0].message.content                                                                                                                                      # type: ignore

    logger.info(f"{changelog}")


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
        default="gemini-1.5-pro",
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
            help_lines = subparser.format_help().split("\n")
            help_lines[0] = "\n\u001b[34;01m" + help_lines[0].replace("usage: ", "")
            help_lines.pop(1)
            help_lines[1] = "\u001b[34m" + help_lines[1] + "\u001b[00m"
            PARSER.epilog = (PARSER.epilog or "") + ("\u001b[00m\n\u001b[36;00m".join(help_lines[0:2]) + "\n" + ("\n  ").join(help_lines[2:]))

    # try to make the first argument a subcommand if it's a number
    # this is useful for running `cactus 1` instead of `cactus generate 1`
    if len(sys.argv) == 2 and sys.argv[1].isdigit():
        sys.argv.insert(1, "generate")
    args = PARSER.parse_args()

    setup_logging("INFO")
    # setup_logging("DEBUG")

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
