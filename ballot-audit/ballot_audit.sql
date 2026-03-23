-- ballot_audit.sql

CREATE TABLE IF NOT EXISTS ballot_audit (
    audit_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    exercise_id BIGINT NOT NULL,
    run_at TIMESTAMP NOT NULL,
    status VARCHAR(50) NOT NULL
);

-- Sample records
INSERT INTO ballot_audit (exercise_id, run_at, status) VALUES
(1, '2025-06-01 10:00:00', 'cancelled'),
(1, '2025-06-01 10:05:00', 'completed'),
(2, '2025-01-01 09:00:00', 'completed');