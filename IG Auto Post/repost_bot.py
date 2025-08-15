import os
from dotenv import load_dotenv
import instaloader
import time
import random
from datetime import datetime, timedelta
import json
import shutil
import schedule
import urllib.parse
import requests
from upload_post import UploadPostClient

load_dotenv()

class ReelReposter:
    def __init__(self):
        self.target_account = os.getenv('DOWNLOAD_TARGET', 'fineshytreels')
        self.download_folder = f"downloads/{self.target_account}"
        self.processed_folder = "processed"
        self.state_file = "bot_state.json"
        self.caption = "#fyp #viral"
        
        # Mode: 'catchup' or 'monitor'
        self.mode = self.load_state()
        
        # Proxy configuration
        self.proxy_url = os.getenv('PROXY_URL')
        if self.proxy_url:
            print(f"Proxy configured: {self.proxy_url.split('@')[-1]}")
    
    def get_proxy_dict(self):
        """Get proxy dictionary for requests"""
        if self.proxy_url:
            return {
                'http': self.proxy_url,
                'https': self.proxy_url
            }
        return None
    
    def get_instaloader_session(self, try_different_proxy=False):
        """Get Instaloader with proxy and session management"""
        L = instaloader.Instaloader(
            quiet=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=True,
            compress_json=False,
            request_timeout=60,
            max_connection_attempts=1  # Don't retry on same proxy
        )
        
        # Configure proxy if available
        if self.proxy_url:
            proxy_to_use = self.proxy_url
            
            # Try different proxy port if requested
            if try_different_proxy:
                current_port = int(self.proxy_url.split(':')[-1])
                new_port = random.choice([p for p in range(10001, 10011) if p != current_port])
                proxy_to_use = self.proxy_url.replace(str(current_port), str(new_port))
                print(f"Switching to proxy port {new_port}")
            
            proxies = {
                'http': proxy_to_use,
                'https': proxy_to_use
            }
            L.context._session.proxies.update(proxies)
            print("Proxy configured for Instaloader")
        
        # Try to load saved session
        session_file = "session-downloader"
        
        try:
            if os.path.exists(session_file):
                print("Loading saved session...")
                L.load_session_from_file("downloader", session_file)
                print("Session loaded successfully!")
                
                # Test if session is still valid
                try:
                    L.context.test_login()
                    print("Session is valid!")
                    return L
                except:
                    print("Session expired, will create new one if needed")
                    os.remove(session_file)
        except Exception as e:
            print(f"Session load failed: {e}")
        
        # Return without login - we'll login only if needed
        print("Will attempt download without login first (public profiles only)")
        return L
    
    def login_if_needed(self, L):
        """Login only if required - using dummy account for downloads"""
        # Since we're only downloading public content, we don't need login
        # This method is kept for compatibility but returns False
        print("Login not implemented for download-only mode")
        return False
        
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
        L = self.get_instaloader_session()
        
        print(f"Downloading ALL reels from @{self.target_account} for catchup...")
        
        # First try without login (works for public profiles)
        logged_in = False
        
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
                        try:
                            L.download_post(post, target=self.download_folder)
                            count += 1
                            print(f"Downloaded reel #{count}: {post.shortcode}")
                            
                            # No delay between downloads - go fast!
                            # time.sleep(random.uniform(15, 30))
                        except Exception as dl_error:
                            if "login" in str(dl_error).lower() and not logged_in:
                                print("Login required for this content...")
                                if self.login_if_needed(L):
                                    logged_in = True
                                    # Retry this download
                                    L.download_post(post, target=self.download_folder)
                                    count += 1
                                    print(f"Downloaded reel #{count}: {post.shortcode}")
                                else:
                                    print("Skipping private content")
                                    continue
                            else:
                                print(f"Download error for {post.shortcode}: {dl_error}")
                    
            print(f"Total new reels downloaded: {count}")
            return count > 0
            
        except Exception as e:
            error_str = str(e).lower()
            if "login" in error_str or "401" in error_str:
                print("Profile might be private or login required...")
                if not logged_in and self.login_if_needed(L):
                    # Retry with login
                    return self.download_all_reels()
            print(f"Download error: {e}")
            return False
    
    def download_latest_reel(self):
        """Download only the most recent reel for monitoring mode"""
        L = self.get_instaloader_session()
        
        print("Checking for new reels...")
        logged_in = False
        
        try:
            profile = instaloader.Profile.from_username(L.context, self.target_account)
            
            # Get the most recent post
            for post in profile.get_posts():
                if post.is_video and post.typename == 'GraphVideo':
                    video_file = os.path.join(self.download_folder, f"{post.shortcode}.mp4")
                    processed_file = os.path.join(self.processed_folder, f"{post.shortcode}.mp4")
                    
                    # Check if it's new
                    if not os.path.exists(video_file) and not os.path.exists(processed_file):
                        try:
                            L.download_post(post, target=self.download_folder)
                            print(f"New reel found and downloaded: {post.shortcode}")
                            return True
                        except Exception as dl_error:
                            if "login" in str(dl_error).lower() and not logged_in:
                                print("Login required for download...")
                                if self.login_if_needed(L):
                                    logged_in = True
                                    L.download_post(post, target=self.download_folder)
                                    print(f"New reel found and downloaded: {post.shortcode}")
                                    return True
                            print(f"Download error: {dl_error}")
                            return False
                    else:
                        print("No new reels found")
                        return False
                        
            return False
            
        except Exception as e:
            error_str = str(e).lower()
            if ("login" in error_str or "401" in error_str) and not logged_in:
                print("Login required...")
                if self.login_if_needed(L):
                    return self.download_latest_reel()
            print(f"Check error: {e}")
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
        """Upload video to your account using Upload Post SDK"""
        
        print(f"\n=== STARTING UPLOAD ===")
        print(f"Video path: {video_path}")
        
        # Get API credentials
        api_key = os.getenv('UPLOAD_POST_API_KEY')
        managed_user = os.getenv('UPLOAD_POST_USER')  # Your managed user from upload-post.com
        
        print(f"API Key present: {'Yes' if api_key else 'No'}")
        print(f"Managed User: {managed_user if managed_user else 'NOT SET'}")
        
        if not api_key:
            print("ERROR: UPLOAD_POST_API_KEY not set in environment variables!")
            print("Set it in Railway with your Upload Post API key")
            return False
        
        if not managed_user:
            print("ERROR: UPLOAD_POST_USER not set in environment variables!")
            print("This should be the username you created in Upload Post dashboard")
            print("NOT your Instagram username!")
            return False
        
        # Check video file
        if not os.path.exists(video_path):
            print(f"Video file not found: {video_path}")
            return False
        
        # Check file size (max 300MB for Instagram)
        file_size = os.path.getsize(video_path) / (1024 * 1024)  # Size in MB
        if file_size > 300:
            print(f"Video file too large: {file_size:.1f}MB (max 300MB)")
            return False
        
        try:
            print(f"Uploading {os.path.basename(video_path)} via Upload Post SDK...")
            
            # Initialize the Upload Post client
            client = UploadPostClient(api_key=api_key)
            
            # Upload the video
            response = client.upload_video(
                video_path=video_path,
                title=self.caption,  # "#fyp #viral"
                user=managed_user,
                platforms=["instagram"]  # Just Instagram for now
            )
            
            print(f"Upload response: {response}")
            
            # If successful, move to processed folder
            if response and response.get('success', False):
                filename = os.path.basename(video_path)
                shutil.move(video_path, os.path.join(self.processed_folder, filename))
                
                # Also move metadata files if they exist
                base_name = filename.rsplit('.', 1)[0]
                for ext in ['.json', '.jpg', '.txt']:
                    meta_file = os.path.join(self.download_folder, base_name + ext)
                    if os.path.exists(meta_file):
                        shutil.move(meta_file, os.path.join(self.processed_folder, base_name + ext))
                
                print(f"Upload completed at {datetime.now()}")
                return True
            else:
                print(f"Upload failed! Response: {response}")
                return False
                    
        except Exception as e:
            print(f"Upload error: {e}")
            return False
    
    def download_one_reel(self):
        """Download just one reel that we haven't downloaded yet"""
        # Try with current proxy first
        for attempt in range(3):
            try_different_proxy = (attempt > 0)  # Use different proxy on retries
            L = self.get_instaloader_session(try_different_proxy=try_different_proxy)
            
            try:
                profile = instaloader.Profile.from_username(L.context, self.target_account)
                
                # Get list of already downloaded/processed files
                downloaded = set()
                for file in os.listdir(self.download_folder):
                    if file.endswith('.mp4'):
                        downloaded.add(file.replace('.mp4', ''))
                for file in os.listdir(self.processed_folder):
                    if file.endswith('.mp4'):
                        downloaded.add(file.replace('.mp4', ''))
                
                # Find first reel we haven't downloaded
                for post in profile.get_posts():
                    if post.is_video and post.typename == 'GraphVideo':
                        if post.shortcode not in downloaded:
                            try:
                                L.download_post(post, target=self.download_folder)
                                print(f"Downloaded reel: {post.shortcode}")
                                return True
                            except Exception as dl_error:
                                error_str = str(dl_error).lower()
                                
                                # If we get 429, wait and retry with different proxy
                                if "429" in error_str:
                                    print(f"Rate limited on attempt {attempt + 1}, trying different proxy immediately...")
                                    break  # Break inner loop to retry with different proxy
                                
                                # Skip login errors - just move to next video
                                if "login" in error_str:
                                    print("This reel requires login, skipping to next...")
                                    continue
                                    
                                print(f"Download error: {dl_error}")
                                return False
                
                print("No new reels found to download")
                return False
                
            except Exception as e:
                error_str = str(e).lower()
                
                # Handle 429 rate limit
                if "429" in error_str:
                    if attempt < 2:
                        print(f"Rate limited, trying different proxy port immediately...")
                        continue
                    else:
                        print("Rate limited on all proxy attempts")
                        return False
                
                # Skip login-related errors
                if "login" in error_str or "401" in error_str:
                    print("Profile might be private or login required, skipping...")
                    return False
                    
                print(f"Download error: {e}")
                return False
        
        return False
    
    def catchup_mode(self):
        """Download and post one reel at a time with 30 min intervals"""
        print("Running in CATCHUP mode - download, post, wait 30 mins, repeat")
        
        # Check if we have any unprocessed videos first
        unprocessed = self.get_unprocessed_videos()
        
        if unprocessed:
            # Upload one existing video
            print(f"Found {len(unprocessed)} unprocessed videos, uploading one...")
            if self.upload_video(unprocessed[0]):
                print("Upload successful, waiting 30 minutes before next cycle...")
                time.sleep(1800)  # 30 minutes
            else:
                print("Upload failed! Waiting 30 minutes before retry...")
                time.sleep(1800)  # Still wait 30 mins even on failure
            return
        
        # Download one new reel immediately
        print("Downloading next reel...")
        if self.download_one_reel():
            # Upload immediately after download
            videos = self.get_unprocessed_videos(limit=1)
            if videos:
                print(f"Uploading video immediately...")
                if self.upload_video(videos[0]):
                    print("Upload successful, waiting 30 minutes before next download...")
                    time.sleep(1800)  # 30 minutes
                else:
                    print("Upload failed, waiting 30 minutes before retry...")
                    time.sleep(1800)  # 30 minutes
            else:
                print("ERROR: No video found after download!")
        else:
            # No more reels to download
            print("No more reels to download - checking if we should switch to monitor mode")
            
            # Check if we have any unprocessed videos
            unprocessed = self.get_unprocessed_videos()
            if not unprocessed:
                print("All reels processed - switching to monitor mode")
                self.mode = 'monitor'
                self.save_state('monitor')
            else:
                print(f"Still have {len(unprocessed)} videos to process")
                # Wait 30 minutes before checking again
                time.sleep(1800)
    
    def monitor_mode(self):
        """Check for new reels and post immediately"""
        print("Running in MONITOR mode - checking for new reels")
        
        if self.download_latest_reel():
            # Upload immediately
            print("New reel detected! Uploading immediately...")
            
            videos = self.get_unprocessed_videos(limit=1)
            if videos:
                self.upload_video(videos[0])
    
    def run_once(self):
        """Run one cycle based on current mode"""
        self.setup_folders()
        
        if self.mode == 'catchup':
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
    
    # Check if we're in catchup mode
    if bot.mode == 'catchup':
        print("Starting in CATCHUP mode - will download and post one reel every 30 minutes")
        # In catchup mode, continuously download and post
        while bot.mode == 'catchup':
            bot.run_once()
            # run_once will handle the 30-minute wait internally
    
    # Once caught up, switch to random hourly monitoring
    print("Starting MONITOR mode - will check hourly at random times")
    bot.schedule_random_hourly()

if __name__ == "__main__":
    main()
