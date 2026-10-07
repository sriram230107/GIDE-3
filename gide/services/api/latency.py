import time
import asyncio
from app.ai import llm

async def main():
    with open('../../evidence/step2/latency.log', 'w') as f:
        start = time.time()
        await llm.agenerate_text('Hello, say hi')
        f.write(f'Text: {time.time()-start:.2f}s\n')
        
        start = time.time()
        await llm.agenerate_json('Return {"greeting":"hi"} as JSON')
        f.write(f'JSON: {time.time()-start:.2f}s\n')
        
        start = time.time()
        await llm.aembed_texts(['hello world'])
        f.write(f'Embed: {time.time()-start:.2f}s\n')
        
        img_data = b'GIF89a\x01\x00\x01\x00\x80\x00\x00\xff\xff\xff\x00\x00\x00!\xf9\x04\x01\x00\x00\x00\x00,\x00\x00\x00\x00\x01\x00\x01\x00\x00\x02\x02D\x01\x00;'
        try:
            start = time.time()
            await llm.adescribe_image(img_data, 'image/gif', 'What is this? Return {"desc":"..."}')
            f.write(f'Vision: {time.time()-start:.2f}s\n')
        except Exception as e:
            f.write(f'Vision failed: {e}\n')

if __name__ == '__main__':
    asyncio.run(main())
