-- Document Service Database
CREATE DATABASE IF NOT EXISTS documents;
USE documents;

CREATE TABLE IF NOT EXISTS documents (
    document_id BIGINT AUTO_INCREMENT PRIMARY KEY,
    application_id BIGINT NOT NULL,
    document_type VARCHAR(20) NOT NULL,
    storage_path TEXT NOT NULL,
    status VARCHAR(20) NOT NULL,
    fields_json JSON DEFAULT NULL,
    uploaded_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);
