from torch.multiprocessing import get_context, set_start_method

try:
    set_start_method("spawn")
except RuntimeError:
    pass

_manager = None


def get_manager():
    global _manager
    if _manager is None:
        _manager = get_context("spawn").Manager()
    return _manager
