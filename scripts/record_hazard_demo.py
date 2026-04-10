import time
import os
import shutil
from playwright.sync_api import sync_playwright

def run(playwright):
    browser = playwright.chromium.launch(headless=True)
    
    # 1080p recording for high quality
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        record_video_dir="docs/",
        record_video_size={"width": 1920, "height": 1080}
    )
    
    page = context.new_page()
    print("Navigating to TerminalRescue...")
    page.goto("http://localhost:8000")
    
    time.sleep(2)
    print("Dismissing briefing modal to start mission...")
    page.keyboard.press("Space")
    
    # Give drones a couple of seconds to fan out
    print("Waiting 3 seconds for drones to begin forming the mesh...")
    time.sleep(3)
    
    # The "Hazard Wall" Stunt
    print("Dropping a firewall of HAZARDS right in front of the swarm...")
    
    # We will build a barrier of hazards across the middle of the 10x10 grid (y=4, x=2 to 7)
    for x in range(2, 8):
        cell_id = f"#cell-{x}_4"
        cell_locator = page.locator(cell_id)
        if cell_locator.is_visible():
            cell_locator.click(force=True)
            # Short pause to make it look like a human is rapidly mapping threats
            time.sleep(0.3)
            
    print("Hazards deployed! Watch the drones instantly recompute aversion trajectories...")
    
    # Let it record the avoidance behavior as they snake around the wall
    time.sleep(15)
    
    # We don't need to record until 100% since we just want to showcase the avoidance mechanic
    print("Captured Hazard Avoidance behavior.")
    
    video_path = page.video.path()
    context.close()
    browser.close()
    
    final_path = "docs/hazard-avoidance-demo.webm"
    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(video_path, final_path)
    print(f"✅ Success! Hazard Stunt saved to docs/hazard-avoidance-demo.webm")

if __name__ == "__main__":
    print("Starting automated Playwright Hazard recording...")
    with sync_playwright() as playwright:
        run(playwright)
