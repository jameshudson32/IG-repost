import os
from dotenv import load_dotenv
import instaloader
from instagrapi import Client
import time
import random
from datetime import datetime, timedelta
import json
import shutil
import schedule

load_dotenv()

class ReelReposter:
    def __init__(self):
        self.target_account = os.getenv('DOWNLOAD_TARGET', 'fineshytreels')
        self.upload_account = os.getenv('UPLOAD_ACCOUNT', 'mila.zeira')
        self.upload_password = os.getenv('UPLOAD_PASSWORD')
        self.download_folder = f"downloads/{self.target_account}"
        self.processed_folder = "processed"
        self.state_file = "bot_state.json"
        self.caption = "#fyp #viral"
        
        # Mode: 'catchup' or 'monitor'
        self.mode = self.load_state()
        
    def setup_folders(self):
        """Create necessary folders"""
        os.makedirs(self.download_folder, exist_ok=True)
        os.makedirs(self.processed_folder, exist_ok=True)
        
    def load_state(self):
        """Load bot state from file"""
        if os.path.exists(self.state_file):
            with open(self.state_file, 'r') as f:
                state = json.load(f)
                return state.get('mode', 'catchup')
        return 'catchup'
    
    def save_state(self, mode):
        """Save bot state to file"""
        with open(self.state_file, 'w') as f:
            json.dump({'mode': mode, 'last_update': str(datetime.now())}, f)
    
    def download_all_reels(self):
        """Download ALL reels from target account for catchup"""
        L = instaloader.Instaloader(
            quiet=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=True,  # Keep metadata to track what's new
            compress_json=False
        )
        
        print(f"Downloading ALL reels from @{self.target_account} for catchup...")
        
        try:
            profile = instaloader.Profile.from_username(L.context, self.target_account)
            
            count = 0
            for post in profile.get_posts():
                # Only get reels/videos
                if post.is_video and post.typename == 'GraphVideo':
                    # Check if already downloaded
                    video_file = os.path.join(self.download_folder, f"{post.shortcode}.mp4")
                    if not os.path.exists(video_file) and not os.path.exists(
                        os.path.join(self.processed_folder, f"{post.shortcode}.mp4")
                    ):
                        L.download_post(post, target=self.download_folder)
                        count += 1
                        print(f"Downloaded reel #{count}: {post.shortcode}")
                        
                        # Small delay between downloads
                        time.sleep(random.uniform(5, 15))
                    
            print(f"Total new reels downloaded: {count}")
            return count > 0
            
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def download_latest_reel(self):
        """Download only the most recent reel for monitoring mode"""
        L = instaloader.Instaloader(
            quiet=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=True,
            compress_json=False
        )
        
        try:
            profile = instaloader.Profile.from_username(L.context, self.target_account)
            
            # Get the most recent post
            for post in profile.get_posts():
                if post.is_video and post.typename == 'GraphVideo':
                    video_file = os.path.join(self.download_folder, f"{post.shortcode}.mp4")
                    processed_file = os.path.join(self.processed_folder, f"{post.shortcode}.mp4")
                    
                    # Check if it's new
                    if not os.path.exists(video_file) and not os.path.exists(processed_file):
                        L.download_post(post, target=self.download_folder)
                        print(f"New reel found and downloaded: {post.shortcode}")
                        return True
                    else:
                        print("No new reels found")
                        return False
                        
            return False
            
        except Exception as e:
            print(f"Download error: {e}")
            return False
    
    def get_unprocessed_videos(self, limit=None):
        """Find videos that haven't been uploaded yet"""
        videos = []
        for file in os.listdir(self.download_folder):
            if file.endswith('.mp4'):
                videos.append(os.path.join(self.download_folder, file))
        
        # Sort by creation time (oldest first for catchup)
        videos.sort(key=lambda x: os.path.getctime(x))
        
        if limit:
            return videos[:limit]
        return videos
    
    def upload_video(self, video_path):
        """Upload video to your account"""
        client = Client()
        
        try:
            client.login(self.upload_account, self.upload_password)
            print(f"Logged in as {self.upload_account}")
        except Exception as e:
            print(f"Login failed: {e}")
            return False
            
        try:
            print(f"Uploading {os.path.basename(video_path)}...")
            
            # Upload as reel
            media = client.clip_upload(
                video_path,
                caption=self.caption
            )
            
            # Move to processed folder
            filename = os.path.basename(video_path)
            shutil.move(video_path, os.path.join(self.processed_folder, filename))
            
            # Also move the metadata files if they exist
            base_name = filename.rsplit('.', 1)[0]
            for ext in ['.json', '.jpg', '.txt']:
                meta_file = os.path.join(self.download_folder, base_name + ext)
                if os.path.exists(meta_file):
                    shutil.move(meta_file, os.path.join(self.processed_folder, base_name + ext))
            
            print(f"Upload successful at {datetime.now()}")
            return True
            
        except Exception as e:
            print(f"Upload error: {e}")
            return False
    
    def catchup_mode(self):
        """Post 5 videos per hour until caught up"""
        print("Running in CATCHUP mode - posting 5 per hour")
        
        videos = self.get_unprocessed_videos(limit=5)
        
        if not videos:
            print("No videos to process - switching to monitor mode")
            self.mode = 'monitor'
            self.save_state('monitor')
            return
        
        for i, video in enumerate(videos):
            if self.upload_video(video):
                # Random delay between uploads (8-12 minutes)
                if i < len(videos) - 1:
                    delay = random.uniform(480, 720)
                    print(f"Waiting {int(delay/60)} minutes before next upload...")
                    time.sleep(delay)
            else:
                print(f"Failed to upload {video}")
                time.sleep(60)  # Short delay on failure
    
    def monitor_mode(self):
        """Check for new reels and post immediately"""
        print("Running in MONITOR mode - checking for new reels")
        
        if self.download_latest_reel():
            # Wait a bit before uploading to seem natural
            delay = random.uniform(300, 900)  # 5-15 minutes
            print(f"New reel detected! Waiting {int(delay/60)} minutes before uploading...")
            time.sleep(delay)
            
            videos = self.get_unprocessed_videos(limit=1)
            if videos:
                self.upload_video(videos[0])
    
    def run_once(self):
        """Run one cycle based on current mode"""
        self.setup_folders()
        
        if self.mode == 'catchup':
            # Download all reels if this is first run
            if not os.listdir(self.download_folder):
                self.download_all_reels()
            self.catchup_mode()
        else:
            self.monitor_mode()
    
    def schedule_random_hourly(self):
        """Schedule uploads at random times each hour"""
        def job():
            # Random minute within the hour
            random_minute = random.randint(5, 55)
            next_run = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=random_minute)
            
            print(f"Next upload scheduled for {next_run.strftime('%H:%M')}")
            
            # Wait until that time
            wait_seconds = (next_run - datetime.now()).total_seconds()
            if wait_seconds > 0:
                time.sleep(wait_seconds)
            
            # Run the bot
            self.run_once()
        
        # Schedule for every hour
        schedule.every().hour.do(job)
        
        # Run immediately on start
        self.run_once()
        
        # Keep running
        while True:
            schedule.run_pending()
            time.sleep(60)

def main():
    """Main entry point"""
    bot = ReelReposter()
    
    # Check if we're in catchup mode and need frequent runs
    if bot.mode == 'catchup':
        print("Starting in CATCHUP mode - will post 5 videos per hour")
        # In catchup mode, run every hour
        while bot.mode == 'catchup':
            bot.run_once()
            if bot.mode == 'catchup':  # Still in catchup mode
                print("Waiting 1 hour before next catchup batch...")
                time.sleep(3600)  # 1 hour
    
    # Once caught up, switch to random hourly monitoring
    print("Starting MONITOR mode - will check hourly at random times")
    bot.schedule_random_hourly()

if __name__ == "__main__":
    main()
