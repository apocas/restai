import sys
import importlib
import pickle

if __name__ == "__main__":
    # Args: worker_module, prompt, sharedmem_path
    worker_module = sys.argv[1]
    prompt = sys.argv[2]
    sharedmem_path = sys.argv[3]

    # Load sharedmem dict from file
    with open(sharedmem_path, "rb") as f:
        sharedmem = pickle.load(f)

    # Import and run the worker
    mod = importlib.import_module(worker_module)
    mod.worker(prompt, sharedmem)

    # Save sharedmem dict back to file
    with open(sharedmem_path, "wb") as f:
        pickle.dump(sharedmem, f)
