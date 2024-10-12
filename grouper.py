from typing import List
import os
import re
from collections import Counter
import tempfile
import subprocess

import numpy as np
from loguru import logger
from scipy.cluster import hierarchy
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz
from unidiff import PatchedFile, PatchSet, UnidiffParseError

# List of common programming language reserved words to exclude (example for Python)
RESERVED_WORDS = set([
    "def",
    "import",
    "from",
    "as",
    "if",
    "else",
    "return",
    "class",
    "self",
    "for",
    "in",
    "try",
    "except",
    "with",
    "while",
    "break",
    "continue",
    "pass",
    "lambda",
    "is",
    "not",
    "and",
    "or",
    "None",
    "True",
    "False"
])

# List of common English words to exclude
COMMON_ENGLISH_WORDS = set([
    "the",
    "and",
    "in",
    "to",
    "a",
    "of",
    "is",
    "it",
    "that",
    "for",
    "on",
    "with",
    "this",
    "as",
    "by",
    "are",
    "be",
    "or",
    "an",
    "have",
    "can"
])


def jaccard_similarity(str1, str2):
    words1 = set(str1.split())
    words2 = set(str2.split())

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    if not union:
        return 0

    return len(intersection) / len(union)


def get_most_common_words(hunks, n=10):
    word_counts = Counter()

    for hunk in hunks:
        words = re.findall(r'\w+', get_modified_lines(hunk))
        word_counts.update(words)

    return [word for word, _ in word_counts.most_common(n)]


def get_optimal_n_common_words(hunks, min_n=1, max_n=50):
    explained_variances = []

    for n in range(min_n, max_n + 1):
        # Get the most common words for the current value of n
        most_common_words = get_most_common_words(hunks, n=n)

        # Calculate the similarity matrix while ignoring the most common words
        stop_words = list(set().union(most_common_words, RESERVED_WORDS, COMMON_ENGLISH_WORDS))
        matrix = similarity_matrix(hunks, type='count', stop_words=stop_words)

        # Calculate the explained variance for the current n
        explained_variance = np.sum(np.var(matrix, axis=0))
        explained_variances.append(explained_variance)

    ## Plot the explained variance as a function of n
    # plt.plot(range(min_n, max_n + 1), explained_variances)
    # plt.xlabel('Number of Most Common Words Ignored')
    # plt.ylabel('Explained Variance')
    # plt.show()

    # Find the optimal n using the elbow method
    optimal_n = min_n
    max_diff = 0
    for i in range(1, len(explained_variances) - 1):
        diff = explained_variances[i - 1] - explained_variances[i + 1]
        if diff > max_diff:
            max_diff = diff
            optimal_n = i + min_n

    # return the words that we want to ignore
    return get_most_common_words(hunks, optimal_n)


def similarity_matrix(hunks, type='count', stop_words=None):
    if type == 'tfidf':
        # Compute the TF-IDF matrix for the hunks
        vectorizer = TfidfVectorizer(stop_words=stop_words, lowercase=False)
        tfidf_matrix = vectorizer.fit_transform(hunks)

        # Calculate the pairwise cosine similarity
        matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
    elif type == 'count':
        # Compute the Bag of Words matrix for the hunks
        vectorizer = CountVectorizer(stop_words=stop_words, lowercase=False)
        bow_matrix = vectorizer.fit_transform(hunks)

        # Calculate the pairwise cosine similarity between the matrix rows
        matrix = cosine_similarity(bow_matrix)
    elif type == 'jaccard' or type == 'fuzzy':
        n = len(hunks)
        matrix = np.zeros((n, n))

        for i in range(n):
            for j in range(i, n):
                if i == j:
                    matrix[i][j] = 1
                else:
                    if type == 'jaccard':
                        sim_score = jaccard_similarity(hunks[i], hunks[j])
                    elif type == 'fuzzy':
                        sim_score = fuzz.token_set_ratio(hunks[i], hunks[j]) / 100
                    matrix[i][j] = sim_score
                    matrix[j][i] = sim_score
    return matrix


def get_modified_lines(hunk):
    filtered_lines = []
    for line in hunk.splitlines():
        if line.startswith('+') or line.startswith('-'):
            line = re.sub(r" +", " ", line)
            line = re.sub(r"([+-]) ?", "", line)
            # replaces all special characters with space
            line = re.sub(r"[^a-zA-Z0-9\s]", " ", line)
            filtered_lines.append(line)
    return os.linesep.join(filtered_lines)


def extract_renames(git_diff):
    patch_set = parse_diff(git_diff)

    renames = []
    clean_diff = []

    for patched_file in patch_set:
        if patched_file.is_rename:
            renames.append((patched_file, str(patched_file)))
        else:
            clean_diff.append(str(patched_file))

    return renames, clean_diff


def parse_diff(git_diff) -> List[PatchedFile]:
    for _ in range(5):
        try:
            # Attempt to parse the diff
            patch_set = PatchSet.from_string(git_diff)
            break  # Parsing successful, break the loop
        except UnidiffParseError:
            # If parsing fails, add a newline and try again
            git_diff += os.linesep
    return patch_set


def stage_changes(hunks):
    # Handle regular changes
    with tempfile.NamedTemporaryFile(mode='wb', prefix='.tmp_patch_', delete=False) as fd:
        filename = fd.name

    for hunk in hunks:
        with open(filename, 'ab') as fd:
            fd.write(str(hunk).encode('utf-8'))
            fd.write(b'\n')

    # Apply the patch file
    result = subprocess.run(
        f'git apply --cached --unidiff-zero --ignore-whitespace {filename}',
        shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, encoding='utf-8')
    
    if result.returncode != 0:
        logger.error(f"Failed to apply patch: {result.stderr}")
        raise Exception("Failed to apply patch")

    # Clean up the temporary file
    os.unlink(filename)
