import json
import os
import re
import shutil
import subprocess
import tempfile

from http.server import BaseHTTPRequestHandler

import imageio_ffmpeg

FFMPEG_PATH = imageio_ffmpeg.get_ffmpeg_exe()
YTDLP_PATH = shutil.which("yt-dlp")
GROQ_API_KEY = os.environ.get("GROQ_API_KEY", "")


def validate_instagram_url(url: str) -> bool:
    pattern = r"https?://(www\.)?(instagram\.com|instagr\.am)/(reel|reels|p)/[\w-]+"
    return bool(re.match(pattern, url))


def download_video(url: str, sessionid: str, output_dir: str) -> str:
    output_path = os.path.join(output_dir, "video.mp4")

    # sessionid로 임시 쿠키 파일 생성
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
        raise RuntimeError(f"영상 다운로드 실패")

    for f in os.listdir(output_dir):
        if f.startswith("video"):
            return os.path.join(output_dir, f)
    raise RuntimeError("다운로드된 파일을 찾을 수 없습니다.")


def extract_audio(video_path: str, output_dir: str) -> str:
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


def transcribe_with_groq(audio_path: str) -> dict:
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
    full_text = transcription.text.strip()
    return {"full_text": full_text, "segments": segments}


class handler(BaseHTTPRequestHandler):
    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = json.loads(self.rfile.read(content_length))

        url = body.get("url", "").strip()
        sessionid = body.get("sessionid", "").strip()

        if not validate_instagram_url(url):
            self._respond(400, {"detail": "올바른 인스타그램 릴스 URL이 아닙니다."})
            return

        if not sessionid:
            self._respond(400, {"detail": "sessionid를 입력해주세요."})
            return

        if not GROQ_API_KEY:
            self._respond(500, {"detail": "서버에 GROQ_API_KEY가 설정되지 않았습니다."})
            return

        tmp_dir = tempfile.mkdtemp()
        try:
            video_path = download_video(url, sessionid, tmp_dir)
            audio_path = extract_audio(video_path, tmp_dir)
            result = transcribe_with_groq(audio_path)
            self._respond(200, result)
        except RuntimeError as e:
            self._respond(500, {"detail": str(e)})
        except Exception as e:
            self._respond(500, {"detail": f"처리 중 오류: {str(e)}"})
        finally:
            shutil.rmtree(tmp_dir, ignore_errors=True)

    def _respond(self, status, data):
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(data, ensure_ascii=False).encode())
