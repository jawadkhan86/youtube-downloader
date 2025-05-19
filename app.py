from flask import Flask, render_template, request, send_file, jsonify
import yt_dlp
import os
import uuid
import threading
import time
import re

app = Flask(__name__)
app.secret_key = 'smartmotionapp-downloader-key'

DOWNLOAD_FOLDER = os.path.join(os.getcwd(), "downloads")
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# Store progress
progress_store = {}

# Clean file title
def clean_filename(title):
    title = re.sub(r'[\\/*?:"<>|]', '', title)
    title = re.sub(r'\s+', ' ', title).strip()
    return title

# Delete old files
def delete_file_later(filepath, delay=600):
    def delayed_delete():
        time.sleep(delay)
        if os.path.exists(filepath):
            try:
                os.remove(filepath)
                print(f"✅ Deleted file after {delay}s: {filepath}")
            except Exception as e:
                print(f"⚠️ Could not delete file: {filepath} – {e}")
    threading.Thread(target=delayed_delete).start()

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/download', methods=['POST'])
def download():
    url = request.form.get('url')
    quality = request.form.get('quality')
    is_audio = request.form.get('audio') == 'on'

    if not url:
        return jsonify({'status': 'error', 'message': 'URL is missing.'})

    uid = str(uuid.uuid4())
    progress_store[uid] = {'progress': 0, 'status': 'starting'}

    def progress_hook(d):
        if d['status'] == 'downloading':
            downloaded = d.get('downloaded_bytes', 0)
            total = d.get('total_bytes') or d.get('total_bytes_estimate')
            if total:
                percent = int(downloaded * 100 / total)
                progress_store[uid] = {
                    'progress': percent,
                    'downloaded': f"{downloaded / 1024 / 1024:.1f} MB",
                    'total': f"{total / 1024 / 1024:.1f} MB",
                    'status': 'downloading'
                }

    def start_download():
        try:
            ydl_opts = {
                'noplaylist': True,
                'progress_hooks': [progress_hook],
                'quiet': True
            }

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', f"video-{uid}")
                safe_title = clean_filename(title)
                final_title = f"smartmotionapp.com - {safe_title}"
                ext = 'mp3' if is_audio else 'mp4'
                outtmpl = os.path.join(DOWNLOAD_FOLDER, f"{final_title}.%(ext)s")
                ydl_opts['outtmpl'] = outtmpl

                if is_audio:
                    ydl_opts['format'] = 'bestaudio/best'
                    ydl_opts['postprocessors'] = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3',
                        'preferredquality': '192',
                    }]
                else:
                    format_map = {
                        'high': 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]',
                        'medium': 'best[height<=480][ext=mp4]/best',
                        'low': 'best[height<=360][ext=mp4]/best'
                    }
                    ydl_opts['format'] = format_map.get(quality, 'best')

                with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                    final_info = ydl.extract_info(url)
                    filename = ydl.prepare_filename(final_info)
                    if is_audio:
                        filename = os.path.splitext(filename)[0] + '.mp3'

                    progress_store[uid]['status'] = 'finished'
                    progress_store[uid]['filename'] = filename
                    progress_store[uid]['title'] = final_info.get('title', 'Downloaded Video')
                    progress_store[uid]['thumbnail'] = final_info.get('thumbnail', '')

                    delete_file_later(filename)

        except Exception as e:
            progress_store[uid] = {
                'status': 'error',
                'message': str(e)
            }

    threading.Thread(target=start_download).start()
    return jsonify({'status': 'started', 'id': uid})

@app.route('/progress/<uid>')
def progress(uid):
    return jsonify(progress_store.get(uid, {'status': 'unknown'}))

@app.route('/download_file/<uid>')
def download_file(uid):
    file_info = progress_store.get(uid)
    if file_info and file_info.get('status') == 'finished':
        file_path = file_info['filename']
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True)
        else:
            return "File not found", 404
    return "File not ready", 400

if __name__ == '__main__':
    app.run(debug=True)
