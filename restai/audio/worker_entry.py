import sys
import importlib
import pickle

if __name__ == "__main__":
    worker_module = sys.argv[1]
    prompt = sys.argv[2]
    sharedmem_path = sys.argv[3]

    with open(sharedmem_path, "rb") as f:
        sharedmem = pickle.load(f)

    mod = importlib.import_module(worker_module)
    mod.worker(prompt, sharedmem)

    with open(sharedmem_path, "wb") as f:
        pickle.dump(sharedmem, f)
