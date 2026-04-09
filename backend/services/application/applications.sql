-- Application Service Database
CREATE DATABASE IF NOT EXISTS applications;
USE applications;

CREATE TABLE IF NOT EXISTS application (
    application_id INT AUTO_INCREMENT PRIMARY KEY,
    exercise_id INT NOT NULL,
    project_id INT NOT NULL,
    flat_type VARCHAR(50) NOT NULL,
    main_applicant_nric VARCHAR(20) NOT NULL,
    income_document_id BIGINT DEFAULT NULL,
    hfe_document_id BIGINT DEFAULT NULL,
    application_status ENUM('SUBMITTED', 'SUCCESSFUL', 'UNSUCCESSFUL', 'CANCELLED') NOT NULL DEFAULT 'SUBMITTED',
    submitted_at DATETIME DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS application_member (
    member_id INT AUTO_INCREMENT PRIMARY KEY,
    application_id INT NOT NULL,
    member_role ENUM('MAIN_APPLICANT', 'CO_APPLICANT', 'OCCUPANT') NOT NULL,
    nric_fin VARCHAR(20) NOT NULL,
    full_name VARCHAR(255) NOT NULL,
    relationship_to_main VARCHAR(50) NOT NULL,
    date_of_birth DATE NOT NULL,
    citizenship_status VARCHAR(20) NOT NULL,
    marital_status VARCHAR(20) DEFAULT NULL,
    contact_number VARCHAR(30) DEFAULT NULL,
    email VARCHAR(255) DEFAULT NULL,
    income_amount DECIMAL(12,2) DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    FOREIGN KEY (application_id) REFERENCES application(application_id) ON DELETE CASCADE
);

-- -----------------------------------------------------------------------
-- Demo applications aligned to real MockPass v3 personas.
--
-- App 2001 ? TAN HENG HUAT + JENNY LIM WAI FOOK applying for 5-Room.
-- App 2002 ? VENKATA NARASIMHA RAJUVARIPET S/O ABHAYANANDA applying solo for 2-Room Flexi.
-- App 2003 ? SAM YEE applying for 5-Room (historical unsuccessful example; closed exercise).
--
-- Additional exercise-6 rows below are also backed by real personas from
-- mockpass/v3.json so they remain visible and recognizable during ballot demos.
-- -----------------------------------------------------------------------
-- INSERT INTO application (
--     application_id,
--     exercise_id,
--     project_id,
--     flat_type,
--     main_applicant_nric,
--     income_document_id,
--     hfe_document_id,
--     application_status,
--     submitted_at,
--     created_at,
--     updated_at
-- ) VALUES
-- (
--     2001,
--     6,
--     51,
--     '5-Room',
--     'S9812381D',
--     1,
--     2,
--     'SUCCESSFUL',
--     '2026-03-15 10:00:00',
--     '2026-03-15 09:45:00',
--     '2026-03-15 10:00:00'
-- ),
-- (
--     2002,
--     6,
--     1,
--     '2-Room Flexi',
--     'S9912364H',
--     3,
--     4,
--     'SUCCESSFUL',
--     '2026-03-20 14:30:00',
--     '2026-03-20 14:15:00',
--     '2026-03-20 14:30:00'
-- ),
-- (
--     2003,
--     3,
--     31,
--     '5-Room',
--     'S9812346F',
--     5,
--     6,
--     'UNSUCCESSFUL',
--     '2025-11-18 14:05:00',
--     '2025-11-18 13:40:00',
--     '2025-12-02 09:10:00'
-- );

-- Additional demo applications for exercise 6 so ballot runs produce richer queue output
-- across projects and flat types, while still matching real MockPass personas.
INSERT INTO application (
    application_id,
    exercise_id,
    project_id,
    flat_type,
    main_applicant_nric,
    income_document_id,
    hfe_document_id,
    application_status,
    submitted_at,
    created_at,
    updated_at
) VALUES
(2011, 6, 40, '3-Room',       'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:20:00', '2026-03-22 09:05:00', '2026-03-22 09:20:00'),
(2012, 6, 41, '4-Room',       'S9812353I', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:30:00', '2026-03-22 09:10:00', '2026-03-22 09:30:00'),
(2014, 6, 40, '5-Room',       'S9912365F', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:50:00', '2026-03-22 09:20:00', '2026-03-22 09:50:00'),
(2015, 6, 40, '4-Room',       'S9812388Z', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:00:00', '2026-03-22 09:25:00', '2026-03-22 10:00:00'),
(2016, 6, 41, '5-Room',       'S9812388A', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:10:00', '2026-03-22 09:30:00', '2026-03-22 10:10:00'),
(2017, 6, 42,  '3-Room',       'S9812346F', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:20:00', '2026-03-22 09:35:00', '2026-03-22 10:20:00'),
(2018, 6, 42, '2-Room Flexi', 'S9812385G', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:30:00', '2026-03-22 09:40:00', '2026-03-22 10:30:00'),
(2019, 6, 40, '4-Room',       'S6005055D', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:40:00', '2026-03-22 09:45:00', '2026-03-22 10:40:00');

INSERT INTO application_member (
    member_id,
    application_id,
    member_role,
    nric_fin,
    full_name,
    relationship_to_main,
    date_of_birth,
    citizenship_status,
    marital_status,
    contact_number,
    email,
    income_amount,
    created_at,
    updated_at
) VALUES
-- App 2001: Tan Heng Huat + Jenny Lim Wai Fook
-- (
--     3001,
--     2001,
--     'MAIN_APPLICANT',
--     'S9812381D',
--     'TAN HENG HUAT',
--     'Self',
--     '1998-06-06',
--     'Citizen',
--     'Married',
--     '+65 91234567',
--     'tan.heng.huat@example.com',
--     5366.67,
--     '2026-03-15 09:45:00',
--     '2026-03-15 10:00:00'
-- ),
-- (
--     3002,
--     2001,
--     'CO_APPLICANT',
--     'G1612350T',
--     'JENNY LIM WAI FOOK',
--     'Spouse',
--     '1992-02-01',
--     'PR',
--     'Married',
--     '+65 92345678',
--     'jenny.lim@example.com',
--     4500.00,
--     '2026-03-15 09:45:00',
--     '2026-03-15 10:00:00'
-- ),
-- -- App 2002: Venkata solo
-- (
--     3003,
--     2002,
--     'MAIN_APPLICANT',
--     'S9912364H',
--     'VENKATA NARASIMHA RAJUVARIPET S/O ABHAYANANDA',
--     'Self',
--     '1960-05-17',
--     'Citizen',
--     'Single',
--     '+65 93456789',
--     'venkata.rajuvaripet@example.com',
--     3056.50,
--     '2026-03-20 14:15:00',
--     '2026-03-20 14:30:00'
-- ),

-- App 2011..2019 demo members backed by mockpass/v3.json personas
(3011, 2011, 'MAIN_APPLICANT', 'S9912370B', 'ELIZABERTH PIERCE JOHNSON', 'Self', '1999-10-06', 'Citizen', 'Widowed', '+ 65 00000000', 'demo@gmail.com', 4500.00, '2026-03-22 09:05:00', '2026-03-22 09:20:00'),
(3012, 2012, 'MAIN_APPLICANT', 'S9812353I', 'SONG CHIN YONG', 'Self', '1988-10-06', 'Citizen', 'Single', '+65 00000000', 'demo@gmail.com', 0.00, '2026-03-22 09:10:00', '2026-03-22 09:30:00'),
(3015, 2014, 'MAIN_APPLICANT', 'S9912365F', 'CHENG MEI QIN', 'Self', '1961-06-17', 'Citizen', 'Single', '+65 00000000', 'demo@gmail.com', 10103.42, '2026-03-22 09:20:00', '2026-03-22 09:50:00'),
(3016, 2015, 'MAIN_APPLICANT', 'S9812388Z', 'PATRICIA TAN XIAO HUI', 'Self', '1988-06-06', 'Citizen', '', '+65 91448782', 'irvintzh123@gmail.com', 4500.00, '2026-03-22 09:25:00', '2026-03-22 10:00:00'),
(3017, 2016, 'MAIN_APPLICANT', 'S9812388A', 'TAN MING HENG TERENCE', 'Self', '1992-02-01', 'Citizen', 'Single', '+65 00000000', 'demo@gmail.com', 11117.58, '2026-03-22 09:30:00', '2026-03-22 10:10:00'),
(3018, 2017, 'MAIN_APPLICANT', 'S9812346F', 'SAM YEE', 'Self', '1989-12-06', 'Citizen', 'Married', '+65 00000000', 'demo@gmail.com', 0.00, '2026-03-22 09:35:00', '2026-03-22 10:20:00'),
(3019, 2018, 'MAIN_APPLICANT', 'S9812385G', 'DEWANARA VANASAMIN', 'Self', '1950-10-06', 'Citizen', 'Single', '+65 00000000', 'demo@gmail.com', 0.00, '2026-03-22 09:40:00', '2026-03-22 10:30:00'),
(3020, 2019, 'MAIN_APPLICANT', 'S6005055D', 'MY.INFO:CC', 'Self', '1948-02-01', 'Citizen', 'Single', '+65 91448782', 'irvintzh123@gmail.com', 7035.92, '2026-03-22 09:45:00', '2026-03-22 10:40:00');

INSERT INTO application (
    application_id,
    exercise_id,
    project_id,
    flat_type,
    main_applicant_nric,
    income_document_id,
    hfe_document_id,
    application_status,
    submitted_at,
    created_at,
    updated_at
) VALUES
    (2020, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:00:00', '2026-04-01 09:45:00', '2026-04-01 10:00:00'),
    (2021, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:01:00', '2026-04-01 09:46:00', '2026-04-01 10:01:00'),
    (2022, 6, 40, '5-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:02:00', '2026-04-01 09:47:00', '2026-04-01 10:02:00'),
    (2023, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:03:00', '2026-04-01 09:48:00', '2026-04-01 10:03:00'),
    (2024, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:04:00', '2026-04-01 09:49:00', '2026-04-01 10:04:00'),
    (2025, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:05:00', '2026-04-01 09:50:00', '2026-04-01 10:05:00'),
    (2026, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:06:00', '2026-04-01 09:51:00', '2026-04-01 10:06:00'),
    (2027, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:07:00', '2026-04-01 09:52:00', '2026-04-01 10:07:00'),
    (2028, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:08:00', '2026-04-01 09:53:00', '2026-04-01 10:08:00'),
    (2029, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:09:00', '2026-04-01 09:54:00', '2026-04-01 10:09:00'),
    (2030, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:10:00', '2026-04-01 09:55:00', '2026-04-01 10:10:00'),
    (2031, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:11:00', '2026-04-01 09:56:00', '2026-04-01 10:11:00'),
    (2032, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:12:00', '2026-04-01 09:57:00', '2026-04-01 10:12:00'),
    (2033, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:13:00', '2026-04-01 09:58:00', '2026-04-01 10:13:00'),
    (2034, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:14:00', '2026-04-01 09:59:00', '2026-04-01 10:14:00'),
    (2035, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:15:00', '2026-04-01 10:00:00', '2026-04-01 10:15:00'),
    (2036, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:16:00', '2026-04-01 10:01:00', '2026-04-01 10:16:00'),
    (2037, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:17:00', '2026-04-01 10:02:00', '2026-04-01 10:17:00'),
    (2038, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:18:00', '2026-04-01 10:03:00', '2026-04-01 10:18:00'),
    (2039, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:19:00', '2026-04-01 10:04:00', '2026-04-01 10:19:00'),
    (2040, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:20:00', '2026-04-01 10:05:00', '2026-04-01 10:20:00'),
    (2041, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:21:00', '2026-04-01 10:06:00', '2026-04-01 10:21:00'),
    (2042, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:22:00', '2026-04-01 10:07:00', '2026-04-01 10:22:00'),
    (2043, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:23:00', '2026-04-01 10:08:00', '2026-04-01 10:23:00'),
    (2044, 6, 40, '4-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:24:00', '2026-04-01 10:09:00', '2026-04-01 10:24:00'),
    (2045, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:25:00', '2026-04-01 10:10:00', '2026-04-01 10:25:00'),
    (2046, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:26:00', '2026-04-01 10:11:00', '2026-04-01 10:26:00'),
    (2047, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:27:00', '2026-04-01 10:12:00', '2026-04-01 10:27:00'),
    (2048, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:28:00', '2026-04-01 10:13:00', '2026-04-01 10:28:00'),
    (2049, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:29:00', '2026-04-01 10:14:00', '2026-04-01 10:29:00'),
    (2050, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:30:00', '2026-04-01 10:15:00', '2026-04-01 10:30:00'),
    (2051, 6, 40, '3-Room', 'S9912370B', NULL, NULL, 'SUCCESSFUL', '2026-04-01 10:31:00', '2026-04-01 10:16:00', '2026-04-01 10:31:00')
ON DUPLICATE KEY UPDATE
    exercise_id = VALUES(exercise_id),
    project_id = VALUES(project_id),
    flat_type = VALUES(flat_type),
    main_applicant_nric = VALUES(main_applicant_nric),
    income_document_id = VALUES(income_document_id),
    hfe_document_id = VALUES(hfe_document_id),
    application_status = VALUES(application_status),
    submitted_at = VALUES(submitted_at),
    created_at = VALUES(created_at),
    updated_at = VALUES(updated_at);

-- Add missing MAIN_APPLICANT members for S9912370B demo applications
INSERT INTO application_member (
    application_id,
    member_role,
    nric_fin,
    full_name,
    relationship_to_main,
    date_of_birth,
    citizenship_status,
    marital_status,
    contact_number,
    email,
    income_amount,
    created_at,
    updated_at
 )
SELECT
    a.application_id,
    'MAIN_APPLICANT',
    a.main_applicant_nric,
    'ELIZABERTH PIERCE JOHNSON',
    'Self',
    '1999-10-06',
    'Citizen',
    'Widowed',
    '+65 00000000',
    'demo@gmail.com',
    4500.00,
    a.created_at,
    a.updated_at
FROM application a
LEFT JOIN application_member m
    ON m.application_id = a.application_id
   AND m.member_role = 'MAIN_APPLICANT'
   AND m.nric_fin = a.main_applicant_nric
WHERE a.application_id BETWEEN 2020 AND 2051
  AND m.member_id IS NULL;

