import requests
from bs4 import BeautifulSoup
import time
import threading

# URL of the product
URL = "https://mastercoins.com.au/product/pokemon-tcg-151-sv2a-booster-box-japanese/"

# Read webhook URL from file
try:
    with open("webhook.txt", "r") as f:
        WEBHOOK_URL = f.read().strip()
except FileNotFoundError:
    print("Error: webhook.txt file not found!")
    input("Press Enter to exit...")
    exit()

# How often to check (in seconds)
CHECK_INTERVAL = 3600  # 1 hour

# Global variable to track last status
last_status = None

def get_stock_status():
    """Check if the product is in stock by scraping the page."""
    headers = {"User-Agent": "Mozilla/5.0"}
    response = requests.get(URL, headers=headers, timeout=10)
    soup = BeautifulSoup(response.text, "html.parser")
    
    # Find the main product summary section ONLY
    product_summary = soup.find('div', class_='product-summary')
    
    if not product_summary:
        print("⚠️ Warning: Could not find product summary section")
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
    """Perform a manual stock check."""
    try:
        print("\n🔍 Running manual check...")
        in_stock = get_stock_status()
        
        if in_stock is True:
            print("✅ Product is IN STOCK!")
        elif in_stock is False:
            print("❌ Product is OUT OF STOCK")
        else:
            print("❓ Could not determine stock status")
            
    except Exception as e:
        print(f"❌ Error during manual check: {e}")

def automatic_monitor():
    """Automatic monitoring loop that runs every hour."""
    global last_status
    print("🔍 Starting automatic monitoring (checks every hour)...\n")
    
    while True:
        try:
            in_stock = get_stock_status()
            
            if in_stock is True and last_status != True:
                send_discord_alert("🎉 The Pokémon 151 Booster Box is **IN STOCK**! Go now: " + URL)
                print("✅ Sent IN STOCK alert to Discord!")
            elif in_stock is False and last_status != False:
                print("📦 Still out of stock.")
            elif in_stock is None:
                print("❓ Couldn't determine stock status.")
            
            last_status = in_stock
            
        except Exception as e:
            print(f"❌ Error checking stock: {e}")
        
        time.sleep(CHECK_INTERVAL)

def command_listener():
    """Listen for user commands."""
    print("💬 Command listener active. Available commands:")
    print("   - check_stock : Manually check stock now")
    print("   - status      : Show last known status")
    print("   - quit        : Exit program\n")
    
    while True:
        try:
            command = input().strip().lower()
            
            if command == "check_stock":
                manual_check()
            elif command == "status":
                if last_status is True:
                    print("📊 Last status: IN STOCK")
                elif last_status is False:
                    print("📊 Last status: OUT OF STOCK")
                else:
                    print("📊 Last status: UNKNOWN")
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