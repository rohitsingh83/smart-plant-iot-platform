import time
import os
import io
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import imageio

def record_demo():
    print("Initializing headless Chrome for recording...")
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1280,800')
    opts.add_argument('--hide-scrollbars')

    driver = webdriver.Chrome(options=opts)
    
    # Target URL - GitHub Pages deployment
    target_url = "https://rohitsingh83.github.io/smart-plant-iot-platform/"
    print(f"Loading {target_url}...")
    driver.get(target_url)
    
    # Wait for initial load, charts, and telemetry loop to stabilize
    time.sleep(3.0)

    frames = []
    fps = 10
    
    # Phase 1: Capture initial normal baseline state (~2.5 seconds = 25 frames)
    print("Phase 1: Capturing baseline telemetry state (2.5s)...")
    for _ in range(25):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)

    # Phase 2: Click Manual Irrigation Pulse
    print("Phase 2: Triggering manual irrigation pulse (5s pump active)...")
    btn = driver.find_element(By.ID, "btnManualActuate")
    btn.click()

    # Phase 3: Capture active watering animation (~6.5 seconds = 65 frames)
    # This covers the entire 5-second pulse where water droplets animate, pump turns cyan, moisture increases
    print("Phase 3: Capturing active watering animation & droplet cascade (6.5s)...")
    for _ in range(65):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)

    # Phase 4: Capture post-watering cooldown, log updates, and stabilization (~6 seconds = 60 frames)
    print("Phase 4: Capturing post-watering stabilization & cooldown (6.0s)...")
    for _ in range(60):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)

    driver.quit()
    total_frames = len(frames)
    duration_sec = total_frames / fps
    print(f"Total frames captured: {total_frames} (~{duration_sec:.1f} seconds duration at {fps} fps)")

    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)
    
    mp4_path = os.path.join(out_dir, "smart_plant_watering_demo.mp4")
    gif_path = os.path.join(out_dir, "smart_plant_watering_demo.gif")

    # Ensure width and height are divisible by 16 for H.264
    w, h = frames[0].size
    new_w = (w // 16) * 16
    new_h = (h // 16) * 16
    print(f"Resizing video frames to {new_w}x{new_h} for perfect H.264 encoding...")
    formatted_frames = [f.resize((new_w, new_h), Image.Resampling.LANCZOS) for f in frames]

    # Save MP4
    print("Encoding H.264 MP4 video...")
    imageio.mimwrite(
        mp4_path,
        formatted_frames,
        fps=fps,
        format="FFMPEG",
        codec="libx264",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "22", "-preset", "medium"]
    )
    mp4_size_kb = os.path.getsize(mp4_path) / 1024
    print(f"MP4 Video saved successfully: {mp4_path} ({mp4_size_kb:.1f} KB)")

    # Save animated GIF (sample every 2nd frame at 5 fps or resize to 960 width for fast loading)
    print("Generating optimized animated GIF...")
    gif_frames = [f.resize((960, int(new_h * 960 / new_w)), Image.Resampling.LANCZOS) for f in formatted_frames[::2]]
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=200,  # 200ms per frame = 5 fps (matching the 2x step)
        loop=0,
        optimize=True
    )
    gif_size_kb = os.path.getsize(gif_path) / 1024
    print(f"GIF saved successfully: {gif_path} ({gif_size_kb:.1f} KB)")

if __name__ == "__main__":
    record_demo()
