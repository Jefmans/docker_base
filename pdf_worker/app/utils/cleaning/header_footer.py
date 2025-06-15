# from collections import defaultdict, Counter
from typing import List #, Dict
# import fitz
from typing import List, Tuple, Set
from rapidfuzz import fuzz



def normalize(line: str) -> str:
    return line.strip().lower()

def detect_repeating_lines_next_pages(
    pages_text: List[List[str]],
    n: int = 5
) -> List[Tuple[List[str], List[str]]]:
    """
    For each page, return (header_lines, footer_lines) if any of them repeat
    exactly in the next 1–2 pages.
    """
    results = []

    for i, page in enumerate(pages_text):
        top_lines = [normalize(line) for line in page[:n]]
        bottom_lines = [normalize(line) for line in page[-n:]]

        header_matches = set()
        footer_matches = set()

        for j in [1, 2]:  # lookahead: next page and one after
            if i + j >= len(pages_text):
                continue

            next_page = pages_text[i + j]
            next_top = [normalize(line) for line in next_page[:n]]
            next_bottom = [normalize(line) for line in next_page[-n:]]

            # Exact match for header lines
            for line in top_lines:
                if line and line in next_top:
                    header_matches.add(line)

            # Exact match for footer lines
            for line in bottom_lines:
                if line and line in next_bottom:
                    footer_matches.add(line)

        results.append((
            list(header_matches),
            list(footer_matches)
        ))

    return results



def normalize(line: str) -> str:
    return line.strip().lower()

def collect_repeating_lines(
    pages_text: List[List[str]],
    n: int = 5,
    lookahead: int = 2,
    threshold: int = 100  # exact match = 100, or set to 85 for fuzzy
) -> (Set[str], Set[str]):
    """
    Scans all pages. For each page, checks top/bottom `n` lines against the next `lookahead` pages.
    If any line is repeated, it is added to the global header/footer sets.
    """
    header_candidates = set()
    footer_candidates = set()

    for i, page in enumerate(pages_text):
        top_lines = [normalize(line) for line in page[:n]]
        bottom_lines = [normalize(line) for line in page[-n:]]

        for j in range(1, lookahead + 1):
            if i + j >= len(pages_text):
                break

            next_top = [normalize(line) for line in pages_text[i + j][:n]]
            next_bottom = [normalize(line) for line in pages_text[i + j][-n:]]

            for line in top_lines:
                if line and any(fuzz.ratio(line, other) >= threshold for other in next_top):
                    header_candidates.add(line)

            for line in bottom_lines:
                if line and any(fuzz.ratio(line, other) >= threshold for other in next_bottom):
                    footer_candidates.add(line)

    return header_candidates, footer_candidates




def remove_repeating_lines(
    pages_text: List[List[str]],
    header_set: Set[str],
    footer_set: Set[str],
    n: int = 5
) -> List[str]:
    """
    Removes lines from each page if they match a known header/footer line
    (within top/bottom `n` lines).
    Returns list of cleaned page strings.
    """
    cleaned_pages = []

    for page in pages_text:
        cleaned = []
        for i, line in enumerate(page):
            norm = line.strip().lower()

            is_header_zone = i < n
            is_footer_zone = i >= len(page) - n

            if is_header_zone and norm in header_set:
                continue
            if is_footer_zone and norm in footer_set:
                continue

            cleaned.append(line)

        cleaned_pages.append("\n".join(cleaned))

    return cleaned_pages


# if __name__ == "__main__":
#     # file_path = 'pdfs/black_hole.pdf'
#     # file_path = 'pdfs/de_witte.pdf'
#     file_path = 'pdfs/astronomy.pdf'

#     doc = fitz.open(file_path)
#     pages_text = [page.get_text().splitlines() for page in doc[61:66]]

#     # Step 1: Detect repeated lines
#     header_set, footer_set = collect_repeating_lines(pages_text, n=5)

#     # Step 2: Remove them from the text
#     cleaned_pages = remove_repeating_lines(pages_text, header_set, footer_set, n=5)

#     # Output
#     for i, page in enumerate(cleaned_pages):
#         print(f"\n--- Page {i + 1} ---\n{page}")
