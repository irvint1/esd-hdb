-- Flat Availability Service Database
CREATE DATABASE IF NOT EXISTS flat_availability;
USE flat_availability;

-- BTO Projects table (e.g. "Tengah Garden Walk" in Tengah town)
CREATE TABLE IF NOT EXISTS bto_project (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(100) NOT NULL,
    town VARCHAR(50) NOT NULL,
    description TEXT,
    launch_date DATE,
    booking_start_date DATE,
    booking_end_date DATE
);

-- Individual flats within projects
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

-- Sample data
INSERT INTO bto_project (project_name, town, description, launch_date, booking_start_date, booking_end_date) VALUES
('Tengah Garden Walk', 'Tengah', 'Located in the heart of Tengah plantation district', '2025-08-15', '2025-09-01', '2025-09-30'),
('Woodlands North Vista', 'Woodlands', 'Near Woodlands MRT and Causeway Point', '2025-08-15', '2025-09-01', '2025-09-30');

-- Sample flats for Tengah Garden Walk (project_id = 1)
INSERT INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status) VALUES
(1, '101A', 'Tengah Garden Walk', 2, '201', '4-Room', 93.00, 350000.00, 'available'),
(1, '101A', 'Tengah Garden Walk', 2, '202', '4-Room', 93.00, 352000.00, 'available'),
(1, '101A', 'Tengah Garden Walk', 5, '501', '4-Room', 93.00, 365000.00, 'available'),
(1, '101A', 'Tengah Garden Walk', 5, '502', '5-Room', 112.00, 450000.00, 'available'),
(1, '101A', 'Tengah Garden Walk', 10, '1001', '5-Room', 112.00, 480000.00, 'available'),
(1, '102B', 'Tengah Garden Walk', 3, '301', '3-Room', 68.00, 250000.00, 'available'),
(1, '102B', 'Tengah Garden Walk', 3, '302', '2-Room Flexi', 48.00, 180000.00, 'available'),
(1, '102B', 'Tengah Garden Walk', 8, '801', '3-Room', 68.00, 265000.00, 'available');

-- Sample flats for Woodlands North Vista (project_id = 2)
INSERT INTO flat (project_id, block, street_name, floor_number, unit_number, flat_type, area_sqm, price, status) VALUES
(2, '501C', 'Woodlands Ave 5', 4, '401', '4-Room', 90.00, 320000.00, 'available'),
(2, '501C', 'Woodlands Ave 5', 4, '402', '4-Room', 90.00, 322000.00, 'available'),
(2, '501C', 'Woodlands Ave 5', 12, '1201', '5-Room', 110.00, 420000.00, 'available'),
(2, '502D', 'Woodlands Ave 5', 6, '601', '3-Room', 66.00, 230000.00, 'available'),
(2, '502D', 'Woodlands Ave 5', 6, '602', '3Gen', 115.00, 500000.00, 'available');
