"""历史数据路由：流量记录、小时统计、预警列表、连接会话、热力图、CSV 导出。"""
import csv
import io
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response, status
from sqlalchemy import func, select

from models import (
    ConnectionSession,
    HourlyStatistics,
    TrafficAlert,
    TrafficRecord,
)
from routers.deps import AdminUser, CurrentUser, DBSession
from schemas.history import (
    AlertListResponse,
    AlertResponse,
    AlertResolveRequest,
    HeatmapResponse,
    HourlyStatisticsResponse,
    SessionListResponse,
    SessionResponse,
    TrafficRecordResponse,
)

router = APIRouter(prefix="/api/history", tags=["history"])

_WEEKDAY_LABELS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ── 流量记录 ─────────────────────────────────────────────────────────────────────

@router.get("/traffic", response_model=list[TrafficRecordResponse], summary="查询流量记录（分钟粒度）")
async def get_traffic(
    session: DBSession,
    _user: CurrentUser,
    device_id: int = Query(...),
    start: datetime = Query(..., description="起始时间 ISO8601"),
    end: datetime = Query(..., description="结束时间 ISO8601"),
    limit: int = Query(default=1440, ge=1, le=10000),
) -> list[TrafficRecordResponse]:
    result = await session.execute(
        select(TrafficRecord)
        .where(
            TrafficRecord.device_id == device_id,
            TrafficRecord.recorded_at >= start,
            TrafficRecord.recorded_at <= end,
        )
        .order_by(TrafficRecord.recorded_at)
        .limit(limit)
    )
    rows = result.scalars().all()
    return [TrafficRecordResponse.model_validate(r) for r in rows]


@router.get("/traffic/hourly", response_model=list[HourlyStatisticsResponse], summary="查询小时统计")
async def get_hourly(
    session: DBSession,
    _user: CurrentUser,
    device_id: int = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
) -> list[HourlyStatisticsResponse]:
    result = await session.execute(
        select(HourlyStatistics)
        .where(
            HourlyStatistics.device_id == device_id,
            HourlyStatistics.hour_at >= start,
            HourlyStatistics.hour_at <= end,
        )
        .order_by(HourlyStatistics.hour_at)
    )
    rows = result.scalars().all()
    return [HourlyStatisticsResponse.model_validate(r) for r in rows]


# ── 预警列表 ─────────────────────────────────────────────────────────────────────

@router.get("/alerts", response_model=AlertListResponse, summary="查询预警记录（支持分页和 is_resolved 过滤）")
async def list_alerts(
    session: DBSession,
    _user: CurrentUser,
    device_id: Optional[int] = Query(default=None),
    is_resolved: Optional[bool] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> AlertListResponse:
    conditions = []
    if device_id is not None:
        conditions.append(TrafficAlert.device_id == device_id)
    if is_resolved is not None:
        conditions.append(TrafficAlert.is_resolved == is_resolved)

    total_q = select(func.count()).select_from(TrafficAlert)
    if conditions:
        total_q = total_q.where(*conditions)
    total = (await session.execute(total_q)).scalar_one()

    q = select(TrafficAlert).order_by(TrafficAlert.triggered_at.desc())
    if conditions:
        q = q.where(*conditions)
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    return AlertListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[AlertResponse.model_validate(r) for r in rows],
    )


@router.put("/alerts/{alert_id}/resolve", response_model=AlertResponse, summary="手动解除预警")
async def resolve_alert(
    alert_id: int,
    body: AlertResolveRequest,
    session: DBSession,
    _user: CurrentUser,
) -> AlertResponse:
    result = await session.execute(select(TrafficAlert).where(TrafficAlert.id == alert_id))
    alert = result.scalar_one_or_none()
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": 4001, "message": "预警不存在"})
    if alert.is_resolved:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": 4002, "message": "预警已解除"})

    now = _utcnow()
    alert.is_resolved = True
    alert.resolved_at = now
    alert.resolved_by = body.resolved_by
    alert.duration_seconds = int((now - alert.triggered_at).total_seconds())
    await session.commit()
    await session.refresh(alert)
    return AlertResponse.model_validate(alert)


# ── 连接会话 ─────────────────────────────────────────────────────────────────────

@router.get("/sessions", response_model=SessionListResponse, summary="查询连接会话列表")
async def list_sessions(
    session: DBSession,
    _user: CurrentUser,
    device_id: Optional[int] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> SessionListResponse:
    conditions = []
    if device_id is not None:
        conditions.append(ConnectionSession.device_id == device_id)

    total_q = select(func.count()).select_from(ConnectionSession)
    if conditions:
        total_q = total_q.where(*conditions)
    total = (await session.execute(total_q)).scalar_one()

    q = select(ConnectionSession).order_by(ConnectionSession.connected_at.desc())
    if conditions:
        q = q.where(*conditions)
    q = q.offset((page - 1) * page_size).limit(page_size)
    rows = (await session.execute(q)).scalars().all()

    return SessionListResponse(
        total=total,
        page=page,
        page_size=page_size,
        items=[SessionResponse.model_validate(r) for r in rows],
    )


# ── 热力图 ────────────────────────────────────────────────────────────────────────

@router.get("/heatmap", response_model=HeatmapResponse, summary="返回 7×24 热力矩阵（近7天，行=星期，列=小时）")
async def get_heatmap(
    session: DBSession,
    _user: CurrentUser,
    device_id: int = Query(...),
    end_date: Optional[date] = Query(default=None, description="基准日期（默认今天）"),
) -> HeatmapResponse:
    base = end_date or datetime.now(timezone.utc).date()
    # 取完整7天（不含 base 当天若未结束）
    end_dt = datetime(base.year, base.month, base.day, 23, 59, 59)
    start_dt = end_dt - timedelta(days=6, hours=23, minutes=59, seconds=59)

    result = await session.execute(
        select(HourlyStatistics)
        .where(
            HourlyStatistics.device_id == device_id,
            HourlyStatistics.hour_at >= start_dt,
            HourlyStatistics.hour_at <= end_dt,
        )
    )
    rows = result.scalars().all()

    # 构建 7x24 矩阵（默认 0.0）
    matrix: list[list[float]] = [[0.0] * 24 for _ in range(7)]
    count_matrix: list[list[int]] = [[0] * 24 for _ in range(7)]

    for row in rows:
        weekday = row.hour_at.weekday()  # 0=Mon, 6=Sun
        hour = row.hour_at.hour
        matrix[weekday][hour] += row.total_passed
        count_matrix[weekday][hour] += 1

    # 计算均值
    for d in range(7):
        for h in range(24):
            if count_matrix[d][h] > 0:
                matrix[d][h] = round(matrix[d][h] / count_matrix[d][h], 1)

    return HeatmapResponse(rows=_WEEKDAY_LABELS, data=matrix)


# ── CSV 导出 ──────────────────────────────────────────────────────────────────────

@router.get("/export", summary="导出流量记录 CSV（admin）")
async def export_csv(
    session: DBSession,
    _admin: AdminUser,
    device_id: int = Query(...),
    start: datetime = Query(...),
    end: datetime = Query(...),
) -> Response:
    result = await session.execute(
        select(TrafficRecord)
        .where(
            TrafficRecord.device_id == device_id,
            TrafficRecord.recorded_at >= start,
            TrafficRecord.recorded_at <= end,
        )
        .order_by(TrafficRecord.recorded_at)
    )
    rows = result.scalars().all()

    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "id", "device_id", "recorded_at",
        "avg_count", "max_count",
        "passed_count", "passed_in_count", "passed_out_count",
    ])
    for r in rows:
        writer.writerow([
            r.id, r.device_id, r.recorded_at.isoformat(),
            r.avg_count, r.max_count,
            r.passed_count, r.passed_in_count, r.passed_out_count,
        ])

    return Response(
        content=output.getvalue(),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename=traffic_{device_id}_{start.date()}_{end.date()}.csv"
        },
    )
