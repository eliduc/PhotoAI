# PhotoSuite — AI-Powered Photo Management & Cataloging Toolkit

<!--- A comprehensive suite of tools for detecting, recognizing, and cataloging people and dogs in photographs, with AI-driven description generation and robust database management utilities. -->

```
🖼️ Photo Processing | 🤖 AI Descriptions | 🗄️ Database Management | 🐩 Dog Recognition
```
</p><p>
PhotoSuite is a powerful, integrated collection of Python-based GUI applications designed for advanced photo management. It leverages modern machine learning models to automatically detect and identify people and dogs in your photo collection. The suite also features LLM-powered tools to generate descriptive metadata and rename files intelligently.
</p><p>
All tools are unified under a single, multilingual launcher for a seamless user experience.
</p><p>
---

## 💫 Key Features
</p><p>
- <b>Unified Launcher</b>: Start all suite components from a single, user-friendly interface with smooth animations. [cite: 2]
</p><p>
- <b>Multi-Object Detection</b>: Automatically detects people (using <b>YOLOv8</b>) and dogs (using <b>Torchvision's Faster R-CNN</b>). [cite: 5, 11]
</p><p>
- <b>Face Recognition</b>: Recognizes faces using the <code>face_recognition</code> library, with options for fast (HOG) or accurate (CNN) models. [cite: 5, 11]
</p><p>
- <b>Dog Breed Classification</b>: Identifies dog breeds using a <b>DenseNet-121</b> model. [cite: 5, 11]
</p><p>
- <b>AI Description Generation</b>: Connects to <b>OpenAI (GPT-4o), Anthropic (Claude 3 Haiku), or Google (Gemini 1.5 Flash)</b> to generate short and long descriptions for your photos. [cite: 1]
</p><p>
- <b>Intelligent File Renaming</b>: Automatically renames photo files based on AI-generated descriptions. [cite: 1]
</p><p>
- <b>Comprehensive Database Tools</b>: Includes a DB viewer, a cleaner for merging duplicates, a face vector updater, and an ID generator for unknown entities. [cite: 3, 4, 10, 12]
</p><p>
- <b>Multilingual Support</b>: Most modules support English (EN), Russian (RU), and Italian (IT). [cite: 3, 4, 11]
</p><p>
---

## 🛠️ Suite Components
</p><p>
The toolkit is composed of several specialized applications, all accessible from the main launcher.
</p><p>
| Application | Filename | Purpose |
| --- | --- | --- |
| <b>PhotoSuite Launcher</b> | <code>PhotoSuiteLauncher.py</code> | A modern, multilingual launchpad for all other utilities. [cite: 2] |
| <b>Face Detection</b> | <code>FaceDetection.py</code> | The core application for scanning photos, recognizing faces and dogs, and cataloging them in a database. [cite: 11] |
| <b>Face DB Viewer</b> | <code>FaceDBViewer.py</code> | A powerful tool to browse, search, and edit the recognition database. [cite: 12] |
| <b>AI Description Generator</b> | <code>AIPhotoDescriptionGenerator.py</code> | Generates photo descriptions using an LLM and renames files. [cite: 1] |
| <b>Face DB Cleaner</b> | <code>FaceDB_Cleaner.py</code> | Finds and merges duplicate people, dogs, and photos in the database. [cite: 3] |
| <b>Face Vector Updater</b> | <code>FaceVectorUpdater.py</code> | Analyzes, re-computes, and optimizes face vectors for better recognition accuracy. [cite: 4] |
| <b>NA to ID</b> | <code>NA-to-ID.py</code> | A utility to generate unique database entries for all unidentified detections. [cite: 10] |
</p><p>
---

## 🚀 Setup & Installation
</p><p>
1. <b>Clone the Repository</b>:
   ```bash
   git clone [your-repository-url]
   cd PhotoSuite
   ```
</p><p>
2. <b>Install Dependencies</b>:
   It's highly recommended to use a virtual environment.
   ```bash
   python -m venv venv
   source venv/bin/activate # On Windows, use: venv\Scripts\activate
   pip install -r requirements.txt
   ```
   * The <code>requirements.txt</code> should include: <code>Pillow</code>, <code>opencv-python</code>, <code>numpy</code>, <code>face_recognition</code>, <code>ultralytics</code>, <code>torch</code>, <code>torchvision</code>, <code>openai</code>, <code>anthropic</code>, <code>google-generativeai</code>, <code>imagehash</code>.
</p><p>
3. <b>Configure AI Services</b> (Optional):
   To use the <code>AIPhotoDescriptionGenerator</code>, create a file named <code>keys-ai.ini</code> in the root directory with your API keys: [cite: 1]
   ```ini
   [Keys]
   OpenAI = your_openai_api_key
   ANTHROPIC = your_anthropic_api_key
   GEMINI = your_google_gemini_api_key
   ```
</p><p>
---

## 🎊 How to Use
</p><p>
The entire suite is designed to be run from the central launcher.
</p><p>
1. <b>Start the Launcher</b>:
   ```bash
   python PhotoSuiteLauncher.py
   ```
    The launcher provides a modern, multilingual interface to access all the tools. [cite: 2]*
</p><p>
2. <b>Select a Module</b>:
   Click on any of the tiles to start the corresponding application. For example, click on <b>Photo Processing</b> to launch <code>FaceDetection.py</code>.
</p><p>
3. <b>Typical Workflow</b>:
   a. Use <b>Face Detection</b> to scan your photo directories and create/populate a <code>.db</code> database file.
   b. Use the <b>Face DB Viewer</b> to browse the results and manually correct any misidentifications.
   c. Run the <b>AI Description Generator</b> on the same database to add metadata and rename files.
   d. Periodically use the <b>Face DB Cleaner</b> and <b>Face Vector Updater</b> to maintain database health and improve recognition accuracy.
</p><p>
---

## 📒 Database Schema
</p><p>
All tools in the suite operate on a shared <b>SQLite</b> database schema. When you run the <code>FaceDetection.py</code> module for the first time, it will prompt you to create a new database file. This file will contain several tables to store information about images, people, dogs, and their respective detections and encodings. [cite: 5, 11]
</p><p>
The key tables include:
- <code>images</code>: Stores metadata about each processed photo, including AI-generated descriptions. [cite: 1, 5, 11]
</p><p>
- <code>persons</code>: A catalog of all unique individuals (known and unknown). [cite: 5, 11]
</p><p>
- <code>dogs</code>: A catalog of all unique dogs. [cite: 5, 11]
</p><p>
- <code>person_detections</code> & <code>dog_detections</code>: Link tables that store the location (bounding box) of each detection within an image. [cite: 5, 11]
</p><p>
- <code>face_encodings</code>: Stores the 128-d face vectors used for recognizing individuals. [cite: 5, 11]
</p><p>
* The utilities automatically handle schema creation and updates (e.g., adding columns for AI descriptions). [cite: 1, 5, 11]*