CREATE DATABASE IF NOT EXISTS fire_incident_db
  CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
USE fire_incident_db;

CREATE TABLE IF NOT EXISTS users (
  id INT AUTO_INCREMENT PRIMARY KEY,
  username VARCHAR(80) NOT NULL UNIQUE,
  password_hash VARCHAR(255) NOT NULL,
  role ENUM('admin') NOT NULL DEFAULT 'admin',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS incidents (
  id INT AUTO_INCREMENT PRIMARY KEY,
  reporter_name VARCHAR(120) NOT NULL,
  phone VARCHAR(30) NOT NULL,
  location VARCHAR(255) NOT NULL,
  incident_type VARCHAR(80) NOT NULL,
  description TEXT NOT NULL,
  status ENUM('Pending','Under Review','Assigned','Resolved','Closed')
    NOT NULL DEFAULT 'Pending',
  created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
  updated_at TIMESTAMP NULL DEFAULT NULL
);
