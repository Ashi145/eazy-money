import sqlite3
import datetime
from flask import Flask, jsonify, request
from flask_cors import CORS
from googleapiclient.discovery import build

app = Flask(__name__)
CORS(app)

# --- CONFIGURATION ---
# PASTE YOUR YOUTUBE DATA API KEY HERE
YOUTUBE_API_KEY = 'AIzaSyAsW-5rxfwxXbSD1SJ5xbX2jiQGjgWRw04' 
CHANNEL_ID = 'UCm8g3HVApSWOLrXm-Pa8thw'
DAILY_VIDEO_LIMIT = 5

# --- DATABASE SETUP ---
def init_db():
    conn = sqlite3.connect('eazymoney.db')
    c = conn.cursor()
    
    # Users Table
    c.execute('''CREATE TABLE IF NOT EXISTS users (
        user_id TEXT PRIMARY KEY,
        points INTEGER DEFAULT 0,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    # Task Tracking Table (Prevents double watching)
    c.execute('''CREATE TABLE IF NOT EXISTS task_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT,
        video_id TEXT,
        completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )''')
    
    conn.commit()
    conn.close()

init_db()

# --- YOUTUBE API FETCH ---
def get_channel_videos():
    try:
        youtube = build('youtube', 'v3', developerKey=YOUTUBE_API_KEY)
        
        # Get Uploads Playlist ID
        request = youtube.channels().list(part='contentDetails', id=CHANNEL_ID)
        response = request.execute()
        uploads_id = response['items'][0]['contentDetails']['relatedPlaylists']['uploads']
        
        # Get Videos from Playlist
        request = youtube.playlistItems().list(
            part='snippet', 
            playlistId=uploads_id, 
            maxResults=10 # Fetch last 10 videos
        )
        response = request.execute()
        
        videos = []
        for item in response['items']:
            video_data = {
                'id': item['snippet']['resourceId']['videoId'],
                'title': item['snippet']['title'],
                'thumbnail': item['snippet']['thumbnails']['medium']['url']
            }
            videos.append(video_data)
        return videos
    except Exception as e:
        print("YouTube API Error:", e)
        return []

# --- ROUTES ---

@app.route('/api/videos', methods=['GET'])
def get_videos():
    videos = get_channel_videos()
    user_id = request.args.get('user_id')
    
    conn = sqlite3.connect('eazymoney.db')
    c = conn.cursor()
    
    # Calculate Watched Today
    today = datetime.date.today()
    c.execute("SELECT COUNT(*) FROM task_history WHERE user_id=? AND DATE(completed_at)=?", (user_id, today))
    count = c.fetchone()[0]
    
    # Logic: If they watched 5, return empty list (or mark others as locked)
    remaining = DAILY_VIDEO_LIMIT - count
    if remaining <= 0:
        conn.close()
        return jsonify({"videos": [], "message": "Daily limit reached!"})
    
    conn.close()
    return jsonify({"videos": videos, "remaining": remaining})

@app.route('/api/user_data', methods=['GET'])
def get_user_data():
    user_id = request.args.get('user_id')
    conn = sqlite3.connect('eazymoney.db')
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if not row:
        c.execute("INSERT INTO users (user_id) VALUES (?)", (user_id,))
        conn.commit()
        points = 0
    else:
        points = row[0]
        
    # Get today's count for UI
    today = datetime.date.today()
    c.execute("SELECT COUNT(*) FROM task_history WHERE user_id=? AND DATE(completed_at)=?", (user_id, today))
    watched_today = c.fetchone()[0]
    
    conn.close()
    return jsonify({
        "points": points, 
        "watched_today": watched_today, 
        "limit": DAILY_VIDEO_LIMIT
    })

@app.route('/api/earn_video', methods=['POST'])
def earn_video():
    data = request.json
    user_id = data.get('user_id')
    video_id = data.get('video_id')
    
    conn = sqlite3.connect('eazymoney.db')
    c = conn.cursor()
    
    # Check limit
    today = datetime.date.today()
    c.execute("SELECT COUNT(*) FROM task_history WHERE user_id=? AND DATE(completed_at)=?", (user_id, today))
    watched_today = c.fetchone()[0]
    
    if watched_today >= DAILY_VIDEO_LIMIT:
        conn.close()
        return jsonify({"success": False, "message": "Daily limit of 5 videos reached!"})
    
    # Check if already watched this specific video
    c.execute("SELECT * FROM task_history WHERE user_id=? AND video_id=?", (user_id, video_id))
    if c.fetchone():
        conn.close()
        return jsonify({"success": False, "message": "Video already watched!"})
    
    # Award Points
    c.execute("UPDATE users SET points = points + 4 WHERE user_id=?", (user_id,))
    c.execute("INSERT INTO task_history (user_id, video_id) VALUES (?, ?)", (user_id, video_id))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "+4 Points Added!"})

@app.route('/api/withdraw', methods=['POST'])
def withdraw():
    data = request.json
    user_id = data.get('user_id')
    
    conn = sqlite3.connect('eazymoney.db')
    c = conn.cursor()
    c.execute("SELECT points FROM users WHERE user_id=?", (user_id,))
    row = c.fetchone()
    
    if not row or row[0] < 100:
        conn.close()
        return jsonify({"success": False, "message": "Need 100 points to withdraw."})
    
    # Reset points
    c.execute("UPDATE users SET points = 0 WHERE user_id=?", (user_id,))
    conn.commit()
    conn.close()
    
    return jsonify({"success": True, "message": "Withdrawal Request Sent!"})

if __name__ == '__main__':
    print("Server running on http://127.0.0.1:5000")
    app.run(debug=True, port=5000)