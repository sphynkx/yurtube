from typing import List, Optional, Tuple


def normalize_page(page: Optional[int]) -> int:
    try:
        p = int(page or 1)
    except Exception:
        p = 1
    return 1 if p < 1 else p


def normalize_page_size(ps: Optional[int]) -> int:
    try:
        v = int(ps or 24)
    except Exception:
        v = 24
    if v < 6:
        v = 6
    if v > 96:
        v = 96
    return v


def build_page_range(current: int, total_pages: int, window: int = 2) -> List[Tuple[str, Optional[int]]]:
    """
    Returns the range of pages to display:
    - Always show the first and last pages.
    - Show the neighborhood around the current page: current-window .. current+window.
    - Insert '...' (ellipsis) between non-consecutive segments.
    Elements are returned as ("number", n) or ("ellipsis", None).
    """
    if total_pages <= 1:
        return [("number", 1)]

    pages: List[int] = []
    pages.append(1)
    start = max(2, current - window)
    end = min(total_pages - 1, current + window)
    for p in range(start, end + 1):
        pages.append(p)
    pages.append(total_pages)

    # Remove dups, and sort
    pages = sorted(set(pages))

    # Build with ellipsis
    result: List[Tuple[str, Optional[int]]] = []
    prev = None
    for p in pages:
        if prev is not None and p != prev + 1:
            result.append(("ellipsis", None))
        result.append(("number", p))
        prev = p
    return result