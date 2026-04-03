from torch.multiprocessing import get_context, set_start_method

try:
    set_start_method("spawn")
except RuntimeError:
    pass

_manager = None


def get_manager():
    global _manager
    if _manager is None:
        try:
            _manager = get_context("spawn").Manager()
        except Exception:
            # Fallback for environments where multiprocessing Manager fails
            # (e.g., after many test iterations in CI)
            import multiprocessing
            _manager = multiprocessing.Manager()
    return _manager
