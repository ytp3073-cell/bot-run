# Voice API (PHP + FFmpeg)

Simple PHP API that increases pitch of any audio file to sound female-like.

## Requirements
- PHP 7.4+
- ffmpeg installed on server

## Usage
POST multipart/form-data to `convert.php`
- `audio`: uploaded file (wav/mp3)
- `semitones`: pitch shift (default 5)
- `format`: output file format (wav/mp3)

**Example:**
```bash
curl -F "audio=@male.wav" -F "semitones=5" -F "format=wav" http://yourserver/voice-api/convert.php