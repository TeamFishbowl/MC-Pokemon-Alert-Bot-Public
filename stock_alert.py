import requests
from bs4 import BeautifulSoup
import time
import threading
from datetime import datetime, timezone
import sys
import json

# Read config from JSON file
try:
    with open("config.json", "r") as f:
        config = json.load(f)
        GROUPS = config.get("groups", [])
    if not GROUPS:
        print("Error: No groups found in config.json!")
        input("Press Enter to exit...")
        sys.exit()
except FileNotFoundError:
    print("Error: config.json file not found!")
    input("Press Enter to exit...")
    sys.exit()
except json.JSONDecodeError as e:
    print(f"Error: Invalid JSON format in config.json: {e}")
    input("Press Enter to exit...")
    sys.exit()

# How often to check (in seconds)
CHECK_INTERVAL = 3600  # 1 hour
DISCORD_RATE_LIMIT_DELAY = 1.0  # Delay between Discord messages to avoid rate limiting

# Global variables
last_status = {}
alerts_enabled = False
send_oos_alerts = True

def get_product_name(url):
    """Extract a readable product name from the URL."""
    product_slug = url.rstrip('/').split('/')[-1]
    return product_slug.replace('-', ' ').title()

def get_product_image(soup):
    """Extract the product image URL from the page."""
    print("   🔍 Searching for product image...")
    
    try:
        # Method 1: Look for data-large_image attribute (WooCommerce standard for full-size image)
        img = soup.find('img', class_='wp-post-image')
        if img and img.get('data-large_image'):
            img_url = img.get('data-large_image')
            print(f"   ✓ Found image in data-large_image: {img_url}")
            if img_url.startswith('http'):
                return img_url
        
        # Method 2: Look for data-src (lazy loading)
        if img and img.get('data-src'):
            img_url = img.get('data-src')
            if img_url.startswith('http') and not img_url.startswith('data:'):
                print(f"   ✓ Found image in data-src: {img_url}")
                return img_url
        
        # Method 3: Look in gallery wrapper
        gallery = soup.find('div', class_='woocommerce-product-gallery__wrapper')
        if gallery:
            link = gallery.find('a')
            if link and link.get('href'):
                img_url = link.get('href')
                if img_url.startswith('http') and any(ext in img_url for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                    print(f"   ✓ Found image in gallery link: {img_url}")
                    return img_url
        
        # Method 4: Look for any img with mastercoins.com.au domain
        all_imgs = soup.find_all('img')
        for img in all_imgs:
            for attr in ['src', 'data-src', 'data-large_image']:
                if img.get(attr):
                    img_url = img.get(attr)
                    if 'mastercoins.com.au/wp-content/uploads' in img_url and any(ext in img_url for ext in ['.jpg', '.jpeg', '.png', '.webp']):
                        print(f"   ✓ Found image in {attr}: {img_url}")
                        return img_url
        
        print("   ⚠️ No valid product image found")
    except Exception as e:
        print(f"   ❌ Error getting product image: {e}")
    
    return None

def get_product_price(soup):
    """Extract the product price from the page."""
    print("   💰 Searching for product price...")
    
    try:
        # Look for price-wrapper div
        price_wrapper = soup.find('div', class_='price-wrapper')
        if price_wrapper:
            # Try to find the price span
            price_span = price_wrapper.find('span', class_='woocommerce-Price-amount')
            if price_span:
                price_text = price_span.get_text(strip=True)
                print(f"   ✓ Found price: {price_text}")
                return price_text
            
            # Fallback: get all text from price-wrapper
            price_text = price_wrapper.get_text(strip=True)
            if price_text:
                print(f"   ✓ Found price (fallback): {price_text}")
                return price_text
        
        print("   ⚠️ No price found")
    except Exception as e:
        print(f"   ❌ Error getting product price: {e}")
    
    return None

def get_stock_status(url, retry=False):
    """Check if the product is in stock by scraping the page."""
    headers = {"User-Agent": "Mozilla/5.0"}
    
    try:
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, "html.parser")
        
        # Find the main product summary section ONLY
        product_summary = soup.find('div', class_='product-summary')
        
        if not product_summary:
            print(f"⚠️ Warning: Could not find product summary section for {url}")
            return None, None, None
        
        # Get product image and price
        image_url = get_product_image(soup)
        price = get_product_price(soup)
        
        # Now search ONLY within the product summary section
        
        # Look for "Email when stock available" button - indicates out of stock
        email_button = product_summary.find('button', class_='woocommerce-email-subscription')
        if email_button:
            return False, image_url, price
        
        # Look for "Out of stock" text
        out_of_stock_text = product_summary.find(string=lambda text: text and "out of stock" in text.lower())
        if out_of_stock_text:
            return False, image_url, price
        
        # Look for "Add to cart" or "Buy now" buttons - indicates in stock
        add_to_cart = product_summary.find('button', class_='single_add_to_cart_button')
        if add_to_cart and add_to_cart.get_text().strip().lower() in ['add to cart', 'buy now']:
            return True, image_url, price
        
        # Check for "in stock" text
        in_stock_text = product_summary.find(string=lambda text: text and "in stock" in text.lower())
        if in_stock_text:
            return True, image_url, price
        
        # If we can't determine, return None
        return None, image_url, price
        
    except requests.exceptions.Timeout:
        if not retry:
            print("   ⏱️ Request timed out. Waiting 10 seconds and retrying...")
            time.sleep(10)
            return get_stock_status(url, retry=True)
        else:
            print("   ❌ Request timed out again after retry.")
            return None, None, None
    except Exception as e:
        print(f"   ❌ Unexpected error: {e}")
        return None, None, None

def send_discord_alert(product_name, url, in_stock, image_url, price, webhook_url):
    """Send a message to Discord via webhook with embed."""
    global send_oos_alerts
    
    # Skip out of stock alerts if disabled
    if not in_stock and not send_oos_alerts:
        print(f"   ⏭️ Skipping out-of-stock alert (OOS alerts disabled)")
        return None
    
    print(f"📤 Sending Discord alert for {product_name}...")
    
    if in_stock:
        fields = [
            {
                "name": "Product",
                "value": product_name,
                "inline": False
            }
        ]
        
        # Add price if available
        if price:
            fields.append({
                "name": "Price",
                "value": price,
                "inline": True
            })
        
        fields.append({
            "name": "Link",
            "value": f"[Click here to buy now!]({url})",
            "inline": False
        })
        
        embed = {
            "title": "🎉 PRODUCT IN STOCK! 🎉",
            "description": f"**{product_name}** is now available!",
            "url": url,
            "color": 65280,
            "fields": fields,
            "footer": {
                "text": "Rahmis Cooked Bot"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    else:
        fields = [
            {
                "name": "Product",
                "value": product_name,
                "inline": False
            }
        ]
        
        # Add price if available
        if price:
            fields.append({
                "name": "Price",
                "value": price,
                "inline": True
            })
        
        fields.append({
            "name": "Status",
            "value": "Out of Stock",
            "inline": False
        })
        
        embed = {
            "title": "❌ Product Out of Stock",
            "description": f"**{product_name}** is currently unavailable.",
            "url": url,
            "color": 16711680,
            "fields": fields,
            "footer": {
                "text": "Rahmis Cooked Bot"
            },
            "timestamp": datetime.now(timezone.utc).isoformat()
        }
    
    # Add image as thumbnail if found
    if image_url:
        embed["thumbnail"] = {"url": image_url}
        print(f"   🖼️ Adding thumbnail to embed: {image_url}")
    else:
        print(f"   ⚠️ No image to add to embed")
    
    payload = {"embeds": [embed]}
    response = requests.post(webhook_url, json=payload)
    
    if response.status_code != 204:
        print(f"   ⚠️ Discord returned status {response.status_code}")
        print(f"   Response: {response.text}")
    
    return response

def send_monitored_list(group_name, webhook_url, urls):
    """Send a list of monitored products for a specific group to Discord."""
    print(f"\n📋 Sending monitored products list for '{group_name}' to Discord...")
    
    # Build the list of products
    product_list = ""
    for i, url in enumerate(urls, 1):
        product_name = get_product_name(url)
        product_list += f"{i}. [{product_name}]({url})\n"
    
    embed = {
        "title": f"📋 Currently Monitoring - {group_name}",
        "description": f"Tracking {len(urls)} product(s) for stock changes:",
        "color": 3447003,
        "fields": [
            {
                "name": "Products",
                "value": product_list if product_list else "No products being monitored",
                "inline": False
            }
        ],
        "footer": {
            "text": "Rahmis Cooked Bot"
        },
        "timestamp": datetime.now(timezone.utc).isoformat()
    }
    
    payload = {"embeds": [embed]}
    response = requests.post(webhook_url, json=payload)
    
    if response.status_code == 204:
        print(f"✅ Monitored list for '{group_name}' sent to Discord!")
    else:
        print(f"❌ Failed to send list for '{group_name}'. Status: {response.status_code}")

def initial_check_and_alert():
    """Perform initial check and send alerts for all in-stock items across all groups."""
    global last_status
    print("\n🔍 Running initial check and sending alerts for in-stock items across all groups...")
    
    for group in GROUPS:
        group_name = group.get("name", "Unnamed Group")
        webhook_url = group.get("webhook")
        urls = group.get("urls", [])
        
        print(f"\n📦 Checking group: {group_name}")
        
        for i, url in enumerate(urls, 1):
            try:
                product_name = get_product_name(url)
                print(f"\n[{i}/{len(urls)}] 🌐 Checking {product_name}...")
                
                in_stock, image_url, price = get_stock_status(url)
                
                print(f"[{i}/{len(urls)}] ✓ Finished checking {product_name}")
                
                if in_stock is True:
                    print(f"[{i}/{len(urls)}] ✅ {product_name}: IN STOCK")
                    send_discord_alert(product_name, url, True, image_url, price, webhook_url)
                    print(f"[{i}/{len(urls)}] 📨 Sent IN STOCK alert!")
                    time.sleep(DISCORD_RATE_LIMIT_DELAY)
                elif in_stock is False:
                    print(f"[{i}/{len(urls)}] ❌ {product_name}: OUT OF STOCK")
                    if send_oos_alerts:
                        send_discord_alert(product_name, url, False, image_url, price, webhook_url)
                        print(f"[{i}/{len(urls)}] 📨 Sent OUT OF STOCK alert!")
                        time.sleep(DISCORD_RATE_LIMIT_DELAY)
                else:
                    print(f"[{i}/{len(urls)}] ❓ {product_name}: UNKNOWN")
                
                last_status[url] = in_stock
                
            except Exception as e:
                print(f"[{i}/{len(urls)}] ❌ Error checking {url}: {e}")
    
    print("\n✅ Initial check complete! Automatic monitoring will now track changes.")

def test_webhook():
    """Test if all webhooks are working."""
    print("\n🧪 Testing all webhooks...")
    
    for group in GROUPS:
        group_name = group.get("name", "Unnamed Group")
        webhook_url = group.get("webhook")
        
        print(f"\nTesting webhook for '{group_name}'...")
        
        payload = {
            "embeds": [{
                "title": "✅ Webhook Test",
                "description": f"If you see this message, the webhook for '{group_name}' is working correctly!",
                "color": 3447003,
                "footer": {
                    "text": "Rahmis Cooked Bot"
                },
                "timestamp": datetime.now(timezone.utc).isoformat()
            }]
        }
        
        try:
            response = requests.post(webhook_url, json=payload)
            print(f"Status code: {response.status_code}")
            
            if response.status_code == 204:
                print(f"✅ Webhook test successful for '{group_name}'! Check your Discord channel.")
            elif response.status_code == 404:
                print(f"❌ Webhook not found for '{group_name}'. The URL might be invalid or deleted.")
            elif response.status_code == 401:
                print(f"❌ Unauthorized for '{group_name}'. Check your webhook URL.")
            else:
                print(f"⚠️ Unexpected response for '{group_name}': {response.text}")
        except Exception as e:
            print(f"❌ Error sending test message for '{group_name}': {e}")
        
        time.sleep(DISCORD_RATE_LIMIT_DELAY)

def manual_check():
    """Perform a manual stock check for all URLs across all groups."""
    print("\n🔍 Running manual check for all products across all groups...")
    
    for group in GROUPS:
        group_name = group.get("name", "Unnamed Group")
        urls = group.get("urls", [])
        
        print(f"\n📦 Checking group: {group_name}")
        
        for i, url in enumerate(urls, 1):
            try:
                product_name = get_product_name(url)
                print(f"\n[{i}/{len(urls)}] 🌐 Scraping {product_name}...")
                
                in_stock, image_url, price = get_stock_status(url)
                
                print(f"[{i}/{len(urls)}] ✓ Finished scraping {product_name}")
                
                if price:
                    print(f"[{i}/{len(urls)}] 💰 Price: {price}")
                
                if in_stock is True:
                    print(f"[{i}/{len(urls)}] ✅ {product_name}: IN STOCK")
                elif in_stock is False:
                    print(f"[{i}/{len(urls)}] ❌ {product_name}: OUT OF STOCK")
                else:
                    print(f"[{i}/{len(urls)}] ❓ {product_name}: UNKNOWN")
                    
            except Exception as e:
                print(f"[{i}/{len(urls)}] ❌ Error checking {url}: {e}")
    
    print("\n✅ Manual check complete!")

def automatic_monitor():
    """Automatic monitoring loop that runs every hour."""
    global last_status, alerts_enabled
    
    total_products = sum(len(group.get("urls", [])) for group in GROUPS)
    print(f"🔍 Automatic monitoring initialized for {len(GROUPS)} group(s) with {total_products} total product(s).")
    print(f"⏸️ Alerts are PAUSED. Type 'start_alerts' to begin sending alerts.\n")
    
    # Initialize last_status for all URLs
    for group in GROUPS:
        for url in group.get("urls", []):
            if url not in last_status:
                last_status[url] = None
    
    while True:
        if alerts_enabled:
            print(f"\n⏰ Starting automatic check at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
            
            for group in GROUPS:
                group_name = group.get("name", "Unnamed Group")
                webhook_url = group.get("webhook")
                urls = group.get("urls", [])
                
                print(f"\n📦 Checking group: {group_name}")
                
                for i, url in enumerate(urls, 1):
                    try:
                        product_name = get_product_name(url)
                        print(f"\n[{i}/{len(urls)}] 🌐 Checking {product_name}...")
                        
                        in_stock, image_url, price = get_stock_status(url)
                        
                        print(f"[{i}/{len(urls)}] ✓ Finished checking {product_name}")
                        
                        if in_stock is True and last_status[url] != True:
                            send_discord_alert(product_name, url, True, image_url, price, webhook_url)
                            print(f"[{i}/{len(urls)}] ✅ Sent IN STOCK alert for {product_name}!")
                            time.sleep(DISCORD_RATE_LIMIT_DELAY)
                        elif in_stock is False and last_status[url] != False:
                            response = send_discord_alert(product_name, url, False, image_url, price, webhook_url)
                            if response:
                                print(f"[{i}/{len(urls)}] 📦 Sent OUT OF STOCK alert for {product_name}.")
                            time.sleep(DISCORD_RATE_LIMIT_DELAY)
                        elif in_stock is None:
                            print(f"[{i}/{len(urls)}] ❓ {product_name}: Couldn't determine stock status.")
                        else:
                            print(f"[{i}/{len(urls)}] 🔄 {product_name}: No status change")
                        
                        last_status[url] = in_stock
                        
                    except Exception as e:
                        print(f"[{i}/{len(urls)}] ❌ Error checking {url}: {e}")
            
            print(f"\n💤 Sleeping for {CHECK_INTERVAL}s until next check...")
        
        time.sleep(CHECK_INTERVAL)

def command_listener():
    """Listen for user commands."""
    global alerts_enabled, send_oos_alerts
    
    print("💬 Command listener active. Type 'commands' to see all available commands.\n")
    
    while True:
        try:
            command = input().strip().lower()
            
            if command == "commands":
                print("\n📋 Available Commands:")
                print("   • commands         - Show this list of all commands")
                print("   • start_alerts     - Start sending Discord alerts (checks all items first)")
                print("   • check_stock      - Manually check stock for all products")
                print("   • test_webhook     - Test if all Discord webhooks are working")
                print("   • status           - Show last known status for all products")
                print("   • list             - Show all monitored groups and URLs")
                print("   • send_alert_list  - Send list of monitored products to Discord (all groups)")
                print("   • stop_oos         - Stop sending out-of-stock alerts")
                print("   • start_oos        - Resume sending out-of-stock alerts")
                print("   • quit             - Exit program\n")
            
            elif command == "start_alerts":
                if alerts_enabled:
                    print("⚠️ Alerts are already enabled!")
                else:
                    alerts_enabled = True
                    print("✅ Alerts enabled! Running initial check...")
                    initial_check_and_alert()
            
            elif command == "check_stock":
                manual_check()
            
            elif command == "test_webhook":
                test_webhook()
            
            elif command == "status":
                print("\n📊 Current status for all products:")
                for group in GROUPS:
                    group_name = group.get("name", "Unnamed Group")
                    print(f"\n📦 {group_name}:")
                    for url in group.get("urls", []):
                        product_name = get_product_name(url)
                        status = last_status.get(url, None)
                        if status is True:
                            print(f"   ✅ {product_name}: IN STOCK")
                        elif status is False:
                            print(f"   ❌ {product_name}: OUT OF STOCK")
                        else:
                            print(f"   ❓ {product_name}: UNKNOWN")
            
            elif command == "list":
                print(f"\n📋 Monitoring {len(GROUPS)} group(s):")
                for group in GROUPS:
                    group_name = group.get("name", "Unnamed Group")
                    urls = group.get("urls", [])
                    print(f"\n📦 {group_name} ({len(urls)} product(s)):")
                    for i, url in enumerate(urls, 1):
                        product_name = get_product_name(url)
                        print(f"   {i}. {product_name}")
                        print(f"      {url}")
            
            elif command == "send_alert_list":
                for group in GROUPS:
                    group_name = group.get("name", "Unnamed Group")
                    webhook_url = group.get("webhook")
                    urls = group.get("urls", [])
                    send_monitored_list(group_name, webhook_url, urls)
                    time.sleep(DISCORD_RATE_LIMIT_DELAY)
            
            elif command == "stop_oos":
                if not send_oos_alerts:
                    print("⚠️ Out-of-stock alerts are already disabled!")
                else:
                    send_oos_alerts = False
                    print("🔕 Out-of-stock alerts disabled. Only in-stock alerts will be sent.")
            
            elif command == "start_oos":
                if send_oos_alerts:
                    print("⚠️ Out-of-stock alerts are already enabled!")
                else:
                    send_oos_alerts = True
                    print("🔔 Out-of-stock alerts enabled. Both in-stock and out-of-stock alerts will be sent.")
            
            elif command == "quit" or command == "exit":
                print("👋 Exiting program...")
                sys.exit()
            
            else:
                print(f"❌ Unknown command: '{command}'. Type 'commands' for a list of available commands.")
                
        except Exception as e:
            print(f"❌ Error: {e}")

def main():
    monitor_thread = threading.Thread(target=automatic_monitor, daemon=True)
    monitor_thread.start()
    
    command_listener()

if __name__ == "__main__":
    main()