# Card contract

## Production-plan card

Display in this order:

1. Department and report date.
2. Total order-process tasks, pending, in progress, completed.
3. Deterministic status summary, completion/pending/overdue percentages, and overdue/important counts.
4. Up to five focus orders: order number, process, status, planned completion time, risk reason.
5. A truthful Excel-detail note.

Focus priority:

1. Important and overdue.
2. Overdue.
3. Important.
4. Regular orders by earliest delivery date when included in a full export.

Important means the product order number contains `JJ` or `YP`, or customer grade is `A`.
Overdue means the planned completion date or delivery date is before the current date while status is pending or not produced.

## Work-report card

Display in this order:

1. Department and report date.
2. Expected, reported, pending-report counts and reporting rate.
3. Completed order-process count and output; keep length and pieces separate.
4. Up to five performers with completed output, completion rate, and report count.
5. Pending-report and unmatched-report counts.
6. Ranking scope and a truthful Excel-detail note.

Definitions:

- Expected count: distinct planned order-process keys for the department.
- Reported count: expected keys with at least one report during the reporting day.
- Reporting rate: reported count divided by expected count; return zero when expected count is zero and state the empty scope.
- Performer completion rate: average of that person's valid record completion rates so incompatible units are never added together.

## Deterministic status labels

Production plan:

- No tasks: `暂无数据`.
- No overdue tasks: `进度平稳`.
- Overdue share at most 10%: `需关注`.
- Overdue share above 10%: `风险较高`.

Work report:

- No expected tasks: `暂无数据`.
- Reporting rate at least 90%: `良好`.
- Reporting rate from 70% to below 90%: `需跟进`.
- Reporting rate below 70%: `进度滞后`.

These labels describe data status only; do not use them as employee performance conclusions.

## HTML and PNG

Use the same validated payload as the card. Show a title, department/date, one-sentence summary, metric tiles, and aligned detail tables. Escape every business-text cell. Keep unmatched work reports visible as `待核对` but exclude them from official output and ranking. Convert only locally generated HTML to PNG.

## Data safety

Use only the minimum employee display name needed for the internal card. Do not include tokens, cookies, source credentials, phone numbers, personal contact details, or raw API responses.
