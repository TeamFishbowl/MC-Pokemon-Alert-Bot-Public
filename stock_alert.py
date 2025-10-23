import requests
from bs4 import BeautifulSoup
import time
import threading
from datetime import datetime

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
    product_slug = url.rstrip('/').split('/')[-1]
    return product_slug.replace('-', ' ').title()

def get_product_image(soup):
    """Extract the product image URL from the page."""
    # Try to find the main product image
    img = soup.find('img', class_='wp-post-image')
    if img and img.get('src'):
        return img.get('src')
    
    # Fallback: try to find any product image
    product_images = soup.find('div', class_='product-images')
    if product_images:
        img = product_images.find('img')
        if img and img.get('src'):
            return img.get('src')
    
    return None

def get_stock_status(url):
    """Check if the product is in stock by scraping the page."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(url, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find the main product summary section ONLY
    product_summary = soup.find('div', class_='product-summary')
    
    if not product_summary:
        print(f"⚠️ Warning: Could not find product summary section for {url}")
        return None, None
    
    # Get product image
    image_url = get_product_image(soup)
    
    # Now search ONLY within the product summary section
    
    # Look for "Email when stock available" button - indicates out of stock
    email_button = product_summary.find('button', class_='woocommerce-email-subscription')
    if email_button:
        return False, image_url
    
    # Look for "Out of stock" text
    out_of_stock_text = product_summary.find(string=lambda text: text and "out of stock" in text.lower())
    if out_of_stock_text:
        return False, image_url
    
    # Look for "Add to cart" or "Buy now" buttons - indicates in stock
    add_to_cart = product_summary.find('button', class_='single_add_to_cart_button')
    if add_to_cart and add_to_cart.get_text().strip().lower() in ['add to cart', 'buy now']:
        return True, image_url
    
    # Check for "in stock" text
    in_stock_text = product_summary.find(string=lambda text: text and "in stock" in text.lower())
    if in_stock_text:
        return True, image_url
    
    # If we can't determine, return None
    return None, image_url

def send_discord_alert(product_name, url, in_stock, image_url):
    """Send a message to Discord via webhook with embed."""
    if in_stock:
        embed = {
            "title": "🎉 PRODUCT IN STOCK! 🎉",
            "description": f"**{product_name}** is now available!",
            "url": url,
            "color": 65280,
            "fields": [
                {
                    "name": "Product",
                    "value": product_name,
                    "inline": False
                },
                {
                    "name": "Link",
                    "value": f"[Click here to buy now!]({url})",
                    "inline": False
                }
            ],
            "footer": {
                "text": "Rahmis Cooked Bot"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    else:
        embed = {
            "title": "❌ Product Out of Stock",
            "description": f"**{product_name}** is currently unavailable.",
            "url": url,
            "color": 16711680,
            "fields": [
                {
                    "name": "Product",
                    "value": product_name,
                    "inline": False
                },
                {
                    "name": "Status",
                    "value": "Out of Stock",
                    "inline": False
                }
            ],
            "footer": {
                "text": "Rahmis Cooked Bot"
            },
            "timestamp": datetime.utcnow().isoformat()
        }
    
    if image_url:
        embed["thumbnail"] = {"url": image_url}
    
    payload = {"embeds": [embed]}
    response = requests.post(WEBHOOK_URL, json=payload)
    return response

def test_webhook():
    """Test if the webhook is working."""
    print("\n🧪 Testing webhook...")
    payload = {
        "embeds": [{
            "title": "✅ Webhook Test",
            "description": "If you see this message, your webhook is working correctly!",
            "color": 3447003,
            "footer": {
                "text": "Rahmis Cooked Bot"
            },
            "timestamp": datetime.utcnow().isoformat()
        }]
    }
    
    try:
        response = requests.post(WEBHOOK_URL, json=payload)
        print(f"Status code: {response.status_code}")
        
        if response.status_code == 204:
            print("✅ Webhook test successful! Check your Discord channel.")
        elif response.status_code == 404:
            print("❌ Webhook not found. The URL might be invalid or deleted.")
        elif response.status_code == 401:
            print("❌ Unauthorized. Check your webhook URL.")
        else:
            print(f"⚠️ Unexpected response: {response.text}")
    except Exception as e:
        print(f"❌ Error sending test message: {e}")

def manual_check():
    """Perform a manual stock check for all URLs."""
    print("\n🔍 Running manual check for all products...")
    for url in URLS:
        try:
            product_name = get_product_name(url)
            in_stock, image_url = get_stock_status(url)
            
            if in_stock is True:
                print(f"✅ {product_name}: IN STOCK")
                response = send_discord_alert(product_name, url, True, image_url)
                print(f"   Discord response: {response.status_code}")
            elif in_stock is False:
                print(f"❌ {product_name}: OUT OF STOCK")
                response = send_discord_alert(product_name, url, False, image_url)
                print(f"   Discord response: {response.status_code}")
            else:
                print(f"❓ {product_name}: UNKNOWN")
                
        except Exception as e:
            print(f"❌ Error checking {url}: {e}")

def automatic_monitor():
    """Automatic monitoring loop that runs every hour."""
    global last_status
    print(f"🔍 Starting automatic monitoring for {len(URLS)} product(s) (checks every hour)...\n")
    
    for url in URLS:
        if url not in last_status:
            last_status[url] = None
    
    while True:
        for url in URLS:
            try:
                product_name = get_product_name(url)
                in_stock, image_url = get_stock_status(url)
                
                if in_stock is True and last_status[url] != True:
                    send_discord_alert(product_name, url, True, image_url)
                    print(f"✅ Sent IN STOCK alert for {product_name}!")
                elif in_stock is False and last_status[url] != False:
                    send_discord_alert(product_name, url, False, image_url)
                    print(f"📦 Sent OUT OF STOCK alert for {product_name}.")
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
    print("   - test_webhook : Test if Discord webhook is working")
    print("   - status      : Show last known status for all products")
    print("   - list        : Show all monitored URLs")
    print("   - quit        : Exit program\n")
    
    while True:
        try:
            command = input().strip().lower()
            
            if command == "check_stock":
                manual_check()
            elif command == "test_webhook":
                test_webhook()
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
    monitor_thread = threading.Thread(target=automatic_monitor, daemon=True)
    monitor_thread.start()
    
    command_listener()

if __name__ == "__main__":
    main()