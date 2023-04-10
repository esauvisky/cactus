import re
import subprocess
import os
import shlex
import numpy as np
from unidiff import PatchSet, PatchedFile, UnidiffParseError, Hunk
from scipy.cluster import hierarchy
from sklearn.cluster import AgglomerativeClustering
from tempfile import NamedTemporaryFile
from loguru import logger
from thefuzz import fuzz

from sklearn.feature_extraction.text import TfidfVectorizer, CountVectorizer
from sklearn.metrics.pairwise import cosine_similarity

def jaccard_similarity(str1, str2):
    words1 = set(str1.split())
    words2 = set(str2.split())

    intersection = words1.intersection(words2)
    union = words1.union(words2)

    if not union:
        return 0

    return len(intersection) / len(union)


def similarity_matrix(hunks, type='fuzzy'):
    if type == 'tfidf':
        # Compute the TF-IDF matrix for the hunks
        vectorizer = TfidfVectorizer()
        tfidf_matrix = vectorizer.fit_transform(hunks)

        # Calculate the pairwise cosine similarity
        matrix = cosine_similarity(tfidf_matrix, tfidf_matrix)
    elif type == 'count':
        # Compute the Bag of Words matrix for the hunks
        vectorizer = CountVectorizer()
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


def group_hunks(git_diff, n_clusters, affinity_threshold):
    # Parse hunks from the git_diff
    patch_set = PatchSet(git_diff)
    hunk_data = [(patched_file, str(hunk)) for patched_file in patch_set for hunk in patched_file]

    if len(hunk_data) <= 2:
        return {0: hunk_data}

    # Calculate the similarity matrix
    matrix = similarity_matrix([get_modified_lines(h[1]) for h in hunk_data])

    # Perform clustering using AgglomerativeClustering
    clustering = AgglomerativeClustering(
        n_clusters=n_clusters, metric="precomputed", linkage="average", distance_threshold=1 - affinity_threshold)
    clustering.fit(1 - matrix)

    # Create clusters of hunks
    clusters = {}
    for idx, label in enumerate(clustering.labels_):
        if label not in clusters:
            clusters[label] = []
        clusters[label].append(hunk_data[idx])

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


def stage_changes(hunks):
    with NamedTemporaryFile(mode='w', prefix='.tmp_patch_', delete=False) as fd:
        fd.write("".join(hunks[0][0].patch_info))
        filename = fd.name
        for hunk_info in hunks:
            patched_file, hunk = hunk_info
            fd.write(f"--- {patched_file.source_file}\n")
            fd.write(f"+++ {patched_file.target_file}\n")
            fd.write(str(hunk))
            fd.write("\n")
    subprocess.run(
        f'git apply --cached --unidiff-zero {filename}', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
