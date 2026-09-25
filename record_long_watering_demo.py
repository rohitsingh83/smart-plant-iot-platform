import time
import os
import io
from PIL import Image
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
import imageio

def record_long_watering():
    print("Configuring headless Chrome...")
    opts = Options()
    opts.add_argument('--headless=new')
    opts.add_argument('--disable-gpu')
    opts.add_argument('--window-size=1280,800')
    opts.add_argument('--hide-scrollbars')

    driver = webdriver.Chrome(options=opts)
    
    local_index = os.path.abspath("index.html").replace("\\", "/")
    target_url = f"file:///{local_index}"
    print(f"Loading local dashboard: {target_url}...")
    driver.get(target_url)
    
    # Wait for Chart.js, SVG and loop initialization
    time.sleep(2.5)

    # Configure long watering:
    # Set soil moisture to 34% (deficit) and pump duration to 20 seconds
    print("Configuring digital twin for extended watering demonstration...")
    driver.execute_script("""
        if (window.physicsTwin) {
            window.physicsTwin.soilMoisture = 34.0;
            window.currentConfig.pumpDuration = 20.0;
            const btnText = document.getElementById('btnManualActuateText');
            if (btnText) btnText.innerText = 'Manual Irrigation Pulse (20s)';
            if (window.updateUI) window.updateUI();
        }
    """)
    time.sleep(1.0)

    frames = []
    fps = 10

    # Phase 1: Baseline dry state (3 seconds = 30 frames)
    print("Phase 1: Recording dry baseline state before irrigation (3.0s)...")
    for _ in range(30):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)

    # Phase 2: Trigger manual irrigation pulse
    print("Phase 2: Triggering manual irrigation pulse (20-second active watering cycle)...")
    btn = driver.find_element(By.ID, "btnManualActuate")
    btn.click()

    # Phase 3: Active watering animation for 20 continuous seconds (200 frames at 10 fps = 20s)
    # The water droplets cascade continuously, impeller spins, soil darkens, moisture rises
    print("Phase 3: Recording extended 20-second continuous active watering animation...")
    for i in range(200):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)
        if (i + 1) % 40 == 0:
            print(f"  Watering progress: frame {i + 1}/200 ({(i + 1)/10:.1f}s of continuous watering)...")

    # Phase 4: Post-watering saturated & stabilized state (5.0 seconds = 50 frames)
    print("Phase 4: Recording post-watering hydrated state & stabilization (5.0s)...")
    for _ in range(50):
        png = driver.get_screenshot_as_png()
        img = Image.open(io.BytesIO(png)).convert("RGB")
        frames.append(img)
        time.sleep(0.1)

    driver.quit()
    total_frames = len(frames)
    duration_sec = total_frames / fps
    print(f"Successfully captured {total_frames} frames ({duration_sec:.1f} seconds total runtime).")

    out_dir = os.path.abspath("screenshots")
    os.makedirs(out_dir, exist_ok=True)

    mp4_path = os.path.join(out_dir, "smart_plant_watering_demo.mp4")
    gif_path = os.path.join(out_dir, "smart_plant_watering_demo.gif")

    w, h = frames[0].size
    new_w = (w // 16) * 16
    new_h = (h // 16) * 16
    print(f"Formatting frames to {new_w}x{new_h} for standard H.264 macroblocks...")
    formatted_frames = [f.resize((new_w, new_h), Image.Resampling.LANCZOS) for f in frames]

    # Save MP4 video
    print(f"Encoding extended {duration_sec:.1f}s H.264 MP4 video...")
    imageio.mimwrite(
        mp4_path,
        formatted_frames,
        fps=fps,
        format="FFMPEG",
        codec="libx264",
        ffmpeg_params=["-pix_fmt", "yuv420p", "-crf", "20", "-preset", "medium"]
    )
    mp4_size_kb = os.path.getsize(mp4_path) / 1024
    print(f"MP4 Video saved: {mp4_path} ({mp4_size_kb:.1f} KB, duration: {duration_sec:.1f}s)")

    # Save animated GIF (sample every 2nd frame at 5 fps, width 960)
    print("Encoding animated GIF preview...")
    gif_frames = [f.resize((960, int(new_h * 960 / new_w)), Image.Resampling.LANCZOS) for f in formatted_frames[::2]]
    gif_frames[0].save(
        gif_path,
        save_all=True,
        append_images=gif_frames[1:],
        duration=200,  # 5 fps
        loop=0,
        optimize=True
    )
    gif_size_kb = os.path.getsize(gif_path) / 1024
    print(f"GIF saved: {gif_path} ({gif_size_kb:.1f} KB)")

if __name__ == "__main__":
    record_long_watering()
