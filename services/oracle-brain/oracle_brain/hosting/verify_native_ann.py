"""Network-free stock SDK/native ANN qualification with invented vectors only."""
from importlib.metadata import version
from pathlib import Path
from tempfile import TemporaryDirectory


def qualify():
    import hnswlib
    import numpy as np
    from graphrag_sdk import GraphRAG

    if version("hnswlib") != "0.8.0" or version("graphrag-sdk") != "1.4.0":
        raise RuntimeError("pinned native search and SDK require requalification")
    if not callable(GraphRAG):
        raise RuntimeError("stock SDK unavailable")
    vectors = np.eye(8, dtype=np.float32)[:3]
    labels = np.array([101, 202, 303], dtype=np.int64)
    index = hnswlib.Index(space="l2", dim=8)
    index.init_index(max_elements=3, ef_construction=32, M=8)
    index.set_num_threads(1)
    index.add_items(vectors, labels)
    index.set_ef(8)
    found, distances = index.knn_query(vectors, k=1)
    if not np.array_equal(found[:, 0], labels) or not np.all(distances == 0):
        raise RuntimeError("native ANN retrieval qualification failed")
    with TemporaryDirectory(prefix="oracle-native-ann-") as directory:
        path = str(Path(directory) / "invented.index")
        index.save_index(path)
        restored = hnswlib.Index(space="l2", dim=8)
        restored.load_index(path, max_elements=3)
        restored.set_num_threads(1)
        restored.set_ef(8)
        again, restored_distances = restored.knn_query(vectors, k=1)
        if not np.array_equal(again, found) or not np.array_equal(restored_distances, distances):
            raise RuntimeError("native ANN persistence qualification failed")
    return {"native_ann": "qualified", "stock_sdk": "1.4.0", "vectors": 3, "provider_calls": 0}


if __name__ == "__main__":
    import json
    print(json.dumps(qualify(), sort_keys=True))
