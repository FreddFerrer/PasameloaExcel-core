from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path


def iter_events(logs_dir: Path):
    for file_path in sorted(logs_dir.glob("feedback-*.jsonl")):
        for line in file_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                yield json.loads(line)
            except json.JSONDecodeError:
                continue


def main() -> None:
    parser = argparse.ArgumentParser(description="Analisis agregado de eventos de aprendizaje JSONL.")
    parser.add_argument(
        "--logs-dir",
        type=Path,
        default=Path("app/logs/learning"),
        help="Directorio con archivos feedback-YYYYMMDD.jsonl",
    )
    args = parser.parse_args()

    events = list(iter_events(args.logs_dir))
    if not events:
        print("No se encontraron eventos.")
        return

    by_template = Counter()
    by_pattern = Counter()
    pattern_by_template: dict[str, Counter] = defaultdict(Counter)

    for event in events:
        template = event.get("template_detected") or "template_unknown"
        by_template[template] += 1
        for pattern in event.get("change_patterns", []):
            by_pattern[pattern] += 1
            pattern_by_template[template][pattern] += 1

    print(f"Eventos totales: {len(events)}")
    print("\nEventos por template:")
    for template, count in by_template.most_common():
        print(f"- {template}: {count}")

    print("\nPatrones globales:")
    for pattern, count in by_pattern.most_common():
        print(f"- {pattern}: {count}")

    print("\nPatrones por template:")
    for template, pattern_counts in pattern_by_template.items():
        if not pattern_counts:
            continue
        top_patterns = ", ".join(f"{pattern}={count}" for pattern, count in pattern_counts.most_common(5))
        print(f"- {template}: {top_patterns}")


if __name__ == "__main__":
    main()

