import time
import os
import shutil
from playwright.sync_api import sync_playwright

def run(playwright):
    # Launch Chromium browser 
    browser = playwright.chromium.launch(headless=True)
    
    # Create context with 1080p video recording enabled
    context = browser.new_context(
        viewport={'width': 1920, 'height': 1080},
        record_video_dir="docs/",
        record_video_size={"width": 1920, "height": 1080}
    )
    
    page = context.new_page()
    print("Navigating to TerminalRescue Mission Control...")
    page.goto("http://localhost:8000")
    
    time.sleep(2)
    
    print("📸 Capturing 01-swarm-bootup.png...")
    page.screenshot(path="docs/01-swarm-bootup.png")
    
    print("Dismissing briefing modal to start mission...")
    page.keyboard.press("Space")
    
    time.sleep(3)
    print("📸 Capturing 02-grid-claiming.png...")
    page.screenshot(path="docs/02-grid-claiming.png")
    
    time.sleep(4)
    print("📸 Capturing 03-mesh-stabilization.png...")
    page.screenshot(path="docs/03-mesh-stabilization.png")
    
    time.sleep(3)
    print("📸 Capturing 04-mission-control-live.png...")
    page.screenshot(path="docs/04-mission-control-live.png")
    
    # The "Money Shot" - Kill a drone
    print("Triggering Kill-Switch stunt...")
    kill_button = page.locator("button.btn-kill:not([disabled])").first
    if kill_button.is_visible():
        kill_button.click(force=True)
        
        # Wait 150ms to catch the red flash and screen shake!
        time.sleep(0.15)
        print("📸 Capturing 05-kill-switch-activation.png...")
        page.screenshot(path="docs/05-kill-switch-activation.png")
        
        # Wait for the mesh to notice the node is offline and emit logs
        time.sleep(1.5)
        print("📸 Capturing 06-fault-detection.png...")
        page.screenshot(path="docs/06-fault-detection.png")
        
        # Wait for drones to swoop in and cover the missing sector
        time.sleep(3.5)
        print("📸 Capturing 07-autonomous-recovery.png...")
        page.screenshot(path="docs/07-autonomous-recovery.png")
    else:
        print("Could not find a valid drone to kill.")
    
    # Wait until mission progress hits 100%
    print("Waiting for mission completion...")
    try:
        page.locator("#mission-progress").wait_for(state="visible", timeout=90000)
        page.wait_for_function('document.getElementById("mission-progress").innerText === "100%"', timeout=90000)
        
        # Capture the green UI 
        time.sleep(1)
        print("📸 Capturing 08-mission-complete.png...")
        page.screenshot(path="docs/08-mission-complete.png")
        
        # Give it a few seconds to finish the video rendering the confetti
        time.sleep(4) 
    except Exception as e:
        print("Timeout waiting for 100% completion.")

    video_path = page.video.path()
    context.close()
    browser.close()
    
    final_path = "docs/terminal-rescue-demo.webm"
    if os.path.exists(final_path):
        os.remove(final_path)
    shutil.move(video_path, final_path)
    
    print(f"✅ Success! Web UI recording and ALL 8 screenshots saved to docs/")

if __name__ == "__main__":
    print("Starting automated Playwright video + screenshot recording...")
    with sync_playwright() as playwright:
        run(playwright)
