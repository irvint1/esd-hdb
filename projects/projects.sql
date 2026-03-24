-- Projects Service Database
CREATE DATABASE IF NOT EXISTS projects;
USE projects;

DROP TABLE IF EXISTS projects;

CREATE TABLE IF NOT EXISTS projects (
    project_id INT AUTO_INCREMENT PRIMARY KEY,
    project_name VARCHAR(64) NOT NULL,
    town VARCHAR(64) NOT NULL,
    exercise_id INT NOT NULL
);

-- Sample records aligned with exercise_id values used in other services
INSERT INTO projects (project_id, project_name, town, exercise_id) VALUES
(1, 'Tengah Garden Walk', 'Tengah', 1),
(2, 'Woodlands North Vista', 'Woodlands', 1),
(11, 'Bedok North Bloom', 'Bedok', 1),
(12, 'Tampines GreenCourt', 'Tampines', 1),
(13, 'Yishun RiverVale', 'Yishun', 1),
(14, 'Woodlands ParkVista', 'Woodlands', 1),
(15, 'Hougang SpringGrove', 'Hougang', 1),
(21, 'Punggol SeaVista', 'Punggol', 2),
(22, 'Sengkang FernSpring', 'Sengkang', 2),
(23, 'Pasir Ris BlueHaven', 'Pasir Ris', 2),
(24, 'Serangoon MeadowRise', 'Serangoon', 2),
(31, 'Jurong West LakeEdge', 'Jurong West', 3),
(32, 'Clementi RidgeView', 'Clementi', 3),
(33, 'Bukit Batok Hillcrest', 'Bukit Batok', 3),
(41, 'Toa Payoh CentralTerrace', 'Toa Payoh', 4),
(42, 'Bishan ParkEdge', 'Bishan', 4),
(43, 'Ang Mo Kio ForestGlade', 'Ang Mo Kio', 4),
(51, 'Queenstown SkyGrove', 'Queenstown', 5),
(52, 'Kallang RiverFront', 'Kallang', 5),
(53, 'Geylang East Crest', 'Geylang', 5);
