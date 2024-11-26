import sys
from loguru import logger

from constants import MODEL_TOKEN_LIMITS, PROMPT_CHANGELOG_GENERATOR, PROMPT_CHANGELOG_SYSTEM
from api import num_tokens_from_string, split_into_chunks
from utils import run
import google.generativeai as genai
import openai

def generate_changelog(args, model):
    # get list of commit messages from args.sha to HEAD
    commit_messages = [msg for msg in run(f"git log --pretty=format:'%s' {args.sha}..HEAD").stdout.decode('utf-8').split("\n") if msg]

    # prepare exclude patterns for git diff
    pathspec = f"-- {args.pathspec}" if args.pathspec else ''

    # get git diff from args.sha to HEAD
    result = run(f"git diff --ignore-all-space --ignore-blank-lines -U{args.context_size} {args.sha} {pathspec}")
    if result.returncode != 0:
        logger.error(f"An error occurred while getting git diff: {result.stderr.decode('utf-8')}")
        sys.exit(1)
    diff = result.stdout.decode('utf-8')

    # Split the diff into chunks if it exceeds the token limit
    chunks = split_into_chunks(diff, model)
    logger.debug(f"Diff length: {len(diff)}")

    if len(chunks) > 1:
        logger.warning(
            f"Diff went over max token limit ({num_tokens_from_string(diff, model)} > {MODEL_TOKEN_LIMITS.get(model)}). Splitted into {len(chunks)} chunks.")

    changelog = ''.join(
        genai.GenerativeModel(
            model_name=model,
            generation_config={
                "temperature": 1,
                "top_p": 0.95,
                "top_k": 64,
                "max_output_tokens": 8192,
                "response_mime_type": "text/plain",
            },
            system_instruction=PROMPT_CHANGELOG_SYSTEM,
        ).start_chat().send_message(
            PROMPT_CHANGELOG_GENERATOR.format(commit_messages=commit_messages, chunk=chunk)
        ).text if "gemini" in model else openai.chat.completions.create(
            model=model,
            n=1,
            top_p=0.8,
            temperature=0.8,
            max_tokens=1000,
            messages=[
                {"role": "system", "content": PROMPT_CHANGELOG_SYSTEM},
                {"role": "user", "content": PROMPT_CHANGELOG_GENERATOR.format(commit_messages=commit_messages, chunk=chunk)}
            ]
        ).choices[0].message.content for chunk in chunks
    )
    logger.info(changelog)
