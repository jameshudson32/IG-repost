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
        self.download_folder = "downloads"  # Let Instaloader handle subfolders
        self.processed_folder = "processed"
        self.state_file = "bot_state.json"
        self.processed_posts_file = "processed_posts.json"
        self.caption = "#fyp #viral #foryoupage"
        
        # Mode: 'catchup' or 'monitor'
        self.mode = self.load_state()
        
        # Load processed posts tracking
        self.processed_posts = self.load_processed_posts()
        
        # Proxy configuration
        self.proxy_url = os.getenv('PROXY_URL')
        if self.proxy_url:
            print(f"Proxy configured: {self.proxy_url.split('@')[-1]}")
    
    def load_processed_posts(self):
        """Load list of posts we've already processed"""
        if os.path.exists(self.processed_posts_file):
            with open(self.processed_posts_file, 'r') as f:
                return set(json.load(f))
        return set()
    
    def save_processed_posts(self):
        """Save list of processed posts"""
        with open(self.processed_posts_file, 'w') as f:
            json.dump(list(self.processed_posts), f)
    
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
            max_connection_attempts=1,  # Don't retry on same proxy
            dirname_pattern=self.download_folder  # Set download directory
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
    
    def find_all_mp4_files(self):
        """Find all MP4 files recursively in downloads and processed folders"""
        all_files = []
        
        # Search in downloads folder and all subfolders
        for root, dirs, files in os.walk(self.download_folder):
            for file in files:
                if file.endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    all_files.append(full_path)
        
        # Search in processed folder
        for root, dirs, files in os.walk(self.processed_folder):
            for file in files:
                if file.endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    all_files.append(full_path)
        
        return all_files
    
    def get_unprocessed_videos(self, limit=None):
        """Find videos that haven't been uploaded yet"""
        videos = []
        
        # Search recursively in downloads folder
        for root, dirs, files in os.walk(self.download_folder):
            for file in files:
                if file.endswith('.mp4'):
                    full_path = os.path.join(root, file)
                    videos.append(full_path)
        
        # Sort by creation time (oldest first for catchup)
        if videos:
            videos.sort(key=lambda x: os.path.getctime(x))
        
        if limit:
            return videos[:limit]
        return videos
    
    def download_latest_reel(self):
        """Download only the most recent reel for monitoring mode"""
        L = self.get_instaloader_session()
        
        print("Checking for new reels...")
        
        # Count MP4 files before download
        files_before = len(self.find_all_mp4_files())
        print(f"MP4 files before download: {files_before}")
        
        try:
            profile = instaloader.Profile.from_username(L.context, self.target_account)
            
            # Get the most recent post
            for post in profile.get_posts():
                if post.is_video and post.typename == 'GraphVideo':
                    # Check if we've already processed this post
                    if post.shortcode in self.processed_posts:
                        print(f"Latest reel {post.shortcode} already processed")
                        return False
                    
                    # Download the post
                    try:
                        L.download_post(post, target=profile.username)
                        
                        # Check if a new file was created
                        files_after = len(self.find_all_mp4_files())
                        print(f"MP4 files after download: {files_after}")
                        
                        if files_after > files_before:
                            print(f"New reel downloaded successfully!")
                            # Mark as processed
                            self.processed_posts.add(post.shortcode)
                            self.save_processed_posts()
                            return True
                        else:
                            print("This reel was already downloaded")
                            # Still mark as processed to avoid rechecking
                            self.processed_posts.add(post.shortcode)
                            self.save_processed_posts()
                            return False
                            
                    except Exception as dl_error:
                        print(f"Download error: {dl_error}")
                        return False
                        
            print("No video reels found")
            return False
            
        except Exception as e:
            print(f"Check error: {e}")
            return False
    
    def upload_video(self, video_path):
        """Upload video to your account using Upload Post SDK"""
        
        print(f"\n=== STARTING UPLOAD ===")
        print(f"Video path: {video_path}")
        
        # Get API credentials
        api_key = os.getenv('UPLOAD_POST_API_KEY')
        managed_user = os.getenv('UPLOAD_POST_USER')  # Your managed user from upload-post.com
        
        print(f"API Key present: {'Yes' if api_key else 'No'}")
        print(f"API Key length: {len(api_key) if api_key else 0}")
        print(f"Managed User: '{managed_user}'" if managed_user else "NOT SET")
        
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
        print(f"Video size: {file_size:.1f}MB")
        if file_size > 300:
            print(f"Video file too large: {file_size:.1f}MB (max 300MB)")
            return False
        
        try:
            print(f"Uploading {os.path.basename(video_path)} via Upload Post SDK...")
            print(f"Caption: {self.caption}")
            print(f"User: {managed_user}")
            print(f"Platforms: instagram")
            
            # Initialize the Upload Post client
            client = UploadPostClient(api_key=api_key)
            
            # Upload the video
            response = client.upload_video(
                video_path=video_path,
                title=self.caption,  # "#fyp #viral"
                user=managed_user,
                platforms=["instagram"]  # Just Instagram for now
            )
            
            print(f"\nFull Upload Response:")
            print(json.dumps(response, indent=2))
            
            # Check if the API call succeeded
            if response and response.get('success', False):
                # Check if Instagram upload actually succeeded
                instagram_result = response.get('results', {}).get('instagram', {})
                if instagram_result.get('success', False):
                    # Actually successful - move to processed
                    filename = os.path.basename(video_path)
                    dest_path = os.path.join(self.processed_folder, filename)
                    
                    # Create processed folder if needed
                    os.makedirs(self.processed_folder, exist_ok=True)
                    
                    # Move the file
                    shutil.move(video_path, dest_path)
                    print(f"✓ Upload SUCCESSFUL! Moved {filename} to processed folder")
                    
                    # Extract shortcode from filename if possible and mark as processed
                    # This prevents re-downloading the same video
                    for shortcode in self.processed_posts:
                        if shortcode in filename:
                            break
                    else:
                        # If we can't find the shortcode, add the filename itself
                        base_name_no_ext = filename.rsplit('.', 1)[0]
                        print(f"Marking as fully processed: {base_name_no_ext}")
                    
                    # Also move metadata files if they exist
                    video_dir = os.path.dirname(video_path)
                    base_name = filename.rsplit('.', 1)[0]
                    for ext in ['.json', '.jpg', '.txt']:
                        meta_file = os.path.join(video_dir, base_name + ext)
                        if os.path.exists(meta_file):
                            shutil.move(meta_file, os.path.join(self.processed_folder, base_name + ext))
                    
                    print(f"Upload completed at {datetime.now()}")
                    return True
                else:
                    # Instagram upload failed
                    error_msg = instagram_result.get('error', 'Unknown error')
                    print(f"\n✗ Instagram upload FAILED!")
                    print(f"Error: {error_msg}")
                    print("\nPossible issues:")
                    print("1. Check if managed user name matches EXACTLY in Upload Post dashboard")
                    print(f"   You have: '{managed_user}'")
                    print("2. Try disconnecting and reconnecting Instagram in Upload Post")
                    print("3. Make sure 2FA is disabled on Instagram")
                    print("\nVideo NOT moved - will retry on next cycle")
                    return False
            else:
                print(f"\n✗ API call failed!")
                print(f"Response: {response}")
                return False
                    
        except Exception as e:
            print(f"\n✗ Upload error: {e}")
            print(f"Error type: {type(e)}")
            import traceback
            traceback.print_exc()
            return False
    
    def download_one_reel(self):
        """Download just one reel that we haven't downloaded yet"""
        # Try with current proxy first
        for attempt in range(3):
            try_different_proxy = (attempt > 0)  # Use different proxy on retries
            L = self.get_instaloader_session(try_different_proxy=try_different_proxy)
            
            # Count videos before download
            videos_before = self.get_unprocessed_videos()
            print(f"Videos in download folder before: {len(videos_before)}")
            print(f"Already processed {len(self.processed_posts)} posts total")
            
            try:
                profile = instaloader.Profile.from_username(L.context, self.target_account)
                total_posts = profile.mediacount
                print(f"Profile has {total_posts} total posts")
                
                # Track how many we've checked
                posts_checked = 0
                posts_skipped = 0
                
                # Try to download any reel we don't have
                for post in profile.get_posts():
                    if post.is_video and post.typename == 'GraphVideo':
                        posts_checked += 1
                        
                        # Check if we've already processed this post
                        if post.shortcode in self.processed_posts:
                            posts_skipped += 1
                            if posts_skipped % 50 == 0:  # Log every 50 skips
                                print(f"Skipped {posts_skipped} already processed videos...")
                            continue
                        
                        # This is a new video - try to download it
                        try:
                            print(f"Found new reel to download: {post.shortcode}")
                            print(f"Post date: {post.date_local}")
                            print(f"Attempting download (checked {posts_checked} posts so far)...")
                            
                            L.download_post(post, target=profile.username)
                            
                            # Check if we have more videos now
                            videos_after = self.get_unprocessed_videos()
                            
                            if len(videos_after) > len(videos_before):
                                print(f"✓ Successfully downloaded NEW reel: {post.shortcode}")
                                # Mark this post as processed
                                self.processed_posts.add(post.shortcode)
                                self.save_processed_posts()
                                return True
                            else:
                                # Download didn't create new file, but mark as processed anyway
                                print("Download completed but no new file (might be non-video content)")
                                self.processed_posts.add(post.shortcode)
                                self.save_processed_posts()
                                
                        except Exception as dl_error:
                            error_str = str(dl_error).lower()
                            
                            # If we get 429, wait and retry with different proxy
                            if "429" in error_str:
                                print(f"Rate limited on attempt {attempt + 1}, trying different proxy immediately...")
                                break  # Break inner loop to retry with different proxy
                            
                            # Skip login errors but mark as processed
                            if "login" in error_str:
                                print("This reel requires login, marking as processed and skipping...")
                                self.processed_posts.add(post.shortcode)
                                self.save_processed_posts()
                                continue
                                
                            print(f"Download error: {dl_error}")
                            continue
                
                print(f"Checked all {posts_checked} video posts")
                print(f"Already processed: {posts_skipped}")
                print(f"No new downloadable reels found")
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
        print("\n" + "="*50)
        print("Running in CATCHUP mode - download, post, wait 30 mins, repeat")
        print(f"Already processed: {len(self.processed_posts)} posts")
        print("="*50 + "\n")
        
        # Check if we have any unprocessed videos first
        unprocessed = self.get_unprocessed_videos()
        
        if unprocessed:
            # Upload one existing video
            print(f"Found {len(unprocessed)} unprocessed videos in queue, uploading one...")
            print(f"Uploading: {unprocessed[0]}")
            
            if self.upload_video(unprocessed[0]):
                print("\n✓ Upload successful, waiting 30 minutes before next cycle...")
                print(f"Progress: {len(self.processed_posts)} posts completed")
                time.sleep(1800)  # 30 minutes
            else:
                print("\n✗ Upload failed! Waiting 30 minutes before retry...")
                time.sleep(1800)  # Still wait 30 mins even on failure
            return
        
        # Download one new reel immediately
        print("No unprocessed videos found, downloading next reel...")
        print(f"Looking for new content (already processed {len(self.processed_posts)} posts)...")
        
        if self.download_one_reel():
            # Check what we downloaded
            videos = self.get_unprocessed_videos(limit=1)
            if videos:
                print(f"Found new video to upload: {videos[0]}")
                print(f"Uploading video immediately...")
                
                if self.upload_video(videos[0]):
                    print("\n✓ Upload successful, waiting 30 minutes before next download...")
                    print(f"Progress: {len(self.processed_posts)} posts completed")
                    time.sleep(1800)  # 30 minutes
                else:
                    print("\n✗ Upload failed, waiting 30 minutes before retry...")
                    time.sleep(1800)  # 30 minutes
            else:
                print("ERROR: Downloaded but no video found in folder!")
                # Show what's in the downloads directory
                print("Searching for MP4 files...")
                for root, dirs, files in os.walk(self.download_folder):
                    print(f"Directory: {root}")
                    for file in files:
                        if file.endswith('.mp4'):
                            print(f"  Found: {file}")
        else:
            # No more reels to download
            print("No more reels to download - checking if we should switch to monitor mode")
            
            # Check if we have any unprocessed videos
            unprocessed = self.get_unprocessed_videos()
            if not unprocessed:
                print(f"All reels processed! Total: {len(self.processed_posts)} posts")
                print("Switching to monitor mode")
                self.mode = 'monitor'
                self.save_state('monitor')
            else:
                print(f"Still have {len(unprocessed)} videos to process")
                # Wait 30 minutes before checking again
                time.sleep(1800)
    
    def monitor_mode(self):
        """Check for new reels and post immediately"""
        print("\n" + "="*50)
        print("Running in MONITOR mode - checking for new reels")
        print("="*50 + "\n")
        
        if self.download_latest_reel():
            # Upload immediately
            print("New reel detected! Uploading immediately...")
            
            videos = self.get_unprocessed_videos(limit=1)
            if videos:
                print(f"Uploading: {videos[0]}")
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
    print("=== Instagram Reel Reposter Bot Starting ===")
    print(f"Current directory: {os.getcwd()}")
    print(f"Directory contents: {os.listdir('.')}")
    
    # Check for reset command
    import sys
    if len(sys.argv) > 1 and sys.argv[1] == 'reset':
        print("\nRESETTING BOT STATE...")
        if os.path.exists('processed_posts.json'):
            os.remove('processed_posts.json')
            print("✓ Cleared processed posts tracking")
        if os.path.exists('bot_state.json'):
            os.remove('bot_state.json')
            print("✓ Reset to catchup mode")
        print("Bot reset complete! Starting fresh...\n")
    
    bot = ReelReposter()
    
    # Check if we're in catchup mode
    if bot.mode == 'catchup':
        print(f"Starting in CATCHUP mode - will download and post one reel every 30 minutes")
        print(f"Already processed: {len(bot.processed_posts)} posts")
        # In catchup mode, continuously download and post
        while bot.mode == 'catchup':
            bot.run_once()
            # run_once will handle the 30-minute wait internally
    
    # Once caught up, switch to random hourly monitoring
    print("Starting MONITOR mode - will check hourly at random times")
    bot.schedule_random_hourly()

if __name__ == "__main__":
    main()
