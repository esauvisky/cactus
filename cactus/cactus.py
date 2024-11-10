__version__ = "4.4.0"
import os  # Added to handle relative imports

sys.path.append(os.path.dirname(os.path.dirname(os.path.realpath(__file__))))  # Add

from api import get_clusters_from_gemini, get_clusters_from_openai, load_api_key, setup_api_key
from changelog import generate_changelog
from utils import setup_logging
from git_utils import run, get_git_diff, restore_changes, parse_diff, stage_changes
from grouper import parse_diff, stage_changes

from prompt import display_clusters, handle_user_input
        file_headers.append(str("".join(list(patched_file.patch_info)[:-1])).strip())
        if patched_file.is_modified_file:
            file_headers.append(f'--- {patched_file.source_file}')
            file_headers.append(f'+++ {patched_file.target_file}')

        file_header_text = '\n'.join(file_headers)
        if len(patched_file) == 0:
            logger.info(f"No hunks found for {patched_file.path}.")
            patch_bytes = file_header_text.encode('latin-1')
            patches.append(patch_bytes)
            continue
            patch_text = file_header_text + '\n' + hunk_text
    Prepares the prompt data in specific format from the diff data.
    file_data = []
    hunk_data = []
        return ""
    hunk_index = 1
    # Prepare files and hunks section
        file_data.append(f"\n# FILE: {file_path}")
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
            hunk_lines = [line.encode('latin-1').decode('utf-8', errors='replace') for line in str(hunk).splitlines()]
            hunk_data.append(f"\n## HUNK {hunk_index} ({file_path})")
            for line in hunk_lines:
                hunk_data.append(f"HUNK: {line}")
    prompt_data = file_data + hunk_data
    return "\n".join(prompt_data)
            stage_changes([all_hunks[i - 1] for i in cluster["hunk_indices"]])
    logger.info(f"Running cactus version {__version__}")

