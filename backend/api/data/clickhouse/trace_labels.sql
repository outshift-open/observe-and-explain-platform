CREATE TABLE IF NOT EXISTS oxp.trace_labels
(
    session_id  String,
    label       Bool,
    labeler     String,
    reason      Nullable(String),
    updated_at  DateTime DEFAULT now()
) ENGINE = ReplacingMergeTree(updated_at)
ORDER BY session_id;
