from app.performance_checks.models import PerformanceCheckResult


def build_business_one_card_text(result: PerformanceCheckResult, request_id: str) -> str:
    """Render the summary for official totals versus publication details."""
    official_total = result.reported_published_total
    detail_total = result.actual_published_total
    difference = official_total - detail_total
    official_issue_accounts = sorted(
        {item.account_name for item in result.items if item.status in {"mismatch", "missing_platform"}}
    )
    detail_issue_accounts = sorted(
        {item.account_name for item in result.items if item.status in {"mismatch", "missing_report"}}
    )
    matched_accounts = sorted({item.account_name for item in result.items if item.status == "matched"})

    def account_text(accounts: list[str]) -> str:
        return "、".join(accounts) if accounts else "无"

    return "\n".join(
        [
            "🔴【绩效核查督导】",
            f"# 运营绩效核对报告｜{result.period_end}",
            "",
            "📊 核对总览",
            f"• 平台官方汇总（爬运营日报）：{official_total}",
            f"• 系统明细汇总（发布明细求和）：{detail_total}",
            "",
            "📉 差异统计",
            f"• 平台汇总 vs 系统明细：差异 {difference}，待复核账号：{len(official_issue_accounts)} 个",
            "",
            "💡 解读提示",
            "1.「平台官方汇总」：爬运营日报得到的平台输出汇总，作为业务 1 官方基准。",
            "2.「系统明细汇总」：爬运营发布数量后，按日期、平台、账号、运营人员求和。",
            "3. 两边出现差异时，优先排查平台历史数据回滚、跨日发布、审核中或删除内容。",
            "",
            f"✅ 汇总与明细一致账号：{account_text(matched_accounts)}",
            f"⚠️ 官方汇总侧待复核账号：{account_text(official_issue_accounts)}",
            f"⚠️ 发布明细侧待复核账号：{account_text(detail_issue_accounts)}",
            "",
            f"请求编号：{request_id}",
        ]
    )
