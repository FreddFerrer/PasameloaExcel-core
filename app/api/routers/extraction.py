from __future__ import annotations

import json
import logging
from io import BytesIO

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status
from fastapi.responses import StreamingResponse

from app.application.use_cases import (
    ExportExcelUseCase,
    ExtractPreviewUseCase,
    SubmitExtractSupportUseCase,
)
from app.core.dependencies import (
    get_export_excel_use_case,
    get_extract_preview_use_case,
    get_submit_extract_support_use_case,
)
from app.schemas.export import ExportExcelRequest
from app.schemas.preview import ExtractPreviewResponse
from app.schemas.support import SupportSubmissionResponse

router = APIRouter(tags=["extraction"])
logger = logging.getLogger(__name__)


@router.post("/extract-preview", response_model=ExtractPreviewResponse)
async def extract_preview(
    file: UploadFile = File(...),
    extract_preview_use_case: ExtractPreviewUseCase = Depends(get_extract_preview_use_case),
) -> ExtractPreviewResponse:
    filename = file.filename or "extracto.pdf"

    payload = await file.read()
    logger.info(
        "extract_preview_request_received",
        extra={
            "event": "extract_preview_request",
            "upload_filename": filename,
            "file_size_bytes": len(payload),
            "content_type": file.content_type or "unknown",
        },
    )
    try:
        return extract_preview_use_case.execute(pdf_bytes=payload, filename=filename)
    except NotImplementedError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post("/export-excel")
def export_excel(
    request: ExportExcelRequest,
    export_excel_use_case: ExportExcelUseCase = Depends(get_export_excel_use_case),
) -> StreamingResponse:
    logger.info(
        "export_excel_request_received",
        extra={
            "event": "export_excel_request",
            "document_id": request.document_id,
            "session_id": request.session_id,
            "template_detected": request.template_detected,
            "parse_status": request.parse_status,
            "rows_original_count": len(request.rows_original),
            "rows_final_count": len(request.rows_final),
            "rows_edited": request.change_set.rows_edited,
            "rows_added": request.change_set.rows_added,
            "rows_deleted": request.change_set.rows_deleted,
            "fields_corrected_keys": sorted(request.change_set.fields_corrected.keys()),
            "error_pattern_count": len(request.change_set.error_patterns),
        },
    )
    result = export_excel_use_case.execute(request)
    headers = {"Content-Disposition": f'attachment; filename="{result.filename}"'}
    return StreamingResponse(
        BytesIO(result.content),
        media_type=result.media_type,
        headers=headers,
    )


@router.post("/support/submit-extract", response_model=SupportSubmissionResponse)
async def submit_extract_to_support(
    file: UploadFile = File(...),
    preview_json: str = Form(...),
    session_id: str | None = Form(default=None),
    user_note: str | None = Form(default=None),
    submit_extract_support_use_case: SubmitExtractSupportUseCase = Depends(get_submit_extract_support_use_case),
) -> SupportSubmissionResponse:
    filename = file.filename or "extracto.pdf"

    payload = await file.read()
    preview_payload: dict = {}
    preview_row_count: int | None = None
    if preview_json:
        try:
            preview_payload = json.loads(preview_json)
            preview_rows = preview_payload.get("rows")
            preview_row_count = len(preview_rows) if isinstance(preview_rows, list) else None
        except json.JSONDecodeError:
            preview_row_count = None
    logger.info(
        "support_submit_request_received",
        extra={
            "event": "support_submit_request",
            "upload_filename": filename,
            "file_size_bytes": len(payload),
            "content_type": file.content_type or "unknown",
            "document_id": preview_payload.get("document_id"),
            "template_detected": preview_payload.get("template_detected"),
            "support_recommended": preview_payload.get("support_recommended"),
            "preview_row_count": preview_row_count,
            "session_id": session_id,
            "user_note_len": len(user_note or ""),
        },
    )
    try:
        return submit_extract_support_use_case.execute(
            pdf_bytes=payload,
            filename=filename,
            preview_json=preview_json,
            user_note=user_note,
            session_id=session_id,
        )
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc

