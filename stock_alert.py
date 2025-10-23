import requests
from bs4 import BeautifulSoup
import time
import threading

# Read webhook URL from file
try:
    with open("webhook.txt", "r") as f:
        WEBHOOK_URL = f.read().strip()
except FileNotFoundError:
    print("Error: webhook.txt file not found!")
    input("Press Enter to exit...")
    exit()

# Read URLs from file
try:
    with open("urls.txt", "r") as f:
        URLS = [line.strip() for line in f.readlines() if line.strip()]
    if not URLS:
        print("Error: urls.txt is empty!")
        input("Press Enter to exit...")
        exit()
except FileNotFoundError:
    print("Error: urls.txt file not found!")
    input("Press Enter to exit...")
    exit()

# How often to check (in seconds)
CHECK_INTERVAL = 3600  # 1 hour

# Global variable to track last status for each URL
last_status = {}

def get_product_name(url):
    """Extract a readable product name from the URL."""
    # Gets the last part of the URL path and makes it readable
    product_slug = url.rstrip('/').split('/')[-1]
    return product_slug.replace('-', ' ').title()

def get_stock_status(url):
    """Check if the product is in stock by scraping the page."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find the main product summary section ONLY
    product_summary = soup.find('div', class_='product-summary')
    
    if not product_summary:
        print(f"⚠️ Warning: Could not find product summary section for {url}")
        return None
    
    # Now search ONLY within the product summary section
    
    # Look for "Email when stock available" button - indicates out of stock
    email_button = product_summary.find('button', class_='woocommerce-email-subscription')
    if email_button:
        return False
    
    # Look for "Out of stock" text
    out_of_stock_text = product_summary.find(string=lambda text: text and "out of stock" in text.lower())
    if out_of_stock_text:
        return False
    
    # Look for "Add to cart" or "Buy now" buttons - indicates in stock
    add_to_cart = product_summary.find('button', class_='single_add_to_cart_button')
    if add_to_cart and add_to_cart.get_text().strip().lower() in ['add to cart', 'buy now']:
        return True
    
    # Check for "in stock" text
    in_stock_text = product_summary.find(string=lambda text: text and "in stock" in text.lower())
    if in_stock_text:
        return True
    
    # If we can't determine, return None
    return None

def send_discord_alert(message):
    """Send a message to Discord via webhook."""
    payload = {"content": message}
    requests.post(WEBHOOK_URL, json=payload)

def manual_check():
    """Perform a manual stock check for all URLs."""
    print("\n🔍 Running manual check for all products...")
    for url in URLS:
        try:
            product_name = get_product_name(url)
            in_stock = get_stock_status(url)
            
            if in_stock is True:
                print(f"✅ {product_name}: IN STOCK")
            elif in_stock is False:
                print(f"❌ {product_name}: OUT OF STOCK")
            else:
                print(f"❓ {product_name}: UNKNOWN")
                
        except Exception as e:
            print(f"❌ Error checking {url}: {e}")

def automatic_monitor():
    """Automatic monitoring loop that runs every hour."""
    global last_status
    print(f"🔍 Starting automatic monitoring for {len(URLS)} product(s) (checks every hour)...\n")
    
    # Initialize last_status for all URLs
    for url in URLS:
        if url not in last_status:
            last_status[url] = None
    
    while True:
        for url in URLS:
            try:
                product_name = get_product_name(url)
                in_stock = get_stock_status(url)
                
                if in_stock is True and last_status[url] != True:
                    send_discord_alert(f"🎉 **{product_name}** is IN STOCK! Go now: {url}")
                    print(f"✅ Sent IN STOCK alert for {product_name}!")
                elif in_stock is False and last_status[url] != False:
                    print(f"📦 {product_name}: Still out of stock.")
                elif in_stock is None:
                    print(f"❓ {product_name}: Couldn't determine stock status.")
                
                last_status[url] = in_stock
                
            except Exception as e:
                print(f"❌ Error checking {url}: {e}")
        
        time.sleep(CHECK_INTERVAL)

def command_listener():
    """Listen for user commands."""
    print("💬 Command listener active. Available commands:")
    print("   - check_stock : Manually check stock now")
    print("   - status      : Show last known status for all products")
    print("   - list        : Show all monitored URLs")
    print("   - quit        : Exit program\n")
    
    while True:
        try:
            command = input().strip().lower()
            
            if command == "check_stock":
                manual_check()
            elif command == "status":
                print("\n📊 Current status for all products:")
                for url in URLS:
                    product_name = get_product_name(url)
                    status = last_status.get(url, None)
                    if status is True:
                        print(f"   ✅ {product_name}: IN STOCK")
                    elif status is False:
                        print(f"   ❌ {product_name}: OUT OF STOCK")
                    else:
                        print(f"   ❓ {product_name}: UNKNOWN")
            elif command == "list":
                print(f"\n📋 Monitoring {len(URLS)} product(s):")
                for i, url in enumerate(URLS, 1):
                    product_name = get_product_name(url)
                    print(f"   {i}. {product_name}")
                    print(f"      {url}")
            elif command == "quit" or command == "exit":
                print("👋 Exiting program...")
                exit()
            else:
                print(f"❌ Unknown command: '{command}'")
                
        except Exception as e:
            print(f"❌ Error: {e}")

def main():
    # Start automatic monitoring in a separate thread
    monitor_thread = threading.Thread(target=automatic_monitor, daemon=True)
    monitor_thread.start()
    
    # Start command listener in main thread
    command_listener()

if __name__ == "__main__":
    main()