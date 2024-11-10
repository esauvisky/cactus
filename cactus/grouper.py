from typing import List
import os
import re
import numpy as np
from collections import Counter
from git_utils import parse_diff, stage_changes
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
        filtered_words = filter(lambda word: word.lower() not in RESERVED_WORDS | COMMON_ENGLISH_WORDS, map(str.lower, words))
        word_counts.update(filtered_words)

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
    vectorizer = TfidfVectorizer if type == 'tfidf' else CountVectorizer
    matrix = cosine_similarity(vectorizer(stop_words=stop_words, lowercase=False).fit_transform(hunks)) if type in ['tfidf', 'count'] else np.array([
        [1 if i == j else (jaccard_similarity(hunks[i], hunks[j]) if type == 'jaccard' else fuzz.token_set_ratio(hunks[i], hunks[j]) / 100) for j in range(len(hunks))] for i in range(len(hunks))
    ])
    return matrix


def get_modified_lines(hunk):
    return os.linesep.join(
        re.sub(r"[^a-zA-Z0-9\s]", " ", re.sub(r"([+-]) ?", "", re.sub(r" +", " ", line)))
        for line in hunk.splitlines() if line.startswith(('+', '-'))
    )


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


