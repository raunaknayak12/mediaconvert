# MediaConvert

A media URL converter web application. Convert YouTube, Instagram, TikTok, and other media URLs to MP3 or MP4 format.

Built with Flask, yt-dlp, SQLite, and Docker.

## Features

- Convert media URLs to MP3 (audio) or MP4 (video)
- Real-time progress tracking
- Conversion history with Re-Convert and Delete actions
- Secure: files are streamed directly and never stored on the server
- Dockerized for easy deployment

## Project Structure

```
├── app.py              # Flask backend
├── requirements.txt    # Python dependencies
├── Dockerfile          # Container configuration
├── render.yaml         # Render deployment blueprint
├── .dockerignore       # Docker build exclusions
├── .gitignore          # Git exclusions
├── templates/
│   └── index.html      # Frontend HTML
└── static/
    ├── css/style.css   # Styles
    └── js/app.js       # Frontend logic
```

## Run Locally

```bash
pip install -r requirements.txt
python app.py
```

Open http://localhost:5000

## Run with Docker

```bash
docker build -t mediaconvert .
docker run -p 5000:5000 mediaconvert
```

Open http://localhost:5000

## Deploy to Render (Step-by-Step)

### Step 1: Install Git

Download and install Git from https://git-scm.com/downloads

After installing, restart your terminal and verify:

```bash
git --version
```

### Step 2: Create a GitHub Repository

1. Go to https://github.com/new
2. Name it `mediaconvert` (or any name you like)
3. Set it to **Public**
4. Do NOT add a README or .gitignore (we already have them)
5. Click **Create repository**

### Step 3: Push Your Code to GitHub

Open a terminal in this project folder and run:

```bash
git init
git add .
git commit -m "Initial commit"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/mediaconvert.git
git push -u origin main
```

Replace `YOUR_USERNAME` with your GitHub username.

If prompted, enter your GitHub credentials. For password, use a Personal Access Token (generate one at Settings > Developer Settings > Personal Access Tokens on GitHub).

### Step 4: Deploy on Render

1. Go to https://dashboard.render.com
2. Click **New** > **Web Service**
3. Connect your GitHub account if you haven't already
4. Select the `mediaconvert` repository
5. Configure:
   - **Name**: `mediaconvert`
   - **Region**: Pick nearest (e.g., Frankfurt or Oregon)
   - **Runtime**: **Docker**
   - **Plan**: **Free**
6. Click **Deploy Web Service**

Render will:
- Pull your code from GitHub
- Build the Docker image using your Dockerfile
- Install Python, pip dependencies, and ffmpeg
- Start the app with Gunicorn

The build takes 3-5 minutes. Once done, Render gives you a public URL like:
`https://mediaconvert-xxxx.onrender.com`

### Step 5: Verify

Open the Render URL in your browser. The app should be live and working.

## Deploy to AWS EC2

### Prerequisites

- AWS account
- EC2 instance (Amazon Linux 2023, t2.micro)
- Security Group open on ports 22, 80, 5000

### Steps

SSH into your EC2 instance:

```bash
ssh -i your-key.pem ec2-user@YOUR_EC2_IP
```

Install dependencies:

```bash
sudo dnf update -y
sudo dnf install python3 python3-pip ffmpeg git -y
```

Clone your repo:

```bash
git clone https://github.com/YOUR_USERNAME/mediaconvert.git
cd mediaconvert
```

Install Python packages:

```bash
pip3 install -r requirements.txt
```

Run with Gunicorn:

```bash
gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 300 app:app &
```

The app is now live at `http://YOUR_EC2_IP:5000`.

### Run as a System Service (optional)

Create `/etc/systemd/system/mediaconvert.service`:

```ini
[Unit]
Description=MediaConvert
After=network.target

[Service]
User=ec2-user
WorkingDirectory=/home/ec2-user/mediaconvert
ExecStart=/usr/local/bin/gunicorn --bind 0.0.0.0:5000 --workers 2 --timeout 300 app:app
Restart=always

[Install]
WantedBy=multi-user.target
```

Then:

```bash
sudo systemctl daemon-reload
sudo systemctl enable mediaconvert
sudo systemctl start mediaconvert
```

## Tech Stack

- **Backend**: Python Flask
- **Conversion**: yt-dlp + ffmpeg
- **Database**: SQLite
- **Server**: Gunicorn
- **Container**: Docker
- **Deployment**: Render / AWS EC2
