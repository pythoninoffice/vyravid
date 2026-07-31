#!/usr/bin/env python3
"""
Simple AssemblyAI URL transcription test
"""

import asyncio
import aiohttp
import os
import time

# AssemblyAI API configuration
ASSEMBLYAI_API_KEY = os.getenv("ASSEMBLYAI_API_KEY")
BASE_URL = "https://api.assemblyai.com/v2"
TRANSCRIPT_URL = f"{BASE_URL}/transcript"

async def transcribe_url(audio_url: str):
    """Simple URL transcription test"""
    if not ASSEMBLYAI_API_KEY:
        raise RuntimeError("Missing ASSEMBLYAI_API_KEY environment variable")

    headers = {
        'Authorization': ASSEMBLYAI_API_KEY,
        'Content-Type': 'application/json'
    }
    
    # Submit transcription
    transcript_request = {
        'audio_url': audio_url,
        'punctuate': True,
        'format_text': True,
        'language_detection': True
    }
    
    print(f"📝 Submitting: {audio_url}")
    
    async with aiohttp.ClientSession() as session:
        # Submit job
        async with session.post(TRANSCRIPT_URL, headers=headers, json=transcript_request) as response:
            if response.status != 200:
                error_text = await response.text()
                print(f"❌ Submit failed: {response.status} - {error_text}")
                return
            
            submit_response = await response.json()
            transcript_id = submit_response['id']
            print(f"✅ Job submitted: {transcript_id}")
        
        # Poll for completion
        get_url = f"{TRANSCRIPT_URL}/{transcript_id}"
        start_time = time.time()
        
        while True:
            await asyncio.sleep(5)  # Wait 5 seconds between polls
            
            async with session.get(get_url, headers=headers) as response:
                if response.status != 200:
                    print(f"❌ Poll failed: {response.status}")
                    return
                
                result = await response.json()
                status = result.get('status')
                elapsed = time.time() - start_time
                
                print(f"🔄 Status: {status} ({elapsed:.1f}s)")
                
                if status == 'completed':
                    print(f"✅ Completed in {elapsed:.1f}s")
                    print(f"📄 Text: {result.get('text', 'No text')[:200]}...")
                    print(f"📊 Confidence: {result.get('confidence', 0):.2f}")
                    print(f"⏱️ Duration: {result.get('audio_duration', 0)/1000:.1f}s")
                    
                    # Save response to file
                    output_file = f"assemblyai_response_{transcript_id}.ass"
                    with open(output_file, 'w', encoding='utf-8') as f:
                        import json
                        f.write(json.dumps(result, indent=2, ensure_ascii=False))
                    
                    print(f"💾 Response saved to: {output_file}")
                    return result
                elif status == 'error':
                    print(f"❌ Failed: {result.get('error', 'Unknown error')}")
                    return
                elif elapsed > 300:  # 5 minute timeout
                    print(f"⏰ Timeout after 5 minutes")
                    return

async def main():
    # Test with public sample audio
    audio_url = "https://storage.googleapis.com/vyra-public/20250907_003919_d7d20965-c595-443d-aae6-dee32312e3f3.mp3"
    await transcribe_url(audio_url)

if __name__ == "__main__":
    asyncio.run(main())
