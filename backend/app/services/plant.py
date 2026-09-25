"""厂区单元业务规则：状态流转、字段校验、筛选口径与处理量班组汇总都收在这里。"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Any

from app.store import store

MODULE = "plant"
REQUIRED_FIELDS = ["单元编码", "单元名称", "处理工艺"]
STATUS_ORDER = ["待调试", "正常运行", "减量运行", "已停用"]
ACTION_RULES = {"完成调试": "正常运行", "安排减量": "减量运行", "停用单元": "已停用"}
NEGATIVE_ACTIONS = ["停用单元"]

CODE_FIELD = "单元编码"
CRAFT_FIELD = "处理工艺"
DESIGN_FIELD = "设计处理量"
ACTUAL_FIELD = "实际处理量"
TEAM_FIELD = "运行班组"
REDUCED_STATUS = "减量运行"
MISSING_GROUP_LABEL = "未填写单元编码/处理工艺"

_NUMBER_RE = re.compile(r"-?\d+(?:\.\d+)?")


def _text(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _number(value: Any) -> float | None:
    """从处理量字段里取数字；空值或写的不是数字时返回 None，汇总时逐条说明。"""
    text = _text(value)
    if not text:
        return None
    match = _NUMBER_RE.search(text.replace(",", ""))
    if match is None:
        return None
    return float(match.group())


def _fmt_number(value: float) -> float | int:
    if abs(value - round(value)) < 1e-9:
        return int(round(value))
    return round(value, 2)


class PlantService:
    def _filter_rows(
        self,
        *,
        keyword: str | None = None,
        craft: str | None = None,
        status: str | None = None,
        team: str | None = None,
    ) -> list[dict[str, Any]]:
        """厂区单元的统一筛选口径，列表与汇总必须走同一套，保证数量口径一致。"""
        rows = store.rows(MODULE)
        if keyword:
            rows = [
                row
                for row in rows
                if keyword in _text(row.get(CODE_FIELD)) or keyword in _text(row.get("单元名称"))
            ]
        if craft:
            rows = [row for row in rows if craft in _text(row.get(CRAFT_FIELD))]
        if team:
            rows = [row for row in rows if team in _text(row.get(TEAM_FIELD))]
        if status:
            rows = [row for row in rows if _text(row.get("status")) == status]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        craft: str | None = None,
        status: str | None = None,
        team: str | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filter_rows(keyword=keyword, craft=craft, status=status, team=team)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def get_entry(self, entry_id: int) -> dict[str, Any] | None:
        return store.find(MODULE, entry_id)

    def create_entry(self, values: dict[str, Any]) -> tuple[dict[str, Any] | None, list[str]]:
        missing = [field for field in REQUIRED_FIELDS if not str(values.get(field) or "").strip()]
        if missing:
            return None, missing
        rows = store.rows(MODULE)
        entry = {"id": max((int(row.get("id", 0)) for row in rows), default=0) + 1}
        entry.update({field: values.get(field) for field in REQUIRED_FIELDS})
        entry["status"] = STATUS_ORDER[0]
        entry["pending"] = True
        entry["abnormal"] = False
        rows.append(entry)
        return entry, []

    def run_action(self, entry_id: int, action: str) -> tuple[dict[str, Any] | None, str]:
        entry = store.find(MODULE, entry_id)
        if entry is None:
            return None, f"工艺单元 {entry_id} 不存在或已归档"
        if action not in ACTION_RULES:
            return None, f"动作「{action}」不属于厂区单元可执行范围"
        target = ACTION_RULES[action]
        if target not in STATUS_ORDER:
            return None, f"目标状态「{target}」不在允许的状态序列里"
        entry["status"] = target
        entry["pending"] = target != STATUS_ORDER[-1]
        entry["abnormal"] = action in NEGATIVE_ACTIONS
        return entry, f"工艺单元已{action}"

    def summarize(
        self,
        *,
        keyword: str | None = None,
        craft: str | None = None,
        status: str | None = None,
        team: str | None = None,
    ) -> dict[str, Any]:
        """按单元编码 + 处理工艺分组汇总设计/实际处理量、班组与减量运行单元。

        分组缺数据、处理量为空、重复编码都逐条写进 issues，避免静默丢数；
        分组基于与列表完全相同的筛选结果，汇总数量与列表 total 保持一致。
        """
        rows = self._filter_rows(keyword=keyword, craft=craft, status=status, team=team)
        total = len(rows)

        code_seen: dict[str, list[Any]] = {}
        buckets: "OrderedDict[tuple[str, str], dict[str, Any]]" = OrderedDict()
        issues: list[dict[str, str]] = []

        for row in rows:
            code = _text(row.get(CODE_FIELD))
            craft_name = _text(row.get(CRAFT_FIELD))
            team_name = _text(row.get(TEAM_FIELD)) or "未填写班组"
            design = _number(row.get(DESIGN_FIELD))
            actual = _number(row.get(ACTUAL_FIELD))
            row_status = _text(row.get("status"))
            entry_id = row.get("id")

            if code:
                code_seen.setdefault(code, []).append(entry_id)
            else:
                issues.append({
                    "level": "warning",
                    "kind": "missing_code",
                    "message": f"单元记录（id={entry_id}，名称：{_text(row.get('单元名称')) or '未填写'}）"
                               f"单元编码为空，已归入「{MISSING_GROUP_LABEL}」分组，不参与编码去重判断。",
                })
            if not craft_name:
                issues.append({
                    "level": "warning",
                    "kind": "missing_craft",
                    "message": f"单元记录（id={entry_id}，编码：{code or '未填写'}）处理工艺为空，"
                               f"已归入「{MISSING_GROUP_LABEL}」分组。",
                })
            design_raw = _text(row.get(DESIGN_FIELD))
            if not design_raw:
                issues.append({
                    "level": "warning",
                    "kind": "missing_design",
                    "message": f"单元 {code or f'id={entry_id}'} 设计处理量为空，不计入设计处理量合计。",
                })
            elif design is None:
                issues.append({
                    "level": "warning",
                    "kind": "invalid_design",
                    "message": f"单元 {code or f'id={entry_id}'} 设计处理量「{design_raw}」无法识别为数字，"
                               f"不计入设计处理量合计。",
                })
            actual_raw = _text(row.get(ACTUAL_FIELD))
            if not actual_raw:
                issues.append({
                    "level": "warning",
                    "kind": "missing_actual",
                    "message": f"单元 {code or f'id={entry_id}'} 实际处理量为空，不计入实际处理量合计。",
                })
            elif actual is None:
                issues.append({
                    "level": "warning",
                    "kind": "invalid_actual",
                    "message": f"单元 {code or f'id={entry_id}'} 实际处理量「{actual_raw}」无法识别为数字，"
                               f"不计入实际处理量合计。",
                })

            key = (code or "未填写单元编码", craft_name or "未填写处理工艺")
            group = buckets.get(key)
            if group is None:
                group = {
                    "code": key[0],
                    "craft": key[1],
                    "incomplete_group": not code or not craft_name,
                    "units": [],
                    "teams": OrderedDict(),
                    "design_total": 0.0,
                    "actual_total": 0.0,
                    "design_count": 0,
                    "actual_count": 0,
                    "reduced_count": 0,
                }
                buckets[key] = group

            group["units"].append({
                "id": entry_id,
                "code": code,
                "name": _text(row.get("单元名称")),
                "design": _fmt_number(design) if design is not None else None,
                "actual": _fmt_number(actual) if actual is not None else None,
                "design_missing": design is None,
                "actual_missing": actual is None,
                "team": team_name,
                "status": row_status,
                "reduced": row_status == REDUCED_STATUS,
                "commission_date": _text(row.get("投运日期")),
            })
            if design is not None:
                group["design_total"] += design
                group["design_count"] += 1
            if actual is not None:
                group["actual_total"] += actual
                group["actual_count"] += 1
            if row_status == REDUCED_STATUS:
                group["reduced_count"] += 1
            team_bucket = group["teams"].setdefault(
                team_name,
                {"team": team_name, "count": 0, "actual_total": 0.0, "actual_count": 0, "reduced_count": 0},
            )
            team_bucket["count"] += 1
            if actual is not None:
                team_bucket["actual_total"] += actual
                team_bucket["actual_count"] += 1
            if row_status == REDUCED_STATUS:
                team_bucket["reduced_count"] += 1

        # 重复单元编码：同一编码出现多条，逐条列出冲突记录。
        for code, entry_ids in code_seen.items():
            if len(entry_ids) > 1:
                for dup_id in entry_ids:
                    issues.append({
                        "level": "danger",
                        "kind": "duplicate_code",
                        "message": f"单元编码 {code} 重复：该编码下共有 {len(entry_ids)} 条记录"
                                   f"（id 列表：{', '.join(str(item) for item in entry_ids)}），"
                                   f"记录 id={dup_id} 参与了同一分组的汇总，请核对登记数据。",
                    })

        all_design = sum(bucket["design_total"] for bucket in buckets.values())
        all_actual = sum(bucket["actual_total"] for bucket in buckets.values())
        reduced_total = sum(bucket["reduced_count"] for bucket in buckets.values())

        groups: list[dict[str, Any]] = []
        for bucket in buckets.values():
            units = bucket["units"]
            units.sort(key=lambda item: (not item["reduced"], item["code"], str(item["id"])))
            teams = list(bucket["teams"].values())
            for team_bucket in teams:
                team_bucket["actual_total"] = _fmt_number(team_bucket["actual_total"])
            count = len(units)
            groups.append({
                "code": bucket["code"],
                "craft": bucket["craft"],
                "incomplete_group": bucket["incomplete_group"],
                "count": count,
                "count_ratio": round(count / total, 4) if total else 0.0,
                "design_total": _fmt_number(bucket["design_total"]),
                "actual_total": _fmt_number(bucket["actual_total"]),
                "design_ratio": round(bucket["design_total"] / all_design, 4) if all_design else 0.0,
                "actual_ratio": round(bucket["actual_total"] / all_actual, 4) if all_actual else 0.0,
                "design_missing_count": count - bucket["design_count"],
                "actual_missing_count": count - bucket["actual_count"],
                "reduced_count": bucket["reduced_count"],
                "teams": teams,
                "units": units,
            })
        groups.sort(key=lambda item: (item["incomplete_group"], -item["design_total"], item["code"]))

        if not rows:
            active_filters = {
                "keyword": keyword or "",
                "craft": craft or "",
                "status": status or "",
                "team": team or "",
            }
            if any(active_filters.values()):
                desc = "、".join(
                    f"{name}「{value}」"
                    for name, value in [
                        ("单元编码/名称", active_filters["keyword"]),
                        ("处理工艺", active_filters["craft"]),
                        ("单元状态", active_filters["status"]),
                        ("运行班组", active_filters["team"]),
                    ]
                    if value
                )
                issues.append({
                    "level": "info",
                    "kind": "empty_filter",
                    "message": f"当前筛选条件（{desc}）下没有任何厂区单元，分组结果为空；可重置条件后再查询。",
                })
            else:
                issues.append({
                    "level": "info",
                    "kind": "empty_data",
                    "message": "厂区单元暂无任何登记记录，没有可汇总的分组；可先在列表页登记工艺单元。",
                })

        return {
            "total": total,
            "group_count": len(groups),
            "design_total": _fmt_number(all_design),
            "actual_total": _fmt_number(all_actual),
            "reduced_total": reduced_total,
            "groups": groups,
            "issues": issues,
            "filters": {
                "keyword": keyword or "",
                "craft": craft or "",
                "status": status or "",
                "team": team or "",
            },
        }
