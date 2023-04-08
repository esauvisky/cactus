import subprocess
import os
import shlex
import numpy as np
from unidiff import PatchSet, PatchedFile, UnidiffParseError, Hunk
import tensorflow_hub as hub
from scipy.cluster import hierarchy
from sklearn.cluster import KMeans, DBSCAN

def embed_hunks(embed, hunks):
    hunk_texts = [str(hunk) for hunk in hunks]
    return embed(hunk_texts).numpy()


def cluster_embeddings(embeddings: np.ndarray, threshold: float = 0.7):
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


def create_patch(hunks):
    retval = ""
    last_patch_info = None
    for hunk_info in hunks:
        patched_file, hunk = hunk_info
        if last_patch_info != patched_file.patch_info:
            retval += "\n" + "".join(patched_file.patch_info)
            last_patch_info = patched_file.patch_info
        retval += f"--- {patched_file.source_file}\n"
        retval += f"+++ {patched_file.target_file}\n"
        retval += str(hunk) + "\n\n"
    return retval


def get_hunks(git_diff):
    grouped_hunks = {}
    try:
        patch_set = PatchSet(git_diff)
        hunks = [(patched_file, hunk) for patched_file in patch_set for hunk in patched_file]
        embed = hub.load("https://tfhub.dev/google/universal-sentence-encoder/4")
        embeddings = embed_hunks(embed, hunks)


        # dbscan = DBSCAN(n_jobs=-1).fit(embeddings)
        # cluster_labels = dbscan.labels_

        # kmeans = KMeans(n_clusters=3).fit(embeddings)
        # cluster_labels = kmeans.labels_

        clusters = cluster_embeddings(embeddings)
        grouped_hunks = group_hunks_by_cluster(hunks, clusters)

        # # Map the cluster labels back to the original Git diff hunks
        # diff_hunk_groups = {}
        # for i, label in enumerate(cluster_labels):
        #     if label not in diff_hunk_groups:
        #         diff_hunk_groups[label] = []
        #     diff_hunk_groups[label].append(hunks[i])
        # grouped_hunks = diff_hunk_groups
    except UnidiffParseError:
        patch_set = PatchSet([git_diff])
        if len(patch_set) == 1:
            # Only one hunk in the git_diff
            hunks = [(patch_set[0], patch_set[0][0])]
            grouped_hunks = {1: hunks}
    except Exception as e:
        print(f"Error parsing git diff: {e}")

    return grouped_hunks

def stage_hunks(hunks):
    for hunk_info in hunks:
        patched_file, hunk = hunk_info

        with open("temp.diff", "w") as f:
            f.write(f"--- {patched_file.source_file}\n")
            f.write(f"+++ {patched_file.target_file}\n")
            f.write(str(hunk))
            f.write("\n")
        subprocess.run(["git", "apply", "--cached", "temp.diff"])
    os.remove("temp.diff")


def stage_changes(hunks):
    with open('.tmp_patch', 'w') as fd:
        fd.write("".join(hunks[0][0].patch_info))
        for hunk_info in hunks:
            patched_file, hunk = hunk_info
            fd.write(f"--- {patched_file.source_file}\n")
            fd.write(f"+++ {patched_file.target_file}\n")
            fd.write(str(hunk))
            fd.write("\n")

    subprocess.run('git apply --cached .tmp_patch', shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    os.remove('.tmp_patch')
    # print(f'Staged patch:\n{patch}')

# def extract_hunks(git_diff):
#     hunks = []
#     current_hunk = ""

#     for line in git_diff.split("\n"):
#         if line.startswith("diff --git"):  # New file diff starts
#             if current_hunk:  # Save the previous hunk if it exists
#                 hunks.append(current_hunk.strip())
#                 current_hunk = ""
#             header = line
#         elif line.startswith("@@"):  # New block starts
#             if current_hunk:
#                 hunks.append(current_hunk.strip())
#                 current_hunk = ""
#             current_hunk += header + "\n"

#         current_hunk += line + "\n"

#     # Save the last hunk
#     if current_hunk:
#         hunks.append(current_hunk.strip())

#     return hunks

# def compute_embeddings(tokenizer, model, hunks):
#     embeddings = []
#     for hunk in hunks:
#         inputs = tokenizer(str(hunk), return_tensors='pt', truncation=True)
#         outputs = model(**inputs, return_dict=True)
#         mean_embedding = np.mean(outputs.last_hidden_state[0].detach().numpy(), axis=0)
#         embeddings.append(mean_embedding)
#     return np.array(embeddings)

# def group_related_changes_clustering(embeddings, num_groups=2):
#     clustering = AgglomerativeClustering(n_clusters=num_groups).fit(embeddings)
#     groups = {i: [] for i in range(num_groups)}

#     for i, cluster_label in enumerate(clustering.labels_):
#         groups[cluster_label].append(i)

#     return groups

# def group_related_changes_cosine(embeddings, cosine_similarity_threshold=0.98):
#     groups = defaultdict(list)

#     group_id = 0
#     for idx, emb in enumerate(embeddings):
#         if idx == 0:
#             groups[group_id].append(idx)
#             continue

#         # Compute cosine similarity with the last element of each group
#         similarities = [
#             cosine_similarity(emb.reshape(1, -1), embeddings[group[-1]].reshape(1, -1))
#             for group in groups.values()
#         ]

#         # Find the maximum similarity and its index to determine the related group
#         max_sim_idx, max_sim = max(enumerate(similarities), key=lambda x: x[1])

#         if max_sim > cosine_similarity_threshold:
#             groups[max_sim_idx].append(idx)
#         else:
#             group_id += 1
#             groups[group_id].append(idx)

#     return groups

# def group_hunks_by_cluster(hunks, clusters):
#     grouped_hunks = {}
#     for hunk_info, cluster in zip(hunks, clusters):
#         _, hunk = hunk_info
#         if cluster not in grouped_hunks:
#             grouped_hunks[cluster] = []
#         grouped_hunks[cluster].append(hunk_info)

# def get_grouped_hunks(diff):
#     # Extract hunks from the diff
#     patch_set = PatchSet(diff)
#     hunks = [(patched_file, hunk) for patched_file in patch_set for hunk in patched_file]

#     # Load the model and tokenizer
#     model_name = "distilgpt2"
#     tokenizer = AutoTokenizer.from_pretrained(model_name)
#     model = AutoModel.from_pretrained(model_name)

#     # Compute embeddings for each hunk
#     embeddings = compute_embeddings(tokenizer, model, hunks)

#     # Cluster hunks into groups
#     # num_groups = 4  # Anticipated number of groups, can be adjusted based on your use-case
#     # groups = group_related_changes_clustering(embeddings, num_groups=num_groups)

#     # You can adjust `cosine_similarity_threshold` value to group the changes
#     groups = group_related_changes_cosine(embeddings, cosine_similarity_threshold=0.99)

#     grouped_hunks = []
#     for _, hunk_ids in groups.items():
#         grouped_hunks.append([hunks[hunk_id] for hunk_id in hunk_ids])

#     return grouped_hunks
