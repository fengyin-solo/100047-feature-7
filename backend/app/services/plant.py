"""厂区单元业务规则：状态流转、字段校验与筛选口径都收在这里。"""
from __future__ import annotations

from typing import Any

from app.store import store

MODULE = "plant"
REQUIRED_FIELDS = ["单元编码", "单元名称", "处理工艺"]
FILTER_FIELDS = ["单元编码", "单元名称", "处理工艺"]
STATUS_ORDER = ["待调试", "正常运行", "减量运行", "已停用"]
ACTION_RULES = {"完成调试": "正常运行", "安排减量": "减量运行", "停用单元": "已停用"}
NEGATIVE_ACTIONS = ["停用单元"]
REDUCED_STATUS = "减量运行"
CAPACITY_FIELDS = ["设计处理量", "实际处理量"]
EMPTY_LABEL = "（未填写）"


def _parse_capacity(raw: Any) -> float | None:
    """把处理量解析成数字；空值或非数字都返回 None，由调用方逐条说明。"""
    text = str(raw or "").strip()
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


class PlantService:
    def _filtered_rows(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        field_filters: dict[str, str | None] | None = None,
    ) -> list[dict[str, Any]]:
        """列表与汇总共用的筛选口径，保证两边数字一致。"""
        rows = list(store.rows(MODULE))
        if keyword:
            rows = [row for row in rows if keyword in str(row.get("单元编码", ""))]
        if status:
            rows = [row for row in rows if row.get("status") == status]
        for field, value in (field_filters or {}).items():
            text = str(value or "").strip()
            if text:
                rows = [row for row in rows if text in str(row.get(field, ""))]
        return rows

    def list_entries(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        field_filters: dict[str, str | None] | None = None,
        page: int = 1,
        size: int = 20,
    ) -> tuple[list[dict[str, Any]], int]:
        rows = self._filtered_rows(keyword=keyword, status=status, field_filters=field_filters)
        total = len(rows)
        start = max(page - 1, 0) * size
        return rows[start:start + size], total

    def summary(
        self,
        *,
        keyword: str | None = None,
        status: str | None = None,
        field_filters: dict[str, str | None] | None = None,
    ) -> dict[str, Any]:
        """按单元编码与处理工艺分组汇总处理量与班组，与列表共用同一筛选口径。"""
        rows = self._filtered_rows(keyword=keyword, status=status, field_filters=field_filters)
        total = len(rows)
        notes: list[str] = []
        if not rows:
            notes.append("当前筛选条件下没有厂区单元记录，处理量与班组汇总为空，请调整筛选条件后重新查询")
            return {"total": total, "groups": [], "notes": notes}

        code_ids: dict[str, list[int]] = {}
        for row in rows:
            code = str(row.get("单元编码") or "").strip()
            if code:
                code_ids.setdefault(code, []).append(int(row.get("id", 0)))
        for code in sorted(code_ids):
            ids = code_ids[code]
            if len(ids) > 1:
                notes.append(
                    f"单元编码「{code}」重复出现 {len(ids)} 次（记录 id：{'、'.join(str(i) for i in ids)}），"
                    "已按处理工艺分别归组，请核对登记数据"
                )

        groups: dict[tuple[str, str], dict[str, Any]] = {}
        for row in rows:
            code = str(row.get("单元编码") or "").strip() or EMPTY_LABEL
            process = str(row.get("处理工艺") or "").strip() or EMPTY_LABEL
            name = str(row.get("单元名称") or "").strip() or code
            group = groups.setdefault((code, process), {
                "单元编码": code,
                "处理工艺": process,
                "单元数量": 0,
                "班组": set(),
                "减量运行单元": [],
                "sums": dict.fromkeys(CAPACITY_FIELDS, 0.0),
                "valid": dict.fromkeys(CAPACITY_FIELDS, False),
            })
            group["单元数量"] += 1
            team = str(row.get("运行班组") or "").strip()
            if team:
                group["班组"].add(team)
            if row.get("status") == REDUCED_STATUS:
                group["减量运行单元"].append(name)
            for field in CAPACITY_FIELDS:
                raw = row.get(field)
                text = str(raw or "").strip()
                if not text:
                    notes.append(f"单元「{code}」（{name}）的{field}为空，未计入分组合计")
                    continue
                number = _parse_capacity(raw)
                if number is None:
                    notes.append(f"单元「{code}」（{name}）的{field}「{text}」不是有效数字，未计入分组合计")
                    continue
                group["sums"][field] += number
                group["valid"][field] = True

        result_groups: list[dict[str, Any]] = []
        for key in sorted(groups):
            group = groups[key]
            item: dict[str, Any] = {
                "单元编码": group["单元编码"],
                "处理工艺": group["处理工艺"],
                "运行班组": sorted(group["班组"]),
                "单元数量": group["单元数量"],
                "减量运行单元": group["减量运行单元"],
                "占比": f"{group['单元数量'] / total * 100:.1f}%",
            }
            for field in CAPACITY_FIELDS:
                item[f"{field}合计"] = (
                    round(group["sums"][field], 2) if group["valid"][field] else None
                )
            result_groups.append(item)
        return {"total": total, "groups": result_groups, "notes": notes}

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
