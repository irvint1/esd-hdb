CREATE DATABASE IF NOT EXISTS flat_selection;
USE flat_selection;

DROP TABLE IF EXISTS flat_selection_forfeit_penalty;
DROP TABLE IF EXISTS flat_selection;

CREATE TABLE IF NOT EXISTS flat_selection (
    selection_id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    applicant_nric VARCHAR(20) NOT NULL,
    co_applicant_nric VARCHAR(20) NULL,
    project_id INT NOT NULL,
    queue_number INT NOT NULL,
    flat_id INT DEFAULT NULL,
    status ENUM('balloted', 'selecting', 'reserved', 'paid', 'forfeited', 'not_called', 'no_flat_selected') NOT NULL DEFAULT 'balloted',
    reserved_at DATETIME DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_application (application_id),
    KEY idx_application_id (application_id),
    KEY idx_applicant_nric (applicant_nric),
    KEY idx_co_applicant_nric (co_applicant_nric),
    KEY idx_status (status)
);

CREATE TABLE IF NOT EXISTS flat_selection_forfeit_penalty (
    penalty_id INT AUTO_INCREMENT PRIMARY KEY,
    selection_id INT NOT NULL,
    forfeited_at DATETIME NOT NULL,
    penalty_start_at DATETIME NOT NULL,
    penalty_end_at DATETIME NOT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_selection_forfeit (selection_id),
    KEY idx_penalty_end_at (penalty_end_at),
    CONSTRAINT fk_forfeit_selection
        FOREIGN KEY (selection_id) REFERENCES flat_selection(selection_id)
        ON DELETE CASCADE
);

INSERT INTO flat_selection (
    application_id,
    applicant_nric,
    co_applicant_nric,
    project_id,
    queue_number,
    status
) VALUES
-- Historical/demo rows for prior runs.
-- Queue numbers are now coherent within each project (starting from 1).
(1801, 'S9701234K', 'S8805678E', 40, 1, 'selecting'),
(1802, 'S8501234A', NULL,        40, 2, 'not_called'),
(1803, 'S9206789F', NULL,        40, 3, 'forfeited'),
(1804, 'S9812346F', NULL,        41, 1, 'not_called'),
(1805, 'S9812346F', NULL,        41, 2, 'not_called'),
(1806, 'S6005055D', NULL,        42, 1, 'not_called'),
(1807, 'S9201234W', NULL,        42, 2, 'balloted'),
(1808, 'S9401234L', NULL,        42, 3, 'not_called'),
(1809, 'S9501234R', NULL,        43, 1, 'balloted'),
(1810, 'S9601234S', NULL,        43, 2, 'balloted'),
(1811, 'S8901234D', NULL,        43, 3, 'balloted');

INSERT INTO flat_selection_forfeit_penalty (
    selection_id,
    forfeited_at,
    penalty_start_at,
    penalty_end_at
) VALUES
(3, '2026-01-10 12:00:00', '2026-01-10 12:00:00', '2027-01-10 12:00:00');
