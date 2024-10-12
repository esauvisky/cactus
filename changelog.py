import sys
from loguru import logger

from constants import MODEL_TOKEN_LIMITS, PROMPT_CHANGELOG_GENERATOR, PROMPT_CHANGELOG_SYSTEM
from api import num_tokens_from_string, split_into_chunks
from utils import run
import google.generativeai as genai
import openai

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
        logger.warning(
            f"Diff went over max token limit ({num_tokens_from_string(diff, model)} > {MODEL_TOKEN_LIMITS.get(model)}). Splitted into {len(chunks)} chunks.")

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
                generation_config=generation_config,  # type: ignore
                # safety_settings=Adjust safety settings
                # See https://ai.google.dev/gemini-api/docs/safety-settings
                system_instruction=PROMPT_CHANGELOG_SYSTEM,
            )
            chat_session = gemini_model.start_chat()
            response = chat_session.send_message(PROMPT_CHANGELOG_GENERATOR.format(commit_messages=commit_messages, chunk=chunk))
            changelog += response.text
        else:
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
                        "content": PROMPT_CHANGELOG_SYSTEM
                    },
                    {
                        "role": "user",
                        "content": PROMPT_CHANGELOG_GENERATOR.format(commit_messages=commit_messages, chunk=chunk)
                        # "content": PROMPT_CHANGELOG + "\n\nDIFF:\n" + chunk
                    },
                ])
            changelog += response.choices[0].message.content  # type: ignore

    logger.info(f"{changelog}")
