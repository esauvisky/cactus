import json
import os
import pprint
from loguru import logger
import openai
import tiktoken

from .constants import CLASSIFICATOR_SCHEMA_GEMINI, CLASSIFICATOR_SCHEMA_OPENAI, MODEL_TOKEN_LIMITS, PROMPT_CLASSIFICATOR_SYSTEM

import google.generativeai as genai
from google.generativeai import protos
from google.generativeai.types import HarmCategory, HarmBlockThreshold


def setup_api_key(api_type):
    api_key = input(f"Enter your {api_type} API key: ")
    config_dir = os.path.expanduser("~/.config/cactus")
    os.makedirs(config_dir, exist_ok=True)
    with open(os.path.join(config_dir, f"{api_type.lower()}_api_key"), "w", encoding='utf-8', newline=os.linesep) as f:
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
    """
    Split the text into chunks of the specified size.
    """
    max_tokens = MODEL_TOKEN_LIMITS.get(model, 127514) - 64 # Default to 127514 if model not found
    tokens = text.split('\n')
    chunks, current_chunk, current_length = [], [], 0

    for token in tokens:
        token_length = num_tokens_from_string(token, model)
        if current_length + token_length > max_tokens:
            chunks.append('\n'.join(current_chunk))
            current_chunk, current_length = [], 0
        current_chunk.append(token)
        current_length += token_length

    if current_chunk:
        chunks.append('\n'.join(current_chunk))

    return chunks


def get_clusters_from_openai(prompt_data, clusters_n, hunks_n, model):
    model_instance = openai.chat.completions.create(
        model=model,
        top_p=1,
        temperature=1,
        max_tokens=1024,
        response_format={"type": "json_schema", "json_schema": CLASSIFICATOR_SCHEMA_OPENAI}, # type: ignore

        messages=[
            {
                "role": "system", "content": PROMPT_CLASSIFICATOR_SYSTEM
            },
            {
                "role": "user", "content": json.dumps(prompt_data) + (f"\n\nReturn a JSON with {clusters_n} commits for the hunks above."
                                                                     if clusters_n else "\n\nReturn the JSON for the hunks above.")
            },
        ])
    clusters = json.loads(model_instance.choices[0].message.content)["commits"]                           # type: ignore
    sum_hunks = sum([len(cluster['hunk_indices']) for cluster in clusters])
    if sum_hunks != hunks_n:
        logger.warning(f"Expected {hunks_n} hunks, but got {sum_hunks}. Trying again.")
        logger.debug(pprint.pformat(clusters))
        return get_clusters_from_openai(prompt_data, clusters_n, hunks_n, model)
    return clusters


def get_clusters_from_gemini(prompt_data, clusters_n, hunks_n, model):
    model_instance = genai.GenerativeModel(
        model_name=model,
        generation_config={
            "temperature": 1,
            "top_p": 1,
            "max_output_tokens": 1024,
            "response_mime_type": "application/json",
            "response_schema": CLASSIFICATOR_SCHEMA_GEMINI
        },                                                                                 # type: ignore
        safety_settings={
            HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HARASSMENT: HarmBlockThreshold.BLOCK_NONE,
            HarmCategory.HARM_CATEGORY_HATE_SPEECH: HarmBlockThreshold.BLOCK_NONE
        },
        system_instruction=PROMPT_CLASSIFICATOR_SYSTEM,
    )

    chat_session = model_instance.start_chat(history=[])

    response = chat_session.send_message(json.dumps(prompt_data) + (f"\n\nReturn a JSON with {clusters_n} commits for the hunks above."
                                         if clusters_n else "\n\nReturn the JSON for the hunks above."))
    content = json.loads(response.text)
    clusters = content["commits"]

    sum_hunks = sum([len(cluster['hunk_indices']) for cluster in clusters])
    if sum_hunks != hunks_n:
        logger.warning(f"Expected {hunks_n} hunks, but got {sum_hunks}. Trying again.")
        logger.debug(pprint.pformat(clusters))
        return get_clusters_from_gemini(prompt_data, clusters_n, hunks_n, model)
    return clusters
