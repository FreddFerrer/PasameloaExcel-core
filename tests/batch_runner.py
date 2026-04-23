from __future__ import annotations

import sys
import time
from dataclasses import dataclass
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from app.core.config import get_settings
from app.exporters.excel_exporter import ExcelBytesExporter
from app.services.parser_service import ParserService


@dataclass(slots=True)
class BatchResult:
    pdf_name: str
    ok: bool
    rows: int = 0
    parse_status: str | None = None
    template_detected: str | None = None
    elapsed_ms: int = 0
    output_file: str | None = None
    error: str | None = None


def _resolve_input_dir(default_input: Path) -> Path:
    """Use requested folder first; fallback to legacy test assets when needed."""
    legacy_input = REPO_ROOT / "backend" / "app" / "tests" / "input"
    if default_input.exists() and any(default_input.glob("*.pdf")):
        return default_input
    if legacy_input.exists() and any(legacy_input.glob("*.pdf")):
        print(f"[INFO] No PDFs en {default_input}. Usando fallback legacy: {legacy_input}")
        return legacy_input
    return default_input


def _safe_stem(value: str) -> str:
    stem = Path(value).stem
    cleaned = "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in stem)
    return cleaned or "documento"


def run_batch() -> int:
    backend_dir = REPO_ROOT / "backend"
    input_dir = _resolve_input_dir(backend_dir / "tests" / "input")
    output_dir = backend_dir / "tests" / "output"
    output_dir.mkdir(parents=True, exist_ok=True)

    pdf_files = sorted(input_dir.glob("*.pdf"))
    if not pdf_files:
        print(f"[WARN] No se encontraron PDFs en: {input_dir}")
        print("[HINT] Copia archivos .pdf a tests/input y vuelve a ejecutar.")
        return 1

    settings = get_settings()
    parser_service = ParserService(settings=settings)
    exporter = ExcelBytesExporter(working_temp_dir=settings.working_temp_dir)

    print(f"[RUN] Input:  {input_dir}")
    print(f"[RUN] Output: {output_dir}")
    print(f"[RUN] PDFs detectados: {len(pdf_files)}")
    print("")

    results: list[BatchResult] = []

    for pdf_path in pdf_files:
        start = time.perf_counter()
        print(f"[FILE] Procesando: {pdf_path.name}")
        try:
            execution = parser_service.parse_pdf(pdf_path)
            xlsx_bytes = exporter.export(execution.rows)
            output_name = f"{_safe_stem(pdf_path.name)}.xlsx"
            output_path = output_dir / output_name
            output_path.write_bytes(xlsx_bytes)

            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result = BatchResult(
                pdf_name=pdf_path.name,
                ok=True,
                rows=len(execution.rows),
                parse_status=execution.parse_status,
                template_detected=execution.template_detected,
                elapsed_ms=elapsed_ms,
                output_file=str(output_path),
            )
            results.append(result)
            print(
                "[OK] "
                f"rows={result.rows} "
                f"status={result.parse_status} "
                f"template={result.template_detected or 'none'} "
                f"time={result.elapsed_ms}ms "
                f"-> {output_name}"
            )
        except Exception as exc:  # noqa: BLE001
            elapsed_ms = int((time.perf_counter() - start) * 1000)
            result = BatchResult(
                pdf_name=pdf_path.name,
                ok=False,
                elapsed_ms=elapsed_ms,
                error=f"{type(exc).__name__}: {exc}",
            )
            results.append(result)
            print(f"[ERROR] time={elapsed_ms}ms {result.error}")
        print("")

    ok_count = sum(1 for item in results if item.ok)
    fail_count = len(results) - ok_count
    total_rows = sum(item.rows for item in results if item.ok)
    total_ms = sum(item.elapsed_ms for item in results)

    print("========== RESUMEN FINAL ==========")
    print(f"Total PDFs:      {len(results)}")
    print(f"Exitosos:        {ok_count}")
    print(f"Con error:       {fail_count}")
    print(f"Filas exportadas:{total_rows}")
    print(f"Tiempo total:    {total_ms}ms")

    if fail_count:
        print("")
        print("Fallos:")
        for item in results:
            if item.ok:
                continue
            print(f"- {item.pdf_name}: {item.error}")

    return 0 if fail_count == 0 else 2


if __name__ == "__main__":
    raise SystemExit(run_batch())

