Rahmis Stock Alert Bot -
Overview
A Python-based web scraping bot that monitors product stock status on e-commerce websites and sends real-time Discord notifications when products come in or go out of stock.
Core Features
Multi-Channel Support

Monitor multiple product groups simultaneously
Each group sends alerts to its own dedicated Discord channel via webhooks
Supports up to 5 different groups (easily expandable)
Configuration managed through a single JSON file

#Stock Monitoring#
Automatic Checks: Runs every 1 hour to check all monitored products
Smart Alerts: Only sends notifications when stock status changes (prevents spam)
Initial Check: When alerts are enabled, immediately checks and reports status of all products
Manual Checks: Check stock on-demand without sending Discord alerts

#Discord Integration#
Rich Embeds: Colored embeds (green for in-stock, red for out-of-stock)
Product Information: Displays product name, price, link, and image
Thumbnail Images: Automatically scrapes and includes product images
Rate Limiting: 1-second delay between Discord requests to prevent rate limiting
Webhook Testing: Test all webhooks to ensure they're working

#Web Scraping Capabilities#
Stock Status Detection: Checks for "Add to Cart" buttons, "Out of Stock" text, and "Email when available" buttons
Price Scraping: Extracts current product prices from the page
Image Scraping: Finds product images from multiple sources (lazy-loaded images, gallery links, etc.)
Timeout Handling: Automatically retries requests that time out (waits 10 seconds then retries once)
Targeted Scraping: Only searches within the product summary section to avoid false positives from related products

#Flexible Alert Controls#
Start/Stop Alerts: Enable or disable Discord notifications on command
Out-of-Stock Toggle: Choose whether to send out-of-stock alerts or only in-stock alerts
Monitored List: Send a formatted list of all monitored products to Discord channels

#Command System#
Interactive command-line interface with the following commands:

#commands - Display all available commands#
start_alerts - Enable Discord alerts and run initial stock check
check_stock - Manually check all products without sending alerts
test_webhook - Test all Discord webhooks
status - View current stock status of all monitored products
list - Display all groups and their monitored URLs
send_alert_list - Send monitored products list to Discord
stop_oos - Disable out-of-stock alerts
start_oos - Enable out-of-stock alerts
quit - Exit the program

#Technical Specifications#
Requirements

#Python 3.x#
Libraries: requests, beautifulsoup4
Configuration file: config.json

Configuration (config.json)
json{
  "groups": [
    {
      "name": "Group Name",
      "webhook": "Discord Webhook URL",
      "urls": ["product URL 1", "product URL 2"]
    }
  ]
}

#Monitoring Details#
Check Interval: 3600 seconds (1 hour)
Request Timeout: 10 seconds (with automatic retry)
Discord Rate Limit: 1 second delay between messages
User Agent: Mozilla/5.0

#Error Handling#
Graceful handling of timeout errors with automatic retry
Validation of JSON configuration file
Detailed error messages in console
Continues monitoring even if individual product checks fail

#Use Cases#
Monitor limited edition collectibles
Track restocks of popular products
Get instant notifications when sold-out items return
Monitor price changes on multiple products across different categories
Manage multiple Discord communities with separate product alerts

#Status Tracking#
Maintains last known status for each product
Only alerts on status changes (prevents duplicate notifications)
Displays status history via status command
Tracks in-stock, out-of-stock, and unknown states