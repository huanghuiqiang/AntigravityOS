import sys
import re
import os
import json
from youtube_transcript_api import YouTubeTranscriptApi
from youtube_transcript_api.formatters import TextFormatter, SRTFormatter

def extract_video_id(url):
    regex = r"(?:v=|\/)([0-9A-Za-z_-]{11}).*"
    match = re.search(regex, url)
    if match:
        return match.group(1)
    return None

def download_transcript(video_url, output_format='txt', lang_code='en', output_dir=None):
    if output_dir is None:
        # Default to GlobalDownloads next to GlobalTools
        script_dir = os.path.dirname(os.path.abspath(__file__))
        output_dir = os.path.join(script_dir, '../../GlobalDownloads')

    video_id = extract_video_id(video_url)
    if not video_id:
        return {"success": False, "error": "Invalid YouTube URL"}

    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    try:
        yt = YouTubeTranscriptApi()
        
        # Try fetch directly
        try:
            data = yt.get_transcript(video_id, languages=[lang_code])
        except AttributeError:
            data = yt.fetch(video_id, languages=[lang_code])
        except Exception:
            # Fallback to listing
            transcript_list = None
            if hasattr(yt, 'list_transcripts'):
                transcript_list = yt.list_transcripts(video_id)
            else:
                transcript_list = yt.list(video_id)
            
            try:
                transcript = transcript_list.find_generated_transcript([lang_code])
                data = transcript.fetch()
            except:
                first_transcript = next(iter(transcript_list))
                data = first_transcript.fetch()
                lang_code = first_transcript.language_code

        # Format
        ext = output_format.lower()
        if ext == 'srt':
            formatter = SRTFormatter()
        else:
            formatter = TextFormatter()
        
        formatted_text = formatter.format_transcript(data)

        # Save
        filename = f"{video_id}.{ext}"
        filepath = os.path.join(output_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(formatted_text)
            
        return {
            "success": True, 
            "video_id": video_id, 
            "filepath": os.path.abspath(filepath),
            "filename": filename,
            "language": lang_code
        }
        
    except Exception as e:
        return {"success": False, "error": str(e)}

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print(json.dumps({"success": False, "error": "Usage: python script.py <url>"}))
        sys.exit(1)
    
    url = sys.argv[1]
    fmt = sys.argv[2] if len(sys.argv) > 2 else 'txt'
    lang = sys.argv[3] if len(sys.argv) > 3 else 'en'
    
    # Run and output JSON for Agent to parse
    result = download_transcript(url, fmt, lang)
    print(json.dumps(result, indent=2))

