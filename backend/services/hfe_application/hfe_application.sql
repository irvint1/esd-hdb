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
    (201, 'S9912364H', 'VENKATA NARASIMHA RAJUVARIPET S/O ABHAYANANDA', NULL, NULL, 3056.50, 'ELIGIBLE', '2-Room Flexi', 'Single Singapore Citizen (SSC) Scheme', 135000.00, 55000.00, '2026-04-01', '2027-03-31'),
    (202, 'S9812381D', 'TAN HENG HUAT', 'G1612350T', 'JENNY LIM WAI FOOK', 9866.67, 'ELIGIBLE', '4-Room, 5-Room', 'Public Scheme (Married Couple)', 550000.00, 80000.00, '2026-04-01', '2027-03-31'),
    (203, 'S9912374E', 'TIMOTHY TAN CHENG GUAN', 'G1612350T', 'JENNY LIM WAI FOOK', 10925.00, 'INELIGIBLE', '3-Room', 'Public Scheme (Married Couple)', 550000.00, 80000.00, '2026-04-01', '2027-03-31')
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
