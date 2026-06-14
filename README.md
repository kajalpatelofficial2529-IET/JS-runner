# 🚀 JS-Engine: Ultimate Python-Based JavaScript Runtime

A high-performance, custom-built JavaScript execution engine built from scratch in Python for the **Hunder Hackathon 2.0**. 

## 🏆 Hackathon Project Details
- **Project Name:** JS-Engine (Custom Python Runtime)
- **Built For:** Hunder Hackathon 2.0
- **Objective:** To build a robust JavaScript runtime from scratch using Python without relying on pre-built JS execution engines.
- **Live Demo:** [https://js-runner-k35p.onrender.com/](https://js-runner-k35p.onrender.com/)

## 🌟 Technical Highlights
* **Core Architecture:** Custom AST Evaluator handling lexical scoping, closures, and variable memory via an `Environment` class.
* **Modern ES6+ Support:** Custom regex-based transpilation engine that natively converts Arrow Functions (`=>`), Exponentiation (`**`), and Spread Operators (`...`) to ES5-compatible Python-executable AST nodes.
* **Robust Callbacks:** Full native implementation of Array HOFs (`map`, `filter`, `reduce`, `find`) using Python callbacks.
* **Runtime Safety:** Integrated execution timeout (5s) and call-stack depth protection to prevent infinite loops and recursive crashes.
* **UI/UX:** Sleek, dark-themed developer-first interface built with Flask and TailwindCSS.

## 🛠️ Tech Stack
* **Backend:** Python 3 (Flask)
* **AST Parsing:** `pyjsparser`
* **Frontend:** TailwindCSS, Vanilla JavaScript, Fetch API

## ⚙️ Submission Requirements & Setup
### 1. Installation
Ensure Python 3 is installed. Clone the repository and run:
```bash
pip install flask pyjsparser gunicorn
