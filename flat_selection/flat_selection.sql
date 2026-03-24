-- Flat Selection Service Database
CREATE DATABASE IF NOT EXISTS flat_selection;
USE flat_selection;

CREATE TABLE IF NOT EXISTS flat_selection (
    selection_id INT AUTO_INCREMENT PRIMARY KEY,
    applicant_id INT NOT NULL,
    co_applicant_id INT DEFAULT NULL,
    project_id INT NOT NULL,
    queue_number INT NOT NULL,
    flat_id INT DEFAULT NULL,
    status ENUM('balloted', 'selecting', 'reserved', 'paid', 'forfeited') NOT NULL DEFAULT 'balloted',
    reserved_at DATETIME DEFAULT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    UNIQUE KEY unique_queue (project_id, queue_number)
);

-- Sample data
INSERT INTO flat_selection (applicant_id, co_applicant_id, project_id, queue_number, status) VALUES
(1, 2, 1, 1, 'balloted'),
(3, 4, 1, 2, 'balloted'),
(5, 6, 1, 3, 'balloted'),
(7, NULL, 1, 4, 'balloted');
