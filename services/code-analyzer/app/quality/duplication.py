"""Copy-pasted code inside one project (FR-03.4), robust to renamed variables."""

from collections import defaultdict

from app.quality.tokens import fingerprints, tokenize

MIN_FILE_TOKENS = 40


def find_duplicates(sources: dict[str, str]) -> dict:
    """sources: path -> code. Returns duplicated blocks and the duplicated-line share."""
    places: dict[int, list[tuple[str, int]]] = defaultdict(list)
    total_lines = 0
    for path, source in sources.items():
        total_lines += sum(1 for line in source.splitlines() if line.strip())
        tokens = tokenize(source)
        if len(tokens) < MIN_FILE_TOKENS:
            continue
        for fingerprint in fingerprints(tokens):
            places[fingerprint.hash].append((path, fingerprint.line))

    # Pair up the locations that share fingerprints, then merge them into line ranges.
    pairs: dict[tuple[str, str], list[tuple[int, int]]] = defaultdict(list)
    for locations in places.values():
        unique = sorted(set(locations))
        for i in range(len(unique)):
            for j in range(i + 1, len(unique)):
                (file_a, line_a), (file_b, line_b) = unique[i], unique[j]
                if file_a == file_b and abs(line_a - line_b) < 3:
                    continue  # the same spot seen twice
                pairs[(file_a, file_b)].append((line_a, line_b))

    blocks, duplicated = [], defaultdict(set)
    for (file_a, file_b), hits in pairs.items():
        if len(hits) < 2:
            continue  # one shared fingerprint is too little to call a copy
        lines_a = [a for a, _ in hits]
        lines_b = [b for _, b in hits]
        block = {
            "file": file_a,
            "lines": [min(lines_a), max(lines_a)],
            "other_file": file_b,
            "other_lines": [min(lines_b), max(lines_b)],
        }
        blocks.append(block)
        duplicated[file_b].update(range(block["other_lines"][0], block["other_lines"][1] + 1))
    lines = sum(len(v) for v in duplicated.values())
    blocks.sort(key=lambda b: b["lines"][1] - b["lines"][0], reverse=True)
    return {
        "duplicate_blocks": blocks[:20],
        "duplicated_lines": lines,
        "code_duplication_percentage": round(100 * lines / total_lines, 1) if total_lines else 0.0,
    }
