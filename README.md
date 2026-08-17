# 🎓 Automated Attendance System

An AI-powered **Automated Attendance System** designed to simplify student attendance management using **Face Recognition, OpenCV, Flask, and SQLite**.

The system allows administrators/teachers to register students, capture their facial data, recognize registered students through a camera, and automatically record attendance.

---

## 📌 Project Overview

Traditional attendance systems require teachers to manually mark attendance, which can be time-consuming and may lead to errors.

This project provides an automated solution using **facial recognition technology**.

When a registered student's face is detected through the camera, the system identifies the student and can record their attendance automatically.

### 🎯 Main Goal

To develop a simple, reliable, and user-friendly attendance system that reduces manual work and improves attendance management.

---

## 🎯 Problem Statement

Manual attendance systems have several limitations:

* ⏱️ Time-consuming attendance process
* ❌ Possibility of human errors
* 📝 Manual record maintenance
* 🔄 Difficult to manage large numbers of students
* 📊 Attendance reporting requires additional manual work

The proposed system addresses these problems using computer vision and automated attendance recording.

---

## 💡 Proposed Solution

The system uses **OpenCV-based face detection and recognition** to identify registered students.

### Basic workflow

```text
Student Registration
        ↓
Face Registration
        ↓
Face Model Training
        ↓
Camera Captures Face
        ↓
Face Detection
        ↓
Face Recognition
        ↓
Student Identification
        ↓
Attendance Recording
        ↓
Attendance Reports
```

---

# ⚙️ Features

### 👨‍🎓 Student Management

* Add new students
* Store student information
* View registered students
* Manage student records

### 📷 Face Registration

* Capture student's face using a camera
* Store facial training images locally
* Associate facial data with student ID

### 🧠 Face Recognition

* Detect faces using OpenCV
* Recognize registered students
* Identify student ID
* Display recognition confidence

### 📝 Automatic Attendance

* Identify students through camera
* Record attendance automatically
* Prevent unnecessary duplicate attendance entries

### 📊 Attendance Management

* Store attendance records
* Maintain date and time information
* Generate attendance information for future reporting

### 🌐 Web Dashboard

* Flask-based web interface
* Student management dashboard
* Simple and user-friendly interface

---

# 🧠 Technologies Used

| Technology | Purpose                        |
| ---------- | ------------------------------ |
| 🐍 Python  | Core programming language      |
| 🌐 Flask   | Web application framework      |
| 👁️ OpenCV | Face detection and recognition |
| 🗄️ SQLite | Database management            |
| HTML       | Web page structure             |
| CSS        | User interface styling         |
| JavaScript | Frontend interactions          |
| Git        | Version control                |
| GitHub     | Source code hosting            |

---

# 🏗️ System Architecture

```text
                   ┌──────────────────────┐
                   │       User / Admin   │
                   └──────────┬───────────┘
                              │
                              ▼
                   ┌──────────────────────┐
                   │    Flask Web App     │
                   └──────────┬───────────┘
                              │
             ┌────────────────┼────────────────┐
             │                │                │
             ▼                ▼                ▼
      Student Management  Face System     Attendance
             │                │                │
             │                ▼                │
             │          OpenCV Camera          │
             │                │                │
             │                ▼                │
             │        Face Detection           │
             │                │                │
             │                ▼                │
             │        Face Recognition         │
             │                │                │
             └────────────────┼────────────────┘
                              ▼
                    ┌──────────────────┐
                    │  SQLite Database │
                    └──────────────────┘
```

---

# 📂 Project Structure

```text
Automated-Attendance-System/
│
├── ai/
│   └── face_detection.py
│
├── templates/
│   ├── dashboard.html
│   └── ...
│
├── static/
│   └── ...
│
├── data/
│   └── ...
│
├── app.py
├── attendance.py
├── database.py
├── live_recognition.py
├── train_faces.py
├── test_recognition.py
├── requirements.txt
├── .gitignore
└── README.md
```

> The exact files may change as the project is further developed.

---

# 🚀 Installation

## 1. Clone the Repository

```bash
git clone https://github.com/sriguganeswar333-pixel/Automated-Attendance-System.git
```

```bash
cd Automated-Attendance-System
```

---

## 2. Create a Virtual Environment

### Windows

```bash
python -m venv venv
```

Activate it:

```bash
venv\Scripts\activate
```

---

## 3. Install Dependencies

```bash
pip install -r requirements.txt
```

---

# ▶️ Running the Application

Start the Flask application:

```bash
python app.py
```

Then open the local Flask address shown in the terminal, typically:

```text
http://127.0.0.1:5000
```

---

# 📷 Face Registration Workflow

The face registration process follows these steps:

```text
Select Student
      ↓
Open Camera
      ↓
Capture Face Images
      ↓
Store Training Images
      ↓
Train Face Recognition Model
      ↓
Save Trained Model
```

The trained face model is then used during live recognition.

---

# 🧠 Face Recognition Workflow

During live recognition:

```text
Camera
  ↓
Capture Frame
  ↓
Detect Face
  ↓
Extract Facial Information
  ↓
Compare With Trained Model
  ↓
Identify Student
  ↓
Display Student ID
  ↓
Record Attendance
```

---

# 📊 Attendance Workflow

```text
Student Appears Before Camera
              ↓
        Face Detected
              ↓
       Face Recognized
              ↓
       Student Identified
              ↓
       Check Attendance
              ↓
      Record Date & Time
```

This allows attendance to be recorded without manually entering the student's details.

---

# 🔐 Privacy & Biometric Data

This project involves facial recognition and therefore requires responsible handling of biometric-related data.

For development and demonstration purposes:

* Student facial images should not be uploaded to the public repository.
* Trained face-recognition model files should not be committed to GitHub.
* Attendance database files should remain local.
* Personal student information should be handled securely.
* Access to facial data should be restricted to authorized users.

The repository intentionally excludes sensitive/generated files through `.gitignore`.

### 🚫 Files intentionally excluded

```text
attendance.db
venv/
face_model.yml
student face images
other generated biometric data
```

---

# 🛡️ GitHub Security

The project uses `.gitignore` to prevent unnecessary or sensitive local files from being uploaded.

Example:

```text
venv/
__pycache__/
*.pyc
attendance.db
data/faces/
*.yml
.env
```

> Make sure your actual `.gitignore` matches the files you want to keep private.

---

# 🔮 Future Enhancements

Planned improvements include:

* 📊 Advanced attendance reports
* 📅 Daily/monthly attendance filtering
* 📈 Attendance percentage calculation
* 📥 Export attendance to CSV/Excel
* 👨‍🏫 Teacher/admin authentication
* 🔔 Attendance notifications
* ☁️ Cloud database integration
* 📱 Mobile-friendly interface
* 🤖 Improved face recognition accuracy
* 🧑‍🎓 Student profile management
* 📷 Better camera and lighting handling
* 🔐 Enhanced biometric-data security

---

# 🎓 Educational Purpose

This project demonstrates the practical integration of:

* Artificial Intelligence
* Computer Vision
* Face Recognition
* Python Programming
* Web Development
* Database Management
* Software Engineering
* Git & GitHub

It is developed as an academic/project implementation to demonstrate how AI and computer vision can be applied to automate real-world administrative tasks.

---

# 👨‍💻 Author

**SRIGUGANESWAR.C**

B.Tech – Artificial Intelligence & Data Science

Panimalar Engineering College

---

# ⭐ Project

**Automated Attendance System**

Built using:

```text
Python + Flask + OpenCV + SQLite
```

If you find this project useful, consider giving the repository a ⭐ on GitHub.

---

## 📜 License

This project is intended primarily for educational and academic purposes.
