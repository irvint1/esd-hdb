-- Flat Availability Service Database
CREATE DATABASE IF NOT EXISTS flat_availability;
USE flat_availability;

CREATE TABLE IF NOT EXISTS bto_project (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(100) NOT NULL,
    town VARCHAR(50) NOT NULL,
    description TEXT,
    launch_date DATE,
    booking_start_date DATE,
    booking_end_date DATE
);

CREATE TABLE IF NOT EXISTS flat (
    flat_id INT AUTO_INCREMENT PRIMARY KEY,
    project_id INT NOT NULL,
    block VARCHAR(10) NOT NULL,
    street_name VARCHAR(100) NOT NULL,
    floor_number INT NOT NULL,
    unit_number VARCHAR(10) NOT NULL,
    flat_type ENUM('2-Room Flexi', '3-Room', '4-Room', '5-Room', '3Gen') NOT NULL,
    area_sqm DECIMAL(6,2) NOT NULL,
    price DECIMAL(12,2) NOT NULL,
    status ENUM('available', 'reserved', 'sold') NOT NULL DEFAULT 'available',
    reserved_by VARCHAR(50) DEFAULT NULL,
    reserved_at DATETIME DEFAULT NULL,
    FOREIGN KEY (project_id) REFERENCES bto_project(project_id),
    UNIQUE KEY unique_unit (project_id, block, floor_number, unit_number)
);

INSERT INTO bto_project (project_id, project_name, town, description, launch_date, booking_start_date, booking_end_date) VALUES
(40, 'Tengah Garden Walk', 'Tengah', 'Located in the heart of Tengah plantation district', '2026-02-10', '2026-03-01', '2026-03-31'),
(41, 'Punggol SeaVista', 'Punggol', 'Waterfront living close to Punggol Coast precinct', '2026-02-10', '2026-03-01', '2026-03-31'),
(42, 'Queenstown SkyGrove', 'Queenstown', 'Mature estate development with central-city access', '2026-02-10', '2026-03-01', '2026-03-31'),
(43, 'Kallang RiverFront', 'Kallang/Whampoa', 'River-facing homes with excellent city connectivity', '2026-02-10', '2026-03-01', '2026-03-31')
ON DUPLICATE KEY UPDATE
    project_name = VALUES(project_name),
    town = VALUES(town),
    description = VALUES(description);

-- Floor-to-unit-count map (shared across all blocks). Deliberately irregular.
-- Floor 2: 4 units, Floor 3: 3, Floor 4: 5, Floor 5: 2, Floor 6: 6,
-- Floor 7: 4, Floor 8: 3, Floor 9: 5, Floor 10: 4, Floor 11: 2,
-- Floor 12: 6, Floor 13: 3, Floor 14: 4
DROP TEMPORARY TABLE IF EXISTS floor_units;
CREATE TEMPORARY TABLE floor_units (
    floor_number INT NOT NULL,
    unit_no INT NOT NULL,
    PRIMARY KEY (floor_number, unit_no)
);

INSERT INTO floor_units (floor_number, unit_no) VALUES
(2,1),(2,2),(2,3),(2,4),
(3,1),(3,2),(3,3),
(4,1),(4,2),(4,3),(4,4),(4,5),
(5,1),(5,2),
(6,1),(6,2),(6,3),(6,4),(6,5),(6,6),
(7,1),(7,2),(7,3),(7,4),
(8,1),(8,2),(8,3),
(9,1),(9,2),(9,3),(9,4),(9,5),
(10,1),(10,2),(10,3),(10,4),
(11,1),(11,2),
(12,1),(12,2),(12,3),(12,4),(12,5),(12,6),
(13,1),(13,2),(13,3),
(14,1),(14,2),(14,3),(14,4);

-- ─── Project 40: Tengah Garden Walk ─────────────────────────────────────────
INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 40, '101A', 'Tengah Garden Walk', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '4-Room', 93.00, 380000 + (floor_number * 1200) + (unit_no * 600), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 40, '102B', 'Tengah Garden Walk', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '2-Room Flexi', 48.00, 195000 + (floor_number * 600) + (unit_no * 300), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 40, '103C', 'Tengah Garden Walk', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '5-Room', 112.00, 520000 + (floor_number * 1600) + (unit_no * 800), 'available'
FROM floor_units;

-- ─── Project 41: Punggol SeaVista ───────────────────────────────────────────
INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 41, '211A', 'Punggol Way', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '3-Room', 68.00, 290000 + (floor_number * 900) + (unit_no * 450), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 41, '212B', 'Punggol Way', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '4-Room', 93.00, 410000 + (floor_number * 1200) + (unit_no * 600), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 41, '213C', 'Punggol Way', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '5-Room', 112.00, 560000 + (floor_number * 1700) + (unit_no * 850), 'available'
FROM floor_units;

-- ─── Project 42: Queenstown SkyGrove ────────────────────────────────────────
INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 42, '511A', 'Queenstown Avenue', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '2-Room Flexi', 47.00, 220000 + (floor_number * 700) + (unit_no * 350), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 42, '512B', 'Queenstown Avenue', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '3-Room', 70.00, 335000 + (floor_number * 1000) + (unit_no * 500), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 42, '513C', 'Queenstown Avenue', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '4-Room', 95.00, 480000 + (floor_number * 1400) + (unit_no * 700), 'available'
FROM floor_units;

-- ─── Project 43: Kallang RiverFront ─────────────────────────────────────────
INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 43, '521A', 'Kallang Basin', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '3-Room', 69.00, 320000 + (floor_number * 1000) + (unit_no * 500), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 43, '522B', 'Kallang Basin', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '4-Room', 94.00, 455000 + (floor_number * 1300) + (unit_no * 650), 'available'
FROM floor_units;

INSERT IGNORE INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status)
SELECT 43, '523C', 'Kallang Basin', floor_number,
    CONCAT(LPAD(floor_number, 2, '0'), '-', LPAD(unit_no, 2, '0')),
    '5-Room', 113.00, 610000 + (floor_number * 1700) + (unit_no * 850), 'available'
FROM floor_units;

DROP TEMPORARY TABLE IF EXISTS floor_units;