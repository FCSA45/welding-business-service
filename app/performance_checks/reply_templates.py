from collections import defaultdict

from app.performance_checks.models import PerformanceCheckResult


def _rate(numerator: int, denominator: int) -> float:
    return round(100 if denominator == 0 else min(numerator / denominator * 100, 100), 1)


def _metrics(result: PerformanceCheckResult) -> dict:
    reported = sum(item.reported_published_count for item in result.items)
    actual = sum(item.actual_published_count for item in result.items)
    scripts = sum(item.actual_script_count or item.reported_script_count for item in result.items)
    filled = sum(item.filled_script_data_count for item in result.items)
    high = max(reported, actual)
    return {
        "reported": reported,
        "actual": actual,
        "difference": reported - actual,
        "agreement": round(100 if high == 0 else min(reported, actual) / high * 100, 1),
        "completeness": _rate(filled, scripts),
        "review": sum(item.status != "matched" for item in result.items),
        "matched": sum(item.status == "matched" for item in result.items),
        "accounts": len({(item.platform, item.account_name) for item in result.items}),
        "operators": len({item.operator_name for item in result.items}),
    }


def _change(current: int, previous: int) -> str:
    if previous == 0:
        return "暂无可比基准"
    value = round((current - previous) / previous * 100, 1)
    return f"{value:+.1f}%"


def _group(result: PerformanceCheckResult, field: str) -> list[dict]:
    grouped: dict[str, list] = defaultdict(list)
    for item in result.items:
        grouped[getattr(item, field)].append(item)
    rows = []
    for name, items in grouped.items():
        reported = sum(item.reported_published_count for item in items)
        actual = sum(item.actual_published_count for item in items)
        review = sum(item.status != "matched" for item in items)
        rows.append({"name": name, "reported": reported, "actual": actual, "review": review})
    return sorted(rows, key=lambda row: (-row["review"], -row["actual"]))


def _attention_lines(result: PerformanceCheckResult) -> list[str]:
    lines: list[str] = []
    missing_platform = sum(item.status == "missing_platform" for item in result.items)
    missing_report = sum(item.status == "missing_report" for item in result.items)
    mismatch = sum(item.status == "mismatch" for item in result.items)
    incomplete = sum(item.script_data_completeness_rate < 90 for item in result.items)
    if missing_platform:
        lines.append(f"- {missing_platform} 条记录缺少平台数据，应先检查采集状态，暂不用于人员评价。")
    if missing_report:
        lines.append(f"- {missing_report} 条平台记录缺少对应运营日报，需要核对日报来源或统计日期。")
    if mismatch:
        lines.append(f"- {mismatch} 条记录的日报发布量与平台实际值不一致，需要确认跨日、审核中或删除内容。")
    if incomplete:
        lines.append(f"- {incomplete} 条记录的脚本数据完整率低于90%，建议补齐效果数据。")
    return lines or ["- 当前没有需要优先核查的异常。"]


def _period_observations(period: str, result: PerformanceCheckResult) -> tuple[str, list[str]]:
    platforms = sorted(_group(result, "platform"), key=lambda row: -row["actual"])
    operators = sorted(_group(result, "operator_name"), key=lambda row: -row["actual"])
    if period == "weekly":
        daily_actual: dict[str, int] = defaultdict(int)
        for item in result.items:
            daily_actual[item.report_date.isoformat()] += item.actual_published_count
        peak = max(daily_actual.items(), key=lambda item: item[1]) if daily_actual else None
        return "本周执行观察", [
            f"- 本周发布高峰：{peak[0]}，平台实际发布 {peak[1]} 条。"
            if peak else "- 本周暂无发布数据。",
            f"- 主要产出平台：{platforms[0]['name']}，实际发布 {platforms[0]['actual']} 条。"
            if platforms else "- 暂无平台贡献数据。",
            f"- 主要产出人员：{operators[0]['name']}，实际发布 {operators[0]['actual']} 条。"
            if operators else "- 暂无人员贡献数据。",
        ]

    if period == "monthly":
        account_reviews: dict[tuple[str, str], int] = defaultdict(int)
        for item in result.items:
            if item.status != "matched":
                account_reviews[(item.platform, item.account_name)] += 1
        recurring = sorted(account_reviews.items(), key=lambda item: -item[1])
        recurring_text = (
            f"- 重复异常账号：{recurring[0][0][0]} / {recurring[0][0][1]}，"
            f"本月出现 {recurring[0][1]} 次待核查。"
            if recurring else "- 本月没有重复异常账号。"
        )
        return "月度复盘观察", [
            f"- 本月主要产出平台：{platforms[0]['name']}，实际发布 {platforms[0]['actual']} 条。"
            if platforms else "- 暂无平台贡献数据。",
            f"- 本月主要产出人员：{operators[0]['name']}，实际发布 {operators[0]['actual']} 条。"
            if operators else "- 暂无人员贡献数据。",
            recurring_text,
        ]
    return "当日执行观察", []


def build_performance_reply(
    period: str,
    current: PerformanceCheckResult,
    previous: PerformanceCheckResult,
) -> str:
    current_metrics = _metrics(current)
    previous_metrics = _metrics(previous)
    period_name = {"daily": "日报", "weekly": "周报", "monthly": "月报"}[period]
    comparison_name = {"daily": "较前一日", "weekly": "较上周", "monthly": "较上月"}[period]
    verdict = (
        "核查结果正常，日报与平台数据整体一致。"
        if current_metrics["review"] == 0
        else f"本期有 {current_metrics['review']} 条记录需要核查，差异确认前不建议直接用于绩效扣分。"
    )
    platform_rows = _group(current, "platform")[:3]
    operator_rows = _group(current, "operator_name")[:3]
    platform_text = "\n".join(
        f"- {row['name']}：实际发布 {row['actual']} 条，日报 {row['reported']} 条，待核查 {row['review']} 条"
        for row in platform_rows
    ) or "- 暂无平台数据"
    operator_text = "\n".join(
        f"- {row['name']}：实际发布 {row['actual']} 条，待核查 {row['review']} 条"
        for row in operator_rows
    ) or "- 暂无人员数据"
    attention = "\n".join(_attention_lines(current))
    observation_title, observation_lines = _period_observations(period, current)
    observations = "\n".join(observation_lines)
    action_title = "下周处理建议" if period == "weekly" else "下月改进重点" if period == "monthly" else "当日处理建议"
    return "\n".join([
        f"## 绩效核查{period_name}",
        f"**统计周期：** {current.period_start} 至 {current.period_end}",
        "",
        "### 管理结论",
        verdict,
        "",
        "### 核心指标",
        f"- 平台实际发布：**{current_metrics['actual']} 条**（{comparison_name} {_change(current_metrics['actual'], previous_metrics['actual'])}）",
        f"- 运营日报记录：**{current_metrics['reported']} 条**",
        f"- 发布数量差异：**{current_metrics['difference']} 条**",
        f"- 发布数据一致率：**{current_metrics['agreement']}%**",
        f"- 脚本数据完整率：**{current_metrics['completeness']}%**",
        f"- 覆盖范围：{current_metrics['accounts']} 个账号、{current_metrics['operators']} 名运营人员",
        "",
        f"### {observation_title}",
        observations,
        "",
        "### 平台概况",
        platform_text,
        "",
        "### 人员核查重点",
        operator_text,
        "",
        "### 异常与风险",
        attention,
        "",
        f"### {action_title}",
        "- 优先确认缺失数据与采集故障，再处理人员相关差异。",
        "- 对数据不一致项记录原因，区分跨日发布、审核延迟、删除内容和统计口径问题。",
        "- 对低完整率账号明确补录负责人和完成时间。",
        "",
        "> 数据口径：差异表示运营日报记录与平台采集值的差别；差异仅用于核查，不直接等同于人员绩效结果。",
    ])
