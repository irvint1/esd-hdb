-- Ballot Audit Service Database
CREATE DATABASE IF NOT EXISTS ballot_audits;
USE ballot_audits;

CREATE TABLE IF NOT EXISTS ballot_audits (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    exercise_id BIGINT NOT NULL,
    run_at DATETIME NOT NULL,
    executed_at DATETIME NULL,
    cron_expression VARCHAR(100) NULL,
    error_reason TEXT NULL,
    status ENUM('scheduled', 'in progress', 'completed', 'error', 'cancelled') NOT NULL DEFAULT 'in progress',
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE INDEX idx_ballot_audits_exercise_id ON ballot_audits (exercise_id);
CREATE INDEX idx_ballot_audits_status ON ballot_audits (status);
CREATE INDEX idx_ballot_audits_cron_expression ON ballot_audits (cron_expression(32));

-- Sample records
INSERT INTO ballot_audits (exercise_id, run_at, executed_at, cron_expression, error_reason, status) VALUES
    (1, '2026-03-01 09:00:00', '2026-03-01 09:01:22', NULL, NULL, 'completed'),
    (5, '2026-02-10 11:00:00', '2026-02-10 11:00:46', NULL, 'Upstream timeout while calling process-ballot.', 'error'),
    (4, '2026-03-12 16:00:00', NULL, NULL, NULL, 'cancelled')
ON DUPLICATE KEY UPDATE
    run_at = VALUES(run_at),
    executed_at = VALUES(executed_at),
    cron_expression = VALUES(cron_expression),
    error_reason = VALUES(error_reason),
    status = VALUES(status);
