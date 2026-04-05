CREATE DATABASE IF NOT EXISTS hfe_applications;
USE hfe_applications;

CREATE TABLE IF NOT EXISTS hfe_application (
    hfe_application_id INT AUTO_INCREMENT PRIMARY KEY,
    main_applicant_nric VARCHAR(20) NOT NULL,
    main_applicant_name VARCHAR(255) NOT NULL,
    co_applicant_nric VARCHAR(20) DEFAULT NULL,
    co_applicant_name VARCHAR(255) DEFAULT NULL,
    total_household_income DECIMAL(12,2) DEFAULT NULL,
    assessment_outcome VARCHAR(255) NOT NULL,
    eligible_flat_types VARCHAR(255) NOT NULL,
    application_scheme VARCHAR(100) DEFAULT NULL,
    hdb_loan_ceiling DECIMAL(12,2) DEFAULT NULL,
    total_grants_eligible DECIMAL(12,2) DEFAULT NULL,
    date_of_issue DATE DEFAULT NULL,
    valid_until DATE DEFAULT NULL,
    created_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP
);

-- -----------------------------------------------------------------------
-- Six HFE records — one per PDF dummy variable persona.
--
-- Aaron Tan    : Single (SSC). Income $7,233/mo exceeds 4-Room SSC ceiling
--                of $7,000, so only 3-Room is approved.
-- Brenda Lim   : Single (SSC). Income $5,729/mo — eligible up to 4-Room.
-- Farid + Nurul: Married couple. Combined $9,050/mo — eligible up to 5-Room.
-- Jaya Singh   : Single (SSC). Self-employed $3,575/mo — eligible up to 3-Room.
-- Kevin + Elaine: Married couple. Combined $10,421/mo — eligible 4-Room, 5-Room.
-- Sam Yee      : HFE EXPIRED (valid until 30 Sep 2020). Used as the failing
--                demo scenario.
-- -----------------------------------------------------------------------
INSERT INTO hfe_application (
    hfe_application_id,
    main_applicant_nric,
    main_applicant_name,
    co_applicant_nric,
    co_applicant_name,
    total_household_income,
    assessment_outcome,
    eligible_flat_types,
    application_scheme,
    hdb_loan_ceiling,
    total_grants_eligible,
    date_of_issue,
    valid_until
) VALUES
-- 1. Aaron Tan Wei Ming (S8501234A) — Single, eligible 3-Room only
(
    1,
    'S8501234A',
    'AARON TAN WEI MING',
    NULL,
    NULL,
    7233.33,
    'ELIGIBLE',
    '3-Room',
    'Single Singapore Citizen (SSC) Scheme',
    180000.00,
    55000.00,
    '2025-01-01',
    '2025-09-30'
),
-- 2. Brenda Lim Siew Ling (S9102345B) — Single, eligible 2-Room Flexi to 4-Room
(
    2,
    'S9102345B',
    'BRENDA LIM SIEW LING',
    NULL,
    NULL,
    5729.17,
    'ELIGIBLE',
    '2-Room Flexi, 3-Room, 4-Room',
    'Single Singapore Citizen (SSC) Scheme',
    162000.00,
    55000.00,
    '2025-01-15',
    '2025-10-14'
),
-- 3. Farid Bin Ali (S9206789F) + Nurul Hanis (S9307890G) — Married, eligible 3-Room to 5-Room
(
    3,
    'S9206789F',
    'FARID BIN ALI',
    'S9307890G',
    'NURUL HANIS BINTE HASSAN',
    9050.00,
    'ELIGIBLE',
    '3-Room, 4-Room, 5-Room',
    'Public Scheme (Married Couple)',
    270000.00,
    140000.00,
    '2025-01-27',
    '2025-10-26'
),
-- 4. Jaya D/O Hardev Singh (S9300123J) — Single, self-employed, eligible 2-Room Flexi, 3-Room
(
    4,
    'S9300123J',
    'JAYA D/O HARDEV SINGH',
    NULL,
    NULL,
    3575.00,
    'ELIGIBLE',
    '2-Room Flexi, 3-Room',
    'Single Singapore Citizen (SSC) Scheme',
    135000.00,
    75000.00,
    '2025-02-10',
    '2025-11-09'
),
-- 5. Kevin Tan Wei Jian (S9701234K) + Elaine Koh Mei Ling (S8805678E) — Married, eligible 4-Room, 5-Room
(
    5,
    'S9701234K',
    'KEVIN TAN WEI JIAN',
    'S8805678E',
    'ELAINE KOH MEI LING',
    10420.83,
    'ELIGIBLE',
    '4-Room, 5-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    360000.00,
    100000.00,
    '2025-02-27',
    '2025-11-26'
),
-- 6. Sam Yee (S9812346F) — HFE EXPIRED (2020). Demo scenario for a failing eligibility check.
(
    6,
    'S9812346F',
    'SAM YEE',
    NULL,
    NULL,
    2673.70,
    'ELIGIBLE',
    '4-Room, 5-Room',
    'Public Scheme (Married Couple)',
    385000.00,
    130000.00,
    '2020-04-16',
    '2020-09-30'
),
-- 101. Scenario 1: Lena Ong Jia Hui + Sarah Lim Mei Yen — eligible for 3-Room
(
    101,
    'S9401234L',
    'LENA ONG JIA HUI',
    'S9601234S',
    'SARAH LIM MEI YEN',
    5500.00,
    'ELIGIBLE',
    '3-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    120000.00,
    55000.00,
    '2026-01-15',
    '2026-12-31'
),
-- 102. Scenario 2: Ryan Tan Jian Hui + Sarah Lim Mei Yen — Married couple, eligible for 4-Room and 5-Room
(
    102,
    'S9501234R',
    'RYAN TAN JIAN HUI',
    'S9601234S',
    'SARAH LIM MEI YEN',
    9800.00,
    'ELIGIBLE',
    '4-Room, 5-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    270000.00,
    80000.00,
    '2026-01-15',
    '2026-12-31'
),
-- 103. Scenario 3: Daniel Goh Wei Ming + Marcus Lim Cheng Wei — HFE valid but 3-Room ceiling will be exceeded
(
    103,
    'S8901234D',
    'DANIEL GOH WEI MING',
    'S9101234M',
    'MARCUS LIM CHENG WEI',
    8500.00,
    'ELIGIBLE (3-Room only)',
    '3-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    180000.00,
    35000.00,
    '2026-01-15',
    '2026-12-31'
),
-- 104. Scenario 4: Jasmine Tan Shu Min + Marcus Lim Cheng Wei — Married couple with expired HFE
(
    104,
    'S9001234J',
    'JASMINE TAN SHU MIN',
    'S9101234M',
    'MARCUS LIM CHENG WEI',
    11000.00,
    'ELIGIBLE',
    '4-Room, 5-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    270000.00,
    80000.00,
    '2023-11-15',
    '2024-06-30'
),
-- 105. Scenario 5: Wendy Chen Xin Hui + Ryan Tan Jian Hui — HFE does not allow 4-Room
(
    105,
    'S9201234W',
    'WENDY CHEN XIN HUI',
    'S9501234R',
    'RYAN TAN JIAN HUI',
    4200.00,
    'ELIGIBLE',
    '2-Room Flexi, 3-Room',
    'Public Scheme (Married Couple / Singapore Citizen)',
    135000.00,
    55000.00,
    '2026-01-15',
    '2026-12-31'
)
ON DUPLICATE KEY UPDATE
    main_applicant_name     = VALUES(main_applicant_name),
    co_applicant_nric       = VALUES(co_applicant_nric),
    co_applicant_name       = VALUES(co_applicant_name),
    total_household_income  = VALUES(total_household_income),
    assessment_outcome      = VALUES(assessment_outcome),
    eligible_flat_types     = VALUES(eligible_flat_types),
    application_scheme      = VALUES(application_scheme),
    hdb_loan_ceiling        = VALUES(hdb_loan_ceiling),
    total_grants_eligible   = VALUES(total_grants_eligible),
    date_of_issue           = VALUES(date_of_issue),
    valid_until             = VALUES(valid_until);
