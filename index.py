import json
import os
import re
import shutil
import subprocess
import tempfile
import traceback

from flask import Flask, request, jsonify

import imageio_ffmpeg

app = Flask(__name__)

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
YTDLP_PATH = shutil.which("yt-dlp")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")

HTML_PAGE = '''<!DOCTYPE html>
<html lang="ko">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>릴스 스크립트 추출기</title>
  <style>
    * { margin: 0; padding: 0; box-sizing: border-box; }
    body {
      font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
      background: #0a0a0a; color: #e0e0e0;
      min-height: 100vh; display: flex; align-items: center; justify-content: center;
    }
    .container { width: 100%%; max-width: 640px; padding: 24px; }
    h1 {
      font-size: 28px; font-weight: 700; text-align: center; margin-bottom: 8px;
      background: linear-gradient(135deg, #f09433, #e6683c, #dc2743, #cc2366, #bc1888);
      -webkit-background-clip: text; -webkit-text-fill-color: transparent;
    }
    .subtitle { text-align: center; color: #888; font-size: 14px; margin-bottom: 32px; }
    .session-box {
      background: #1a1a1a; border: 1px solid #333; border-radius: 12px;
      padding: 16px 20px; margin-bottom: 24px;
    }
    .session-box.ready { border-color: #4caf50; }
    .session-box h3 { font-size: 14px; font-weight: 600; margin-bottom: 10px; color: #ccc; }
    .session-steps { font-size: 12px; color: #888; line-height: 1.8; margin-bottom: 12px; }
    .session-steps code { background: #333; padding: 2px 6px; border-radius: 4px; color: #f09433; }
    .session-row { display: flex; gap: 8px; }
    .session-row input {
      flex: 1; padding: 10px 14px; border: 1px solid #333; border-radius: 8px;
      background: #111; color: #fff; font-size: 13px; outline: none; font-family: monospace;
    }
    .session-row input:focus { border-color: #dc2743; }
    .session-btn {
      padding: 10px 16px; border: none; border-radius: 8px;
      background: linear-gradient(135deg, #f09433, #dc2743);
      color: #fff; font-size: 13px; font-weight: 600; cursor: pointer; white-space: nowrap;
    }
    .session-msg { font-size: 12px; margin-top: 8px; }
    .session-msg.ok { color: #4caf50; }
    .input-group { display: flex; gap: 8px; margin-bottom: 24px; }
    input[type="text"] {
      flex: 1; padding: 14px 16px; border: 1px solid #333; border-radius: 12px;
      background: #1a1a1a; color: #fff; font-size: 15px; outline: none;
    }
    input[type="text"]:focus { border-color: #dc2743; }
    input[type="text"]::placeholder { color: #555; }
    button {
      padding: 14px 24px; border: none; border-radius: 12px;
      background: linear-gradient(135deg, #f09433, #dc2743);
      color: #fff; font-size: 15px; font-weight: 600; cursor: pointer; white-space: nowrap;
    }
    button:hover { opacity: 0.9; }
    button:disabled { opacity: 0.5; cursor: not-allowed; }
    .status { text-align: center; padding: 16px; color: #888; font-size: 14px; display: none; }
    .status.visible { display: block; }
    .spinner {
      display: inline-block; width: 16px; height: 16px;
      border: 2px solid #555; border-top-color: #dc2743; border-radius: 50%%;
      animation: spin 0.8s linear infinite; vertical-align: middle; margin-right: 8px;
    }
    @keyframes spin { to { transform: rotate(360deg); } }
    .result { display: none; background: #1a1a1a; border: 1px solid #333; border-radius: 12px; overflow: hidden; }
    .result.visible { display: block; }
    .result-header {
      display: flex; justify-content: space-between; align-items: center;
      padding: 16px 20px; border-bottom: 1px solid #333;
    }
    .result-header h2 { font-size: 16px; font-weight: 600; }
    .copy-btn { padding: 6px 14px; font-size: 13px; border-radius: 8px; background: #333; }
    .copy-btn:hover { background: #444; }
    .tab-bar { display: flex; border-bottom: 1px solid #333; }
    .tab {
      flex: 1; padding: 10px; text-align: center; font-size: 13px; color: #888;
      cursor: pointer; border-bottom: 2px solid transparent;
    }
    .tab.active { color: #fff; border-bottom-color: #dc2743; }
    .tab-content { display: none; padding: 20px; }
    .tab-content.active { display: block; }
    .full-text { font-size: 15px; line-height: 1.8; white-space: pre-wrap; word-break: break-word; }
    .segment { display: flex; gap: 12px; padding: 8px 0; border-bottom: 1px solid #1f1f1f; }
    .segment:last-child { border-bottom: none; }
    .timestamp { color: #dc2743; font-size: 12px; font-family: monospace; min-width: 90px; padding-top: 2px; }
    .segment-text { font-size: 14px; line-height: 1.6; }
    .error { text-align: center; padding: 16px; color: #ff4444; font-size: 14px; display: none; }
    .error.visible { display: block; }
  </style>
</head>
<body>
  <div class="container">
    <h1>릴스 스크립트 추출기</h1>
    <p class="subtitle">인스타그램 릴스 링크를 붙여넣으면 자동으로 스크립트를 추출합니다</p>
    <div class="session-box" id="sessionBox">
      <h3>인스타그램 세션 설정 (최초 1회)</h3>
      <div class="session-steps" id="sessionSteps">
        1. Chrome에서 <strong>instagram.com</strong> 접속 (로그인 상태)<br>
        2. <code>Cmd+Option+I</code> 또는 <code>F12</code> (개발자 도구) &rarr; <code>Application</code> 탭<br>
        3. 왼쪽 <code>Cookies</code> &rarr; <code>https://www.instagram.com</code><br>
        4. <code>sessionid</code>의 <strong>Value</strong> 복사<br>
      </div>
      <div class="session-row">
        <input type="text" id="sessionInput" placeholder="sessionid 값을 붙여넣으세요" />
        <button class="session-btn" onclick="saveSession()">저장</button>
      </div>
      <div class="session-msg" id="sessionMsg"></div>
    </div>
    <div class="input-group">
      <input type="text" id="urlInput" placeholder="https://www.instagram.com/reel/..." />
      <button id="submitBtn" onclick="handleSubmit()">추출하기</button>
    </div>
    <div class="status" id="status">
      <span class="spinner"></span>
      <span id="statusText">처리 중...</span>
    </div>
    <div class="error" id="error"></div>
    <div class="result" id="result">
      <div class="result-header">
        <h2>스크립트</h2>
        <button class="copy-btn" onclick="copyText()">복사하기</button>
      </div>
      <div class="tab-bar">
        <div class="tab active" onclick="switchTab('full')">전체 텍스트</div>
        <div class="tab" onclick="switchTab('segments')">타임라인</div>
      </div>
      <div class="tab-content active" id="tab-full">
        <div class="full-text" id="fullText"></div>
      </div>
      <div class="tab-content" id="tab-segments">
        <div id="segments"></div>
      </div>
    </div>
  </div>
  <script>
    const sessionBox = document.getElementById('sessionBox');
    const sessionMsg = document.getElementById('sessionMsg');
    const sessionSteps = document.getElementById('sessionSteps');
    const saved = localStorage.getItem('ig_sessionid');
    if (saved) setReady();
    function saveSession() {
      const sid = document.getElementById('sessionInput').value.trim();
      if (!sid) return;
      localStorage.setItem('ig_sessionid', sid);
      setReady();
    }
    function setReady() {
      sessionBox.classList.add('ready');
      sessionBox.querySelector('h3').textContent = '인스타그램 세션 설정 완료';
      sessionSteps.style.display = 'none';
      sessionMsg.textContent = '준비 완료! 릴스 URL을 입력하세요.';
      sessionMsg.className = 'session-msg ok';
    }
    document.getElementById('sessionInput').addEventListener('keydown', (e) => {
      if (e.key === 'Enter') saveSession();
    });
    const urlInput = document.getElementById('urlInput');
    const submitBtn = document.getElementById('submitBtn');
    const status = document.getElementById('status');
    const statusText = document.getElementById('statusText');
    const error = document.getElementById('error');
    const result = document.getElementById('result');
    urlInput.addEventListener('keydown', (e) => { if (e.key === 'Enter') handleSubmit(); });
    async function handleSubmit() {
      const url = urlInput.value.trim();
      const sessionid = localStorage.getItem('ig_sessionid');
      if (!url) return;
      if (!sessionid) { showError('먼저 sessionid를 입력해주세요.'); return; }
      submitBtn.disabled = true;
      error.classList.remove('visible');
      result.classList.remove('visible');
      status.classList.add('visible');
      statusText.textContent = '영상 다운로드 + 음성 인식 중...';
      try {
        const res = await fetch('/api/transcribe', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url, sessionid }),
        });
        const text = await res.text();
        let data;
        try { data = JSON.parse(text); }
        catch { throw new Error('서버 응답 오류: ' + text.substring(0, 200)); }
        if (!res.ok) throw new Error(data.detail || '오류가 발생했습니다.');
        document.getElementById('fullText').textContent = data.full_text;
        document.getElementById('segments').innerHTML = data.segments.map(seg =>
          '<div class="segment"><span class="timestamp">' + formatTime(seg.start) + ' &rarr; ' + formatTime(seg.end) + '</span><span class="segment-text">' + escapeHtml(seg.text) + '</span></div>'
        ).join('');
        result.classList.add('visible');
      } catch (e) { showError(e.message); }
      finally { status.classList.remove('visible'); submitBtn.disabled = false; }
    }
    function showError(msg) { error.textContent = msg; error.classList.add('visible'); }
    function formatTime(s) { return Math.floor(s/60)+':'+Math.floor(s%%60).toString().padStart(2,'0'); }
    function escapeHtml(t) { const d=document.createElement('div'); d.textContent=t; return d.innerHTML; }
    function switchTab(tab) {
      document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
      document.querySelectorAll('.tab-content').forEach(t=>t.classList.remove('active'));
      const i=tab==='full'?0:1;
      document.querySelectorAll('.tab')[i].classList.add('active');
      document.getElementById(tab==='full'?'tab-full':'tab-segments').classList.add('active');
    }
    function copyText() {
      navigator.clipboard.writeText(document.getElementById('fullText').textContent).then(()=>{
        const btn=document.querySelector('.copy-btn');btn.textContent='복사됨!';
        setTimeout(()=>btn.textContent='복사하기',1500);
      });
    }
  </script>
</body>
</html>'''


def validate_instagram_url(url):
    pattern = r"https?://(www\.)?(instagram\.com|instagr\.am)/(reel|reels|p)/[\w-]+"
    return bool(re.match(pattern, url))


def download_video(url, sessionid, output_dir):
    output_path = os.path.join(output_dir, "video.mp4")
    cookies_path = os.path.join(output_dir, "cookies.txt")
    with open(cookies_path, "w") as f:
        f.write("# Netscape HTTP Cookie File\n")
        f.write(f".instagram.com\tTRUE\t/\tTRUE\t0\tsessionid\t{sessionid}\n")

    cmd = [
        YTDLP_PATH,
        "--ffmpeg-location", FFMPEG_PATH,
        "--cookies", cookies_path,
        "-o", output_path,
        "--no-playlist",
        url,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    if result.returncode != 0:
        stderr = result.stderr
        if "empty media" in stderr.lower() or "not granting access" in stderr.lower():
            raise RuntimeError("영상에 접근할 수 없습니다. sessionid를 확인해주세요.")
        raise RuntimeError("영상 다운로드 실패")

    for f in os.listdir(output_dir):
        if f.startswith("video"):
            return os.path.join(output_dir, f)
    raise RuntimeError("다운로드된 파일을 찾을 수 없습니다.")


def extract_audio(video_path, output_dir):
    audio_path = os.path.join(output_dir, "audio.wav")
    cmd = [
        FFMPEG_PATH,
        "-i", video_path,
        "-vn", "-acodec", "pcm_s16le", "-ar", "16000", "-ac", "1",
        audio_path, "-y",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError("오디오 추출 실패")
    return audio_path


def transcribe_with_groq(audio_path):
    from groq import Groq
    client = Groq(api_key=GROQ_API_KEY)
    with open(audio_path, "rb") as f:
        transcription = client.audio.transcriptions.create(
            file=(os.path.basename(audio_path), f),
            model="whisper-large-v3",
            language="ko",
            response_format="verbose_json",
        )
    segments = [
        {
            "start": round(seg["start"], 1),
            "end": round(seg["end"], 1),
            "text": seg["text"].strip(),
        }
        for seg in (transcription.segments or [])
    ]
    return {"full_text": transcription.text.strip(), "segments": segments}


@app.route("/")
def home():
    return HTML_PAGE, 200, {"Content-Type": "text/html; charset=utf-8"}


@app.route("/api/transcribe", methods=["POST"])
def transcribe():
    body = request.get_json()
    url = body.get("url", "").strip()
    sessionid = body.get("sessionid", "").strip()

    if not validate_instagram_url(url):
        return jsonify({"detail": "올바른 인스타그램 릴스 URL이 아닙니다."}), 400
    if not sessionid:
        return jsonify({"detail": "sessionid를 입력해주세요."}), 400
    if not GROQ_API_KEY:
        return jsonify({"detail": "서버에 GROQ_API_KEY가 설정되지 않았습니다."}), 500

    tmp_dir = tempfile.mkdtemp()
    try:
        video_path = download_video(url, sessionid, tmp_dir)
        audio_path = extract_audio(video_path, tmp_dir)
        result = transcribe_with_groq(audio_path)
        return jsonify(result)
    except RuntimeError as e:
        return jsonify({"detail": str(e)}), 500
    except Exception as e:
        traceback.print_exc()
        return jsonify({"detail": f"처리 중 오류: {str(e)}"}), 500
    finally:
        shutil.rmtree(tmp_dir, ignore_errors=True)
