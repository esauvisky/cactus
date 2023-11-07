import os
import pprint
import re
import shlex
import subprocess
from collections import Counter
from tempfile import NamedTemporaryFile

import matplotlib.pyplot as plt
import numpy as np
from loguru import logger
from scipy.cluster import hierarchy
from sklearn.cluster import AgglomerativeClustering
from sklearn.feature_extraction.text import CountVectorizer, TfidfVectorizer
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_similarity
from thefuzz import fuzz
from unidiff import Hunk, PatchedFile, PatchSet, UnidiffParseError


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
        matrix = similarity_matrix(hunks, type='count', stop_words=most_common_words)

        # Calculate the explained variance for the current n
        explained_variance = np.sum(np.var(matrix, axis=0))
        explained_variances.append(explained_variance)

    # Plot the explained variance as a function of n
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
    return '\n'.join(filtered_lines)


def extract_renames(git_diff):
    patch_set = PatchSet(git_diff)
    hunks = [(patched_file, str(hunk)) for patched_file in patch_set for hunk in patched_file]
    renames = []
    clean_diff = []

    for patched_file in patch_set:
        if patched_file.is_rename:
            renames.append((patched_file, str(patched_file)))
        else:
            clean_diff.append(str(patched_file))

    return renames, clean_diff


def create_rename_hunks(renames):
    rename_hunks = []
    for old_name, new_name in renames:
        # Create a synthetic hunk string representing the rename
        synthetic_hunk = f"--- a/{old_name}\n+++ b/{new_name}\n"
        rename_hunks.append((old_name, new_name, synthetic_hunk))
    return rename_hunks


def group_hunks(git_diff, n_clusters, affinity_threshold):
    # Parse hunks from the git_diff
    patch_set = PatchSet(git_diff)
    hunks = [(patched_file, str(hunk)) for patched_file in patch_set for hunk in patched_file]

    if len(hunks) < 2:
        return {0: hunks}

    # Get the most common words in the hunks
    most_common_words = get_optimal_n_common_words([hunk for _, hunk in hunks])
    logger.debug("Most common words: {}".format(most_common_words))

    # Calculate the similarity matrix
    matrix = similarity_matrix([get_modified_lines(h[1]) for h in hunks], stop_words=most_common_words)

    # Perform clustering using AgglomerativeClustering
    if n_clusters:
        clustering = AgglomerativeClustering(n_clusters=n_clusters, metric="precomputed", linkage="average")
    else:
        clustering = AgglomerativeClustering(
            n_clusters=None, metric="precomputed", linkage="average", distance_threshold=1 - affinity_threshold)
    clustering.fit(1 - matrix)

    # Create clusters of hunks
    clusters = {}
    for idx, label in enumerate(clustering.labels_):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(hunks[idx])

    return clusters


def embed_hunks(embed, hunks):
    hunk_texts = [str(hunk) for hunk in hunks]
    return embed(hunk_texts).numpy()


def cluster_embeddings(embeddings: np.ndarray, threshold: float = 0.2):
    distance_matrix = 1 - np.inner(embeddings, embeddings)
    linkage = hierarchy.linkage(distance_matrix, 'complete')
    clusters = hierarchy.fcluster(linkage, 1 - threshold, 'distance')
    return clusters


def group_hunks_by_cluster(hunks, clusters):
    grouped_hunks = {}
    for hunk, cluster in zip(hunks, clusters):
        if cluster not in grouped_hunks:
            grouped_hunks[cluster] = []
        grouped_hunks[cluster].append(hunk)
    return grouped_hunks


# Assuming that renames are a list of tuples with (old_name, new_name)
def generate_rename_hunks(renames):
    # We simulate a hunk with the renaming information
    hunks = []
    for rename in renames:
        # print(rename)
        old_name, new_name = rename
        hunk_text = f"rename from {old_name}\nrename to {new_name}\n"
        hunk = (None, hunk_text) # We use None to denote that it's not an actual file change
        hunks.append(hunk)
    return hunks


def stage_renames(renames):
    # Use git mv to handle renames and stage them
    for rename in renames:
        # Handle regular changes
        with NamedTemporaryFile(mode='w', prefix='.tmp_patch_', delete=False) as fd:
            # pprint.pprint(hunks)
            # No need to join on patch_info since it's a string already included in the hunk data
            filename = fd.name

        for patched_file, hunk in rename:
            with open(filename, 'a') as fd:
                fd.write(f"--- {patched_file.source_file}\n")
                fd.write(f"+++ {patched_file.target_file}\n")
                fd.write(str(hunk))
                fd.write("\n")

        # Apply the patch file
        subprocess.run(
            f'git apply --cached --unidiff-zero {filename}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

        # old_name, new_name = patched_file.source_file, patched_file.target_file
        # subprocess.run(['git', 'mv', old_name, new_name], check=True)
        # subprocess.run(['git', 'add', new_name], check=True)

def stage_changes(hunks):
    # Handle regular changes
    with NamedTemporaryFile(mode='w', prefix='.tmp_patch_', delete=False) as fd:
        # pprint.pprint(hunks)
        # No need to join on patch_info since it's a string already included in the hunk data
        filename = fd.name

    for patched_file, hunk in hunks:
        with open(filename, 'a') as fd:
            fd.write(f"--- {patched_file.source_file}\n")
            fd.write(f"+++ {patched_file.target_file}\n")
            fd.write(str(hunk))
            fd.write("\n")

    # Apply the patch file
    subprocess.run(
        f'git apply --cached --unidiff-zero {filename}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
