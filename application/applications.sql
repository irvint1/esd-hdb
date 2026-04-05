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

SET @add_application_member_contact_number = (
    SELECT IF(
        EXISTS(
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'application_member'
              AND COLUMN_NAME = 'contact_number'
        ),
        'SELECT 1',
        'ALTER TABLE application_member ADD COLUMN contact_number VARCHAR(30) DEFAULT NULL AFTER marital_status'
    )
);
PREPARE stmt FROM @add_application_member_contact_number;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @add_application_member_email = (
    SELECT IF(
        EXISTS(
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'application_member'
              AND COLUMN_NAME = 'email'
        ),
        'SELECT 1',
        'ALTER TABLE application_member ADD COLUMN email VARCHAR(255) DEFAULT NULL AFTER contact_number'
    )
);
PREPARE stmt FROM @add_application_member_email;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

SET @drop_application_member_is_pregnant = (
    SELECT IF(
        EXISTS(
            SELECT 1
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'application_member'
              AND COLUMN_NAME = 'is_pregnant'
        ),
        'ALTER TABLE application_member DROP COLUMN is_pregnant',
        'SELECT 1'
    )
);
PREPARE stmt FROM @drop_application_member_is_pregnant;
EXECUTE stmt;
DEALLOCATE PREPARE stmt;

-- -----------------------------------------------------------------------
-- Three demo applications aligned to the dummy variable PDF personas.
--
-- App 2001 — Kevin Tan + Elaine Koh applying for 5-Room (SUCCESSFUL).
--            Happy path: married couple, valid HFE, income within ceiling.
--            Documents: income doc 1 (joint), HFE doc 2 (Kevin+Elaine).
--
-- App 2002 — Aaron Tan applying for 3-Room (SUCCESSFUL).
--            Single applicant, valid HFE, eligible for 3-Room only.
--            Documents: income doc 3 (Aaron CPF), HFE doc 4 (Aaron).
--
-- App 2003 — Sam Yee applying for 5-Room (UNSUCCESSFUL).
--            Failing path: HFE letter expired in September 2020.
--            Documents: income doc 5 (Sam CPF), HFE doc 6 (Sam).
-- -----------------------------------------------------------------------
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
(
    2001,
    6,
    51,
    '5-Room',
    'S9701234K',
    1,
    2,
    'SUCCESSFUL',
    '2026-03-15 10:00:00',
    '2026-03-15 09:45:00',
    '2026-03-15 10:00:00'
),
(
    2002,
    6,
    21,
    '3-Room',
    'S8501234A',
    3,
    4,
    'SUCCESSFUL',
    '2026-03-20 14:30:00',
    '2026-03-20 14:15:00',
    '2026-03-20 14:30:00'
),
(
    2003,
    3,
    31,
    '5-Room',
    'S9812346F',
    5,
    6,
    'UNSUCCESSFUL',
    '2025-11-18 14:05:00',
    '2025-11-18 13:40:00',
    '2025-12-02 09:10:00'
);

-- Additional demo applications for exercise 6 so ballot runs produce richer queue output
-- across projects and flat types.
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
(2010, 6, 1,  '2-Room Flexi', 'S9912364H', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:10:00', '2026-03-22 09:00:00', '2026-03-22 09:10:00'),
(2011, 6, 1,  '4-Room',       'S6005055D', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:20:00', '2026-03-22 09:05:00', '2026-03-22 09:20:00'),
(2012, 6, 1,  '5-Room',       'S9001234J', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:30:00', '2026-03-22 09:10:00', '2026-03-22 09:30:00'),
(2014, 6, 21, '4-Room',       'S9501234R', NULL, NULL, 'SUCCESSFUL', '2026-03-22 09:50:00', '2026-03-22 09:20:00', '2026-03-22 09:50:00'),
(2015, 6, 21, '5-Room',       'S9601234S', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:00:00', '2026-03-22 09:25:00', '2026-03-22 10:00:00'),
(2016, 6, 51, '2-Room Flexi', 'S9201234W', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:10:00', '2026-03-22 09:30:00', '2026-03-22 10:10:00'),
(2017, 6, 51, '3-Room',       'S9812388Z', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:20:00', '2026-03-22 09:35:00', '2026-03-22 10:20:00'),
(2018, 6, 52, '3-Room',       'S8901234D', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:30:00', '2026-03-22 09:40:00', '2026-03-22 10:30:00'),
(2019, 6, 52, '4-Room',       'S9101234M', NULL, NULL, 'SUCCESSFUL', '2026-03-22 10:40:00', '2026-03-22 09:45:00', '2026-03-22 10:40:00');

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
-- App 2001: Kevin + Elaine
(
    3001,
    2001,
    'MAIN_APPLICANT',
    'S9701234K',
    'KEVIN TAN WEI JIAN',
    'Self',
    '1997-10-08',
    'Citizen',
    'Married',
    '+65 9123 4567',
    'kevin.tan@example.com',
    5491.67,
    '2026-03-15 09:45:00',
    '2026-03-15 10:00:00'
),
(
    3002,
    2001,
    'CO_APPLICANT',
    'S8805678E',
    'ELAINE KOH MEI LING',
    'Spouse',
    '1988-09-30',
    'Citizen',
    'Married',
    '+65 9234 5678',
    'elaine.koh@example.com',
    4929.17,
    '2026-03-15 09:45:00',
    '2026-03-15 10:00:00'
),
-- App 2002: Aaron Tan (solo)
(
    3003,
    2002,
    'MAIN_APPLICANT',
    'S8501234A',
    'AARON TAN WEI MING',
    'Self',
    '1985-04-12',
    'Citizen',
    'Single',
    '+65 9345 6789',
    'aaron.tan@example.com',
    7233.33,
    '2026-03-20 14:15:00',
    '2026-03-20 14:30:00'
),
-- App 2003: Sam Yee (solo — expired HFE)
(
    3004,
    2003,
    'MAIN_APPLICANT',
    'S9812346F',
    'SAM YEE',
    'Self',
    '1989-12-06',
    'Citizen',
    'Married',
    '+65 9456 7890',
    'sam.yee@example.com',
    2673.70,
    '2025-11-18 13:40:00',
    '2025-12-02 09:10:00'
),
-- App 2010..2019 demo members
(3010, 2010, 'MAIN_APPLICANT', 'S9912364H', 'NAOMI LEE', 'Self', '1991-06-14', 'Citizen', 'Single', '+65 8111 0001', 'naomi.lee@example.com', 3056.50, '2026-03-22 09:00:00', '2026-03-22 09:10:00'),
(3011, 2011, 'MAIN_APPLICANT', 'S6005055D', 'DESMOND GOH', 'Self', '1990-05-05', 'Citizen', 'Single', '+65 8111 0002', 'desmond.goh@example.com', 7035.92, '2026-03-22 09:05:00', '2026-03-22 09:20:00'),
(3012, 2012, 'MAIN_APPLICANT', 'S9001234J', 'JEREMY ONG', 'Self', '1990-01-23', 'Citizen', 'Married', '+65 8111 0003', 'jeremy.ong@example.com', 0.00, '2026-03-22 09:10:00', '2026-03-22 09:30:00'),
(3013, 2012, 'CO_APPLICANT', 'S9101234M', 'MEI TAN', 'Spouse', '1991-02-18', 'Citizen', 'Married', '+65 8111 0004', 'mei.tan@example.com', 0.00, '2026-03-22 09:10:00', '2026-03-22 09:30:00'),
(3015, 2014, 'MAIN_APPLICANT', 'S9501234R', 'BRYAN CHUA', 'Self', '1995-03-17', 'Citizen', 'Married', '+65 8111 0006', 'bryan.chua@example.com', 0.00, '2026-03-22 09:20:00', '2026-03-22 09:50:00'),
(3016, 2015, 'MAIN_APPLICANT', 'S9601234S', 'CINDY LIM', 'Self', '1996-11-30', 'Citizen', 'Married', '+65 8111 0007', 'cindy.lim@example.com', 0.00, '2026-03-22 09:25:00', '2026-03-22 10:00:00'),
(3017, 2016, 'MAIN_APPLICANT', 'S9201234W', 'DAVID TAN', 'Self', '1992-07-12', 'Citizen', 'Single', '+65 8111 0008', 'david.tan@example.com', 0.00, '2026-03-22 09:30:00', '2026-03-22 10:10:00'),
(3018, 2017, 'MAIN_APPLICANT', 'S9812388Z', 'ELLA GOH', 'Self', '1998-04-03', 'Citizen', 'Single', '+65 8111 0009', 'ella.goh@example.com', 4500.00, '2026-03-22 09:35:00', '2026-03-22 10:20:00'),
(3019, 2018, 'MAIN_APPLICANT', 'S8901234D', 'FARIDAH ISMAIL', 'Self', '1989-09-09', 'Citizen', 'Single', '+65 8111 0010', 'faridah.ismail@example.com', 0.00, '2026-03-22 09:40:00', '2026-03-22 10:30:00'),
(3020, 2019, 'MAIN_APPLICANT', 'S9101234M', 'MEI TAN', 'Self', '1991-02-18', 'Citizen', 'Married', '+65 8111 0011', 'mei.tan.main@example.com', 0.00, '2026-03-22 09:45:00', '2026-03-22 10:40:00');







-- DEMO BULK BALLOT DATA START
-- 100 additional exercise-6 demo applications under project 21 (Punggol SeaVista)
-- to showcase queue-number generation by flat_type buckets within one project.
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
(2200, 6, 21, '3-Room', 'S7700001A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:01:00', '2026-03-23 07:51:00', '2026-03-23 08:01:00'),
(2201, 6, 21, '3-Room', 'S7700002A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:02:00', '2026-03-23 07:52:00', '2026-03-23 08:02:00'),
(2202, 6, 21, '3-Room', 'S7700003A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:03:00', '2026-03-23 07:53:00', '2026-03-23 08:03:00'),
(2203, 6, 21, '3-Room', 'S7700004A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:04:00', '2026-03-23 07:54:00', '2026-03-23 08:04:00'),
(2204, 6, 21, '3-Room', 'S7700005A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:05:00', '2026-03-23 07:55:00', '2026-03-23 08:05:00'),
(2205, 6, 21, '3-Room', 'S7700006A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:06:00', '2026-03-23 07:56:00', '2026-03-23 08:06:00'),
(2206, 6, 21, '3-Room', 'S7700007A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:07:00', '2026-03-23 07:57:00', '2026-03-23 08:07:00'),
(2207, 6, 21, '3-Room', 'S7700008A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:08:00', '2026-03-23 07:58:00', '2026-03-23 08:08:00'),
(2208, 6, 21, '3-Room', 'S7700009A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:09:00', '2026-03-23 07:59:00', '2026-03-23 08:09:00'),
(2209, 6, 21, '3-Room', 'S7700010A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:10:00', '2026-03-23 08:00:00', '2026-03-23 08:10:00'),
(2210, 6, 21, '3-Room', 'S7700011A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:11:00', '2026-03-23 08:01:00', '2026-03-23 08:11:00'),
(2211, 6, 21, '3-Room', 'S7700012A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:12:00', '2026-03-23 08:02:00', '2026-03-23 08:12:00'),
(2212, 6, 21, '3-Room', 'S7700013A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:13:00', '2026-03-23 08:03:00', '2026-03-23 08:13:00'),
(2213, 6, 21, '3-Room', 'S7700014A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:14:00', '2026-03-23 08:04:00', '2026-03-23 08:14:00'),
(2214, 6, 21, '3-Room', 'S7700015A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:15:00', '2026-03-23 08:05:00', '2026-03-23 08:15:00'),
(2215, 6, 21, '3-Room', 'S7700016A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:16:00', '2026-03-23 08:06:00', '2026-03-23 08:16:00'),
(2216, 6, 21, '3-Room', 'S7700017A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:17:00', '2026-03-23 08:07:00', '2026-03-23 08:17:00'),
(2217, 6, 21, '3-Room', 'S7700018A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:18:00', '2026-03-23 08:08:00', '2026-03-23 08:18:00'),
(2218, 6, 21, '3-Room', 'S7700019A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:19:00', '2026-03-23 08:09:00', '2026-03-23 08:19:00'),
(2219, 6, 21, '3-Room', 'S7700020A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:20:00', '2026-03-23 08:10:00', '2026-03-23 08:20:00'),
(2220, 6, 21, '3-Room', 'S7700021A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:21:00', '2026-03-23 08:11:00', '2026-03-23 08:21:00'),
(2221, 6, 21, '3-Room', 'S7700022A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:22:00', '2026-03-23 08:12:00', '2026-03-23 08:22:00'),
(2222, 6, 21, '3-Room', 'S7700023A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:23:00', '2026-03-23 08:13:00', '2026-03-23 08:23:00'),
(2223, 6, 21, '3-Room', 'S7700024A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:24:00', '2026-03-23 08:14:00', '2026-03-23 08:24:00'),
(2224, 6, 21, '3-Room', 'S7700025A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:25:00', '2026-03-23 08:15:00', '2026-03-23 08:25:00'),
(2225, 6, 21, '3-Room', 'S7700026A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:26:00', '2026-03-23 08:16:00', '2026-03-23 08:26:00'),
(2226, 6, 21, '3-Room', 'S7700027A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:27:00', '2026-03-23 08:17:00', '2026-03-23 08:27:00'),
(2227, 6, 21, '3-Room', 'S7700028A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:28:00', '2026-03-23 08:18:00', '2026-03-23 08:28:00'),
(2228, 6, 21, '3-Room', 'S7700029A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:29:00', '2026-03-23 08:19:00', '2026-03-23 08:29:00'),
(2229, 6, 21, '3-Room', 'S7700030A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:30:00', '2026-03-23 08:20:00', '2026-03-23 08:30:00'),
(2230, 6, 21, '3-Room', 'S7700031A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:31:00', '2026-03-23 08:21:00', '2026-03-23 08:31:00'),
(2231, 6, 21, '3-Room', 'S7700032A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:32:00', '2026-03-23 08:22:00', '2026-03-23 08:32:00'),
(2232, 6, 21, '3-Room', 'S7700033A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:33:00', '2026-03-23 08:23:00', '2026-03-23 08:33:00'),
(2233, 6, 21, '3-Room', 'S7700034A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:34:00', '2026-03-23 08:24:00', '2026-03-23 08:34:00'),
(2234, 6, 21, '4-Room', 'S7700035A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:35:00', '2026-03-23 08:25:00', '2026-03-23 08:35:00'),
(2235, 6, 21, '4-Room', 'S7700036A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:36:00', '2026-03-23 08:26:00', '2026-03-23 08:36:00'),
(2236, 6, 21, '4-Room', 'S7700037A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:37:00', '2026-03-23 08:27:00', '2026-03-23 08:37:00'),
(2237, 6, 21, '4-Room', 'S7700038A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:38:00', '2026-03-23 08:28:00', '2026-03-23 08:38:00'),
(2238, 6, 21, '4-Room', 'S7700039A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:39:00', '2026-03-23 08:29:00', '2026-03-23 08:39:00'),
(2239, 6, 21, '4-Room', 'S7700040A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:40:00', '2026-03-23 08:30:00', '2026-03-23 08:40:00'),
(2240, 6, 21, '4-Room', 'S7700041A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:41:00', '2026-03-23 08:31:00', '2026-03-23 08:41:00'),
(2241, 6, 21, '4-Room', 'S7700042A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:42:00', '2026-03-23 08:32:00', '2026-03-23 08:42:00'),
(2242, 6, 21, '4-Room', 'S7700043A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:43:00', '2026-03-23 08:33:00', '2026-03-23 08:43:00'),
(2243, 6, 21, '4-Room', 'S7700044A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:44:00', '2026-03-23 08:34:00', '2026-03-23 08:44:00'),
(2244, 6, 21, '4-Room', 'S7700045A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:45:00', '2026-03-23 08:35:00', '2026-03-23 08:45:00'),
(2245, 6, 21, '4-Room', 'S7700046A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:46:00', '2026-03-23 08:36:00', '2026-03-23 08:46:00'),
(2246, 6, 21, '4-Room', 'S7700047A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:47:00', '2026-03-23 08:37:00', '2026-03-23 08:47:00'),
(2247, 6, 21, '4-Room', 'S7700048A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:48:00', '2026-03-23 08:38:00', '2026-03-23 08:48:00'),
(2248, 6, 21, '4-Room', 'S7700049A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:49:00', '2026-03-23 08:39:00', '2026-03-23 08:49:00'),
(2249, 6, 21, '4-Room', 'S7700050A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:50:00', '2026-03-23 08:40:00', '2026-03-23 08:50:00'),
(2250, 6, 21, '4-Room', 'S7700051A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:51:00', '2026-03-23 08:41:00', '2026-03-23 08:51:00'),
(2251, 6, 21, '4-Room', 'S7700052A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:52:00', '2026-03-23 08:42:00', '2026-03-23 08:52:00'),
(2252, 6, 21, '4-Room', 'S7700053A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:53:00', '2026-03-23 08:43:00', '2026-03-23 08:53:00'),
(2253, 6, 21, '4-Room', 'S7700054A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:54:00', '2026-03-23 08:44:00', '2026-03-23 08:54:00'),
(2254, 6, 21, '4-Room', 'S7700055A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:55:00', '2026-03-23 08:45:00', '2026-03-23 08:55:00'),
(2255, 6, 21, '4-Room', 'S7700056A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:56:00', '2026-03-23 08:46:00', '2026-03-23 08:56:00'),
(2256, 6, 21, '4-Room', 'S7700057A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:57:00', '2026-03-23 08:47:00', '2026-03-23 08:57:00'),
(2257, 6, 21, '4-Room', 'S7700058A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:58:00', '2026-03-23 08:48:00', '2026-03-23 08:58:00'),
(2258, 6, 21, '4-Room', 'S7700059A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 08:59:00', '2026-03-23 08:49:00', '2026-03-23 08:59:00'),
(2259, 6, 21, '4-Room', 'S7700060A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:00:00', '2026-03-23 08:50:00', '2026-03-23 09:00:00'),
(2260, 6, 21, '4-Room', 'S7700061A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:01:00', '2026-03-23 08:51:00', '2026-03-23 09:01:00'),
(2261, 6, 21, '4-Room', 'S7700062A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:02:00', '2026-03-23 08:52:00', '2026-03-23 09:02:00'),
(2262, 6, 21, '4-Room', 'S7700063A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:03:00', '2026-03-23 08:53:00', '2026-03-23 09:03:00'),
(2263, 6, 21, '4-Room', 'S7700064A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:04:00', '2026-03-23 08:54:00', '2026-03-23 09:04:00'),
(2264, 6, 21, '4-Room', 'S7700065A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:05:00', '2026-03-23 08:55:00', '2026-03-23 09:05:00'),
(2265, 6, 21, '4-Room', 'S7700066A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:06:00', '2026-03-23 08:56:00', '2026-03-23 09:06:00'),
(2266, 6, 21, '4-Room', 'S7700067A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:07:00', '2026-03-23 08:57:00', '2026-03-23 09:07:00'),
(2267, 6, 21, '5-Room', 'S7700068A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:08:00', '2026-03-23 08:58:00', '2026-03-23 09:08:00'),
(2268, 6, 21, '5-Room', 'S7700069A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:09:00', '2026-03-23 08:59:00', '2026-03-23 09:09:00'),
(2269, 6, 21, '5-Room', 'S7700070A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:10:00', '2026-03-23 09:00:00', '2026-03-23 09:10:00'),
(2270, 6, 21, '5-Room', 'S7700071A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:11:00', '2026-03-23 09:01:00', '2026-03-23 09:11:00'),
(2271, 6, 21, '5-Room', 'S7700072A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:12:00', '2026-03-23 09:02:00', '2026-03-23 09:12:00'),
(2272, 6, 21, '5-Room', 'S7700073A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:13:00', '2026-03-23 09:03:00', '2026-03-23 09:13:00'),
(2273, 6, 21, '5-Room', 'S7700074A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:14:00', '2026-03-23 09:04:00', '2026-03-23 09:14:00'),
(2274, 6, 21, '5-Room', 'S7700075A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:15:00', '2026-03-23 09:05:00', '2026-03-23 09:15:00'),
(2275, 6, 21, '5-Room', 'S7700076A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:16:00', '2026-03-23 09:06:00', '2026-03-23 09:16:00'),
(2276, 6, 21, '5-Room', 'S7700077A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:17:00', '2026-03-23 09:07:00', '2026-03-23 09:17:00'),
(2277, 6, 21, '5-Room', 'S7700078A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:18:00', '2026-03-23 09:08:00', '2026-03-23 09:18:00'),
(2278, 6, 21, '5-Room', 'S7700079A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:19:00', '2026-03-23 09:09:00', '2026-03-23 09:19:00'),
(2279, 6, 21, '5-Room', 'S7700080A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:20:00', '2026-03-23 09:10:00', '2026-03-23 09:20:00'),
(2280, 6, 21, '5-Room', 'S7700081A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:21:00', '2026-03-23 09:11:00', '2026-03-23 09:21:00'),
(2281, 6, 21, '5-Room', 'S7700082A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:22:00', '2026-03-23 09:12:00', '2026-03-23 09:22:00'),
(2282, 6, 21, '5-Room', 'S7700083A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:23:00', '2026-03-23 09:13:00', '2026-03-23 09:23:00'),
(2283, 6, 21, '5-Room', 'S7700084A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:24:00', '2026-03-23 09:14:00', '2026-03-23 09:24:00'),
(2284, 6, 21, '5-Room', 'S7700085A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:25:00', '2026-03-23 09:15:00', '2026-03-23 09:25:00'),
(2285, 6, 21, '5-Room', 'S7700086A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:26:00', '2026-03-23 09:16:00', '2026-03-23 09:26:00'),
(2286, 6, 21, '5-Room', 'S7700087A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:27:00', '2026-03-23 09:17:00', '2026-03-23 09:27:00'),
(2287, 6, 21, '5-Room', 'S7700088A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:28:00', '2026-03-23 09:18:00', '2026-03-23 09:28:00'),
(2288, 6, 21, '5-Room', 'S7700089A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:29:00', '2026-03-23 09:19:00', '2026-03-23 09:29:00'),
(2289, 6, 21, '5-Room', 'S7700090A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:30:00', '2026-03-23 09:20:00', '2026-03-23 09:30:00'),
(2290, 6, 21, '5-Room', 'S7700091A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:31:00', '2026-03-23 09:21:00', '2026-03-23 09:31:00'),
(2291, 6, 21, '5-Room', 'S7700092A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:32:00', '2026-03-23 09:22:00', '2026-03-23 09:32:00'),
(2292, 6, 21, '5-Room', 'S7700093A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:33:00', '2026-03-23 09:23:00', '2026-03-23 09:33:00'),
(2293, 6, 21, '5-Room', 'S7700094A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:34:00', '2026-03-23 09:24:00', '2026-03-23 09:34:00'),
(2294, 6, 21, '5-Room', 'S7700095A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:35:00', '2026-03-23 09:25:00', '2026-03-23 09:35:00'),
(2295, 6, 21, '5-Room', 'S7700096A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:36:00', '2026-03-23 09:26:00', '2026-03-23 09:36:00'),
(2296, 6, 21, '5-Room', 'S7700097A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:37:00', '2026-03-23 09:27:00', '2026-03-23 09:37:00'),
(2297, 6, 21, '5-Room', 'S7700098A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:38:00', '2026-03-23 09:28:00', '2026-03-23 09:38:00'),
(2298, 6, 21, '5-Room', 'S7700099A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:39:00', '2026-03-23 09:29:00', '2026-03-23 09:39:00'),
(2299, 6, 21, '5-Room', 'S7700100A', NULL, NULL, 'SUCCESSFUL', '2026-03-23 09:40:00', '2026-03-23 09:30:00', '2026-03-23 09:40:00');


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
(3301, 2200, 'MAIN_APPLICANT', 'S7700001A', 'DEMO APPLICANT 001', 'Self', '1987-01-01', 'Citizen', 'Single', '+65 81000001', 'demo001@example.com', 6000.00, '2026-03-23 07:51:00', '2026-03-23 08:01:00'),
(3302, 2201, 'MAIN_APPLICANT', 'S7700002A', 'DEMO APPLICANT 002', 'Self', '1988-02-02', 'Citizen', 'Single', '+65 81000002', 'demo002@example.com', 6000.00, '2026-03-23 07:52:00', '2026-03-23 08:02:00'),
(3303, 2202, 'MAIN_APPLICANT', 'S7700003A', 'DEMO APPLICANT 003', 'Self', '1989-03-03', 'Citizen', 'Single', '+65 81000003', 'demo003@example.com', 6000.00, '2026-03-23 07:53:00', '2026-03-23 08:03:00'),
(3304, 2203, 'MAIN_APPLICANT', 'S7700004A', 'DEMO APPLICANT 004', 'Self', '1990-04-04', 'Citizen', 'Single', '+65 81000004', 'demo004@example.com', 6000.00, '2026-03-23 07:54:00', '2026-03-23 08:04:00'),
(3305, 2204, 'MAIN_APPLICANT', 'S7700005A', 'DEMO APPLICANT 005', 'Self', '1991-05-05', 'Citizen', 'Single', '+65 81000005', 'demo005@example.com', 6000.00, '2026-03-23 07:55:00', '2026-03-23 08:05:00'),
(3306, 2205, 'MAIN_APPLICANT', 'S7700006A', 'DEMO APPLICANT 006', 'Self', '1992-06-06', 'Citizen', 'Single', '+65 81000006', 'demo006@example.com', 6000.00, '2026-03-23 07:56:00', '2026-03-23 08:06:00'),
(3307, 2206, 'MAIN_APPLICANT', 'S7700007A', 'DEMO APPLICANT 007', 'Self', '1993-07-07', 'Citizen', 'Single', '+65 81000007', 'demo007@example.com', 6000.00, '2026-03-23 07:57:00', '2026-03-23 08:07:00'),
(3308, 2207, 'MAIN_APPLICANT', 'S7700008A', 'DEMO APPLICANT 008', 'Self', '1994-08-08', 'Citizen', 'Single', '+65 81000008', 'demo008@example.com', 6000.00, '2026-03-23 07:58:00', '2026-03-23 08:08:00'),
(3309, 2208, 'MAIN_APPLICANT', 'S7700009A', 'DEMO APPLICANT 009', 'Self', '1995-09-09', 'Citizen', 'Single', '+65 81000009', 'demo009@example.com', 6000.00, '2026-03-23 07:59:00', '2026-03-23 08:09:00'),
(3310, 2209, 'MAIN_APPLICANT', 'S7700010A', 'DEMO APPLICANT 010', 'Self', '1986-10-10', 'Citizen', 'Single', '+65 81000010', 'demo010@example.com', 6000.00, '2026-03-23 08:00:00', '2026-03-23 08:10:00'),
(3311, 2210, 'MAIN_APPLICANT', 'S7700011A', 'DEMO APPLICANT 011', 'Self', '1987-11-11', 'Citizen', 'Single', '+65 81000011', 'demo011@example.com', 6000.00, '2026-03-23 08:01:00', '2026-03-23 08:11:00'),
(3312, 2211, 'MAIN_APPLICANT', 'S7700012A', 'DEMO APPLICANT 012', 'Self', '1988-12-12', 'Citizen', 'Single', '+65 81000012', 'demo012@example.com', 6000.00, '2026-03-23 08:02:00', '2026-03-23 08:12:00'),
(3313, 2212, 'MAIN_APPLICANT', 'S7700013A', 'DEMO APPLICANT 013', 'Self', '1989-01-13', 'Citizen', 'Single', '+65 81000013', 'demo013@example.com', 6000.00, '2026-03-23 08:03:00', '2026-03-23 08:13:00'),
(3314, 2213, 'MAIN_APPLICANT', 'S7700014A', 'DEMO APPLICANT 014', 'Self', '1990-02-14', 'Citizen', 'Single', '+65 81000014', 'demo014@example.com', 6000.00, '2026-03-23 08:04:00', '2026-03-23 08:14:00'),
(3315, 2214, 'MAIN_APPLICANT', 'S7700015A', 'DEMO APPLICANT 015', 'Self', '1991-03-15', 'Citizen', 'Single', '+65 81000015', 'demo015@example.com', 6000.00, '2026-03-23 08:05:00', '2026-03-23 08:15:00'),
(3316, 2215, 'MAIN_APPLICANT', 'S7700016A', 'DEMO APPLICANT 016', 'Self', '1992-04-16', 'Citizen', 'Single', '+65 81000016', 'demo016@example.com', 6000.00, '2026-03-23 08:06:00', '2026-03-23 08:16:00'),
(3317, 2216, 'MAIN_APPLICANT', 'S7700017A', 'DEMO APPLICANT 017', 'Self', '1993-05-17', 'Citizen', 'Single', '+65 81000017', 'demo017@example.com', 6000.00, '2026-03-23 08:07:00', '2026-03-23 08:17:00'),
(3318, 2217, 'MAIN_APPLICANT', 'S7700018A', 'DEMO APPLICANT 018', 'Self', '1994-06-18', 'Citizen', 'Single', '+65 81000018', 'demo018@example.com', 6000.00, '2026-03-23 08:08:00', '2026-03-23 08:18:00'),
(3319, 2218, 'MAIN_APPLICANT', 'S7700019A', 'DEMO APPLICANT 019', 'Self', '1995-07-19', 'Citizen', 'Single', '+65 81000019', 'demo019@example.com', 6000.00, '2026-03-23 08:09:00', '2026-03-23 08:19:00'),
(3320, 2219, 'MAIN_APPLICANT', 'S7700020A', 'DEMO APPLICANT 020', 'Self', '1986-08-20', 'Citizen', 'Single', '+65 81000020', 'demo020@example.com', 6000.00, '2026-03-23 08:10:00', '2026-03-23 08:20:00'),
(3321, 2220, 'MAIN_APPLICANT', 'S7700021A', 'DEMO APPLICANT 021', 'Self', '1987-09-21', 'Citizen', 'Single', '+65 81000021', 'demo021@example.com', 6000.00, '2026-03-23 08:11:00', '2026-03-23 08:21:00'),
(3322, 2221, 'MAIN_APPLICANT', 'S7700022A', 'DEMO APPLICANT 022', 'Self', '1988-10-22', 'Citizen', 'Single', '+65 81000022', 'demo022@example.com', 6000.00, '2026-03-23 08:12:00', '2026-03-23 08:22:00'),
(3323, 2222, 'MAIN_APPLICANT', 'S7700023A', 'DEMO APPLICANT 023', 'Self', '1989-11-23', 'Citizen', 'Single', '+65 81000023', 'demo023@example.com', 6000.00, '2026-03-23 08:13:00', '2026-03-23 08:23:00'),
(3324, 2223, 'MAIN_APPLICANT', 'S7700024A', 'DEMO APPLICANT 024', 'Self', '1990-12-24', 'Citizen', 'Single', '+65 81000024', 'demo024@example.com', 6000.00, '2026-03-23 08:14:00', '2026-03-23 08:24:00'),
(3325, 2224, 'MAIN_APPLICANT', 'S7700025A', 'DEMO APPLICANT 025', 'Self', '1991-01-25', 'Citizen', 'Single', '+65 81000025', 'demo025@example.com', 6000.00, '2026-03-23 08:15:00', '2026-03-23 08:25:00'),
(3326, 2225, 'MAIN_APPLICANT', 'S7700026A', 'DEMO APPLICANT 026', 'Self', '1992-02-26', 'Citizen', 'Single', '+65 81000026', 'demo026@example.com', 6000.00, '2026-03-23 08:16:00', '2026-03-23 08:26:00'),
(3327, 2226, 'MAIN_APPLICANT', 'S7700027A', 'DEMO APPLICANT 027', 'Self', '1993-03-27', 'Citizen', 'Single', '+65 81000027', 'demo027@example.com', 6000.00, '2026-03-23 08:17:00', '2026-03-23 08:27:00'),
(3328, 2227, 'MAIN_APPLICANT', 'S7700028A', 'DEMO APPLICANT 028', 'Self', '1994-04-28', 'Citizen', 'Single', '+65 81000028', 'demo028@example.com', 6000.00, '2026-03-23 08:18:00', '2026-03-23 08:28:00'),
(3329, 2228, 'MAIN_APPLICANT', 'S7700029A', 'DEMO APPLICANT 029', 'Self', '1995-05-01', 'Citizen', 'Single', '+65 81000029', 'demo029@example.com', 6000.00, '2026-03-23 08:19:00', '2026-03-23 08:29:00'),
(3330, 2229, 'MAIN_APPLICANT', 'S7700030A', 'DEMO APPLICANT 030', 'Self', '1986-06-02', 'Citizen', 'Single', '+65 81000030', 'demo030@example.com', 6000.00, '2026-03-23 08:20:00', '2026-03-23 08:30:00'),
(3331, 2230, 'MAIN_APPLICANT', 'S7700031A', 'DEMO APPLICANT 031', 'Self', '1987-07-03', 'Citizen', 'Single', '+65 81000031', 'demo031@example.com', 6000.00, '2026-03-23 08:21:00', '2026-03-23 08:31:00'),
(3332, 2231, 'MAIN_APPLICANT', 'S7700032A', 'DEMO APPLICANT 032', 'Self', '1988-08-04', 'Citizen', 'Single', '+65 81000032', 'demo032@example.com', 6000.00, '2026-03-23 08:22:00', '2026-03-23 08:32:00'),
(3333, 2232, 'MAIN_APPLICANT', 'S7700033A', 'DEMO APPLICANT 033', 'Self', '1989-09-05', 'Citizen', 'Single', '+65 81000033', 'demo033@example.com', 6000.00, '2026-03-23 08:23:00', '2026-03-23 08:33:00'),
(3334, 2233, 'MAIN_APPLICANT', 'S7700034A', 'DEMO APPLICANT 034', 'Self', '1990-10-06', 'Citizen', 'Single', '+65 81000034', 'demo034@example.com', 6000.00, '2026-03-23 08:24:00', '2026-03-23 08:34:00'),
(3335, 2234, 'MAIN_APPLICANT', 'S7700035A', 'DEMO APPLICANT 035', 'Self', '1991-11-07', 'Citizen', 'Single', '+65 81000035', 'demo035@example.com', 9000.00, '2026-03-23 08:25:00', '2026-03-23 08:35:00'),
(3336, 2235, 'MAIN_APPLICANT', 'S7700036A', 'DEMO APPLICANT 036', 'Self', '1992-12-08', 'Citizen', 'Single', '+65 81000036', 'demo036@example.com', 9000.00, '2026-03-23 08:26:00', '2026-03-23 08:36:00'),
(3337, 2236, 'MAIN_APPLICANT', 'S7700037A', 'DEMO APPLICANT 037', 'Self', '1993-01-09', 'Citizen', 'Single', '+65 81000037', 'demo037@example.com', 9000.00, '2026-03-23 08:27:00', '2026-03-23 08:37:00'),
(3338, 2237, 'MAIN_APPLICANT', 'S7700038A', 'DEMO APPLICANT 038', 'Self', '1994-02-10', 'Citizen', 'Single', '+65 81000038', 'demo038@example.com', 9000.00, '2026-03-23 08:28:00', '2026-03-23 08:38:00'),
(3339, 2238, 'MAIN_APPLICANT', 'S7700039A', 'DEMO APPLICANT 039', 'Self', '1995-03-11', 'Citizen', 'Single', '+65 81000039', 'demo039@example.com', 9000.00, '2026-03-23 08:29:00', '2026-03-23 08:39:00'),
(3340, 2239, 'MAIN_APPLICANT', 'S7700040A', 'DEMO APPLICANT 040', 'Self', '1986-04-12', 'Citizen', 'Single', '+65 81000040', 'demo040@example.com', 9000.00, '2026-03-23 08:30:00', '2026-03-23 08:40:00'),
(3341, 2240, 'MAIN_APPLICANT', 'S7700041A', 'DEMO APPLICANT 041', 'Self', '1987-05-13', 'Citizen', 'Single', '+65 81000041', 'demo041@example.com', 9000.00, '2026-03-23 08:31:00', '2026-03-23 08:41:00'),
(3342, 2241, 'MAIN_APPLICANT', 'S7700042A', 'DEMO APPLICANT 042', 'Self', '1988-06-14', 'Citizen', 'Single', '+65 81000042', 'demo042@example.com', 9000.00, '2026-03-23 08:32:00', '2026-03-23 08:42:00'),
(3343, 2242, 'MAIN_APPLICANT', 'S7700043A', 'DEMO APPLICANT 043', 'Self', '1989-07-15', 'Citizen', 'Single', '+65 81000043', 'demo043@example.com', 9000.00, '2026-03-23 08:33:00', '2026-03-23 08:43:00'),
(3344, 2243, 'MAIN_APPLICANT', 'S7700044A', 'DEMO APPLICANT 044', 'Self', '1990-08-16', 'Citizen', 'Single', '+65 81000044', 'demo044@example.com', 9000.00, '2026-03-23 08:34:00', '2026-03-23 08:44:00'),
(3345, 2244, 'MAIN_APPLICANT', 'S7700045A', 'DEMO APPLICANT 045', 'Self', '1991-09-17', 'Citizen', 'Single', '+65 81000045', 'demo045@example.com', 9000.00, '2026-03-23 08:35:00', '2026-03-23 08:45:00'),
(3346, 2245, 'MAIN_APPLICANT', 'S7700046A', 'DEMO APPLICANT 046', 'Self', '1992-10-18', 'Citizen', 'Single', '+65 81000046', 'demo046@example.com', 9000.00, '2026-03-23 08:36:00', '2026-03-23 08:46:00'),
(3347, 2246, 'MAIN_APPLICANT', 'S7700047A', 'DEMO APPLICANT 047', 'Self', '1993-11-19', 'Citizen', 'Single', '+65 81000047', 'demo047@example.com', 9000.00, '2026-03-23 08:37:00', '2026-03-23 08:47:00'),
(3348, 2247, 'MAIN_APPLICANT', 'S7700048A', 'DEMO APPLICANT 048', 'Self', '1994-12-20', 'Citizen', 'Single', '+65 81000048', 'demo048@example.com', 9000.00, '2026-03-23 08:38:00', '2026-03-23 08:48:00'),
(3349, 2248, 'MAIN_APPLICANT', 'S7700049A', 'DEMO APPLICANT 049', 'Self', '1995-01-21', 'Citizen', 'Single', '+65 81000049', 'demo049@example.com', 9000.00, '2026-03-23 08:39:00', '2026-03-23 08:49:00'),
(3350, 2249, 'MAIN_APPLICANT', 'S7700050A', 'DEMO APPLICANT 050', 'Self', '1986-02-22', 'Citizen', 'Single', '+65 81000050', 'demo050@example.com', 9000.00, '2026-03-23 08:40:00', '2026-03-23 08:50:00'),
(3351, 2250, 'MAIN_APPLICANT', 'S7700051A', 'DEMO APPLICANT 051', 'Self', '1987-03-23', 'Citizen', 'Single', '+65 81000051', 'demo051@example.com', 9000.00, '2026-03-23 08:41:00', '2026-03-23 08:51:00'),
(3352, 2251, 'MAIN_APPLICANT', 'S7700052A', 'DEMO APPLICANT 052', 'Self', '1988-04-24', 'Citizen', 'Single', '+65 81000052', 'demo052@example.com', 9000.00, '2026-03-23 08:42:00', '2026-03-23 08:52:00'),
(3353, 2252, 'MAIN_APPLICANT', 'S7700053A', 'DEMO APPLICANT 053', 'Self', '1989-05-25', 'Citizen', 'Single', '+65 81000053', 'demo053@example.com', 9000.00, '2026-03-23 08:43:00', '2026-03-23 08:53:00'),
(3354, 2253, 'MAIN_APPLICANT', 'S7700054A', 'DEMO APPLICANT 054', 'Self', '1990-06-26', 'Citizen', 'Single', '+65 81000054', 'demo054@example.com', 9000.00, '2026-03-23 08:44:00', '2026-03-23 08:54:00'),
(3355, 2254, 'MAIN_APPLICANT', 'S7700055A', 'DEMO APPLICANT 055', 'Self', '1991-07-27', 'Citizen', 'Single', '+65 81000055', 'demo055@example.com', 9000.00, '2026-03-23 08:45:00', '2026-03-23 08:55:00'),
(3356, 2255, 'MAIN_APPLICANT', 'S7700056A', 'DEMO APPLICANT 056', 'Self', '1992-08-28', 'Citizen', 'Single', '+65 81000056', 'demo056@example.com', 9000.00, '2026-03-23 08:46:00', '2026-03-23 08:56:00'),
(3357, 2256, 'MAIN_APPLICANT', 'S7700057A', 'DEMO APPLICANT 057', 'Self', '1993-09-01', 'Citizen', 'Single', '+65 81000057', 'demo057@example.com', 9000.00, '2026-03-23 08:47:00', '2026-03-23 08:57:00'),
(3358, 2257, 'MAIN_APPLICANT', 'S7700058A', 'DEMO APPLICANT 058', 'Self', '1994-10-02', 'Citizen', 'Single', '+65 81000058', 'demo058@example.com', 9000.00, '2026-03-23 08:48:00', '2026-03-23 08:58:00'),
(3359, 2258, 'MAIN_APPLICANT', 'S7700059A', 'DEMO APPLICANT 059', 'Self', '1995-11-03', 'Citizen', 'Single', '+65 81000059', 'demo059@example.com', 9000.00, '2026-03-23 08:49:00', '2026-03-23 08:59:00'),
(3360, 2259, 'MAIN_APPLICANT', 'S7700060A', 'DEMO APPLICANT 060', 'Self', '1986-12-04', 'Citizen', 'Single', '+65 81000060', 'demo060@example.com', 9000.00, '2026-03-23 08:50:00', '2026-03-23 09:00:00'),
(3361, 2260, 'MAIN_APPLICANT', 'S7700061A', 'DEMO APPLICANT 061', 'Self', '1987-01-05', 'Citizen', 'Single', '+65 81000061', 'demo061@example.com', 9000.00, '2026-03-23 08:51:00', '2026-03-23 09:01:00'),
(3362, 2261, 'MAIN_APPLICANT', 'S7700062A', 'DEMO APPLICANT 062', 'Self', '1988-02-06', 'Citizen', 'Single', '+65 81000062', 'demo062@example.com', 9000.00, '2026-03-23 08:52:00', '2026-03-23 09:02:00'),
(3363, 2262, 'MAIN_APPLICANT', 'S7700063A', 'DEMO APPLICANT 063', 'Self', '1989-03-07', 'Citizen', 'Single', '+65 81000063', 'demo063@example.com', 9000.00, '2026-03-23 08:53:00', '2026-03-23 09:03:00'),
(3364, 2263, 'MAIN_APPLICANT', 'S7700064A', 'DEMO APPLICANT 064', 'Self', '1990-04-08', 'Citizen', 'Single', '+65 81000064', 'demo064@example.com', 9000.00, '2026-03-23 08:54:00', '2026-03-23 09:04:00'),
(3365, 2264, 'MAIN_APPLICANT', 'S7700065A', 'DEMO APPLICANT 065', 'Self', '1991-05-09', 'Citizen', 'Single', '+65 81000065', 'demo065@example.com', 9000.00, '2026-03-23 08:55:00', '2026-03-23 09:05:00'),
(3366, 2265, 'MAIN_APPLICANT', 'S7700066A', 'DEMO APPLICANT 066', 'Self', '1992-06-10', 'Citizen', 'Single', '+65 81000066', 'demo066@example.com', 9000.00, '2026-03-23 08:56:00', '2026-03-23 09:06:00'),
(3367, 2266, 'MAIN_APPLICANT', 'S7700067A', 'DEMO APPLICANT 067', 'Self', '1993-07-11', 'Citizen', 'Single', '+65 81000067', 'demo067@example.com', 9000.00, '2026-03-23 08:57:00', '2026-03-23 09:07:00'),
(3368, 2267, 'MAIN_APPLICANT', 'S7700068A', 'DEMO APPLICANT 068', 'Self', '1994-08-12', 'Citizen', 'Single', '+65 81000068', 'demo068@example.com', 11000.00, '2026-03-23 08:58:00', '2026-03-23 09:08:00'),
(3369, 2268, 'MAIN_APPLICANT', 'S7700069A', 'DEMO APPLICANT 069', 'Self', '1995-09-13', 'Citizen', 'Single', '+65 81000069', 'demo069@example.com', 11000.00, '2026-03-23 08:59:00', '2026-03-23 09:09:00'),
(3370, 2269, 'MAIN_APPLICANT', 'S7700070A', 'DEMO APPLICANT 070', 'Self', '1986-10-14', 'Citizen', 'Single', '+65 81000070', 'demo070@example.com', 11000.00, '2026-03-23 09:00:00', '2026-03-23 09:10:00'),
(3371, 2270, 'MAIN_APPLICANT', 'S7700071A', 'DEMO APPLICANT 071', 'Self', '1987-11-15', 'Citizen', 'Single', '+65 81000071', 'demo071@example.com', 11000.00, '2026-03-23 09:01:00', '2026-03-23 09:11:00'),
(3372, 2271, 'MAIN_APPLICANT', 'S7700072A', 'DEMO APPLICANT 072', 'Self', '1988-12-16', 'Citizen', 'Single', '+65 81000072', 'demo072@example.com', 11000.00, '2026-03-23 09:02:00', '2026-03-23 09:12:00'),
(3373, 2272, 'MAIN_APPLICANT', 'S7700073A', 'DEMO APPLICANT 073', 'Self', '1989-01-17', 'Citizen', 'Single', '+65 81000073', 'demo073@example.com', 11000.00, '2026-03-23 09:03:00', '2026-03-23 09:13:00'),
(3374, 2273, 'MAIN_APPLICANT', 'S7700074A', 'DEMO APPLICANT 074', 'Self', '1990-02-18', 'Citizen', 'Single', '+65 81000074', 'demo074@example.com', 11000.00, '2026-03-23 09:04:00', '2026-03-23 09:14:00'),
(3375, 2274, 'MAIN_APPLICANT', 'S7700075A', 'DEMO APPLICANT 075', 'Self', '1991-03-19', 'Citizen', 'Single', '+65 81000075', 'demo075@example.com', 11000.00, '2026-03-23 09:05:00', '2026-03-23 09:15:00'),
(3376, 2275, 'MAIN_APPLICANT', 'S7700076A', 'DEMO APPLICANT 076', 'Self', '1992-04-20', 'Citizen', 'Single', '+65 81000076', 'demo076@example.com', 11000.00, '2026-03-23 09:06:00', '2026-03-23 09:16:00'),
(3377, 2276, 'MAIN_APPLICANT', 'S7700077A', 'DEMO APPLICANT 077', 'Self', '1993-05-21', 'Citizen', 'Single', '+65 81000077', 'demo077@example.com', 11000.00, '2026-03-23 09:07:00', '2026-03-23 09:17:00'),
(3378, 2277, 'MAIN_APPLICANT', 'S7700078A', 'DEMO APPLICANT 078', 'Self', '1994-06-22', 'Citizen', 'Single', '+65 81000078', 'demo078@example.com', 11000.00, '2026-03-23 09:08:00', '2026-03-23 09:18:00'),
(3379, 2278, 'MAIN_APPLICANT', 'S7700079A', 'DEMO APPLICANT 079', 'Self', '1995-07-23', 'Citizen', 'Single', '+65 81000079', 'demo079@example.com', 11000.00, '2026-03-23 09:09:00', '2026-03-23 09:19:00'),
(3380, 2279, 'MAIN_APPLICANT', 'S7700080A', 'DEMO APPLICANT 080', 'Self', '1986-08-24', 'Citizen', 'Single', '+65 81000080', 'demo080@example.com', 11000.00, '2026-03-23 09:10:00', '2026-03-23 09:20:00'),
(3381, 2280, 'MAIN_APPLICANT', 'S7700081A', 'DEMO APPLICANT 081', 'Self', '1987-09-25', 'Citizen', 'Single', '+65 81000081', 'demo081@example.com', 11000.00, '2026-03-23 09:11:00', '2026-03-23 09:21:00'),
(3382, 2281, 'MAIN_APPLICANT', 'S7700082A', 'DEMO APPLICANT 082', 'Self', '1988-10-26', 'Citizen', 'Single', '+65 81000082', 'demo082@example.com', 11000.00, '2026-03-23 09:12:00', '2026-03-23 09:22:00'),
(3383, 2282, 'MAIN_APPLICANT', 'S7700083A', 'DEMO APPLICANT 083', 'Self', '1989-11-27', 'Citizen', 'Single', '+65 81000083', 'demo083@example.com', 11000.00, '2026-03-23 09:13:00', '2026-03-23 09:23:00'),
(3384, 2283, 'MAIN_APPLICANT', 'S7700084A', 'DEMO APPLICANT 084', 'Self', '1990-12-28', 'Citizen', 'Single', '+65 81000084', 'demo084@example.com', 11000.00, '2026-03-23 09:14:00', '2026-03-23 09:24:00'),
(3385, 2284, 'MAIN_APPLICANT', 'S7700085A', 'DEMO APPLICANT 085', 'Self', '1991-01-01', 'Citizen', 'Single', '+65 81000085', 'demo085@example.com', 11000.00, '2026-03-23 09:15:00', '2026-03-23 09:25:00'),
(3386, 2285, 'MAIN_APPLICANT', 'S7700086A', 'DEMO APPLICANT 086', 'Self', '1992-02-02', 'Citizen', 'Single', '+65 81000086', 'demo086@example.com', 11000.00, '2026-03-23 09:16:00', '2026-03-23 09:26:00'),
(3387, 2286, 'MAIN_APPLICANT', 'S7700087A', 'DEMO APPLICANT 087', 'Self', '1993-03-03', 'Citizen', 'Single', '+65 81000087', 'demo087@example.com', 11000.00, '2026-03-23 09:17:00', '2026-03-23 09:27:00'),
(3388, 2287, 'MAIN_APPLICANT', 'S7700088A', 'DEMO APPLICANT 088', 'Self', '1994-04-04', 'Citizen', 'Single', '+65 81000088', 'demo088@example.com', 11000.00, '2026-03-23 09:18:00', '2026-03-23 09:28:00'),
(3389, 2288, 'MAIN_APPLICANT', 'S7700089A', 'DEMO APPLICANT 089', 'Self', '1995-05-05', 'Citizen', 'Single', '+65 81000089', 'demo089@example.com', 11000.00, '2026-03-23 09:19:00', '2026-03-23 09:29:00'),
(3390, 2289, 'MAIN_APPLICANT', 'S7700090A', 'DEMO APPLICANT 090', 'Self', '1986-06-06', 'Citizen', 'Single', '+65 81000090', 'demo090@example.com', 11000.00, '2026-03-23 09:20:00', '2026-03-23 09:30:00'),
(3391, 2290, 'MAIN_APPLICANT', 'S7700091A', 'DEMO APPLICANT 091', 'Self', '1987-07-07', 'Citizen', 'Single', '+65 81000091', 'demo091@example.com', 11000.00, '2026-03-23 09:21:00', '2026-03-23 09:31:00'),
(3392, 2291, 'MAIN_APPLICANT', 'S7700092A', 'DEMO APPLICANT 092', 'Self', '1988-08-08', 'Citizen', 'Single', '+65 81000092', 'demo092@example.com', 11000.00, '2026-03-23 09:22:00', '2026-03-23 09:32:00'),
(3393, 2292, 'MAIN_APPLICANT', 'S7700093A', 'DEMO APPLICANT 093', 'Self', '1989-09-09', 'Citizen', 'Single', '+65 81000093', 'demo093@example.com', 11000.00, '2026-03-23 09:23:00', '2026-03-23 09:33:00'),
(3394, 2293, 'MAIN_APPLICANT', 'S7700094A', 'DEMO APPLICANT 094', 'Self', '1990-10-10', 'Citizen', 'Single', '+65 81000094', 'demo094@example.com', 11000.00, '2026-03-23 09:24:00', '2026-03-23 09:34:00'),
(3395, 2294, 'MAIN_APPLICANT', 'S7700095A', 'DEMO APPLICANT 095', 'Self', '1991-11-11', 'Citizen', 'Single', '+65 81000095', 'demo095@example.com', 11000.00, '2026-03-23 09:25:00', '2026-03-23 09:35:00'),
(3396, 2295, 'MAIN_APPLICANT', 'S7700096A', 'DEMO APPLICANT 096', 'Self', '1992-12-12', 'Citizen', 'Single', '+65 81000096', 'demo096@example.com', 11000.00, '2026-03-23 09:26:00', '2026-03-23 09:36:00'),
(3397, 2296, 'MAIN_APPLICANT', 'S7700097A', 'DEMO APPLICANT 097', 'Self', '1993-01-13', 'Citizen', 'Single', '+65 81000097', 'demo097@example.com', 11000.00, '2026-03-23 09:27:00', '2026-03-23 09:37:00'),
(3398, 2297, 'MAIN_APPLICANT', 'S7700098A', 'DEMO APPLICANT 098', 'Self', '1994-02-14', 'Citizen', 'Single', '+65 81000098', 'demo098@example.com', 11000.00, '2026-03-23 09:28:00', '2026-03-23 09:38:00'),
(3399, 2298, 'MAIN_APPLICANT', 'S7700099A', 'DEMO APPLICANT 099', 'Self', '1995-03-15', 'Citizen', 'Single', '+65 81000099', 'demo099@example.com', 11000.00, '2026-03-23 09:29:00', '2026-03-23 09:39:00'),
(3400, 2299, 'MAIN_APPLICANT', 'S7700100A', 'DEMO APPLICANT 100', 'Self', '1986-04-16', 'Citizen', 'Single', '+65 81000100', 'demo100@example.com', 11000.00, '2026-03-23 09:30:00', '2026-03-23 09:40:00');
-- DEMO BULK BALLOT DATA END
